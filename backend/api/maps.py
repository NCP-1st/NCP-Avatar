"""Database-backed map diary endpoints (L-01)."""

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.maps import DiaryLocationCreate, DiaryMapEntry, LocationStatus
from database.conn.db import get_db
from database.models import AvatarVideo, DiarySession, DiaryVersion, LocationMessage

router = APIRouter(prefix="/maps", tags=["maps"])


def _to_entry(row: tuple) -> DiaryMapEntry:
    version: DiaryVersion = row[0]
    session: DiarySession = row[1]
    location: LocationMessage | None = row[2]
    return DiaryMapEntry(
        map_id=location.map_id if location else None,
        version_id=version.version_id,
        session_id=session.session_id,
        diary_date=session.diary_date,
        title=version.title,
        summary=version.summary,
        emotion_tags=list(version.emotion_tags or []),
        latitude=float(location.latitude) if location else None,
        longitude=float(location.longitude) if location else None,
        is_located=location is not None,
        video_status=row[3],
        created_at=location.created_at if location else version.created_at,
    )


@router.get("/diaries", response_model=list[DiaryMapEntry])
async def list_diaries(
    user_id: str = Query(..., min_length=1),
    location_status: LocationStatus = Query("all"),
    keyword: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[DiaryMapEntry]:
    stmt = (
        select(
            DiaryVersion,
            DiarySession,
            LocationMessage,
            AvatarVideo.status.label("video_status"),
        )
        .join(DiarySession, DiaryVersion.session_id == DiarySession.session_id)
        .outerjoin(
            LocationMessage, LocationMessage.version_id == DiaryVersion.version_id
        )
        .outerjoin(AvatarVideo, AvatarVideo.version_id == DiaryVersion.version_id)
        .where(
            DiarySession.user_id == user_id,
            DiaryVersion.approved.is_(True),
        )
        .order_by(DiarySession.diary_date.desc(), DiaryVersion.created_at.desc())
    )
    if location_status == "located":
        stmt = stmt.where(LocationMessage.map_id.is_not(None))
    elif location_status == "unlocated":
        stmt = stmt.where(LocationMessage.map_id.is_(None))
    if keyword and keyword.strip():
        stmt = stmt.where(DiaryVersion.title.ilike(f"%{keyword.strip()}%"))

    result = await db.execute(stmt)
    return [_to_entry(row) for row in result.all()]


@router.post(
    "/diaries",
    response_model=DiaryMapEntry,
    status_code=status.HTTP_201_CREATED,
)
async def create_diary_location(
    payload: DiaryLocationCreate,
    db: AsyncSession = Depends(get_db),
) -> DiaryMapEntry:
    owned_version = await db.execute(
        select(DiaryVersion, DiarySession)
        .join(DiarySession, DiaryVersion.session_id == DiarySession.session_id)
        .where(
            DiaryVersion.version_id == payload.version_id,
            DiarySession.user_id == payload.user_id,
            DiaryVersion.approved.is_(True),
        )
    )
    owned_row = owned_version.first()
    if owned_row is None:
        raise HTTPException(status_code=404, detail="approved diary version not found")
    version, session = owned_row

    existing = await db.scalar(
        select(LocationMessage).where(
            LocationMessage.version_id == payload.version_id
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail="diary version already has a location",
        )

    location = LocationMessage(
        map_id=str(uuid4()),
        user_id=payload.user_id,
        session_id=session.session_id,
        version_id=version.version_id,
        latitude=payload.latitude,
        longitude=payload.longitude,
    )
    db.add(location)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="diary version already has a location",
        ) from exc
    await db.refresh(location)

    video_status = await db.scalar(
        select(AvatarVideo.status).where(AvatarVideo.version_id == version.version_id)
    )
    return _to_entry((version, session, location, video_status))
