"""FastAPI main entrypoint to run the Mediary backend server."""

import logging
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

# Load env variables from project root .env file before loading configs
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

from backend.api import calendar
from database.conn.db import engine

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Mediary Backend API",
    description="Backend API for Mediary MVP - AI Avatar Diary & Calendar",
    version="1.0.0",
)

# Configure CORS for Streamlit frontend interaction
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Streamlit might run on custom ports, adjust in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(calendar.router, prefix="/api")


@app.get("/")
async def root():
    """Health check endpoint."""
    db_ok = False
    try:
        # Simple ping check to database
        from sqlalchemy import text
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as e:
        logger.warning(f"Database connection check failed: {e}")

    return {
        "status": "online",
        "service": "Mediary Backend API",
        "database_connected": db_ok,
    }


if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
