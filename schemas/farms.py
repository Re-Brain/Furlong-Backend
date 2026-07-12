from pydantic import BaseModel
from typing import Optional, List


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
