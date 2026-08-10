"""Environment-only configuration for replaceable external adapters."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from dotenv import dotenv_values

_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def load_config(env_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """Return a fresh config. OS variables override `.env`; secrets have no defaults."""
    path = Path(env_path) if env_path else _ENV_PATH
    file_values = {key: value for key, value in dotenv_values(path).items() if value is not None}
    env = {**file_values, **os.environ}
    return {
        "mode": env.get("MEDIARY_ADAPTER_MODE", "dummy").lower(),
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
        "object_storage": {
            "access_key": env.get("NCP_ACCESS_KEY", ""),
            "secret_key": env.get("NCP_SECRET_KEY", ""),
            "bucket": env.get("NCP_OBJECT_STORAGE_BUCKET", "mediary-dev"),
            "endpoint": env.get("NCP_OBJECT_STORAGE_ENDPOINT", "https://kr.object.ncloudstorage.com"),
        },
        "db": {
            "host": env.get("DB_HOST", "localhost"),
            "port": int(env.get("DB_PORT", "3306")),
            "dbname": env.get("DB_NAME", "mediary"),
            "user": env.get("DB_USER", ""),
            "password": env.get("DB_PASSWORD", ""),
        },
    }


@dataclass(frozen=True)
class Settings:
    adapter_mode: str
    clova_speech_client_id: str
    clova_speech_client_secret: str

    @property
    def use_clova(self) -> bool:
        return self.adapter_mode == "clova"

    def validate_clova(self) -> None:
        required = {
            "CLOVA_SPEECH_CLIENT_ID": self.clova_speech_client_id,
            "CLOVA_SPEECH_CLIENT_SECRET": self.clova_speech_client_secret,
        }
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise RuntimeError(f"missing CLOVA settings: {', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    config = load_config()
    mode = config["mode"]
    if mode not in {"dummy", "clova"}:
        raise RuntimeError("MEDIARY_ADAPTER_MODE must be 'dummy' or 'clova'")
    return Settings(
        adapter_mode=mode,
        clova_speech_client_id=config["speech"]["client_id"],
        clova_speech_client_secret=(
            config["speech"]["client_secret"] or config["speech"]["secret_key"]
        ),
    )
