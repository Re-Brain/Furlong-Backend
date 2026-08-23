from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional


class DonationCheckoutCreate(BaseModel):
    farm_id: int
    amount: int = Field(ge=100)  # whole yen (JPY is zero-decimal in Stripe, no x100); min donation is 100


class DonationCheckoutResponse(BaseModel):
    checkout_url: str


class FarmDonationResponse(BaseModel):
    id: int
    amount_yen: int
    donor_name: Optional[str] = None
    donor_email: Optional[str] = None
    created_at: datetime


class DonationResponse(BaseModel):
    id: int
    farm_id: int
    farm_name: Optional[str] = None
    visitor_id: Optional[int] = None
    visitor_name: Optional[str] = None
    amount: int
    application_fee_amount: int
    currency: str
    stripe_checkout_session_id: str
    stripe_payment_intent_id: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
