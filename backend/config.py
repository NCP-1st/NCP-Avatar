"""
설정 로더 — 프로젝트 루트의 .env를 읽어 설정 딕셔너리를 만든다.

load_config()를 호출해 그때그때 dict를
받아 각 서비스 어댑터에 주입한다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from dotenv import dotenv_values


_ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


def load_config(env_path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """.env(또는 지정 경로)를 읽어 새로운 설정 dict를 반환한다.

    - 호출할 때마다 파일을 다시 읽어 변경된 값이 반영된다.
    - 우선순위는 OS 환경변수 > .env 파일 > 기본값이다.
    - os.environ을 변경하지 않는다.
    - 필수 비밀값은 실제 클라이언트/커넥션 생성 시점에 검증한다.
    """
    path = Path(env_path) if env_path else _ENV_PATH
    file_values = {
        key: value
        for key, value in dotenv_values(path).items()
        if value is not None
    }
    env = {**file_values, **os.environ}

    # Speech Recognition과 Voice가 같은 NCP Application을 사용한다.
    # 공통 키를 우선 사용하고 기존 서비스별 환경변수도 호환한다.
    clova_client_id = env.get(
        "CLOVA_API_CLIENT_ID",
        env.get("CLOVA_VOICE_CLIENT_ID", env.get("CLOVA_SPEECH_CLIENT_ID", "")),
    )
    clova_client_secret = env.get(
        "CLOVA_API_CLIENT_SECRET",
        env.get(
            "CLOVA_VOICE_CLIENT_SECRET",
            env.get("CLOVA_SPEECH_SECRET_KEY", ""),
        ),
    )

    return {
        "llm": {
            "provider": "langchain_naver",
            "api_key": env.get("CLOVA_STUDIO_API_KEY", ""),
            "base_url": env.get(
                "CLOVA_STUDIO_BASE_URL",
                "https://clovastudio.stream.ntruss.com",
            ),
            "model_vision": env.get("CLOVA_STUDIO_MODEL_VISION", "HCX-005"),
            "model_reasoning": env.get(
                "CLOVA_STUDIO_MODEL_REASONING",
                "HCX-007",
            ),
            "timeout_s": float(
                env.get("CLOVA_STUDIO_TIMEOUT_SECONDS", "30")
            ),
            "max_tokens": int(env.get("CLOVA_STUDIO_MAX_TOKENS", "1024")),
        },
        "clova_api": {
            "client_id": clova_client_id,
            "client_secret": clova_client_secret,
        },
        "speech": {
            "api_url": env.get(
                "CLOVA_SPEECH_API_URL",
                env.get(
                    "CLOVA_SPEECH_APi_URL",
                    "https://naveropenapi.apigw.ntruss.com/recog/v1/stt",
                ),
            ),
        },
        "voice": {
            "api_url": env.get(
                "CLOVA_VOICE_API_URL",
                "https://naveropenapi.apigw.ntruss.com/tts-premium/v1/tts",
            ),
            "speaker": env.get("CLOVA_VOICE_SPEAKER", "nara"),
            "format": env.get("CLOVA_VOICE_FORMAT", "mp3"),
            "timeout_s": float(env.get("CLOVA_VOICE_TIMEOUT_SECONDS", "30")),
        },
        "object_storage": {
            "access_key": env.get("NCP_ACCESS_KEY", ""),
            "secret_key": env.get("NCP_SECRET_KEY", ""),
            "bucket": env.get("NCP_OBJECT_STORAGE_BUCKET", "mediary-dev"),
            "endpoint": env.get(
                "NCP_OBJECT_STORAGE_ENDPOINT",
                "https://kr.object.ncloudstorage.com",
            ),
        },
        "db": {
            "host": env.get("DB_HOST", "localhost"),
            "port": int(env.get("DB_PORT", "3306")),
            "dbname": env.get("DB_NAME", "mediary"),
            "user": env.get("DB_USER", ""),
            "password": env.get("DB_PASSWORD", ""),
        },
    }
