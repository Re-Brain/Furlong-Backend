from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile, File
from sqlalchemy import func
from sqlalchemy.orm import Session
import models.models as models
from database import get_db
from routers.farms import get_current_farmer
from core.cloudinary import upload_image, delete_image
import schemas.horses as horse_schemas

router = APIRouter()


def get_farmer_farm(current_user: models.User = Depends(get_current_farmer), db: Session = Depends(get_db)) -> models.Farm:
    farm = db.query(models.Farm).filter(models.Farm.owner_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    return farm


@router.get("/horses", response_model=list[horse_schemas.HorseResponse])
def get_all_horses(db: Session = Depends(get_db)):
    return db.query(models.Horse).all()


@router.get("/horses/me", response_model=list[horse_schemas.HorseResponse])
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


@router.get("/horses/{horse_id}", response_model=horse_schemas.HorseResponse)
def get_horse(horse_id: int, db: Session = Depends(get_db)):
    horse = db.query(models.Horse).filter(models.Horse.id == horse_id).first()
    if not horse:
        raise HTTPException(status_code=404, detail="Horse not found")
    return horse


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

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(horse, field, value)

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

    existing_ids = {img.id for img in horse.images}
    if set(data.image_ids) != existing_ids or len(data.image_ids) != len(existing_ids):
        raise HTTPException(status_code=400, detail="Provided image IDs must exactly match this horse's images")

    image_map = {img.id: img for img in horse.images}
    for position, image_id in enumerate(data.image_ids):
        image_map[image_id].position = position

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

    db.delete(horse)
    db.commit()
    return Response(status_code=204)
