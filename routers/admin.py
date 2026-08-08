from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

import models.models as models
from database import get_db
from core.auth import decode_token
import schemas.farms as farm_schemas
import schemas.horses as horse_schemas

router = APIRouter(prefix="/admin")

FARM_STATUSES = {"pending", "active", "rejected"}
HORSE_STATUSES = {"pending", "approved", "rejected"}


def _reason_missing(reason: Optional[str]) -> bool:
    return reason is None or not reason.strip()


def get_current_admin(email: str = Depends(decode_token), db: Session = Depends(get_db)) -> models.User:
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access this resource")
    return user


@router.get("/farms", response_model=list[farm_schemas.FarmResponse])
def get_admin_farms(
    status: Optional[str] = Query(None, description="Filter by status: pending | active | rejected"),
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(models.Farm)

    if status is not None:
        if status not in FARM_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{status}'. Must be one of {sorted(FARM_STATUSES)}",
            )
        query = query.filter(models.Farm.status == status)

    return query.all()


@router.patch("/farms/{farm_id}", response_model=farm_schemas.FarmResponse)
def update_farm_status(
    farm_id: int,
    data: farm_schemas.FarmModerationUpdate,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    farm = db.query(models.Farm).filter(models.Farm.id == farm_id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")

    if data.status == "rejected" and _reason_missing(data.reason):
        raise HTTPException(status_code=422, detail="A reason is required when rejecting a farm")

    farm.status = data.status
    farm.rejection_reason = data.reason if data.status == "rejected" else None

    db.commit()
    db.refresh(farm)
    return farm


@router.get("/horses", response_model=list[horse_schemas.HorseResponse])
def get_admin_horses(
    status: Optional[str] = Query(None, description="Filter by status: pending | approved | rejected"),
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    query = db.query(models.Horse)

    if status is not None:
        if status not in HORSE_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{status}'. Must be one of {sorted(HORSE_STATUSES)}",
            )
        query = query.filter(models.Horse.status == status)

    return query.all()


@router.patch("/horses/{horse_id}", response_model=horse_schemas.HorseResponse)
def update_horse_status(
    horse_id: int,
    data: horse_schemas.HorseModerationUpdate,
    current_user: models.User = Depends(get_current_admin),
    db: Session = Depends(get_db),
):
    horse = db.query(models.Horse).filter(models.Horse.id == horse_id).first()
    if not horse:
        raise HTTPException(status_code=404, detail="Horse not found")

    if data.status == "rejected" and _reason_missing(data.reason):
        raise HTTPException(status_code=422, detail="A reason is required when rejecting a horse")

    horse.status = data.status
    horse.rejection_reason = data.reason if data.status == "rejected" else None

    db.commit()
    db.refresh(horse)
    return horse
