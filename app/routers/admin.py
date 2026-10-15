from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

from ..database import products_collection, sync_log_collection
from ..services.sync import sync_all_products
from ..dependencies.auth import require_admin
from ..services.email import send_email


router = APIRouter(prefix="/api/admin", tags=["admin"])


class EditorialUpdate(BaseModel):
    tagline: Optional[str] = None
    short_description: Optional[str] = None
    long_description: Optional[str] = None
    collections: Optional[List[str]] = None
    recipients: Optional[List[str]] = None
    occasions: Optional[List[str]] = None
    category_type: Optional[str] = None
    is_bestseller: Optional[bool] = None
    is_loved: Optional[bool] = None
    is_newly_added: Optional[bool] = None
    is_featured: Optional[bool] = None
    is_limited: Optional[bool] = None
    is_personalizable: Optional[bool] = None
    badge_text: Optional[str] = None
    ingredients: Optional[str] = None
    dimensions: Optional[str] = None
    weight_kg: Optional[float] = None
    care_instructions: Optional[str] = None
    shipping_note: Optional[str] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    display_order: Optional[int] = None
    related_product_ids: Optional[List[int]] = None
    is_hidden: Optional[bool] = None


@router.post("/sync")
async def trigger_sync(user: dict = Depends(require_admin)):
    result = await sync_all_products()
    return {"status": "ok", **result}


@router.get("/sync/log")
async def get_sync_log(limit: int = 10, user: dict = Depends(require_admin)):
    cursor = sync_log_collection().find().sort("started_at", -1).limit(limit)
    logs = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        logs.append(doc)
    return {"logs": logs}


@router.get("/products")
async def admin_list_products(
    limit: int = 100,
    page: int = 1,
    user: dict = Depends(require_admin),
):
    skip = (page - 1) * limit
    cursor = products_collection().find().skip(skip).limit(limit)
    products = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        products.append(doc)
    total = await products_collection().count_documents({})
    return {"data": products, "total": total, "page": page}


@router.patch("/products/{slug}")
async def update_editorial(
    slug: str,
    update: EditorialUpdate,
    user: dict = Depends(require_admin),
):
    update_data = {k: v for k, v in update.model_dump().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    result = await products_collection().update_one(
        {"bumpa.slug": slug},
        {
            "$set": {
                **{f"editorial.{k}": v for k, v in update_data.items()},
                "updated_at": datetime.utcnow(),
            }
        },
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")

    return {"status": "ok", "updated_fields": list(update_data.keys())}




@router.post("/test-email")
async def test_email(
    to: str,
    user: dict = Depends(require_admin),
):
    """Send a test email to verify SMTP config works."""
    ok = await send_email(
        to_email=to,
        subject="Test email — Curation by Sarrie",
        template_name="admin_invite.html",
        context={
            "full_name": "Test User",
            "email": to,
            "password": "TestPass123!",
            "role_label": "Test",
            "login_url": "http://localhost:3000/admin/login",
        },
    )
    return {"status": "sent" if ok else "failed", "to": to}