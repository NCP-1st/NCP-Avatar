"""Delete diary media from Object Storage before cascading database rows."""

from __future__ import annotations

from pydantic import BaseModel

from backend.repositories.sqlalchemy import SQLAlchemyDiaryRepository
from backend.services.storage import StorageAdapter


class DiaryDeletionResult(BaseModel):
    version_id: str
    deleted_object_count: int


class DiaryMediaProcessingError(RuntimeError):
    """Raised when a version still has media generation in progress."""


class DiaryDeletionOrchestrator:
    def __init__(self, *, storage_adapter: StorageAdapter) -> None:
        self._storage = storage_adapter

    async def delete_version(
        self,
        *,
        session_id: str,
        version_id: str,
        repository: SQLAlchemyDiaryRepository,
    ) -> DiaryDeletionResult:
        try:
            object_keys = await repository.get_version_media_object_keys(
                session_id=session_id,
                version_id=version_id,
            )
        except RuntimeError as exc:
            raise DiaryMediaProcessingError(str(exc)) from exc
        for object_key in object_keys:
            await self._storage.delete(object_name=object_key)

        await repository.delete_version(
            session_id=session_id,
            version_id=version_id,
        )
        return DiaryDeletionResult(
            version_id=version_id,
            deleted_object_count=len(object_keys),
        )
