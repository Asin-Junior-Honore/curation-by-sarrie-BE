from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, timedelta
from typing import Optional
from bson import ObjectId

from ..models.order import OrderStatusUpdate
from ..dependencies.auth import require_admin
from ..services.orders import (
    list_orders,
    get_order_by_id,
    update_order_status,
)
from ..services.email import (
    send_order_preparing,
    send_order_in_transit,
    send_order_delivered,
)

router = APIRouter(prefix="/api/admin/orders", tags=["admin-orders"])
public_router = APIRouter(prefix="/api/track", tags=["public-tracking"])


def _naira(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"


# ─── ADMIN: Orders list + detail ────────────────────────
@router.get("")
async def admin_list_orders(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    page: int = Query(1, ge=1),
    user: dict = Depends(require_admin),
):
    return await list_orders(
        status=status, search=search, limit=limit, page=page
    )


@router.get("/{order_id}")
async def admin_get_order(
    order_id: str,
    user: dict = Depends(require_admin),
):
    order = await get_order_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order["id"] = str(order["_id"])
    del order["_id"]
    return order


# ─── ADMIN: Update status (fires emails) ────────────────
@router.patch("/{order_id}/status")
async def admin_update_status(
    order_id: str,
    payload: OrderStatusUpdate,
    user: dict = Depends(require_admin),
):
    """
    Update order status. Fires appropriate customer emails on transitions:
    - paid → preparing: "We're preparing your gift"
    - preparing → in_transit: "Your order is on the way"
    - in_transit → delivered: "Delivered — thank you"
    """
    existing = await get_order_by_id(order_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Order not found")
    previous_status = existing.get("status")

    updated = await update_order_status(
        order_id=order_id,
        new_status=payload.status,
        note=payload.note,
        changed_by=str(user["_id"]),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Order not found")

    # Sanitize for email templates (BSON ObjectId → string)
    safe_order = _serialize_order_for_email(updated)

    # Fire status-change emails
    try:
        if payload.status == "preparing" and previous_status != "preparing":
            print(f"📧 Firing PREPARING email for {safe_order.get('order_number')}")
            await send_order_preparing(safe_order)

        elif payload.status == "in_transit" and previous_status != "in_transit":
            print(f"📧 Firing IN_TRANSIT email for {safe_order.get('order_number')}")
            await send_order_in_transit(safe_order)

        elif payload.status == "delivered" and previous_status != "delivered":
            print(f"📧 Firing DELIVERED email for {safe_order.get('order_number')}")
            await send_order_delivered(safe_order)

    except Exception as e:
        import traceback
        print(f"⚠️  Status email failed: {e}")
        traceback.print_exc()

    updated["id"] = str(updated["_id"])
    del updated["_id"]
    return updated


def _serialize_order_for_email(order: dict) -> dict:
    """
    Convert MongoDB types (ObjectId, datetime) to JSON-safe
    before passing to Jinja2 email templates.
    """
    import copy

    def convert(obj):
        if isinstance(obj, dict):
            return {k: convert(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [convert(v) for v in obj]
        if isinstance(obj, ObjectId):
            return str(obj)
        if isinstance(obj, datetime):
            return obj.isoformat()
        return obj

    return convert(copy.deepcopy(order))


# ─── ADMIN: Stats ───────────────────────────────────────
@router.get("/stats/dashboard")
async def admin_dashboard_stats(user: dict = Depends(require_admin)):
    from ..database import orders_collection, products_collection, users_collection

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    orders = orders_collection()
    products = products_collection()
    users = users_collection()

    total_orders = await orders.count_documents({"payment.status": "success"})
    orders_today = await orders.count_documents({
        "payment.status": "success",
        "created_at": {"$gte": today_start}
    })

    pipeline_products_sold = [
        {"$match": {"payment.status": "success"}},
        {"$unwind": "$items"},
        {"$group": {"_id": None, "count": {"$sum": "$items.quantity"}}},
    ]
    result = await orders.aggregate(pipeline_products_sold).to_list(1)
    products_sold = result[0]["count"] if result else 0

    new_customers = await users.count_documents({
        "role": {"$ne": "super_admin"},
        "created_at": {"$gte": month_start}
    })

    pipeline_total = [
        {"$match": {"payment.status": "success"}},
        {"$group": {"_id": None, "total": {"$sum": "$total_kobo"}}},
    ]
    result = await orders.aggregate(pipeline_total).to_list(1)
    total_revenue = result[0]["total"] if result else 0

    pipeline_month = [
        {"$match": {"payment.status": "success", "created_at": {"$gte": month_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$total_kobo"}}},
    ]
    result = await orders.aggregate(pipeline_month).to_list(1)
    month_revenue = result[0]["total"] if result else 0

    pipeline_today = [
        {"$match": {"payment.status": "success", "created_at": {"$gte": today_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$total_kobo"}}},
    ]
    result = await orders.aggregate(pipeline_today).to_list(1)
    today_revenue = result[0]["total"] if result else 0

    pipeline_in_transit = [
        {"$match": {"status": "in_transit", "payment.status": "success"}},
        {"$group": {"_id": None, "total": {"$sum": "$total_kobo"}}},
    ]
    result = await orders.aggregate(pipeline_in_transit).to_list(1)
    in_transit_revenue = result[0]["total"] if result else 0

    pipeline_delivered = [
        {"$match": {"status": "delivered", "payment.status": "success"}},
        {"$group": {"_id": None, "total": {"$sum": "$total_kobo"}}},
    ]
    result = await orders.aggregate(pipeline_delivered).to_list(1)
    delivered_revenue = result[0]["total"] if result else 0

    low_stock_cursor = products.find(
        {
            "bumpa.quantity": {"$lte": 5, "$gt": 0},
            "editorial.is_hidden": {"$ne": True},
            "bumpa.status": 1,
        }
    ).sort("bumpa.quantity", 1).limit(10)

    low_stock = []
    async for doc in low_stock_cursor:
        low_stock.append({
            "id": str(doc["_id"]),
            "slug": doc["bumpa"]["slug"],
            "name": doc["bumpa"]["name"],
            "quantity": doc["bumpa"]["quantity"],
            "image": doc["bumpa"].get("optimized_image_url") or doc["bumpa"].get("image_url"),
        })

    out_of_stock_count = await products.count_documents({
        "bumpa.quantity": 0,
        "editorial.is_hidden": {"$ne": True},
        "bumpa.status": 1,
    })

    channel_pipeline = [
        {"$match": {"payment.status": "success"}},
        {"$group": {"_id": "$payment.channel", "count": {"$sum": 1}}},
    ]
    channels = {}
    async for doc in orders.aggregate(channel_pipeline):
        key = doc["_id"] or "unknown"
        channels[key] = doc["count"]

    status_pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    status_counts = {}
    async for doc in orders.aggregate(status_pipeline):
        status_counts[doc["_id"]] = doc["count"]

    return {
        "cards": {
            "orders_total": total_orders,
            "orders_today": orders_today,
            "products_sold": products_sold,
            "new_customers_month": new_customers,
        },
        "revenue": {
            "total_kobo": total_revenue,
            "total_formatted": _naira(total_revenue),
            "month_kobo": month_revenue,
            "month_formatted": _naira(month_revenue),
            "today_kobo": today_revenue,
            "today_formatted": _naira(today_revenue),
            "in_transit_kobo": in_transit_revenue,
            "in_transit_formatted": _naira(in_transit_revenue),
            "delivered_kobo": delivered_revenue,
            "delivered_formatted": _naira(delivered_revenue),
        },
        "low_stock": low_stock,
        "out_of_stock_count": out_of_stock_count,
        "channels": channels,
        "order_status_breakdown": status_counts,
    }


@router.get("/stats/revenue-chart")
async def admin_revenue_chart(
    days: int = 30,
    user: dict = Depends(require_admin),
):
    from ..database import orders_collection

    now = datetime.utcnow()
    start = now - timedelta(days=days - 1)
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)

    pipeline = [
        {"$match": {"payment.status": "success", "created_at": {"$gte": start}}},
        {
            "$group": {
                "_id": {
                    "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
                },
                "revenue_kobo": {"$sum": "$total_kobo"},
                "orders": {"$sum": 1},
            }
        },
        {"$sort": {"_id": 1}},
    ]

    results = {}
    async for doc in orders_collection().aggregate(pipeline):
        results[doc["_id"]] = doc

    output = []
    for i in range(days):
        day = start + timedelta(days=i)
        day_str = day.strftime("%Y-%m-%d")
        if day_str in results:
            output.append({
                "date": day_str,
                "revenue_kobo": results[day_str]["revenue_kobo"],
                "orders": results[day_str]["orders"],
            })
        else:
            output.append({"date": day_str, "revenue_kobo": 0, "orders": 0})

    return {"days": days, "data": output}


@router.get("/stats/top-products")
async def admin_top_products(
    limit: int = 5,
    user: dict = Depends(require_admin),
):
    from ..database import orders_collection

    pipeline = [
        {"$match": {"payment.status": "success"}},
        {"$unwind": "$items"},
        {
            "$group": {
                "_id": "$items.product_id",
                "name": {"$first": "$items.name"},
                "image": {"$first": "$items.image"},
                "slug": {"$first": "$items.slug"},
                "units_sold": {"$sum": "$items.quantity"},
                "revenue_kobo": {"$sum": "$items.subtotal"},
            }
        },
        {"$sort": {"revenue_kobo": -1}},
        {"$limit": limit},
    ]

    products = []
    async for doc in orders_collection().aggregate(pipeline):
        products.append({
            "product_id": doc["_id"],
            "name": doc["name"],
            "image": doc["image"],
            "slug": doc["slug"],
            "units_sold": doc["units_sold"],
            "revenue_kobo": doc["revenue_kobo"],
            "revenue_formatted": _naira(doc["revenue_kobo"]),
        })

    return {"products": products}


# ─── PUBLIC: Order tracking ─────────────────────────────
@public_router.get("/{order_number}")
async def track_order(order_number: str, email: str = None):
    from ..services.orders import get_order_by_number

    order = await get_order_by_number(order_number)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    if email and order["customer"]["email"].lower() != email.lower():
        raise HTTPException(
            status_code=404, detail="Order not found for this email"
        )

    sanitized = {
        "order_number": order["order_number"],
        "status": order["status"],
        "created_at": order["created_at"],
        "customer": {
            "full_name": order["customer"]["full_name"],
            "email": _mask_email(order["customer"]["email"]),
        },
        "delivery": {
            "city": order["delivery"]["city"],
            "state": order["delivery"]["state"],
            "country": order["delivery"]["country"],
        },
        "items": [
            {
                "name": item["name"],
                "image": item["image"],
                "quantity": item["quantity"],
                "subtotal": item["subtotal"],
            }
            for item in order["items"]
        ],
        "subtotal_kobo": order["subtotal_kobo"],
        "delivery_fee_kobo": order["delivery_fee_kobo"],
        "total_kobo": order["total_kobo"],
        "status_history": [
            {
                "status": entry["status"],
                "note": entry.get("note"),
                "changed_at": entry["changed_at"],
            }
            for entry in order.get("status_history", [])
        ],
    }

    return sanitized


def _mask_email(email: str) -> str:
    try:
        local, domain = email.split("@")
        if len(local) <= 2:
            masked_local = local[0] + "*"
        else:
            masked_local = local[0] + "*" * (len(local) - 1)
        return f"{masked_local}@{domain}"
    except Exception:
        return "***"