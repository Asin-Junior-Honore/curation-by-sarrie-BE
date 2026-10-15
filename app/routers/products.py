from fastapi import APIRouter, HTTPException, Query
from typing import Optional
from ..database import products_collection

router = APIRouter(prefix="/api/products", tags=["products"])


def serialize_product(doc: dict) -> dict:
    """Convert MongoDB _id to string and merge fields."""
    if doc and "_id" in doc:
        doc["_id"] = str(doc["_id"])
    return doc


@router.get("")
async def list_products(
    collection: Optional[str] = None,
    recipient: Optional[str] = None,
    occasion: Optional[str] = None,
    is_bestseller: Optional[bool] = None,
    is_loved: Optional[bool] = None,
    is_featured: Optional[bool] = None,
    is_newly_added: Optional[bool] = None,
    search: Optional[str] = None,
    limit: int = Query(20, le=100),
    page: int = Query(1, ge=1),
):
    """List products with filters."""
    query = {"editorial.is_hidden": {"$ne": True}, "bumpa.status": 1}

    if collection:
        query["editorial.collections"] = collection
    if recipient:
        query["editorial.recipients"] = recipient
    if occasion:
        query["editorial.occasions"] = occasion
    if is_bestseller is not None:
        query["editorial.is_bestseller"] = is_bestseller
    if is_featured is not None:
        query["editorial.is_featured"] = is_featured
    if is_newly_added is not None:
        query["editorial.is_newly_added"] = is_newly_added

        if is_loved is not None:
                query["editorial.is_loved"] = is_loved
                
        
    if search:
        query["bumpa.name"] = {"$regex": search, "$options": "i"}

    skip = (page - 1) * limit
    total = await products_collection().count_documents(query)

    cursor = (
        products_collection()
        .find(query)
        .sort("editorial.display_order", 1)
        .skip(skip)
        .limit(limit)
    )

    products = [serialize_product(doc) async for doc in cursor]

    return {
        "data": products,
        "total": total,
        "page": page,
        "per_page": limit,
        "pages": (total + limit - 1) // limit,
    }


@router.get("/{slug}")
async def get_product(slug: str):
    """Fetch a single product by slug."""
    doc = await products_collection().find_one({"bumpa.slug": slug})
    if not doc:
        raise HTTPException(status_code=404, detail="Product not found")
    return serialize_product(doc)


@router.get("/{slug}/related")
async def get_related_products(slug: str, limit: int = 8):
    """Return products that share collections/recipients with this one."""
    product = await products_collection().find_one({"bumpa.slug": slug})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    editorial = product.get("editorial", {})
    collections = editorial.get("collections", []) or []
    recipients = editorial.get("recipients", []) or []
    category = editorial.get("category_type")

    # Find products sharing any tag, excluding self
    or_clauses = []
    if collections:
        or_clauses.append({"editorial.collections": {"$in": collections}})
    if recipients:
        or_clauses.append({"editorial.recipients": {"$in": recipients}})
    if category:
        or_clauses.append({"editorial.category_type": category})

    query = {
        "bumpa.slug": {"$ne": slug},
        "bumpa.status": 1,
        "editorial.is_hidden": {"$ne": True},
    }
    if or_clauses:
        query["$or"] = or_clauses

    cursor = products_collection().find(query).limit(limit)
    related = []
    async for doc in cursor:
        doc["_id"] = str(doc["_id"])
        related.append(doc)

    return {"data": related, "total": len(related)}