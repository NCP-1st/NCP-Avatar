"""Request and response schemas for diary locations on the map."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field


LocationStatus = Literal["all", "located", "unlocated"]


class DiaryLocationCreate(BaseModel):
    user_id: str = Field(min_length=1, max_length=50)
    version_id: str = Field(min_length=1, max_length=50)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class DiaryMapEntry(BaseModel):
    map_id: str | None = None
    version_id: str
    session_id: str
    diary_date: date
    title: str
    summary: str
    emotion_tags: list[str] = Field(default_factory=list)
    latitude: float | None = None
    longitude: float | None = None
    is_located: bool
    video_status: str | None = None
    created_at: datetime | None = None


# Legacy mock-store schemas kept so older imports do not break. The live API no
# longer uses these types or the JSON-backed DiaryStore.
class DiaryPinCreate(BaseModel):
    title: str = Field(min_length=1)
    summary: str = ""
    emotion: str = ""
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class DiaryPin(DiaryPinCreate):
    id: str
    date: str
