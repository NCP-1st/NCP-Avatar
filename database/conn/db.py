"""Async database connection and request-scoped session factory."""

import logging
from urllib.parse import quote_plus
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from backend.config import load_config

logger = logging.getLogger(__name__)

# Load configuration dynamically
config = load_config()
db_config = config.get("db", {})

host = db_config.get("host", "localhost")
port = db_config.get("port", 5432)
dbname = db_config.get("dbname", "mediary")
user = db_config.get("user", "")
password = db_config.get("password", "")

escaped_user = quote_plus(user) if user else ""
escaped_password = quote_plus(password) if password else ""

DATABASE_URL = f"postgresql+asyncpg://{escaped_user}:{escaped_password}@{host}:{port}/{dbname}"


# Create async engine with pool configurations for managed Naver Cloud DB
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,      # Automatically reconnects if connection is dropped by DB server
    pool_size=10,            # Permanent connection pool size
    max_overflow=20,         # Maximum overflow connections beyond pool_size
)

# Async session factory
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
