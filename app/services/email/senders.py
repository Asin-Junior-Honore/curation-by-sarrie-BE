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
    """
    Generic email sender — used anywhere.
    Kept for backwards compat with existing code (admin_invite).
    """
    if context is None:
        context = {}
    try:
        html = render(template_name, context)
        return await send_raw_email(to_email, subject, html)
    except Exception as e:
        print(f"❌ Email render/send failed: {e}")
        return False


# ─── Order-related ──────────────────────────────────────
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
    return await send_email(
        to_email=settings.super_admin_email,
        subject=f"🎉 New order — {order['order_number']} (₦{order['total_kobo']/100:,.0f})",
        template_name="admin_new_order.html",
        context={
            "order": order,
            "order_number": order["order_number"],
            "admin_order_url": f"{settings.admin_panel_url.replace('/login', '/orders')}/{order['_id']}",
            "total_formatted": _naira(order["total_kobo"]),
        },
    )


# ─── Helpers ────────────────────────────────────────────
def _naira(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"