import asyncio
import logging

from sqlalchemy import select

from backend.config import load_config
from backend.services.embedding.clova_embedding import ClovaEmbeddingAdapter
from database.conn.db import AsyncSessionLocal
from database.models import DiaryEmbedding, DiaryVersion

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mediary.seed_embeddings")


async def populate_existing_embeddings() -> None:
    logger.info("🌱 기존 일기 목데이터 대상 임베딩 생성 및 적재 시작...")
    llm_config = load_config()["llm"]
    embedder = ClovaEmbeddingAdapter(
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        model="bge-m3",
        timeout_seconds=llm_config["timeout_s"],
    )

    async with AsyncSessionLocal() as db:
        # A. 이미 승인된(approved=True) 일기 목록 조회
        stmt = select(DiaryVersion).where(DiaryVersion.approved.is_(True))
        result = await db.execute(stmt)
        diary_versions = result.scalars().all()

        if not diary_versions:
            logger.warning("⚠️ DB에 승인된 일기 데이터(DiaryVersion)가 없습니다.")
            return

        logger.info(f"총 {len(diary_versions)}개의 기존 일기를 찾았습니다.")

        # B. 각 일기별로 임베딩 생성 후 diary_embeddings에 저장
        success_count = 0
        skipped_count = 0
        failed_count = 0
        for version in diary_versions:
            version_id = version.version_id

            # 이미 임베딩이 존재하는지 확인 (중복 적재 방지)
            existing_emb = await db.get(DiaryEmbedding, version_id)
            if existing_emb:
                logger.info(f"⏩ [{version_id}] 이미 임베딩이 존재하여 건너뜁니다.")
                skipped_count += 1
                continue

            # C. CLOVA Embedding API 호출 (content 문단 전체 대상)
            logger.info(f"⏳ [{version_id}] 임베딩 생성 중...")
            try:
                vector = await embedder.embed(version.content)
                
                # D. pgvector 테이블 레코드 추가
                db.add(DiaryEmbedding(version_id=version_id, embedding=vector))
                # 건별 커밋으로 하나가 실패해도 앞서 적재한 벡터는 유지한다.
                await db.commit()
                success_count += 1
            except Exception as e:
                logger.error(f"❌ [{version_id}] 임베딩 생성 실패: {type(e).__name__}")
                await db.rollback()
                failed_count += 1
                continue

        logger.info(
            "✅ 임베딩 적재 완료: 성공=%s, 건너뜀=%s, 실패=%s",
            success_count,
            skipped_count,
            failed_count,
        )

if __name__ == "__main__":
    asyncio.run(populate_existing_embeddings())
