"""FastAPI main entrypoint for the Mediary backend server."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from backend.api import calendar, diary, counsel
from backend.api.maps import router as maps_router
from backend.api.script import router as script_router
from database.conn.db import engine

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Mediary Backend API",
    description="Backend API for Mediary MVP - AI Avatar Diary & Calendar",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(diary.router)
app.include_router(calendar.router, prefix="/api")
app.include_router(maps_router, prefix="/api")
app.include_router(script_router, prefix="/api")
app.include_router(counsel.router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    """Return the backend status."""
    return {"status": "ok"}


@app.get("/")
async def root() -> dict[str, str | bool]:
    """Return the service status and a best-effort database health check."""
    database_connected = False
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        database_connected = True
    except Exception as exc:
        logger.warning(
            "database_health_check_failed",
            extra={"error_type": type(exc).__name__},
        )
    return {
        "status": "online",
        "service": "Mediary Backend API",
        "database_connected": database_connected,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
