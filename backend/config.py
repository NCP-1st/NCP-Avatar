"""Environment-only configuration for replaceable external adapters."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def load_config(env_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Return a fresh config. OS variables override `.env`; secrets have no defaults."""
    path = Path(env_path) if env_path else _ENV_PATH
    file_values = {key: value for key, value in dotenv_values(path).items() if value is not None}
    env = {**file_values, **os.environ}
    avatar_image_path = Path(
        env.get("HF_AVATAR_IMAGE_PATH") or "backend/character/char_1.png"
    )
    if not avatar_image_path.is_absolute():
        avatar_image_path = path.resolve().parent / avatar_image_path
    return {
        "llm": {
            "provider": "clova_native",
            "api_key": env.get("CLOVA_STUDIO_API_KEY", ""),
            "base_url": env.get("CLOVA_STUDIO_BASE_URL", "https://clovastudio.stream.ntruss.com"),
            "model_vision": env.get("CLOVA_STUDIO_MODEL_VISION", "HCX-005"),
            "model_reasoning": env.get("CLOVA_STUDIO_MODEL_REASONING", "HCX-007"),
            "timeout_s": float(env.get("CLOVA_STUDIO_TIMEOUT_SECONDS", "30")),
            "max_tokens": int(env.get("CLOVA_STUDIO_MAX_TOKENS", "1024")),
        },
        "speech": {
            "client_id": env.get("CLOVA_SPEECH_CLIENT_ID", ""),
            "client_secret": env.get("CLOVA_SPEECH_CLIENT_SECRET", ""),
            "invoke_url": env.get("CLOVA_SPEECH_INVOKE_URL", ""),
            "secret_key": env.get("CLOVA_SPEECH_SECRET_KEY", ""),
        },
        "voice": {
            "api_url": env.get(
                "CLOVA_VOICE_API_URL", "https://naveropenapi.apigw.ntruss.com/tts-premium/v1/tts"
            ),
            "client_id": env.get("CLOVA_VOICE_CLIENT_ID", ""),
            "client_secret": env.get("CLOVA_VOICE_CLIENT_SECRET", ""),
        },
        "avatar": {
            "space_id": env.get("HF_AVATAR_SPACE_ID") or "pragnakalp/Wav2lip-ZeroGPU",
            "api_name": env.get("HF_AVATAR_API_NAME") or "/run_infrence",
            "token": env.get("HF_TOKEN") or env.get("ACCESS_TOCKEN", ""),
            "timeout_s": float(env.get("HF_AVATAR_TIMEOUT_SECONDS") or "180"),
            "image_path": str(avatar_image_path.resolve()),
        },
        "object_storage": {
            "access_key": env.get("NCP_ACCESS_KEY", ""),
            "secret_key": env.get("NCP_SECRET_KEY", ""),
            "bucket": env.get("NCP_OBJECT_STORAGE_BUCKET") or "mediary-dev",
            "endpoint": (
                env.get("NCP_OBJECT_STORAGE_ENDPOINT")
                or "https://kr.object.ncloudstorage.com"
            ),
            "region": env.get("NCP_OBJECT_STORAGE_REGION") or "kr-standard",
        },
        "db": {
            "host": env.get("DB_HOST", "localhost"),
            "port": int(env.get("DB_PORT", "5432")),
            "dbname": env.get("DB_NAME", "mediary"),
            "user": env.get("DB_USER", ""),
            "password": env.get("DB_PASSWORD", ""),
        },
    }
