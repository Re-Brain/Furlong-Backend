from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import date

from core.availability import PERIOD_KEYS, default_horse_periods, normalize_periods
from schemas.farms import FarmAvailability


class HorseCreate(BaseModel):
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


class HorsePeriodsUpdate(BaseModel):
    periods: List[str]

    @field_validator("periods")
    @classmethod
    def validate_periods(cls, v: List[str]) -> List[str]:
        invalid = [p for p in v if p not in PERIOD_KEYS]
        if invalid:
            raise ValueError(
                f"periods must be a subset of {PERIOD_KEYS}; got invalid values {invalid}"
            )
        # Dedupe and reorder into canonical order.
        return normalize_periods(v)


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
    images: List[HorseImageResponse] = []
    race_records: List[RaceRecordResponse] = []
    # Visit periods this horse opts into. Defaults to all three when unset (NULL).
    periods: List[str] = []
    # Owning farm's full availability object (resolved to default when unconfigured).
    farm_availability: FarmAvailability

    @field_validator("periods", mode="before")
    @classmethod
    def resolve_periods(cls, v) -> List[str]:
        if v is None:
            return default_horse_periods()
        return normalize_periods(v)

    class Config:
        from_attributes = True
