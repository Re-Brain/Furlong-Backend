from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File, Form
from jose import JWTError, jwt
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import Literal, Optional
import models.models as models
from database import get_db
from core.auth import SECRET_KEY, ALGORITHM
from routers.farms import get_current_farmer
from core.cloudinary import upload_image, delete_image, upload_document, delete_document
from core import email
import schemas.horses as horse_schemas

router = APIRouter()


def get_farmer_farm(current_user: models.User = Depends(get_current_farmer), db: Session = Depends(get_db)) -> models.Farm:
    farm = db.query(models.Farm).filter(models.Farm.owner_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    if farm.status != "active":
        raise HTTPException(status_code=403, detail="Your farm must be approved before you can manage horses")
    return farm


def _assert_editable(horse: models.Horse) -> None:
    if horse.status == "pending":
        raise HTTPException(
            status_code=409,
            detail="This horse is pending review and cannot be edited until a decision is made",
        )


def get_optional_user(request: Request, db: Session = Depends(get_db)) -> Optional[models.User]:
    """Like decode_token -> get_current_user, but the caller need not be logged in."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return None
    try:
        payload = jwt.decode(auth_header.split(" ", 1)[1], SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None
    email = payload.get("sub")
    return db.query(models.User).filter(models.User.email == email).first() if email else None


@router.get("/horses", response_model=list[horse_schemas.HorseResponse])
def get_all_horses(db: Session = Depends(get_db)):
    return db.query(models.Horse).filter(models.Horse.status == "approved").all()


@router.get("/horses/me", response_model=list[horse_schemas.HorseWithDocumentsResponse])
def get_my_horses(farm: models.Farm = Depends(get_farmer_farm), db: Session = Depends(get_db)):
    return db.query(models.Horse).filter(models.Horse.farm_id == farm.id).all()


@router.post("/horses", response_model=horse_schemas.HorseResponse, status_code=201)
def create_horse(
    data: horse_schemas.HorseCreate,
    farm: models.Farm = Depends(get_farmer_farm),
    db: Session = Depends(get_db),
):
    horse = models.Horse(**data.model_dump(), farm_id=farm.id)
    db.add(horse)
    db.commit()
    db.refresh(horse)
    return horse


@router.post("/horses/{horse_id}/submit", response_model=horse_schemas.HorseWithDocumentsResponse)
def submit_horse(
    horse_id: int,
    farm: models.Farm = Depends(get_farmer_farm),
    db: Session = Depends(get_db),
):
    horse = db.query(models.Horse).filter(models.Horse.id == horse_id).first()
    if not horse:
        raise HTTPException(status_code=404, detail="Horse not found")
    if horse.farm_id != farm.id:
        raise HTTPException(status_code=403, detail="You do not own this horse")

    if horse.status not in ("draft", "rejected"):
        raise HTTPException(status_code=409, detail=f"A {horse.status} horse cannot be submitted")

    missing_fields = [
        field for field in horse_schemas.REQUIRED_FIELDS
        if not str(getattr(horse, field) or "").strip()
    ]
    if not horse.images:
        missing_fields.append("images")
    if not horse.race_records:
        missing_fields.append("race_records")
    if missing_fields:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required fields: {', '.join(missing_fields)}",
        )

    missing_documents = horse_schemas.DOCUMENT_TYPES - {doc.document_type for doc in horse.documents}
    if missing_documents:
        raise HTTPException(
            status_code=422,
            detail=f"Missing required documents: {', '.join(sorted(missing_documents))}",
        )

    was_resubmission = horse.status == "rejected"
    horse.status = "pending"
    horse.rejection_reason = None
    db.commit()
    db.refresh(horse)

    admin_emails = [row[0] for row in db.query(models.User.email).filter(models.User.role == "admin").all()]
    if was_resubmission:
        for admin_email in admin_emails:
            email.send_horse_resubmitted_for_review(horse, admin_email)
        email.send_horse_resubmission_receipt(horse)
    else:
        for admin_email in admin_emails:
            email.send_horse_submitted_for_review(horse, admin_email)
        email.send_horse_submission_receipt(horse)

    return horse


@router.get("/horses/{horse_id}")
def get_horse(
    horse_id: int,
    user: Optional[models.User] = Depends(get_optional_user),
    db: Session = Depends(get_db),
):
    horse = db.query(models.Horse).filter(models.Horse.id == horse_id).first()
    if not horse:
        raise HTTPException(status_code=404, detail="Horse not found")

    is_owner = user is not None and user.role == "farmer" and horse.farm.owner_id == user.id
    is_admin = user is not None and user.role == "admin"

    if is_owner or is_admin:
        return horse_schemas.HorseWithDocumentsResponse.model_validate(horse)

    if horse.status != "approved":
        raise HTTPException(status_code=404, detail="Horse not found")
    return horse_schemas.HorseResponse.model_validate(horse)


@router.patch("/horses/{horse_id}", response_model=horse_schemas.HorseResponse)
def update_horse(
    horse_id: int,
    data: horse_schemas.HorseUpdate,
    farm: models.Farm = Depends(get_farmer_farm),
    db: Session = Depends(get_db),
):
    horse = db.query(models.Horse).filter(models.Horse.id == horse_id).first()
    if not horse:
        raise HTTPException(status_code=404, detail="Horse not found")
    if horse.farm_id != farm.id:
        raise HTTPException(status_code=403, detail="You do not own this horse")
    _assert_editable(horse)

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(horse, field, value)

    db.commit()
    db.refresh(horse)
    return horse


@router.put("/horses/{horse_id}/periods", response_model=horse_schemas.HorseResponse)
def update_horse_periods(
    horse_id: int,
    data: horse_schemas.HorsePeriodsUpdate,
    farm: models.Farm = Depends(get_farmer_farm),
    db: Session = Depends(get_db),
):
    horse = db.query(models.Horse).filter(models.Horse.id == horse_id).first()
    if not horse:
        raise HTTPException(status_code=404, detail="Horse not found")
    if horse.farm_id != farm.id:
        raise HTTPException(status_code=403, detail="You do not own this horse")
    _assert_editable(horse)

    # Already validated and normalized to canonical order by the schema.
    horse.periods = data.periods
    db.commit()
    db.refresh(horse)
    return horse


@router.post("/horses/{horse_id}/image", response_model=horse_schemas.HorseResponse)
def upload_horse_image(
    horse_id: int,
    file: UploadFile = File(...),
    farm: models.Farm = Depends(get_farmer_farm),
    db: Session = Depends(get_db),
):
    horse = db.query(models.Horse).filter(models.Horse.id == horse_id).first()
    if not horse:
        raise HTTPException(status_code=404, detail="Horse not found")
    if horse.farm_id != farm.id:
        raise HTTPException(status_code=403, detail="You do not own this horse")
    _assert_editable(horse)
    if len(horse.images) >= 3:
        raise HTTPException(status_code=400, detail="Maximum of 3 images allowed per horse")

    max_pos = db.query(func.max(models.HorseImage.position)).filter(
        models.HorseImage.horse_id == horse_id
    ).scalar()
    next_position = (max_pos + 1) if max_pos is not None else 0

    result = upload_image(file.file.read(), folder="horses")
    new_image = models.HorseImage(
        image_url=result["secure_url"],
        image_public_id=result["public_id"],
        horse_id=horse.id,
        position=next_position,
    )
    db.add(new_image)
    db.commit()
    db.refresh(horse)
    return horse


@router.delete("/horses/{horse_id}/image/{image_id}", response_model=horse_schemas.HorseResponse)
def delete_horse_image(
    horse_id: int,
    image_id: int,
    farm: models.Farm = Depends(get_farmer_farm),
    db: Session = Depends(get_db),
):
    horse = db.query(models.Horse).filter(models.Horse.id == horse_id).first()
    if not horse:
        raise HTTPException(status_code=404, detail="Horse not found")
    if horse.farm_id != farm.id:
        raise HTTPException(status_code=403, detail="You do not own this horse")
    _assert_editable(horse)

    image = db.query(models.HorseImage).filter(
        models.HorseImage.id == image_id,
        models.HorseImage.horse_id == horse_id,
    ).first()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")

    delete_image(image.image_public_id)
    db.delete(image)
    db.flush()

    remaining = db.query(models.HorseImage).filter(
        models.HorseImage.horse_id == horse_id
    ).order_by(models.HorseImage.position).all()
    for i, img in enumerate(remaining):
        img.position = i

    db.commit()
    db.refresh(horse)
    return horse


@router.patch("/horses/{horse_id}/images/order", response_model=horse_schemas.HorseResponse)
def reorder_horse_images(
    horse_id: int,
    data: horse_schemas.ImageReorderRequest,
    farm: models.Farm = Depends(get_farmer_farm),
    db: Session = Depends(get_db),
):
    horse = db.query(models.Horse).filter(models.Horse.id == horse_id).first()
    if not horse:
        raise HTTPException(status_code=404, detail="Horse not found")
    if horse.farm_id != farm.id:
        raise HTTPException(status_code=403, detail="You do not own this horse")
    _assert_editable(horse)

    existing_ids = {img.id for img in horse.images}
    if set(data.image_ids) != existing_ids or len(data.image_ids) != len(existing_ids):
        raise HTTPException(status_code=400, detail="Provided image IDs must exactly match this horse's images")

    image_map = {img.id: img for img in horse.images}
    for position, image_id in enumerate(data.image_ids):
        image_map[image_id].position = position

    db.commit()
    db.refresh(horse)
    return horse


@router.post("/horses/{horse_id}/documents", response_model=horse_schemas.HorseWithDocumentsResponse)
def upload_horse_document(
    horse_id: int,
    document_type: Literal["passport", "registration", "ownership_transfer"] = Form(...),
    file: UploadFile = File(...),
    farm: models.Farm = Depends(get_farmer_farm),
    db: Session = Depends(get_db),
):
    horse = db.query(models.Horse).filter(models.Horse.id == horse_id).first()
    if not horse:
        raise HTTPException(status_code=404, detail="Horse not found")
    if horse.farm_id != farm.id:
        raise HTTPException(status_code=403, detail="You do not own this horse")
    _assert_editable(horse)

    result = upload_document(file.file.read())
    new_document = models.HorseDocument(
        document_type=document_type,
        file_url=result["secure_url"],
        public_id=result["public_id"],
        resource_type=result["resource_type"],
        original_filename=file.filename,
        horse_id=horse.id,
    )
    db.add(new_document)
    # Changing the proof-of-ownership documents on an already-approved horse
    # invalidates that approval — send it back for re-review if it's still
    # complete, or back to draft (editable) if this change left it short of
    # the 3 required types, so it's never incomplete AND locked at once.
    if horse.status == "approved":
        db.flush()
        uploaded_types = {
            row[0] for row in
            db.query(models.HorseDocument.document_type).filter(models.HorseDocument.horse_id == horse.id).all()
        }
        horse.status = "pending" if horse_schemas.DOCUMENT_TYPES <= uploaded_types else "draft"
    db.commit()
    db.refresh(horse)
    return horse


@router.delete("/horses/{horse_id}/documents/{document_id}", response_model=horse_schemas.HorseWithDocumentsResponse)
def delete_horse_document(
    horse_id: int,
    document_id: int,
    farm: models.Farm = Depends(get_farmer_farm),
    db: Session = Depends(get_db),
):
    horse = db.query(models.Horse).filter(models.Horse.id == horse_id).first()
    if not horse:
        raise HTTPException(status_code=404, detail="Horse not found")
    if horse.farm_id != farm.id:
        raise HTTPException(status_code=403, detail="You do not own this horse")
    _assert_editable(horse)

    document = db.query(models.HorseDocument).filter(
        models.HorseDocument.id == document_id,
        models.HorseDocument.horse_id == horse_id,
    ).first()
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    delete_document(document.public_id, document.resource_type)
    db.delete(document)
    # Removing a document from an already-approved horse invalidates that
    # approval. If the horse is still complete without it, send it back for
    # re-review ("pending"); otherwise it needs more work first ("draft") —
    # never incomplete AND locked at the same time.
    if horse.status == "approved":
        db.flush()
        uploaded_types = {
            row[0] for row in
            db.query(models.HorseDocument.document_type).filter(models.HorseDocument.horse_id == horse.id).all()
        }
        horse.status = "pending" if horse_schemas.DOCUMENT_TYPES <= uploaded_types else "draft"
    db.commit()
    db.refresh(horse)
    return horse


@router.post("/horses/{horse_id}/race-records", response_model=horse_schemas.HorseResponse, status_code=201)
def create_race_record(
    horse_id: int,
    data: horse_schemas.RaceRecordCreate,
    farm: models.Farm = Depends(get_farmer_farm),
    db: Session = Depends(get_db),
):
    horse = db.query(models.Horse).filter(models.Horse.id == horse_id).first()
    if not horse:
        raise HTTPException(status_code=404, detail="Horse not found")
    if horse.farm_id != farm.id:
        raise HTTPException(status_code=403, detail="You do not own this horse")
    _assert_editable(horse)

    record = models.RaceRecord(**data.model_dump(), horse_id=horse.id)
    db.add(record)
    db.commit()
    db.refresh(horse)
    return horse


@router.patch("/horses/{horse_id}/race-records/{record_id}", response_model=horse_schemas.RaceRecordResponse)
def update_race_record(
    horse_id: int,
    record_id: int,
    data: horse_schemas.RaceRecordUpdate,
    farm: models.Farm = Depends(get_farmer_farm),
    db: Session = Depends(get_db),
):
    horse = db.query(models.Horse).filter(models.Horse.id == horse_id).first()
    if not horse:
        raise HTTPException(status_code=404, detail="Horse not found")
    if horse.farm_id != farm.id:
        raise HTTPException(status_code=403, detail="You do not own this horse")
    _assert_editable(horse)

    record = db.query(models.RaceRecord).filter(
        models.RaceRecord.id == record_id,
        models.RaceRecord.horse_id == horse_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Race record not found")

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(record, field, value)

    db.commit()
    db.refresh(record)
    return record


@router.delete("/horses/{horse_id}/race-records/{record_id}", response_model=horse_schemas.HorseResponse)
def delete_race_record(
    horse_id: int,
    record_id: int,
    farm: models.Farm = Depends(get_farmer_farm),
    db: Session = Depends(get_db),
):
    horse = db.query(models.Horse).filter(models.Horse.id == horse_id).first()
    if not horse:
        raise HTTPException(status_code=404, detail="Horse not found")
    if horse.farm_id != farm.id:
        raise HTTPException(status_code=403, detail="You do not own this horse")
    _assert_editable(horse)

    record = db.query(models.RaceRecord).filter(
        models.RaceRecord.id == record_id,
        models.RaceRecord.horse_id == horse_id,
    ).first()
    if not record:
        raise HTTPException(status_code=404, detail="Race record not found")

    db.delete(record)
    db.commit()
    db.refresh(horse)
    return horse


@router.delete("/horses/{horse_id}", status_code=204)
def delete_horse(
    horse_id: int,
    farm: models.Farm = Depends(get_farmer_farm),
    db: Session = Depends(get_db),
):
    horse = db.query(models.Horse).filter(models.Horse.id == horse_id).first()
    if not horse:
        raise HTTPException(status_code=404, detail="Horse not found")
    if horse.farm_id != farm.id:
        raise HTTPException(status_code=403, detail="You do not own this horse")

    for image in horse.images:
        delete_image(image.image_public_id)

    db.delete(horse)
    db.commit()
    return Response(status_code=204)
