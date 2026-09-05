from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Literal
from datetime import date, datetime

from core.availability import default_horse_periods
from schemas.farms import FarmAvailability

DOCUMENT_TYPES = {"passport", "registration", "ownership_transfer"}

# Fields a horse must have filled in before it can be submitted for review.
# "name" is excluded — a blank/placeholder name isn't caught here since a farmer
# who never renamed a freshly-created draft still has a non-empty `name` column
# (see create_horse's placeholder fallback). Mirrors the frontend's own
# submit-button validation.
REQUIRED_FIELDS = [
    "color", "gender", "date_of_birth",
    "sire", "dam", "sires_sire", "sires_dam", "dams_sire", "dams_dam",
]


class HorseCreate(BaseModel):
    # Optional so a draft can be created the instant a farmer starts adding a
    # horse, before they've typed anything -- create_horse fills in a
    # placeholder when this is left blank.
    name: Optional[str] = None
    story: Optional[str] = None
    date_of_birth: Optional[date] = None
    color: Optional[str] = None
    gender: Optional[str] = None
    sire: Optional[str] = None
    dam: Optional[str] = None
    sires_sire: Optional[str] = None
    sires_dam: Optional[str] = None
    dams_sire: Optional[str] = None
    dams_dam: Optional[str] = None


class HorseUpdate(BaseModel):
    name: Optional[str] = None
    story: Optional[str] = None
    date_of_birth: Optional[date] = None
    color: Optional[str] = None
    gender: Optional[str] = None
    sire: Optional[str] = None
    dam: Optional[str] = None
    sires_sire: Optional[str] = None
    sires_dam: Optional[str] = None
    dams_sire: Optional[str] = None
    dams_dam: Optional[str] = None


class RaceRecordCreate(BaseModel):
    race_date: date
    course: str
    race_name: str
    grade: Optional[str] = None
    finish_position: Optional[int] = None
    track: Optional[str] = None
    distance: Optional[int] = None
    condition: Optional[str] = None


class RaceRecordUpdate(BaseModel):
    race_date: Optional[date] = None
    course: Optional[str] = None
    race_name: Optional[str] = None
    grade: Optional[str] = None
    finish_position: Optional[int] = None
    track: Optional[str] = None
    distance: Optional[int] = None
    condition: Optional[str] = None


class RaceRecordResponse(BaseModel):
    id: int
    race_date: date
    course: str
    race_name: str
    grade: Optional[str] = None
    finish_position: Optional[int] = None
    track: Optional[str] = None
    distance: Optional[int] = None
    condition: Optional[str] = None
    horse_id: int

    class Config:
        from_attributes = True


class HorseImageResponse(BaseModel):
    id: int
    image_url: str
    position: int

    class Config:
        from_attributes = True


class ImageReorderRequest(BaseModel):
    image_ids: List[int]


class HorseDocumentResponse(BaseModel):
    id: int
    document_type: str
    file_url: str
    original_filename: Optional[str] = None
    uploaded_at: datetime

    class Config:
        from_attributes = True


class HorseModerationUpdate(BaseModel):
    status: Literal["approved", "rejected"]
    # Required when status == "rejected", validated in the route (same
    # pattern as PATCH /bookings/{id} for confirmed/declined).
    reason: Optional[str] = None


class HorsePeriodsCapacity(BaseModel):
    # Always exactly these three keys. Value = max visitors allowed in that
    # period; 0 means the horse isn't offered in that period.
    morning: int = Field(ge=0)
    afternoon: int = Field(ge=0)
    evening: int = Field(ge=0)


class HorsePeriodsUpdate(BaseModel):
    periods: HorsePeriodsCapacity


class HorseResponse(BaseModel):
    id: int
    name: str
    story: Optional[str] = None
    date_of_birth: Optional[date] = None
    color: Optional[str] = None
    gender: Optional[str] = None
    sire: Optional[str] = None
    dam: Optional[str] = None
    sires_sire: Optional[str] = None
    sires_dam: Optional[str] = None
    dams_sire: Optional[str] = None
    dams_dam: Optional[str] = None
    farm_id: int
    farm_name: Optional[str] = None
    status: str
    rejection_reason: Optional[str] = None
    images: List[HorseImageResponse] = []
    race_records: List[RaceRecordResponse] = []
    # Max visitors per period. Defaults to 1 in every period when unset (NULL);
    # 0 means the horse isn't offered in that period.
    periods: HorsePeriodsCapacity
    # Owning farm's full availability object (resolved to default when unconfigured).
    farm_availability: FarmAvailability

    @field_validator("periods", mode="before")
    @classmethod
    def resolve_periods(cls, v):
        if v is None:
            return default_horse_periods()
        return v

    class Config:
        from_attributes = True


class HorseWithDocumentsResponse(HorseResponse):
    # Ownership/identity documents. Not on the base HorseResponse — those are
    # private and must never appear on the public horse endpoints. Only used
    # for the owning farmer's own view and the admin review queue.
    documents: List[HorseDocumentResponse] = []
