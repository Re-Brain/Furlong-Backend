from pydantic import BaseModel
from typing import Optional, List
from datetime import date


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

    class Config:
        from_attributes = True
