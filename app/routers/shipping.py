from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime
from bson import ObjectId
from typing import List, Optional

from ..database import shipping_zones_collection
from ..models.shipping import (
    ShippingZoneCreate,
    ShippingZoneUpdate,
    ShippingZoneResponse,
)
from ..dependencies.auth import require_admin

# ─── PUBLIC ROUTER ──────────────────────────────────────
public_router = APIRouter(prefix="/api/shipping", tags=["shipping-public"])


def _naira(kobo: int) -> str:
    return f"₦{kobo / 100:,.2f}"


def _to_response(doc: dict) -> ShippingZoneResponse:
    return ShippingZoneResponse(
        id=str(doc["_id"]),
        name=doc["name"],
        description=doc.get("description"),
        rate_kobo=doc["rate_kobo"],
        rate_formatted=_naira(doc["rate_kobo"]),
        is_default=doc.get("is_default", False),
        is_active=doc.get("is_active", True),
        display_order=doc.get("display_order", 0),
        created_at=doc.get("created_at", datetime.utcnow()),
        updated_at=doc.get("updated_at", datetime.utcnow()),
    )


@public_router.get("", response_model=List[ShippingZoneResponse])
async def list_shipping_zones_public():
    """Public — used by checkout modal to display available zones."""
    cursor = (
        shipping_zones_collection()
        .find({"is_active": True})
        .sort([("is_default", 1), ("display_order", 1), ("name", 1)])
    )
    zones = []
    async for doc in cursor:
        zones.append(_to_response(doc))
    return zones


# ─── ADMIN ROUTER ───────────────────────────────────────
router = APIRouter(prefix="/api/admin/shipping", tags=["admin-shipping"])


@router.get("", response_model=List[ShippingZoneResponse])
async def admin_list_zones(user: dict = Depends(require_admin)):
    cursor = (
        shipping_zones_collection()
        .find()
        .sort([("display_order", 1), ("name", 1)])
    )
    zones = []
    async for doc in cursor:
        zones.append(_to_response(doc))
    return zones


@router.post("", response_model=ShippingZoneResponse, status_code=201)
async def admin_create_zone(
    payload: ShippingZoneCreate,
    user: dict = Depends(require_admin),
):
    # If this zone is being set as default, unset any existing default
    if payload.is_default:
        await shipping_zones_collection().update_many(
            {"is_default": True}, {"$set": {"is_default": False}}
        )

    now = datetime.utcnow()
    doc = {
        **payload.model_dump(),
        "created_at": now,
        "updated_at": now,
    }
    result = await shipping_zones_collection().insert_one(doc)
    doc["_id"] = result.inserted_id
    return _to_response(doc)


@router.patch("/{zone_id}", response_model=ShippingZoneResponse)
async def admin_update_zone(
    zone_id: str,
    payload: ShippingZoneUpdate,
    user: dict = Depends(require_admin),
):
    try:
        obj_id = ObjectId(zone_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid zone ID")

    updates = {k: v for k, v in payload.model_dump(exclude_none=True).items()}

    # Handle default toggle
    if updates.get("is_default") is True:
        await shipping_zones_collection().update_many(
            {"is_default": True, "_id": {"$ne": obj_id}},
            {"$set": {"is_default": False}},
        )

    updates["updated_at"] = datetime.utcnow()

    result = await shipping_zones_collection().update_one(
        {"_id": obj_id}, {"$set": updates}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Zone not found")

    doc = await shipping_zones_collection().find_one({"_id": obj_id})
    return _to_response(doc)


@router.delete("/{zone_id}")
async def admin_delete_zone(
    zone_id: str,
    user: dict = Depends(require_admin),
):
    try:
        obj_id = ObjectId(zone_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid zone ID")

    result = await shipping_zones_collection().delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Zone not found")

    return {"status": "deleted"}