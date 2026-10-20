from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal
from datetime import datetime

OrderStatus = Literal[
    "pending",       # created, awaiting payment
    "paid",          # payment confirmed
    "preparing",     # admin is preparing the order
    "in_transit",    # shipped / on the way
    "delivered",     # delivered to customer
    "completed",     # admin ticked off
    "cancelled",     # cancelled
    "failed",        # payment failed
    "refunded",      # refunded
]


class OrderItem(BaseModel):
    """One product line in the order."""
    product_id: str           # MongoDB _id
    bumpa_id: int             # Bumpa ID (for sync reference)
    slug: str
    name: str
    image: str
    price: int                # unit price in kobo
    price_formatted: str      # "₦85,000.00"
    quantity: int
    subtotal: int             # price * quantity (kobo)
    is_personalizable: bool = False
    personalization: Optional[dict] = None


class CustomerInfo(BaseModel):
    full_name: str
    email: EmailStr
    phone: str
    phone_secondary: Optional[str] = None
    notes: Optional[str] = None


class DeliveryInfo(BaseModel):
    address: str
    city: str
    state: str
    country: str = "Nigeria"
    landmark: Optional[str] = None
    delivery_instructions: Optional[str] = None
    shipping_zone_id: Optional[str] = None       # ← new
    shipping_zone_name: Optional[str] = None     # ← new


class PaymentInfo(BaseModel):
    provider: str = "paystack"
    reference: str                    # our unique ref, e.g., CBS-20261016-A3F9
    paystack_reference: Optional[str] = None
    authorization_url: Optional[str] = None
    access_code: Optional[str] = None
    status: str = "pending"           # pending | success | failed
    amount_paid: int = 0              # kobo
    channel: Optional[str] = None     # card, bank_transfer, ussd, etc.
    paid_at: Optional[datetime] = None
    paystack_response: Optional[dict] = None  # raw response snapshot


class StatusHistoryEntry(BaseModel):
    status: OrderStatus
    note: Optional[str] = None
    changed_by: Optional[str] = None  # admin user id, or "system"
    changed_at: datetime = Field(default_factory=datetime.utcnow)


class OrderBase(BaseModel):
    customer: CustomerInfo
    delivery: DeliveryInfo
    items: List[OrderItem]

    subtotal_kobo: int
    delivery_fee_kobo: int
    total_kobo: int


class OrderCreate(BaseModel):
    """What the frontend sends to /api/checkout/initialize."""
    customer: CustomerInfo
    delivery: DeliveryInfo
    items: List[dict]  # {product_id, quantity, personalization?}


class OrderInDB(OrderBase):
    """Full document stored in MongoDB."""
    _id: Optional[str] = None
    order_number: str                 # human-readable, e.g., "CBS-00042"
    status: OrderStatus = "pending"
    payment: PaymentInfo
    status_history: List[StatusHistoryEntry] = []
    admin_notes: Optional[str] = None
    internal_notes: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    emails_sent_at: Optional[datetime] = None   # ← new
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OrderResponse(OrderInDB):
    """What the API returns."""
    id: str  # mapped from _id


class OrderStatusUpdate(BaseModel):
    status: OrderStatus
    note: Optional[str] = None


class CheckoutInitializeResponse(BaseModel):
    order_id: str
    order_number: str
    reference: str
    authorization_url: str
    access_code: str
    total_kobo: int
    total_formatted: str