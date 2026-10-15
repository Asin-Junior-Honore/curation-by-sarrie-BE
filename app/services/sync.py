from datetime import datetime
from ..database import products_collection, sync_log_collection
from .bumpa import bumpa_client


def transform_bumpa_product(raw: dict) -> dict:
    """Map Bumpa's raw JSON to our internal BumpaData shape."""
    return {
        "bumpa_id": raw.get("id"),
        "slug": raw.get("slug"),
        "name": raw.get("name") or raw.get("title"),
        "price": float(raw.get("price", 0)),
        "price_formatted": raw.get("price_formatted", ""),
        "compare_at_price": float(raw["compare_at_price"])
            if raw.get("compare_at_price") else None,
        "quantity": raw.get("quantity", 0),
        "status": raw.get("status", 1),
        "type": raw.get("type", "simple"),
        "image_url": raw.get("image_url"),
        "optimized_image_url": raw.get("optimized_image_url"),
        "thumbnail_url": raw.get("thumbnail_url"),
        "additional_images": [
            img.get("path") for img in raw.get("images", [])
        ],
        "bumpa_url": raw.get("url"),
        "variations": raw.get("options", []),
        "last_synced_at": datetime.utcnow(),
    }


async def sync_all_products():
    """Full sync: pull every product, upsert into MongoDB."""
    print("🔄 Starting full sync from Bumpa...")
    started_at = datetime.utcnow()

    try:
        raw_products = await bumpa_client.get_all_products()
        print(f"📦 Fetched {len(raw_products)} products from Bumpa")

        inserted = 0
        updated = 0
        collection = products_collection()

        for raw in raw_products:
            bumpa_data = transform_bumpa_product(raw)
            bumpa_id = bumpa_data["bumpa_id"]

            existing = await collection.find_one({"bumpa.bumpa_id": bumpa_id})

            if existing:
                await collection.update_one(
                    {"bumpa.bumpa_id": bumpa_id},
                    {
                        "$set": {
                            "bumpa": bumpa_data,
                            "updated_at": datetime.utcnow(),
                        }
                    },
                )
                updated += 1
            else:
                doc = {
                    "bumpa": bumpa_data,
                    "editorial": {
                        "collections": [],
                        "recipients": [],
                        "occasions": [],
                        "is_bestseller": False,
                        "is_loved": False,
                        "is_newly_added": False,
                        "is_featured": False,
                        "is_limited": False,
                        "is_personalizable": False,
                        "is_hidden": False,
                        "display_order": 0,
                        "related_product_ids": [],
                    },
                    "created_at": datetime.utcnow(),
                    "updated_at": datetime.utcnow(),
                }
                await collection.insert_one(doc)
                inserted += 1

        finished_at = datetime.utcnow()
        duration = (finished_at - started_at).total_seconds()

        await sync_log_collection().insert_one({
            "type": "full_sync",
            "total": len(raw_products),
            "inserted": inserted,
            "updated": updated,
            "duration_seconds": duration,
            "started_at": started_at,
            "finished_at": finished_at,
        })

        print(f"✅ Sync complete: {inserted} new, {updated} updated in {duration:.2f}s")

        return {
            "total": len(raw_products),
            "inserted": inserted,
            "updated": updated,
            "duration_seconds": duration,
        }

    except Exception as e:
        print(f"❌ Sync failed: {e}")
        await sync_log_collection().insert_one({
            "type": "full_sync",
            "status": "failed",
            "error": str(e),
            "started_at": started_at,
        })
        raise