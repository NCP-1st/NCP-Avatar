"""Calendar endpoints for diary history browsing and detail lookup."""

from __future__ import annotations

import json
import math
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.conn.db import get_db
from database.models import AvatarVideo, DiaryInput, DiarySession, DiaryVersion

router = APIRouter(prefix="/calendar", tags=["calendar"])


class CalendarDayEntry(BaseModel):
    diary_date: date = Field(..., description="Diary entry date")
    session_id: str = Field(..., description="Diary session ID")
    status: str = Field(..., description="Session status")
    title: str | None = Field(None, description="Selected diary version title")
    summary: str | None = Field(None, description="Selected diary version summary")
    script: str | None = Field(None, description="Selected diary version content")
    emotion_tags: list[str] | None = Field(None, description="Selected diary version emotion tags")
    approved: bool | None = Field(None, description="Whether the selected version is approved")
    video_status: str | None = Field(None, description="Avatar video render status")
    video_url: str | None = Field(None, description="Avatar video URL")
    location_name: str | None = Field(None, description="Primary location name")
    latitude: float | None = Field(None, description="Primary latitude")
    longitude: float | None = Field(None, description="Primary longitude")
    created_at: datetime | None = Field(None, description="Session created timestamp")
    updated_at: datetime | None = Field(None, description="Session updated timestamp")
    diary_inputs: list["CalendarDiaryInput"] = Field(default_factory=list)
    versions: list["CalendarVersionPreview"] = Field(default_factory=list)


class CalendarDiaryInput(BaseModel):
    input_id: str
    type: str
    storage_url: str
    transcript: str | None = None
    captured_at: datetime | None = None
    created_at: datetime | None = None


class CalendarVersionPreview(BaseModel):
    version_id: str
    title: str
    summary: str
    script: str
    emotion_tags: list[str] | None = None
    approved: bool
    created_at: datetime | None = None


class CalendarSummary(BaseModel):
    total_entries: int = 0
    completed_entries: int = 0
    processing_entries: int = 0
    failed_entries: int = 0
    approved_entries: int = 0


class CalendarResponse(BaseModel):
    user_id: str
    start_date: date
    end_date: date
    summary: CalendarSummary
    entries: list[CalendarDayEntry]


CalendarDayEntry.model_rebuild()


def _build_ranked_version_subquery() -> Any:
    return (
        select(
            DiaryVersion.version_id,
            DiaryVersion.session_id,
            DiaryVersion.title,
            DiaryVersion.summary,
            DiaryVersion.content.label("script"),
            DiaryVersion.emotion_tags,
            DiaryVersion.approved,
            DiaryVersion.created_at,
            func.row_number().over(
                partition_by=DiaryVersion.session_id,
                order_by=(DiaryVersion.approved.desc(), DiaryVersion.created_at.desc()),
            ).label("rn"),
        ).subquery()
    )


def _parse_emotion_tags(emotion_tags: Any) -> list[str] | None:
    if emotion_tags is None:
        return None
    if isinstance(emotion_tags, list):
        return [str(tag) for tag in emotion_tags]
    if isinstance(emotion_tags, str):
        try:
            parsed = json.loads(emotion_tags)
        except json.JSONDecodeError:
            return [emotion_tags]
        if isinstance(parsed, list):
            return [str(tag) for tag in parsed]
        return [str(parsed)]
    return [str(emotion_tags)]


def _validate_location_filter(
    latitude: float | None,
    longitude: float | None,
    radius: float,
) -> None:
    if radius <= 0:
        raise HTTPException(status_code=400, detail="radius must be greater than 0")
    if (latitude is None) != (longitude is None):
        raise HTTPException(
            status_code=400,
            detail="latitude and longitude must be provided together",
        )
    if latitude is None:
        return
    if not -90 <= latitude <= 90:
        raise HTTPException(status_code=400, detail="latitude must be between -90 and 90")
    if not -180 <= longitude <= 180:
        raise HTTPException(
            status_code=400,
            detail="longitude must be between -180 and 180",
        )


def _build_proximity_clause(
    latitude: float,
    longitude: float,
    radius: float,
) -> tuple[float, float, float, float]:
    lat_delta = radius / 111000.0
    cos_lat = math.cos(math.radians(latitude))
    lon_delta = radius / (111000.0 * cos_lat) if cos_lat else radius / 111000.0
    return (
        latitude - lat_delta,
        latitude + lat_delta,
        longitude - lon_delta,
        longitude + lon_delta,
    )


def _build_diary_inputs(inputs: list[DiaryInput]) -> list[CalendarDiaryInput]:
    sorted_inputs = sorted(
        inputs,
        key=lambda item: (
            item.captured_at or item.created_at or datetime.min,
            item.created_at or datetime.min,
        ),
    )
    return [
        CalendarDiaryInput(
            input_id=item.input_id,
            type=item.type,
            storage_url=item.storage_url,
            transcript=item.transcript,
            captured_at=item.captured_at,
            created_at=item.created_at,
        )
        for item in sorted_inputs
    ]


