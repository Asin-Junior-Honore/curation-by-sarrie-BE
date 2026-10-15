from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class BumpaData(BaseModel):
    """Raw data from Bumpa — auto-synced, never edited manually."""
    bumpa_id: int
    slug: str
    name: str
    price: float
    price_formatted: str
    compare_at_price: Optional[float] = None
    quantity: int
    status: int
    type: str = "simple"
    image_url: Optional[str] = None
    optimized_image_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    additional_images: List[str] = []
    bumpa_url: Optional[str] = None
    variations: List[dict] = []
    last_synced_at: datetime = Field(default_factory=datetime.utcnow)


class EditorialData(BaseModel):
    """Client fills these in via the admin panel."""
    tagline: Optional[str] = None
    short_description: Optional[str] = None
    long_description: Optional[str] = None

    collections: List[str] = []
    recipients: List[str] = []       # Her, Him, Kids, Unisex
    occasions: List[str] = []        # Birthday, Anniversary, etc.
    category_type: Optional[str] = None   # Hamper, Fragrance, etc.

    is_bestseller: bool = False
    is_loved: bool = False
    is_newly_added: bool = False
    is_featured: bool = False
    is_limited: bool = False
    is_personalizable: bool = False
    badge_text: Optional[str] = None

    ingredients: Optional[str] = None
    dimensions: Optional[str] = None
    weight_kg: Optional[float] = None
    care_instructions: Optional[str] = None
    shipping_note: Optional[str] = None

    seo_title: Optional[str] = None
    seo_description: Optional[str] = None

    display_order: int = 0
    related_product_ids: List[int] = []
    is_hidden: bool = False


class ProductResponse(BaseModel):
    """What the API returns — bumpa data + editorial merged."""
    bumpa: BumpaData
    editorial: EditorialData
    created_at: datetime
    updated_at: datetime