"""Async database connection and request-scoped session factory.

Production target: PostgreSQL on Naver Cloud (asyncpg driver).
Tests use SQLite in-memory via FastAPI dependency overrides.
Set ``DATABASE_URL`` to override individual ``DB_*`` variables.
"""

from __future__ import annotations

import logging
import os
from urllib.parse import quote_plus

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.config import load_config

logger = logging.getLogger(__name__)

config = load_config()
db_config = config.get("db", {})

database_url_override = os.environ.get("DATABASE_URL", "").strip()
if database_url_override:
    DATABASE_URL = database_url_override
else:
    host = db_config.get("host", "localhost")
    port = db_config.get("port", 5432)
    dbname = db_config.get("dbname", "mediary")
    user = db_config.get("user", "")
    password = db_config.get("password", "")

    escaped_user = quote_plus(user) if user else ""
    escaped_password = quote_plus(password) if password else ""
    DATABASE_URL = (
        f"postgresql+asyncpg://{escaped_user}:{escaped_password}@{host}:{port}/{dbname}"
    )

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db():
    """FastAPI dependency to yield an async database session."""
    async with AsyncSessionLocal() as session:
        yield session
