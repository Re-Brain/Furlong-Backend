from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from jose import JWTError, jwt
from typing import Optional
import stripe
import models.models as models
from database import get_db
from core.auth import SECRET_KEY, ALGORITHM, ACCESS_COOKIE_NAME
from core.stripe_client import CURRENCY, FRONTEND_URL, PLATFORM_FEE_PERCENT, STRIPE_WEBHOOK_SECRET
from routers.farms import get_current_farmer
from core.rate_limit import enforce_loose_limit
import schemas.donations as donation_schemas

router = APIRouter()


def get_current_farmer_farm(
    current_user: models.User = Depends(get_current_farmer),
    db: Session = Depends(get_db),
) -> models.Farm:
    farm = db.query(models.Farm).filter(models.Farm.owner_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    return farm


def get_optional_visitor(request: Request, db: Session = Depends(get_db)) -> Optional[models.User]:
    """Like decode_token -> get_current_user, but a donor need not be logged in."""
    token = request.cookies.get(ACCESS_COOKIE_NAME)
    if not token:
        return None
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    email = payload.get("sub")
    return db.query(models.User).filter(models.User.email == email).first() if email else None


@router.post("/donations/checkout-session", response_model=donation_schemas.DonationCheckoutResponse)
def create_donation_checkout_session(
    request: Request,
    data: donation_schemas.DonationCheckoutCreate,
    visitor: Optional[models.User] = Depends(get_optional_visitor),
    db: Session = Depends(get_db),
):
    enforce_loose_limit(request, "donations-checkout")

    if visitor and visitor.role in ("farmer", "admin"):
        raise HTTPException(status_code=403, detail="Farmer and admin accounts can't make donations.")

    farm = db.query(models.Farm).filter(models.Farm.id == data.farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    if not farm.stripe_account_id:
        raise HTTPException(status_code=409, detail="This farm is not yet set up to receive donations")

    application_fee_amount = (data.amount * PLATFORM_FEE_PERCENT) // 100

    # Created directly on the connected account (stripe_account = Stripe-Account header),
    # so the farm is the merchant of record; application_fee_amount skims our cut.
    session = stripe.checkout.Session.create(
        mode="payment",
        payment_method_types=["card"],
        line_items=[{
            "price_data": {
                "currency": CURRENCY,
                "unit_amount": data.amount,
                "product_data": {"name": f"Donation to {farm.name}"},
            },
            "quantity": 1,
        }],
        payment_intent_data={
            "application_fee_amount": application_fee_amount,
        },
        metadata={
            "farm_id": str(farm.id),
            "visitor_id": str(visitor.id) if visitor else "",
            "application_fee_amount": str(application_fee_amount),
        },
        success_url=f"{FRONTEND_URL}/donate/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{FRONTEND_URL}/donate/cancel",
        stripe_account=farm.stripe_account_id,
    )

    return {"checkout_url": session.url}


@router.get("/farms/me/donations", response_model=list[donation_schemas.FarmDonationResponse])
def get_my_farm_donations(
    farm: models.Farm = Depends(get_current_farmer_farm),
    db: Session = Depends(get_db),
):
    donations = (
        db.query(models.Donation)
        .filter(models.Donation.farm_id == farm.id)
        .order_by(models.Donation.created_at.desc())
        .all()
    )
    return [
        {
            "id": d.id,
            "amount_yen": d.amount,
            "donor_name": d.visitor_name,
            "donor_email": d.visitor_email,
            "created_at": d.created_at,
        }
        for d in donations
    ]


@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    if event["type"] == "checkout.session.completed":
        # .to_dict() first: this SDK version's StripeObject supports [] but not .get(),
        # including on nested objects like metadata.
        session = event["data"]["object"].to_dict()
        metadata = session.get("metadata") or {}

        already_recorded = db.query(models.Donation).filter(
            models.Donation.stripe_checkout_session_id == session["id"]
        ).first()
        if not already_recorded:
            visitor_id = int(metadata["visitor_id"]) if metadata.get("visitor_id") else None

            db.add(models.Donation(
                farm_id=int(metadata["farm_id"]),
                visitor_id=visitor_id,
                amount=session["amount_total"],
                application_fee_amount=int(metadata["application_fee_amount"]),
                currency=session["currency"],
                stripe_checkout_session_id=session["id"],
                stripe_payment_intent_id=session.get("payment_intent"),
            ))
            db.commit()

    elif event["type"] == "account.updated":
        account = event["data"]["object"].to_dict()
        farm = db.query(models.Farm).filter(models.Farm.stripe_account_id == account["id"]).first()
        if farm:
            farm.payouts_enabled = account.get("payouts_enabled", False)
            db.commit()

    return {"status": "ok"}
