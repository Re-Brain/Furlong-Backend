from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session
from datetime import date as date_cls, timedelta
from typing import Optional
import models.models as models
from database import get_db
from routers.auth import get_current_user
from routers.farms import get_current_farmer
from core.availability import default_horse_periods, DEFAULT_MIN_LEAD_DAYS
from core.rate_limit import enforce_loose_limit
from core import email
import schemas.bookings as booking_schemas

router = APIRouter()

BOOKING_STATUSES = {"pending", "confirmed", "declined", "cancelled"}


def _reason_missing(reason: Optional[str]) -> bool:
    return reason is None or not reason.strip()


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
    request: Request,
    data: booking_schemas.BookingCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    enforce_loose_limit(request, "bookings-create")

    # Locked for the rest of this transaction: the capacity check-and-insert
    # below must be atomic, so a second request for the same horse blocks here
    # until the first one commits (or rolls back), instead of both reading the
    # same "remaining capacity" and overbooking the slot.
    horse = (
        db.query(models.Horse)
        .filter(models.Horse.id == data.horse_id)
        .with_for_update()
        .first()
    )
    if not horse:
        raise HTTPException(status_code=404, detail="Horse not found")

    farm = horse.farm
    # Resolved availability (falls back to the default when the farm never configured it).
    availability = horse.farm_availability

    if not availability.get("enabled", False):
        raise HTTPException(status_code=409, detail="This farm is not accepting bookings")

    if data.date < date_cls.today():
        raise HTTPException(status_code=422, detail="Booking date cannot be in the past")

    min_lead_days = availability.get("min_lead_days", DEFAULT_MIN_LEAD_DAYS)
    if data.date < date_cls.today() + timedelta(days=min_lead_days):
        raise HTTPException(
            status_code=409,
            detail=f"This farm requires at least {min_lead_days} days' notice for bookings.",
        )

    # Python's weekday() is Monday=0..Sunday=6; the schedule uses 0=Sunday..6=Saturday.
    weekday = (data.date.weekday() + 1) % 7
    if weekday not in availability.get("weekdays", []):
        raise HTTPException(status_code=409, detail="The farm is closed on the selected day")

    period_cfg = availability.get("periods", {}).get(data.period)
    if not period_cfg or not period_cfg.get("open", False):
        raise HTTPException(status_code=409, detail=f"The {data.period} period is not open at this farm")

    horse_periods = horse.periods if horse.periods is not None else default_horse_periods()
    capacity = horse_periods.get(data.period, 0)
    if capacity <= 0:
        raise HTTPException(status_code=409, detail=f"This horse is not available in the {data.period} period")

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

    # Live bookings (pending or confirmed) still hold their spot; only
    # declined/cancelled bookings free up capacity. The horse row lock taken
    # above makes this sum-then-insert atomic against concurrent requests.
    existing_party_size = db.query(func.coalesce(func.sum(models.Booking.party_size), 0)).filter(
        models.Booking.horse_id == horse.id,
        models.Booking.date == data.date,
        models.Booking.period == data.period,
        models.Booking.status.in_(("pending", "confirmed")),
    ).scalar()
    if existing_party_size + data.party_size > capacity:
        raise HTTPException(status_code=409, detail="This slot is full.")

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
        status="confirmed",
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)
    email.send_booking_confirmed(booking)
    email.send_booking_confirmed_receipt(booking)
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
        is_visitor = booking.visitor_id == current_user.id
        is_farm_owner = booking.farm.owner_id == current_user.id
        if not is_visitor and not is_farm_owner:
            raise HTTPException(status_code=403, detail="You are not allowed to cancel this booking")

        # The visitor may cancel from pending or confirmed; the farm owner only from
        # confirmed (a pending booking should be declined, not cancelled, by the farm).
        allowed_statuses = set()
        if is_visitor:
            allowed_statuses.update({"pending", "confirmed"})
        if is_farm_owner:
            allowed_statuses.add("confirmed")

        if booking.status not in allowed_statuses:
            raise HTTPException(
                status_code=409,
                detail=f"A {booking.status} booking cannot be cancelled",
            )

        # A farm-owner-initiated cancellation must explain why; a visitor cancelling
        # their own booking doesn't need to. (If someone is somehow both the farm
        # owner and the visitor, that's treated as a visitor action, matching the
        # email branch below — reason stays optional.)
        is_farmer_action = is_farm_owner and not is_visitor
        if is_farmer_action and _reason_missing(data.reason):
            raise HTTPException(status_code=422, detail="A reason is required when the farm cancels a booking")

        booking.status = data.status
        booking.reason = data.reason
        db.commit()
        db.refresh(booking)
        if is_visitor:
            email.send_booking_cancelled_by_visitor(booking)
            email.send_booking_cancellation_receipt(booking)
        else:
            email.send_booking_cancelled_by_farmer(booking)
            email.send_booking_cancelled_by_farmer_receipt(booking)
    else:
        # confirmed / declined: only the farm owner may set these, and only from pending.
        if booking.farm.owner_id != current_user.id:
            raise HTTPException(status_code=403, detail="You can only manage bookings for your own farm")

        if booking.status != "pending":
            raise HTTPException(
                status_code=409,
                detail=f"A {booking.status} booking cannot be {data.status}",
            )

        if booking.date < date_cls.today():
            raise HTTPException(status_code=409, detail="This request's visit date has already passed.")

        if data.status == "declined" and _reason_missing(data.reason):
            raise HTTPException(status_code=422, detail="A reason is required when declining a booking")

        if data.status == "confirmed" and data.reason is not None:
            raise HTTPException(status_code=422, detail="A reason is not applicable when confirming a booking")

        booking.status = data.status
        booking.reason = data.reason
        db.commit()
        db.refresh(booking)
        if data.status == "confirmed":
            email.send_booking_confirmed(booking)
            email.send_booking_confirmed_receipt(booking)
        else:
            email.send_booking_declined(booking)
            email.send_booking_declined_receipt(booking)

    return booking
