from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Literal
import stripe
import models.models as models
from database import get_db
from core.auth import decode_token
from core.cloudinary import upload_image, delete_image, upload_document, delete_document
from core.availability import default_farm_availability
from core.stripe_client import FRONTEND_URL
from core import email
import schemas.farms as farm_schemas

router = APIRouter()


def get_current_farmer(email: str = Depends(decode_token), db: Session = Depends(get_db)) -> models.User:
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != "farmer":
        raise HTTPException(status_code=403, detail="Only farmers can access this resource")
    return user


def _assert_editable(farm: models.Farm) -> None:
    if farm.status == "pending":
        raise HTTPException(
            status_code=409,
            detail="This farm is pending review and cannot be edited until a decision is made",
        )


@router.get("/farms/me", response_model=farm_schemas.FarmWithDocumentsResponse)
def get_my_farm(current_user: models.User = Depends(get_current_farmer), db: Session = Depends(get_db)):
    farm = db.query(models.Farm).filter(models.Farm.owner_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    return farm


@router.patch("/farms/me", response_model=farm_schemas.FarmResponse)
def update_my_farm(
    data: farm_schemas.FarmUpdate,
    current_user: models.User = Depends(get_current_farmer),
    db: Session = Depends(get_db),
):
    farm = db.query(models.Farm).filter(models.Farm.owner_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    _assert_editable(farm)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(farm, field, value)

    db.commit()
    db.refresh(farm)
    return farm


@router.post("/farms/me/submit", response_model=farm_schemas.FarmWithDocumentsResponse)
def submit_farm(
    current_user: models.User = Depends(get_current_farmer),
    db: Session = Depends(get_db),
):
    farm = db.query(models.Farm).filter(models.Farm.owner_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    if farm.status not in ("draft", "rejected"):
        raise HTTPException(status_code=409, detail=f"A {farm.status} farm cannot be submitted")

    missing_fields = [
        field for field in farm_schemas.REQUIRED_FIELDS
        if not str(getattr(farm, field) or "").strip()
    ]
    if missing_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required fields: {', '.join(missing_fields)}",
        )

    if not farm.images:
        raise HTTPException(status_code=400, detail="At least one farm photo is required")

    missing_documents = farm_schemas.DOCUMENT_TYPES - {doc.document_type for doc in farm.documents}
    if missing_documents:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required documents: {', '.join(sorted(missing_documents))}",
        )

    was_resubmission = farm.status == "rejected"
    farm.status = "pending"
    farm.rejection_reason = None
    db.commit()
    db.refresh(farm)

    admin_emails = [row[0] for row in db.query(models.User.email).filter(models.User.role == "admin").all()]
    if was_resubmission:
        for admin_email in admin_emails:
            email.send_farm_resubmitted_for_review(farm, admin_email)
        email.send_farm_resubmission_receipt(farm)
    else:
        for admin_email in admin_emails:
            email.send_farm_submitted_for_review(farm, admin_email)
        email.send_farm_submission_receipt(farm)

    return farm


@router.get("/farms/me/availability", response_model=farm_schemas.FarmAvailability)
def get_my_farm_availability(
    current_user: models.User = Depends(get_current_farmer),
    db: Session = Depends(get_db),
):
    farm = db.query(models.Farm).filter(models.Farm.owner_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    # Never configured -> return the default (do not 404).
    return farm.availability if farm.availability is not None else default_farm_availability()


@router.put("/farms/me/availability", response_model=farm_schemas.FarmAvailability)
def update_my_farm_availability(
    data: farm_schemas.FarmAvailability,
    current_user: models.User = Depends(get_current_farmer),
    db: Session = Depends(get_db),
):
    farm = db.query(models.Farm).filter(models.Farm.owner_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    farm.availability = data.model_dump()
    db.commit()
    db.refresh(farm)
    return farm.availability


@router.get("/farms/me/stripe/status", response_model=farm_schemas.StripeStatusResponse)
def get_my_farm_stripe_status(
    current_user: models.User = Depends(get_current_farmer),
    db: Session = Depends(get_db),
):
    farm = db.query(models.Farm).filter(models.Farm.owner_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    return {
        "connected": farm.stripe_account_id is not None,
        "payouts_enabled": farm.payouts_enabled,
    }


@router.post("/farms/me/stripe/onboard", response_model=farm_schemas.StripeOnboardResponse)
def onboard_my_farm_stripe(
    current_user: models.User = Depends(get_current_farmer),
    db: Session = Depends(get_db),
):
    farm = db.query(models.Farm).filter(models.Farm.owner_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    if farm.status != "active":
        raise HTTPException(status_code=403, detail="Your farm must be approved before you can set up payouts")

    if not farm.stripe_account_id:
        # Express dashboards require the platform to be loss-liable (Stripe: "the Connect
        # application must control losses"), which Thailand-registered platforms are blocked
        # from doing. "full" is the dashboard type that stays self-liable (farm's own account
        # bears its own losses) while still giving the farmer real Stripe Dashboard access.
        account = stripe.Account.create(
            country="TH",
            controller={
                "fees": {"payer": "account"},
                "losses": {"payments": "stripe"},
                "stripe_dashboard": {"type": "full"},
            },
            capabilities={
                "card_payments": {"requested": True},
                "promptpay_payments": {"requested": True},
                "transfers": {"requested": True},
            },
        )
        farm.stripe_account_id = account.id
        db.commit()
        db.refresh(farm)

    account_link = stripe.AccountLink.create(
        account=farm.stripe_account_id,
        refresh_url=f"{FRONTEND_URL}/farm/stripe/refresh",
        return_url=f"{FRONTEND_URL}/farm/stripe/return",
        type="account_onboarding",
    )

    return {"onboarding_url": account_link.url}


@router.post("/farms/me/image", response_model=farm_schemas.FarmResponse)
def upload_farm_image(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_farmer),
    db: Session = Depends(get_db),
):
    farm = db.query(models.Farm).filter(models.Farm.owner_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    _assert_editable(farm)
    if len(farm.images) >= 3:
        raise HTTPException(status_code=400, detail="Maximum of 3 images allowed per farm")

    max_pos = db.query(func.max(models.FarmImage.position)).filter(
        models.FarmImage.farm_id == farm.id
    ).scalar()
    next_position = (max_pos + 1) if max_pos is not None else 0

    result = upload_image(file.file.read(), folder="farms")
    new_image = models.FarmImage(
        image_url=result["secure_url"],
        image_public_id=result["public_id"],
        farm_id=farm.id,
        position=next_position,
    )
    db.add(new_image)
    db.commit()
    db.refresh(farm)
    return farm


@router.delete("/farms/me/image/{image_id}", response_model=farm_schemas.FarmResponse)
def delete_farm_image(
    image_id: int,
    current_user: models.User = Depends(get_current_farmer),
    db: Session = Depends(get_db),
):
    farm = db.query(models.Farm).filter(models.Farm.owner_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    _assert_editable(farm)

    image = db.query(models.FarmImage).filter(
        models.FarmImage.id == image_id,
        models.FarmImage.farm_id == farm.id,
    ).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    delete_image(image.image_public_id)
    db.delete(image)
    db.flush()

    remaining = db.query(models.FarmImage).filter(
        models.FarmImage.farm_id == farm.id
    ).order_by(models.FarmImage.position).all()
    for i, img in enumerate(remaining):
        img.position = i

    db.commit()
    db.refresh(farm)
    return farm


@router.patch("/farms/me/images/order", response_model=farm_schemas.FarmResponse)
def reorder_farm_images(
    data: farm_schemas.ImageReorderRequest,
    current_user: models.User = Depends(get_current_farmer),
    db: Session = Depends(get_db),
):
    farm = db.query(models.Farm).filter(models.Farm.owner_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    existing_ids = {img.id for img in farm.images}
    if set(data.image_ids) != existing_ids or len(data.image_ids) != len(existing_ids):
        raise HTTPException(status_code=400, detail="Provided image IDs must exactly match this farm's images")

    image_map = {img.id: img for img in farm.images}
    for position, image_id in enumerate(data.image_ids):
        image_map[image_id].position = position

    db.commit()
    db.refresh(farm)
    return farm


@router.post("/farms/me/documents", response_model=farm_schemas.FarmWithDocumentsResponse)
def upload_farm_document(
    document_type: Literal["business_registration", "insurance", "facility_license"] = Form(...),
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_farmer),
    db: Session = Depends(get_db),
):
    farm = db.query(models.Farm).filter(models.Farm.owner_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    _assert_editable(farm)

    result = upload_document(file.file.read(), folder="farm_documents")
    new_document = models.FarmDocument(
        document_type=document_type,
        file_url=result["secure_url"],
        public_id=result["public_id"],
        resource_type=result["resource_type"],
        original_filename=file.filename,
        farm_id=farm.id,
    )
    db.add(new_document)
    db.commit()
    db.refresh(farm)
    return farm


@router.delete("/farms/me/documents/{document_id}", response_model=farm_schemas.FarmWithDocumentsResponse)
def delete_farm_document(
    document_id: int,
    current_user: models.User = Depends(get_current_farmer),
    db: Session = Depends(get_db),
):
    farm = db.query(models.Farm).filter(models.Farm.owner_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    _assert_editable(farm)

    document = db.query(models.FarmDocument).filter(
        models.FarmDocument.id == document_id,
        models.FarmDocument.farm_id == farm.id,
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    delete_document(document.public_id, document.resource_type)
    db.delete(document)
    db.commit()
    db.refresh(farm)
    return farm


@router.get("/farms", response_model=list[farm_schemas.FarmResponse])
def get_all_farms(db: Session = Depends(get_db)):
    return db.query(models.Farm).filter(models.Farm.status == "active").all()


@router.get("/farms/{farm_id}", response_model=farm_schemas.FarmResponse)
def get_farm(farm_id: int, db: Session = Depends(get_db)):
    farm = db.query(models.Farm).filter(models.Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    return farm
