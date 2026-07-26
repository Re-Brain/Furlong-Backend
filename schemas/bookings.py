from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import date, datetime


class BookingCreate(BaseModel):
    horse_id: int
    date: date                                        # ISO "YYYY-MM-DD"
    period: Literal["morning", "afternoon", "evening"]
    party_size: int = Field(ge=1)                     # >= 1 (422 otherwise)
    note: Optional[str] = ""                          # may be "" or omitted


class BookingUpdate(BaseModel):
    status: Literal["confirmed", "declined", "cancelled"]


class BookingResponse(BaseModel):
    id: int
    horse_id: int
    horse_name: Optional[str] = None
    farm_id: int
    farm_name: Optional[str] = None
    visitor_id: int
    visitor_name: Optional[str] = None
    visitor_email: Optional[str] = None
    date: date
    period: str
    start: str                                        # resolved from farm schedule
    end: str                                          # resolved from farm schedule
    party_size: int
    note: Optional[str] = None
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
