"""위치 기반 일기(지도 핀) 요청/응답 스키마."""

from pydantic import BaseModel, Field


class DiaryPinCreate(BaseModel):
    """일기 저장 요청 — 위치와 내용만 받고 id/날짜는 서버가 부여한다."""

    title: str = Field(min_length=1)
    summary: str = ""
    emotion: str = ""
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)


class DiaryPin(DiaryPinCreate):
    """저장된 일기 — 지도 마커 하나에 대응한다."""

    id: str
    date: str
