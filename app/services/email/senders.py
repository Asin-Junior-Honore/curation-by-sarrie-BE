from .client import send_raw_email
from .templates import render
from ...config import settings


# ─── Generic ────────────────────────────────────────────
async def send_email(
    to_email: str,
    subject: str,
    template_name: str,
    context: dict | None = None,
) -> bool:
    if context is None:
        context = {}
    try:
        html = render(template_name, context)
        return await send_raw_email(to_email, subject, html)
    except Exception as e:
        print(f"❌ Email render/send failed: {e}")
        return False


# ─── Order lifecycle ────────────────────────────────────
async def send_order_confirmation(order: dict) -> bool:
    """Sent to customer when payment succeeds."""
    return await send_email(
        to_email=order["customer"]["email"],
        subject=f"Order confirmed — {order['order_number']}",
        template_name="order_confirmation.html",
        context={
            "order": order,
            "order_number": order["order_number"],
            "customer_name": order["customer"]["full_name"],
            "customer_first_name": order["customer"]["full_name"].split()[0],
            "tracking_url": f"{settings.frontend_url}/track/{order['order_number']}",
            "total_formatted": _naira(order["total_kobo"]),
            "subtotal_formatted": _naira(order["subtotal_kobo"]),
            "delivery_fee_formatted": _naira(order["delivery_fee_kobo"]),
        },
    )


async def send_order_preparing(order: dict) -> bool:
    """Sent when admin marks order as preparing."""
    return await send_email(
        to_email=order["customer"]["email"],
        subject=f"We're preparing your gift — {order['order_number']} 🎁",
        template_name="order_preparing.html",
        context={
            "order": order,
            "order_number": order["order_number"],
            "customer_name": order["customer"]["full_name"],
            "customer_first_name": order["customer"]["full_name"].split()[0],
            "tracking_url": f"{settings.frontend_url}/track/{order['order_number']}",
        },
    )


async def send_order_in_transit(order: dict) -> bool:
    """Sent when admin marks order as in_transit."""
    return await send_email(
        to_email=order["customer"]["email"],
        subject=f"Your order is on the way — {order['order_number']}",
        template_name="order_in_transit.html",
        context={
            "order": order,
            "order_number": order["order_number"],
            "customer_name": order["customer"]["full_name"],
            "customer_first_name": order["customer"]["full_name"].split()[0],
            "tracking_url": f"{settings.frontend_url}/track/{order['order_number']}",
        },
    )


async def send_order_delivered(order: dict) -> bool:
    """Sent when admin marks order as delivered."""
    return await send_email(
        to_email=order["customer"]["email"],
        subject=f"Delivered — {order['order_number']} 🎁",
        template_name="order_delivered.html",
        context={
            "order": order,
            "order_number": order["order_number"],
            "customer_name": order["customer"]["full_name"],
            "customer_first_name": order["customer"]["full_name"].split()[0],
            "review_url": f"{settings.frontend_url}/gifts",
        },
    )


async def send_admin_new_order_alert(order: dict) -> bool:
    """Sent to admin when a payment succeeds."""
    # Handle ObjectId → string safely
    order_id = order.get("_id") or order.get("id") or ""
    if order_id:
        order_id_str = str(order_id)
    else:
        order_id_str = ""

    admin_url_base = settings.admin_panel_url.replace("/login", "/orders")

    return await send_email(
        to_email=settings.super_admin_email,
        subject=f"🎉 New order — {order['order_number']} (₦{order['total_kobo']/100:,.0f})",
        template_name="admin_new_order.html",
        context={
            "order": order,
            "order_number": order["order_number"],
            "admin_order_url": f"{admin_url_base}/{order_id_str}" if order_id_str else admin_url_base,
            "total_formatted": _naira(order["total_kobo"]),
        },
    )
# ─── Helpers ────────────────────────────────────────────
def _naira(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"