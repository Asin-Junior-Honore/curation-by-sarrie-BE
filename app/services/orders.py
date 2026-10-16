import secrets
from datetime import datetime
from typing import Optional
from bson import ObjectId

from ..database import orders_collection, products_collection
from ..config import settings
from ..models.order import (
    OrderCreate,
    OrderItem,
    OrderInDB,
    PaymentInfo,
    StatusHistoryEntry,
    OrderStatus,
)


def generate_order_number() -> str:
    """Human-friendly order number: CBS-YYMMDD-XXXX"""
    today = datetime.utcnow().strftime("%y%m%d")
    suffix = secrets.token_hex(2).upper()  # 4 hex chars
    return f"CBS-{today}-{suffix}"


def generate_reference() -> str:
    """Paystack-safe unique reference."""
    return f"CBS-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(3).upper()}"


def format_naira(kobo: int) -> str:
    """Convert kobo → ₦ formatted string."""
    naira = kobo / 100
    return f"₦{naira:,.2f}"


async def build_order_items(raw_items: list) -> list[OrderItem]:
    """
    Fetch each product from MongoDB, build OrderItem list.
    Raises ValueError if any product is missing, hidden, or out of stock.
    """
    items: list[OrderItem] = []
    for raw in raw_items:
        product_id = raw["product_id"]
        qty = int(raw.get("quantity", 1))
        personalization = raw.get("personalization")

        try:
            obj_id = ObjectId(product_id)
        except Exception:
            raise ValueError(f"Invalid product ID: {product_id}")

        product = await products_collection().find_one({"_id": obj_id})
        if not product:
            raise ValueError(f"Product not found: {product_id}")

        bumpa = product.get("bumpa", {})
        editorial = product.get("editorial", {})

        if editorial.get("is_hidden"):
            raise ValueError(f"Product unavailable: {bumpa.get('name')}")

        if bumpa.get("quantity", 0) < qty:
            raise ValueError(
                f"Insufficient stock for {bumpa.get('name')}. "
                f"Only {bumpa.get('quantity')} available."
            )

        # Convert price to kobo (Bumpa returns price as float in Naira)
        price_kobo = int(round(float(bumpa["price"]) * 100))

        items.append(
            OrderItem(
                product_id=str(product["_id"]),
                bumpa_id=bumpa["bumpa_id"],
                slug=bumpa["slug"],
                name=bumpa["name"],
                image=bumpa.get("optimized_image_url")
                or bumpa.get("image_url")
                or "",
                price=price_kobo,
                price_formatted=format_naira(price_kobo),
                quantity=qty,
                subtotal=price_kobo * qty,
                is_personalizable=editorial.get("is_personalizable", False),
                personalization=personalization,
            )
        )

    return items


async def create_order(payload: OrderCreate) -> tuple[OrderInDB, str]:
    """
    Build the order document (before payment).
    Returns (order_doc, reference).
    """
    items = await build_order_items(payload.items)

    subtotal_kobo = sum(i.subtotal for i in items)
    delivery_fee_kobo = settings.delivery_fee_kobo
    total_kobo = subtotal_kobo + delivery_fee_kobo

    reference = generate_reference()
    order_number = generate_order_number()

    now = datetime.utcnow()

    order_doc = OrderInDB(
        order_number=order_number,
        customer=payload.customer,
        delivery=payload.delivery,
        items=items,
        subtotal_kobo=subtotal_kobo,
        delivery_fee_kobo=delivery_fee_kobo,
        total_kobo=total_kobo,
        status="pending",
        payment=PaymentInfo(
            provider="paystack",
            reference=reference,
            status="pending",
            amount_paid=0,
        ),
        status_history=[
            StatusHistoryEntry(
                status="pending",
                note="Order created, awaiting payment",
                changed_by="system",
                changed_at=now,
            )
        ],
        created_at=now,
        updated_at=now,
    )

    doc = order_doc.model_dump(exclude={"_id"})
    doc["created_at"] = now
    doc["updated_at"] = now

    result = await orders_collection().insert_one(doc)
    order_doc._id = str(result.inserted_id)

    return order_doc, reference


async def get_order_by_reference(reference: str) -> Optional[dict]:
    return await orders_collection().find_one({"payment.reference": reference})


async def get_order_by_id(order_id: str) -> Optional[dict]:
    try:
        return await orders_collection().find_one({"_id": ObjectId(order_id)})
    except Exception:
        return None


async def get_order_by_number(order_number: str) -> Optional[dict]:
    return await orders_collection().find_one({"order_number": order_number})


async def update_order_payment(
    reference: str,
    status: str,  # success | failed
    amount_paid: int,
    channel: Optional[str],
    paid_at: Optional[datetime],
    paystack_response: dict,
    new_order_status: Optional[OrderStatus] = None,
) -> Optional[dict]:
    """Update order payment + status after Paystack confirms."""
    update = {
        "payment.status": status,
        "payment.amount_paid": amount_paid,
        "payment.channel": channel,
        "payment.paystack_response": paystack_response,
        "updated_at": datetime.utcnow(),
    }
    if paid_at:
        update["payment.paid_at"] = paid_at

    if new_order_status:
        update["status"] = new_order_status
        await orders_collection().update_one(
            {"payment.reference": reference},
            {
                "$set": update,
                "$push": {
                    "status_history": {
                        "status": new_order_status,
                        "note": f"Payment {status}",
                        "changed_by": "system",
                        "changed_at": datetime.utcnow(),
                    }
                },
            },
        )
    else:
        await orders_collection().update_one(
            {"payment.reference": reference}, {"$set": update}
        )

    return await get_order_by_reference(reference)


async def update_order_status(
    order_id: str,
    new_status: OrderStatus,
    note: Optional[str] = None,
    changed_by: Optional[str] = None,
) -> Optional[dict]:
    """Admin updates order status (in_transit, delivered, etc.)."""
    now = datetime.utcnow()
    result = await orders_collection().update_one(
        {"_id": ObjectId(order_id)},
        {
            "$set": {"status": new_status, "updated_at": now},
            "$push": {
                "status_history": {
                    "status": new_status,
                    "note": note,
                    "changed_by": changed_by or "admin",
                    "changed_at": now,
                }
            },
        },
    )
    if result.matched_count == 0:
        return None
    return await get_order_by_id(order_id)


async def list_orders(
    status: Optional[str] = None,
    limit: int = 50,
    page: int = 1,
    search: Optional[str] = None,
) -> dict:
    query: dict = {}
    if status and status != "all":
        query["status"] = status
    if search:
        query["$or"] = [
            {"order_number": {"$regex": search, "$options": "i"}},
            {"customer.full_name": {"$regex": search, "$options": "i"}},
            {"customer.email": {"$regex": search, "$options": "i"}},
            {"customer.phone": {"$regex": search, "$options": "i"}},
        ]

    total = await orders_collection().count_documents(query)
    skip = (page - 1) * limit

    cursor = (
        orders_collection()
        .find(query)
        .sort("created_at", -1)
        .skip(skip)
        .limit(limit)
    )
    orders = []
    async for doc in cursor:
        doc["id"] = str(doc["_id"])
        del doc["_id"]
        orders.append(doc)

    return {
        "data": orders,
        "total": total,
        "page": page,
        "per_page": limit,
        "pages": (total + limit - 1) // limit if total else 0,
    }