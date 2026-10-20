from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ShippingZoneBase(BaseModel):
    name: str                          # "Ikeja LGA"
    description: Optional[str] = None  # "Ikeja, Opebi, Allen Avenue, Maryland, Alausa"
    rate_kobo: int                     # 500000 = ₦5,000
    is_default: bool = False           # Fallback for unmatched areas
    is_active: bool = True
    display_order: int = 0


class ShippingZoneCreate(ShippingZoneBase):
    pass


class ShippingZoneUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    rate_kobo: Optional[int] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    display_order: Optional[int] = None


class ShippingZoneResponse(ShippingZoneBase):
    id: str
    rate_formatted: str
    created_at: datetime
    updated_at: datetime