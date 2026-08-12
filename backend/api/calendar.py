"""Calendar endpoints for diary history browsing and detail lookup."""

from __future__ import annotations

import math
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.repositories.calendar_repository import (
    apply_calendar_filters,
    build_calendar_base_stmt,
    build_ranked_version_subquery,
    fetch_user_emotion_tags,
    legacy_script_field,
    narration_fields,
    parse_emotion_tags,
    parse_string_list,
    sort_diary_inputs,
    sort_versions,
)
from database.conn.db import get_db
from database.models import DiarySession, DiaryVersion
from database.session_status import db_statuses_for_calendar_filter, normalize_session_status

router = APIRouter(prefix="/calendar", tags=["calendar"])


class CalendarEntryPreview(BaseModel):
    diary_date: date
    session_id: str
    status: str
    db_status: str
    title: str | None = None
    summary: str | None = None
    emotion_tags: list[str] | None = None
    approved: bool | None = None
    video_status: str | None = None
    location_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    created_at: datetime | None = None


class CalendarDiaryInput(BaseModel):
    input_id: str
    type: str
    storage_url: str | None = None
    transcript: str | None = None
    captured_at: datetime | None = None
    created_at: datetime | None = None


class CalendarVersionPreview(BaseModel):
    version_id: str
    title: str
    summary: str
    content: str
    paragraphs: list[str] | None = None
    evidence_input_ids: list[str] | None = None
    narration_text: str | None = None
    narration_status: str | None = None
    narration_audio_url: str | None = None
    script: str | None = Field(
        None,
        description="Deprecated alias: narration_text when present, else content",
    )
    emotion_tags: list[str] | None = None
    approved: bool
    created_at: datetime | None = None


class CalendarDayEntry(CalendarEntryPreview):
    content: str | None = None
    paragraphs: list[str] | None = None
    evidence_input_ids: list[str] | None = None
    narration_text: str | None = None
    narration_status: str | None = None
    narration_audio_url: str | None = None
    script: str | None = Field(
        None,
        description="Deprecated alias: narration_text when present, else content",
    )
    video_url: str | None = None
    updated_at: datetime | None = None
    diary_inputs: list[CalendarDiaryInput] = Field(default_factory=list)
    versions: list[CalendarVersionPreview] = Field(default_factory=list)


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
    entries: list[CalendarEntryPreview]


class CalendarEmotionsResponse(BaseModel):
    user_id: str
    start_date: date | None = None
    end_date: date | None = None
    emotions: list[str]


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


def _validate_status_filters(status_filters: list[str]) -> None:
    for status in status_filters:
        if db_statuses_for_calendar_filter(status) is None:
            raise HTTPException(status_code=400, detail=f"unsupported status filter: {status}")


def _row_to_preview(row: tuple) -> CalendarEntryPreview:
    session: DiarySession = row[0]
    return CalendarEntryPreview(
        diary_date=session.diary_date,
        session_id=session.session_id,
        status=normalize_session_status(session.status),
        db_status=session.status,
        title=row[1],
        summary=row[2],
        emotion_tags=parse_emotion_tags(row[6]),
        approved=row[7],
        video_status=row[8],
        location_name=session.location_name,
        latitude=float(session.latitude) if session.latitude is not None else None,
        longitude=float(session.longitude) if session.longitude is not None else None,
        created_at=session.created_at,
    )


def _build_diary_inputs(session: DiarySession) -> list[CalendarDiaryInput]:
    return [
        CalendarDiaryInput(
            input_id=item.input_id,
            type=item.type,
            storage_url=item.storage_url,
            transcript=item.transcript,
            captured_at=item.captured_at,
            created_at=item.created_at,
        )
        for item in sort_diary_inputs(session.inputs)
    ]


def _build_versions(versions: list[DiaryVersion]) -> list[CalendarVersionPreview]:
    previews: list[CalendarVersionPreview] = []
    for version in sort_versions(versions):
        narration_text, narration_status, narration_audio_url = narration_fields(version)
        previews.append(
            CalendarVersionPreview(
                version_id=version.version_id,
                title=version.title,
                summary=version.summary,
                content=version.content,
                paragraphs=parse_string_list(version.paragraphs),
                evidence_input_ids=parse_string_list(version.evidence_input_ids),
                narration_text=narration_text,
                narration_status=narration_status,
                narration_audio_url=narration_audio_url,
                script=legacy_script_field(content=version.content, narration_text=narration_text),
                emotion_tags=parse_emotion_tags(version.emotion_tags),
                approved=version.approved,
                created_at=version.created_at,
            )
        )
    return previews