def _build_versions(versions: list[DiaryVersion]) -> list[CalendarVersionPreview]:
    sorted_versions = sorted(
        versions,
        key=lambda item: (item.created_at or datetime.min),
        reverse=True,
    )
    return [
        CalendarVersionPreview(
            version_id=version.version_id,
            title=version.title,
            summary=version.summary,
            script=version.content,
            emotion_tags=_parse_emotion_tags(version.emotion_tags),
            approved=version.approved,
            created_at=version.created_at,
        )
        for version in sorted_versions
    ]


@router.get("", response_model=CalendarResponse)
async def get_calendar(
    user_id: str = Query(..., description="User ID"),
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    status: str | None = Query(None, description="Session status filter"),
    emotion: str | None = Query(None, description="Emotion tag filter"),
    keyword: str | None = Query(None, description="Keyword search in title/summary/script"),
    latitude: float | None = Query(None, description="Latitude filter"),
    longitude: float | None = Query(None, description="Longitude filter"),
    radius: float = Query(1000.0, description="Location radius in meters"),
    db: AsyncSession = Depends(get_db),
) -> CalendarResponse:
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be before or equal to end_date",
        )

    _validate_location_filter(latitude, longitude, radius)
    version_rank_sub = _build_ranked_version_subquery()

    stmt = (
        select(
            DiarySession,
            version_rank_sub.c.title,
            version_rank_sub.c.summary,
            version_rank_sub.c.script,
            version_rank_sub.c.emotion_tags,
            version_rank_sub.c.approved,
            AvatarVideo.status.label("video_status"),
            AvatarVideo.storage_url.label("video_url"),
        )
        .outerjoin(
            version_rank_sub,
            and_(
                DiarySession.session_id == version_rank_sub.c.session_id,
                version_rank_sub.c.rn == 1,
            ),
        )
        .outerjoin(AvatarVideo, version_rank_sub.c.version_id == AvatarVideo.version_id)
        .where(
            DiarySession.user_id == user_id,
            DiarySession.diary_date >= start_date,
            DiarySession.diary_date <= end_date,
        )
        .options(
            selectinload(DiarySession.inputs),
            selectinload(DiarySession.versions),
        )
        .order_by(DiarySession.diary_date.asc(), DiarySession.created_at.asc())
    )

    if status:
        stmt = stmt.where(DiarySession.status == status)

    if emotion:
        dialect_name = db.bind.dialect.name if db.bind else "mysql"
        if dialect_name == "sqlite":
            stmt = stmt.where(version_rank_sub.c.emotion_tags.like(f'%"{emotion}"%'))
        else:
            stmt = stmt.where(
                func.json_contains(
                    version_rank_sub.c.emotion_tags,
                    func.json_quote(emotion),
                )
            )

    if keyword:
        keyword_pattern = f"%{keyword.strip()}%"
        stmt = stmt.where(
            or_(
                version_rank_sub.c.title.ilike(keyword_pattern),
                version_rank_sub.c.summary.ilike(keyword_pattern),
                version_rank_sub.c.script.ilike(keyword_pattern),
            )
        )

    if latitude is not None and longitude is not None:
        min_lat, max_lat, min_lon, max_lon = _build_proximity_clause(
            latitude,
            longitude,
            radius,
        )
        stmt = stmt.where(
            DiarySession.latitude.is_not(None),
            DiarySession.longitude.is_not(None),
            DiarySession.latitude.between(min_lat, max_lat),
            DiarySession.longitude.between(min_lon, max_lon),
        )

    result = await db.execute(stmt)
    rows = result.all()

    entries: list[CalendarDayEntry] = []
    for row in rows:
        session: DiarySession = row[0]
        entries.append(
            CalendarDayEntry(
                diary_date=session.diary_date,
                session_id=session.session_id,
                status=session.status,
                title=row[1],
                summary=row[2],
                script=row[3],
                emotion_tags=_parse_emotion_tags(row[4]),
                approved=row[5],
                video_status=row[6],
                video_url=row[7],
                location_name=session.location_name,
                latitude=float(session.latitude) if session.latitude is not None else None,
                longitude=float(session.longitude) if session.longitude is not None else None,
                created_at=session.created_at,
                updated_at=session.updated_at,
                diary_inputs=_build_diary_inputs(session.inputs),
                versions=_build_versions(session.versions),
            )
        )

    summary = CalendarSummary(
        total_entries=len(entries),
        completed_entries=sum(entry.status == "completed" for entry in entries),
        processing_entries=sum(entry.status == "processing" for entry in entries),
        failed_entries=sum(entry.status == "failed" for entry in entries),
        approved_entries=sum(entry.approved is True for entry in entries),
    )

    return CalendarResponse(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        summary=summary,
        entries=entries,
    )
