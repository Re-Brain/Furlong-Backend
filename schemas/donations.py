from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional

# Currencies Frankfurter (api.frankfurter.app) can convert JPY into. ECB
# reference rates, so this list changes rarely -- hardcoded rather than
# fetched per-request.
SUPPORTED_FX_CURRENCIES = {
    "AUD", "BRL", "CAD", "CHF", "CNY", "CZK", "DKK", "EUR", "GBP", "HKD",
    "HUF", "IDR", "ILS", "INR", "ISK", "KRW", "MXN", "MYR", "NOK", "NZD",
    "PHP", "PLN", "RON", "SEK", "SGD", "THB", "TRY", "USD", "ZAR",
}


class DonationCheckoutCreate(BaseModel):
    farm_id: int
    amount: int = Field(ge=100)  # whole yen (JPY is zero-decimal in Stripe, no x100); min donation is 100


class FxEstimateResponse(BaseModel):
    """Display-only conversion estimate for the donation form. Never used for
    the actual charge, which always stays in JPY (core.stripe_client.CURRENCY)."""
    jpy_amount: int
    currency: str
    converted_amount: float
    rate_date: date


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
