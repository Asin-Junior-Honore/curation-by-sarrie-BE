from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional

from ..models.order import OrderStatusUpdate
from ..dependencies.auth import require_admin
from ..services.orders import (
    list_orders,
    get_order_by_id,
    update_order_status,
)

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
    updated = await update_order_status(
        order_id=order_id,
        new_status=payload.status,
        note=payload.note,
        changed_by=str(user["_id"]),
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Order not found")

    # TODO: send status change emails (in_transit, delivered)
    # wired in the email drop

    updated["id"] = str(updated["_id"])
    del updated["_id"]
    return updated