"""Calendar read queries shared by list, detail, and emotion endpoints."""

from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any

from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import AvatarVideo, DiaryInput, DiarySession, DiaryVersion, NarrationScript
from database.session_status import db_statuses_for_calendar_filter, normalize_session_status


def build_ranked_version_subquery() -> Any:
    return (
        select(
            DiaryVersion.version_id,
            DiaryVersion.session_id,
            DiaryVersion.title,
            DiaryVersion.summary,
            DiaryVersion.content,
            DiaryVersion.paragraphs,
            DiaryVersion.evidence_input_ids,
            DiaryVersion.emotion_tags,
            DiaryVersion.approved,
            DiaryVersion.created_at,
            func.row_number().over(
                partition_by=DiaryVersion.session_id,
                order_by=(DiaryVersion.approved.desc(), DiaryVersion.created_at.desc()),
            ).label("rn"),
        ).subquery()
    )


def parse_emotion_tags(emotion_tags: Any) -> list[str] | None:
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


def parse_string_list(value: Any) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return [value]
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
        return [str(parsed)]
    return [str(value)]


def legacy_script_field(*, content: str | None, narration_text: str | None) -> str | None:
    if narration_text:
        return narration_text
    return content


def emotion_filter_clause(column: Any, emotion: str, dialect_name: str) -> Any:
    if dialect_name == "sqlite":
        return column.like(f'%"{emotion}"%')
    if dialect_name == "postgresql":
        return cast(column, JSONB).contains([emotion])
    return func.json_contains(column, func.json_quote(emotion))


def expand_status_filters(status_filters: list[str]) -> list[str]:
    db_statuses: list[str] = []
    for status in status_filters:
        mapped = db_statuses_for_calendar_filter(status)
        if mapped is None:
            continue
        for item in mapped:
            if item not in db_statuses:
                db_statuses.append(item)
    return db_statuses


def build_calendar_base_stmt(
    *,
    user_id: str,
    start_date: date,
    end_date: date,
    version_rank_sub: Any,
) -> Any:
    return (
        select(
            DiarySession,
            version_rank_sub.c.title,
            version_rank_sub.c.summary,
            version_rank_sub.c.content,
            version_rank_sub.c.paragraphs,
            version_rank_sub.c.evidence_input_ids,
            version_rank_sub.c.emotion_tags,
            version_rank_sub.c.approved,
            AvatarVideo.status.label("video_status"),
            AvatarVideo.storage_url.label("video_url"),
            NarrationScript.narration_text,
            NarrationScript.status.label("narration_status"),
            NarrationScript.audio_url.label("narration_audio_url"),
        )
        .outerjoin(
            version_rank_sub,
            and_(
                DiarySession.session_id == version_rank_sub.c.session_id,
                version_rank_sub.c.rn == 1,
            ),
        )
        .outerjoin(AvatarVideo, version_rank_sub.c.version_id == AvatarVideo.version_id)
        .outerjoin(
            NarrationScript,
            version_rank_sub.c.version_id == NarrationScript.diary_version_id,
        )
        .where(
            DiarySession.user_id == user_id,
            DiarySession.diary_date >= start_date,
            DiarySession.diary_date <= end_date,
        )
        .order_by(DiarySession.diary_date.asc(), DiarySession.created_at.asc())
    )


def apply_calendar_filters(
    stmt: Any,
    *,
    version_rank_sub: Any,
    dialect_name: str,
    status_filters: list[str] | None,
    emotion: str | None,
    keyword: str | None,
    latitude: float | None,
    longitude: float | None,
    min_lat: float | None,
    max_lat: float | None,
    min_lon: float | None,
    max_lon: float | None,
) -> Any:
    if status_filters:
        db_statuses = expand_status_filters(status_filters)
        if db_statuses:
            stmt = stmt.where(DiarySession.status.in_(db_statuses))

    if emotion:
        stmt = stmt.where(
            emotion_filter_clause(version_rank_sub.c.emotion_tags, emotion, dialect_name)
        )

    if keyword:
        keyword_pattern = f"%{keyword.strip()}%"
        transcript_exists = (
            select(DiaryInput.input_id)
            .where(
                DiaryInput.session_id == DiarySession.session_id,
                or_(
                    DiaryInput.transcript.ilike(keyword_pattern),
                    cast(DiaryInput.transcript, String).ilike(keyword_pattern),
                ),
            )
            .exists()
        )
        stmt = stmt.where(
            or_(
                version_rank_sub.c.title.ilike(keyword_pattern),
                version_rank_sub.c.summary.ilike(keyword_pattern),
                version_rank_sub.c.content.ilike(keyword_pattern),
                cast(version_rank_sub.c.paragraphs, String).ilike(keyword_pattern),
                NarrationScript.narration_text.ilike(keyword_pattern),
                transcript_exists,
            )
        )

    if latitude is not None and longitude is not None:
        stmt = stmt.where(
            DiarySession.latitude.is_not(None),
            DiarySession.longitude.is_not(None),
            DiarySession.latitude.between(min_lat, max_lat),
            DiarySession.longitude.between(min_lon, max_lon),
        )

    return stmt


async def fetch_user_emotion_tags(
    db: AsyncSession,
    *,
    user_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> list[str]:
    stmt = (
        select(DiaryVersion.emotion_tags)
        .join(DiarySession, DiaryVersion.session_id == DiarySession.session_id)
        .where(DiarySession.user_id == user_id)
    )
    if start_date is not None:
        stmt = stmt.where(DiarySession.diary_date >= start_date)
    if end_date is not None:
        stmt = stmt.where(DiarySession.diary_date <= end_date)

    result = await db.execute(stmt)
    tags: set[str] = set()
    for (emotion_tags,) in result.all():
        parsed = parse_emotion_tags(emotion_tags)
        if parsed:
            tags.update(parsed)
    return sorted(tags)


def sort_diary_inputs(inputs: list[DiaryInput]) -> list[DiaryInput]:
    return sorted(
        inputs,
        key=lambda item: (
            item.captured_at or item.created_at or datetime.min,
            item.created_at or datetime.min,
        ),
    )


def sort_versions(versions: list[DiaryVersion]) -> list[DiaryVersion]:
    return sorted(
        versions,
        key=lambda item: (item.created_at or datetime.min),
        reverse=True,
    )


def narration_fields(version: DiaryVersion) -> tuple[str | None, str | None, str | None]:
    narration = version.narration_script
    if narration is None:
        return None, None, None
    return narration.narration_text, narration.status, narration.audio_url
