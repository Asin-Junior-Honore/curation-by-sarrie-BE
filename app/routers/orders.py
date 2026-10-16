from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, timedelta
from typing import Optional

from ..models.order import OrderStatusUpdate
from ..dependencies.auth import require_admin
from ..services.orders import (
    list_orders,
    get_order_by_id,
    update_order_status,
)

from ..services.email import (
    send_order_in_transit,
    send_order_delivered,
)
from ..services.orders import get_order_by_id  # if not already imported

router = APIRouter(prefix="/api/admin/orders", tags=["admin-orders"])


@router.get("")
async def admin_list_orders(
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    page: int = Query(1, ge=1),
    user: dict = Depends(require_admin),
):
    """List orders with filters."""
    return await list_orders(
        status=status, search=search, limit=limit, page=page
    )


@router.get("/{order_id}")
async def admin_get_order(
    order_id: str,
    user: dict = Depends(require_admin),
):
    """Get a single order by ID."""
    order = await get_order_by_id(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    order["id"] = str(order["_id"])
    del order["_id"]
    return order


@router.patch("/{order_id}/status")
async def admin_update_status(
    order_id: str,
    payload: OrderStatusUpdate,
    user: dict = Depends(require_admin),
):
    """Update order status (in_transit, delivered, completed, cancelled)."""
    # Capture previous status
    existing = await get_order_by_id(order_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Order not found")
    previous_status = existing.get("status")

    # Update
    updated = await update_order_status(
        order_id=order_id,
        new_status=payload.status,
        note=payload.note,
        changed_by=str(user["_id"]),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Order not found")

    # Fire emails on status transitions
    try:
        if payload.status == "in_transit" and previous_status != "in_transit":
            await send_order_in_transit(updated)
        elif payload.status == "delivered" and previous_status != "delivered":
            await send_order_delivered(updated)
    except Exception as e:
        print(f"⚠️  Status email failed: {e}")

    updated["id"] = str(updated["_id"])
    del updated["_id"]
    return updated


# ─── PUBLIC ORDER TRACKING ───────────────────────────────
# This route has NO auth guard — customers can look up their orders.
# Rate limiting should be added later (e.g., by IP).

public_router = APIRouter(prefix="/api/track", tags=["public-tracking"])


@public_router.get("/{order_number}")
async def track_order(order_number: str, email: str = None):
    """
    Public order tracking.
    Requires order number. Email is optional for extra validation.
    Returns a SANITIZED order object — no internal admin data.
    """
    from ..services.orders import get_order_by_number

    order = await get_order_by_number(order_number)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Optional email verification — if email is provided, must match
    if email and order["customer"]["email"].lower() != email.lower():
        raise HTTPException(
            status_code=404, detail="Order not found for this email"
        )

    # Sanitize — don't leak internal data
    sanitized = {
        "order_number": order["order_number"],
        "status": order["status"],
        "created_at": order["created_at"],
        "customer": {
            "full_name": order["customer"]["full_name"],
            # Mask email — show first char + domain
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
    """Mask email for public display: j***@example.com"""
    try:
        local, domain = email.split("@")
        if len(local) <= 2:
            masked_local = local[0] + "*"
        else:
            masked_local = local[0] + "*" * (len(local) - 1)
        return f"{masked_local}@{domain}"
    except Exception:
        return "***"



@router.get("/stats/overview")
async def admin_order_stats(user: dict = Depends(require_admin)):
    """
    Dashboard overview stats:
    - Total revenue (all time + this month + today)
    - Total orders by status
    - Recent orders count
    """
    from ..database import orders_collection

    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    col = orders_collection()

    # Revenue (only count paid orders)
    paid_filter = {"payment.status": "success"}

    # Total revenue
    pipeline_total = [
        {"$match": paid_filter},
        {"$group": {"_id": None, "total": {"$sum": "$total_kobo"}}},
    ]
    result = await col.aggregate(pipeline_total).to_list(1)
    total_revenue = result[0]["total"] if result else 0

    # Revenue this month
    pipeline_month = [
        {"$match": {**paid_filter, "created_at": {"$gte": month_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$total_kobo"}}},
    ]
    result = await col.aggregate(pipeline_month).to_list(1)
    month_revenue = result[0]["total"] if result else 0

    # Revenue today
    pipeline_today = [
        {"$match": {**paid_filter, "created_at": {"$gte": today_start}}},
        {"$group": {"_id": None, "total": {"$sum": "$total_kobo"}}},
    ]
    result = await col.aggregate(pipeline_today).to_list(1)
    today_revenue = result[0]["total"] if result else 0

    # Orders by status
    status_pipeline = [
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]
    status_counts = {}
    async for doc in col.aggregate(status_pipeline):
        status_counts[doc["_id"]] = doc["count"]

    total_orders = sum(status_counts.values())

    # New orders today
    today_orders = await col.count_documents(
        {**paid_filter, "created_at": {"$gte": today_start}}
    )

    return {
        "revenue": {
            "total_kobo": total_revenue,
            "total_formatted": _naira(total_revenue),
            "month_kobo": month_revenue,
            "month_formatted": _naira(month_revenue),
            "today_kobo": today_revenue,
            "today_formatted": _naira(today_revenue),
        },
        "orders": {
            "total": total_orders,
            "today": today_orders,
            "by_status": status_counts,
        },
    }


@router.get("/stats/revenue-chart")
async def admin_revenue_chart(
    days: int = 30,
    user: dict = Depends(require_admin),
):
    """
    Daily revenue for the last N days (default 30).
    Returns array: [{date: "2026-10-01", revenue_kobo: 12340000, orders: 5}, ...]
    """
    from ..database import orders_collection

    now = datetime.utcnow()
    start = now - timedelta(days=days - 1)
    start = start.replace(hour=0, minute=0, second=0, microsecond=0)

    pipeline = [
        {
            "$match": {
                "payment.status": "success",
                "created_at": {"$gte": start},
            }
        },
        {
            "$group": {
                "_id": {
                    "$dateToString": {
                        "format": "%Y-%m-%d",
                        "date": "$created_at",
                    }
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

    # Fill in missing days with zeros
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
            output.append({
                "date": day_str,
                "revenue_kobo": 0,
                "orders": 0,
            })

    return {"days": days, "data": output}


@router.get("/stats/top-products")
async def admin_top_products(
    limit: int = 10,
    user: dict = Depends(require_admin),
):
    """
    Top products by units sold and revenue.
    """
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


def _naira(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"