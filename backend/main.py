from fastapi import FastAPI

from backend.api import diary
from backend.config import get_settings

app = FastAPI(title="Mediary Dummy API", version="0.1.0")
app.include_router(diary.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "adapters": get_settings().adapter_mode}