def _row_to_detail(row: tuple, session: DiarySession) -> CalendarDayEntry:
    content = row[3]
    narration_text = row[10]
    preview = _row_to_preview(row)
    return CalendarDayEntry(
        **preview.model_dump(),
        content=content,
        paragraphs=parse_string_list(row[4]),
        evidence_input_ids=parse_string_list(row[5]),
        narration_text=narration_text,
        narration_status=row[11],
        narration_audio_url=row[12],
        script=legacy_script_field(content=content, narration_text=narration_text),
        video_url=row[9],
        updated_at=session.updated_at,
        diary_inputs=_build_diary_inputs(session),
        versions=_build_versions(session.versions),
    )


async def _fetch_calendar_rows(
    db: AsyncSession,
    *,
    user_id: str,
    start_date: date,
    end_date: date,
    status_filters: list[str] | None,
    emotion: str | None,
    keyword: str | None,
    latitude: float | None,
    longitude: float | None,
    radius: float,
) -> list[tuple]:
    _validate_location_filter(latitude, longitude, radius)
    if status_filters:
        _validate_status_filters(status_filters)

    version_rank_sub = build_ranked_version_subquery()
    dialect_name = db.bind.dialect.name if db.bind else "postgresql"
    stmt = build_calendar_base_stmt(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        version_rank_sub=version_rank_sub,
    )

    min_lat = max_lat = min_lon = max_lon = None
    if latitude is not None and longitude is not None:
        min_lat, max_lat, min_lon, max_lon = _build_proximity_clause(latitude, longitude, radius)

    stmt = apply_calendar_filters(
        stmt,
        version_rank_sub=version_rank_sub,
        dialect_name=dialect_name,
        status_filters=status_filters,
        emotion=emotion,
        keyword=keyword,
        latitude=latitude,
        longitude=longitude,
        min_lat=min_lat,
        max_lat=max_lat,
        min_lon=min_lon,
        max_lon=max_lon,
    )

    result = await db.execute(stmt)
    return list(result.all())


@router.get("/emotions", response_model=CalendarEmotionsResponse)
async def get_calendar_emotions(
    user_id: str = Query(..., description="User ID"),
    start_date: date | None = Query(None, description="Optional start date"),
    end_date: date | None = Query(None, description="Optional end date"),
    db: AsyncSession = Depends(get_db),
) -> CalendarEmotionsResponse:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be before or equal to end_date",
        )

    emotions = await fetch_user_emotion_tags(
        db,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
    )
    return CalendarEmotionsResponse(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        emotions=emotions,
    )


@router.get("/{session_id}", response_model=CalendarDayEntry)
async def get_calendar_entry(
    session_id: str,
    user_id: str = Query(..., description="User ID"),
    db: AsyncSession = Depends(get_db),
) -> CalendarDayEntry:
    version_rank_sub = build_ranked_version_subquery()
    stmt = (
        build_calendar_base_stmt(
            user_id=user_id,
            start_date=date(1970, 1, 1),
            end_date=date(9999, 12, 31),
            version_rank_sub=version_rank_sub,
        )
        .where(DiarySession.session_id == session_id)
        .options(
            selectinload(DiarySession.inputs),
            selectinload(DiarySession.versions).selectinload(DiaryVersion.narration_script),
        )
    )
    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        raise HTTPException(status_code=404, detail="calendar entry not found")

    session: DiarySession = row[0]
    return _row_to_detail(row, session)


@router.get("", response_model=CalendarResponse)
async def get_calendar(
    user_id: str = Query(..., description="User ID"),
    start_date: date = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (YYYY-MM-DD)"),
    status: list[str] | None = Query(None, description="Calendar session status filters"),
    emotion: str | None = Query(None, description="Emotion tag filter"),
    keyword: str | None = Query(
        None,
        description="Keyword search in title/summary/content/paragraphs/narration/transcript",
    ),
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

    rows = await _fetch_calendar_rows(
        db,
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        status_filters=status,
        emotion=emotion,
        keyword=keyword,
        latitude=latitude,
        longitude=longitude,
        radius=radius,
    )

    entries = [_row_to_preview(row) for row in rows]
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
