import hmac
import hashlib
from datetime import datetime
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import JSONResponse

from ..config import settings
from ..models.order import (
    OrderCreate,
    CheckoutInitializeResponse,
    OrderResponse,
)
from ..services.email import (
    send_order_confirmation,
    send_admin_new_order_alert,
)
from ..services.paystack import paystack_client
from ..services.orders import (
    create_order,
    get_order_by_reference,
    update_order_payment,
    format_naira,
)

router = APIRouter(prefix="/api/checkout", tags=["checkout"])


# ─── Initialize checkout ────────────────────────────────
@router.post("/initialize", response_model=CheckoutInitializeResponse)
async def initialize_checkout(payload: OrderCreate):
    """
    Create an order and initialize Paystack transaction.
    Frontend redirects user to authorization_url.
    """
    try:
        order, reference = await create_order(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to create order: {str(e)}"
        )

    # Initialize Paystack
    try:
        ps_data = await paystack_client.initialize_transaction(
            email=payload.customer.email,
            amount_kobo=order.total_kobo,
            reference=reference,
            callback_url=settings.checkout_success_url,
            metadata={
                "order_id": order._id,
                "order_number": order.order_number,
                "customer_name": payload.customer.full_name,
            },
        )
    except Exception as e:
        await update_order_payment(
            reference=reference,
            status="failed",
            amount_paid=0,
            channel=None,
            paid_at=None,
            paystack_response={"error": str(e)},
        )
        raise HTTPException(
            status_code=502,
            detail=f"Payment initialization failed: {str(e)}",
        )

    # Save Paystack response data to order
    await update_order_payment(
        reference=reference,
        status="pending",
        amount_paid=0,
        channel=None,
        paid_at=None,
        paystack_response=ps_data,
    )

    return CheckoutInitializeResponse(
        order_id=order._id,
        order_number=order.order_number,
        reference=reference,
        authorization_url=ps_data["authorization_url"],
        access_code=ps_data["access_code"],
        total_kobo=order.total_kobo,
        total_formatted=format_naira(order.total_kobo),
    )


# ─── Verify payment (user returns from Paystack) ────────
@router.get("/verify/{reference}")
async def verify_checkout(reference: str):
    """
    Called by the frontend on the success page.
    Verifies with Paystack and returns current order state.
    """
    order = await get_order_by_reference(reference)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    # Capture current status for idempotency checks
    current_payment_status = order.get("payment", {}).get("status")

    # If already paid, return immediately (idempotency — no duplicate emails)
    if current_payment_status == "success":
        order["id"] = str(order["_id"])
        del order["_id"]
        return {"status": "success", "order": order}

    # Verify with Paystack
    try:
        ps_data = await paystack_client.verify_transaction(reference)
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"Verification failed: {str(e)}"
        )

    # Map Paystack status → our status
    ps_status = ps_data.get("status")  # "success" | "failed" | "abandoned"
    is_success = ps_status == "success"
    amount_paid = int(ps_data.get("amount", 0))
    channel = ps_data.get("channel")
    paid_at_raw = ps_data.get("paid_at")
    paid_at = (
        datetime.fromisoformat(paid_at_raw.replace("Z", "+00:00"))
        if paid_at_raw
        else None
    )

    # Update order
    updated = await update_order_payment(
        reference=reference,
        status="success" if is_success else "failed",
        amount_paid=amount_paid,
        channel=channel,
        paid_at=paid_at,
        paystack_response=ps_data,
        new_order_status="paid" if is_success else "failed",
    )

    # Fire emails only if this is a NEW success
    if updated and is_success and current_payment_status != "success":
        try:
            await send_order_confirmation(updated)
            await send_admin_new_order_alert(updated)
        except Exception as e:
            print(f"⚠️  Verify email failed: {e}")

    if updated:
        updated["id"] = str(updated["_id"])
        del updated["_id"]

    return {
        "status": "success" if is_success else "failed",
        "order": updated,
    }


# ─── Paystack Webhook ───────────────────────────────────
@router.post("/webhook/paystack")
async def paystack_webhook(request: Request):
    """
    Receives Paystack webhook events.
    Verifies HMAC-SHA512 signature before processing.
    Uses idempotency to prevent duplicate processing.
    """
    raw_body = await request.body()
    signature = request.headers.get("x-paystack-signature", "")

    if not signature:
        raise HTTPException(status_code=400, detail="Missing signature")

    expected = hmac.new(
        settings.paystack_secret_key.encode("utf-8"),
        raw_body,
        hashlib.sha512,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        event = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = event.get("event")
    data = event.get("data", {})
    reference = data.get("reference")

    if not reference:
        return JSONResponse({"status": "ignored", "reason": "no reference"})

    order = await get_order_by_reference(reference)
    if not order:
        return JSONResponse({"status": "ignored", "reason": "order not found"})

    current_payment_status = order.get("payment", {}).get("status")

    # ─── Charge success ─────────────────────────────────
    if event_type == "charge.success":
        if current_payment_status == "success":
            return JSONResponse({"status": "already_processed"})

        amount_paid = int(data.get("amount", 0))
        channel = data.get("channel")
        paid_at_raw = data.get("paid_at")
        paid_at = (
            datetime.fromisoformat(paid_at_raw.replace("Z", "+00:00"))
            if paid_at_raw
            else None
        )

        updated = await update_order_payment(
            reference=reference,
            status="success",
            amount_paid=amount_paid,
            channel=channel,
            paid_at=paid_at,
            paystack_response=data,
            new_order_status="paid",
        )

        # Fire emails (non-blocking)
        if updated:
            try:
                await send_order_confirmation(updated)
                await send_admin_new_order_alert(updated)
            except Exception as e:
                print(f"⚠️  Webhook email failed: {e}")

        return JSONResponse({"status": "processed", "event": event_type})

    # ─── Charge failed / abandoned ──────────────────────
    elif event_type in ("charge.failed", "charge.abandoned"):
        if current_payment_status == "failed":
            return JSONResponse({"status": "already_processed"})

        await update_order_payment(
            reference=reference,
            status="failed",
            amount_paid=0,
            channel=data.get("channel"),
            paid_at=None,
            paystack_response=data,
            new_order_status="failed",
        )

        return JSONResponse({"status": "processed", "event": event_type})

    return JSONResponse({"status": "ignored", "event": event_type})