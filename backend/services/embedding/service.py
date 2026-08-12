"""Persistence and similarity search for approved diary embeddings."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.embedding.clova_embedding import EmbeddingAdapter
from database.models import DiaryEmbedding, DiaryVersion


logger = logging.getLogger("mediary.embedding")


class DiaryEmbeddingService:
    def __init__(self, db: AsyncSession, embedder: EmbeddingAdapter) -> None:
        self._db = db
        self._embedder = embedder

    async def index_diary(self, *, version_id: str, content: str) -> None:
        """Index a diary without allowing failures to roll back its approval."""
        try:
            vector = await self._embedder.embed(content)
            stored = await self._db.get(DiaryEmbedding, version_id)
            if stored is None:
                self._db.add(
                    DiaryEmbedding(version_id=version_id, embedding=vector)
                )
            else:
                stored.embedding = vector
            await self._db.commit()
        except Exception as exc:
            logger.warning(
                "diary_embedding_failed",
                extra={
                    "version_id": version_id,
                    "error_type": type(exc).__name__,
                },
            )
            await self._db.rollback()

    async def find_similar_diaries(
        self, query_text: str, *, limit: int = 5
    ) -> list[tuple[DiaryVersion, float]]:
        if limit < 1:
            raise ValueError("limit must be positive")
        query_vector = await self._embedder.embed(query_text)
        distance = DiaryEmbedding.embedding.cosine_distance(query_vector).label(
            "distance"
        )
        result = await self._db.execute(
            select(DiaryVersion, distance)
            .join(DiaryEmbedding, DiaryEmbedding.version_id == DiaryVersion.version_id)
            .where(DiaryVersion.approved.is_(True))
            .order_by(distance)
            .limit(limit)
        )
        return [(version, float(score)) for version, score in result.all()]
