from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List

from core.availability import DEFAULT_MIN_LEAD_DAYS, PERIOD_KEYS, PERIOD_WINDOWS, to_minutes


class FarmUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    capacity: Optional[int] = None


class FarmImageResponse(BaseModel):
    id: int
    image_url: str
    position: int

    class Config:
        from_attributes = True


class ImageReorderRequest(BaseModel):
    image_ids: List[int]


class PeriodConfig(BaseModel):
    open: bool
    start: str  # 24h "HH:MM"
    end: str    # 24h "HH:MM"


class FarmPeriods(BaseModel):
    # Always exactly these three keys.
    morning: PeriodConfig
    afternoon: PeriodConfig
    evening: PeriodConfig


class FarmAvailability(BaseModel):
    enabled: bool = True
    weekdays: List[int]
    periods: FarmPeriods
    # How many days ahead a visit must be booked. Same-day (0) is not allowed.
    min_lead_days: int = Field(default=DEFAULT_MIN_LEAD_DAYS, ge=1, le=90)

    @field_validator("weekdays")
    @classmethod
    def validate_weekdays(cls, v: List[int]) -> List[int]:
        if len(set(v)) != len(v):
            raise ValueError("weekdays must be unique")
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("weekdays must be ints in the range 0..6")
        return v

    @model_validator(mode="after")
    def validate_period_times(self) -> "FarmAvailability":
        # Only validate times for periods that are open.
        for key in PERIOD_KEYS:
            period: PeriodConfig = getattr(self.periods, key)
            if not period.open:
                continue
            window_start, window_end = PERIOD_WINDOWS[key]
            start = to_minutes(period.start)
            end = to_minutes(period.end)
            if start < to_minutes(window_start) or end > to_minutes(window_end):
                raise ValueError(
                    f"{key} times must fall within {window_start}-{window_end}"
                )
            if start >= end:
                raise ValueError(f"{key} start must be strictly before end")
        return self


class FarmResponse(BaseModel):
    id: int
    name: str
    location: Optional[str] = None
    description: Optional[str] = None
    capacity: Optional[int] = None
    status: str
    owner_id: int
    images: List[FarmImageResponse] = []

    class Config:
        from_attributes = True
