from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from datetime import date as date_cls
from typing import Optional
import models.models as models
from database import get_db
from routers.auth import get_current_user
from routers.farms import get_current_farmer
from core.availability import default_horse_periods
import schemas.bookings as booking_schemas

router = APIRouter()

BOOKING_STATUSES = {"pending", "confirmed", "declined", "cancelled"}


def get_current_farmer_farm(
    current_user: models.User = Depends(get_current_farmer),
    db: Session = Depends(get_db),
) -> models.Farm:
    farm = db.query(models.Farm).filter(models.Farm.owner_id == current_user.id).first()
    if not farm:
        raise HTTPException(status_code=404, detail="Farm not found")
    return farm


@router.get("/bookings/me", response_model=list[booking_schemas.BookingResponse])
def get_my_bookings(
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(models.Booking)
        .filter(models.Booking.visitor_id == current_user.id)
        .order_by(models.Booking.created_at.desc())
        .all()
    )


@router.get("/farms/me/bookings", response_model=list[booking_schemas.BookingResponse])
def get_farm_bookings(
    status: Optional[str] = Query(None, description="Filter by status: pending | confirmed | declined | cancelled"),
    farm: models.Farm = Depends(get_current_farmer_farm),
    db: Session = Depends(get_db),
):
    query = db.query(models.Booking).filter(models.Booking.farm_id == farm.id)

    if status is not None:
        if status not in BOOKING_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status '{status}'. Must be one of {sorted(BOOKING_STATUSES)}",
            )
        query = query.filter(models.Booking.status == status)

    # Soonest visit first, then by start time within the day.
    return query.order_by(models.Booking.date.asc(), models.Booking.start.asc()).all()


@router.post("/bookings", response_model=booking_schemas.BookingResponse, status_code=201)
def create_booking(
    data: booking_schemas.BookingCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    horse = db.query(models.Horse).filter(models.Horse.id == data.horse_id).first()
    if not horse:
        raise HTTPException(status_code=404, detail="Horse not found")

    farm = horse.farm
    # Resolved availability (falls back to the default when the farm never configured it).
    availability = horse.farm_availability

    if not availability.get("enabled", False):
        raise HTTPException(status_code=409, detail="This farm is not accepting bookings")

    if data.date < date_cls.today():
        raise HTTPException(status_code=422, detail="Booking date cannot be in the past")

    # Python's weekday() is Monday=0..Sunday=6; the schedule uses 0=Sunday..6=Saturday.
    weekday = (data.date.weekday() + 1) % 7
    if weekday not in availability.get("weekdays", []):
        raise HTTPException(status_code=409, detail="The farm is closed on the selected day")

    period_cfg = availability.get("periods", {}).get(data.period)
    if not period_cfg or not period_cfg.get("open", False):
        raise HTTPException(status_code=409, detail=f"The {data.period} period is not open at this farm")

    horse_periods = horse.periods if horse.periods is not None else default_horse_periods()
    if data.period not in horse_periods:
        raise HTTPException(status_code=409, detail=f"This horse is not available in the {data.period} period")

    if farm.capacity is not None and data.party_size > farm.capacity:
        raise HTTPException(status_code=422, detail=f"Party size exceeds the farm capacity of {farm.capacity}")

    # Reject an exact duplicate so a double-submit doesn't create two rows.
    duplicate = db.query(models.Booking).filter(
        models.Booking.visitor_id == current_user.id,
        models.Booking.horse_id == data.horse_id,
        models.Booking.date == data.date,
        models.Booking.period == data.period,
        models.Booking.status.in_(("pending", "confirmed")),
    ).first()
    if duplicate:
        raise HTTPException(
            status_code=409,
            detail="You already have a booking for this horse on this date and period",
        )

    booking = models.Booking(
        horse_id=horse.id,
        farm_id=horse.farm_id,
        visitor_id=current_user.id,
        date=data.date,
        period=data.period,
        # Snapshot the authoritative times from the schedule — never trust the client.
        start=period_cfg["start"],
        end=period_cfg["end"],
        party_size=data.party_size,
        note=data.note or "",
        status="pending",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    return booking


@router.patch("/bookings/{booking_id}", response_model=booking_schemas.BookingResponse)
def update_booking(
    booking_id: int,
    data: booking_schemas.BookingUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    booking = db.query(models.Booking).filter(models.Booking.id == booking_id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    if data.status == "cancelled":
        if booking.visitor_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only cancel your own booking")

        if booking.status not in ("pending", "confirmed"):
            raise HTTPException(
                status_code=409,
                detail=f"A {booking.status} booking cannot be cancelled",
            )
    else:
        # confirmed / declined: only the farm owner may set these, and only from pending.
        if booking.farm.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only manage bookings for your own farm")

        if booking.status != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"A {booking.status} booking cannot be {data.status}",
            )

    booking.status = data.status
    db.commit()
    db.refresh(booking)
    return booking
