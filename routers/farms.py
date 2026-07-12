from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy import func
from sqlalchemy.orm import Session
import models.models as models
from database import get_db
from core.auth import decode_token
from core.cloudinary import upload_image, delete_image
import schemas.farms as farm_schemas

router = APIRouter()


def get_current_farmer(email: str = Depends(decode_token), db: Session = Depends(get_db)) -> models.User:
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != "farmer":
        raise HTTPException(status_code=403, detail="Only farmers can access this resource")
    return user


@router.get("/farms/me", response_model=farm_schemas.FarmResponse)
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

    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(farm, field, value)

    farm.status = "active" if all([farm.location, farm.description, farm.capacity]) else "pending"

    db.commit()
    db.refresh(farm)
    return farm


@router.post("/farms/me/image", response_model=farm_schemas.FarmResponse)
def upload_farm_image(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_farmer),
    db: Session = Depends(get_db),
):
    farm = db.query(models.Farm).filter(models.Farm.owner_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
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


@router.get("/farms", response_model=list[farm_schemas.FarmResponse])
def get_all_farms(db: Session = Depends(get_db)):
    return db.query(models.Farm).filter(models.Farm.status == "active").all()


@router.get("/farms/{farm_id}", response_model=farm_schemas.FarmResponse)
def get_farm(farm_id: int, db: Session = Depends(get_db)):
    farm = db.query(models.Farm).filter(models.Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    return farm
