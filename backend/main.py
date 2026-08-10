"""FastAPI main entrypoint to run the Mediary backend server."""

import logging
import os

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Load env variables from project root .env file before loading configs
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from backend.api import calendar
from backend.api.maps import router as maps_router
from backend.api.script import router as script_router
from database.conn.db import engine


logging.basicConfig(level=logging.INFO)
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

app.include_router(calendar.router, prefix="/api")
app.include_router(maps_router, prefix="/api")
app.include_router(script_router, prefix="/api")


@app.get("/")
async def root() -> dict[str, object]:
    """Health check endpoint."""
    db_ok = False
    try:
        from sqlalchemy import text

        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:
        logger.warning("Database connection check failed: %s", exc)

    return {
        "status": "online",
        "service": "Mediary Backend API",
        "database_connected": db_ok,
    }


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
