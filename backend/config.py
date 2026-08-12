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
            "profile": env.get("HF_AVATAR_PROFILE") or "sadtalker",
            "space_id": env.get("HF_AVATAR_SPACE_ID") or "nomad0884/SadTalker",
            "api_name": env.get("HF_AVATAR_API_NAME") or "/predict",
            "token": env.get("HF_TOKEN") or env.get("ACCESS_TOCKEN", ""),
            "timeout_s": float(env.get("HF_AVATAR_TIMEOUT_SECONDS") or "600"),
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
        "counsel": {
            # 상담이 과거 일기를 참조할지 정하는 임계값. 실측으로 조정하는 값이라
            # env로 뺀다 — 코드에 박으면 분포를 보고 옮길 때마다 배포해야 한다.
            # 의미는 `services/knowledge/relevance.py::DiaryThresholds` 참고.
            "diary_min_score": float(env.get("DIARY_MIN_SCORE", "0.5")),
            "diary_min_match_tokens": int(env.get("DIARY_MIN_MATCH_TOKENS", "1")),
            "diary_min_headline_tokens": int(
                env.get("DIARY_MIN_HEADLINE_TOKENS", "1")
            ),
            "diary_strong_score": float(env.get("DIARY_STRONG_SCORE", "0.7")),
            # 벡터 검색용 임계값. 코사인 유사도는 어휘 겹침 비율과 분포가 달라
            # 같은 숫자를 쓸 수 없다. bge-m3 는 같은 언어면 무관한 글끼리도
            # 0.4~0.5가 흔히 나온다. 실측(승인본 31건)으로 잡은 값이다:
            #   관련 있는 질의의 1위  0.584 ~ 0.699
            #   무관한 질의의 1위     0.432 ~ 0.572  ("병원 검진"이 0.572)
            # 경계가 0.01밖에 안 떨어져 있어 넉넉하지 않다. 트래픽이 쌓이면
            # CounselTrace.diary_top_candidate 분포를 보고 다시 잡아야 한다.
            "diary_vec_min_score": float(env.get("DIARY_VEC_MIN_SCORE", "0.58")),
            "diary_vec_strong_score": float(env.get("DIARY_VEC_STRONG_SCORE", "0.58")),
            # "sql"(어휘 겹침) 또는 "vector"(임베딩). 벡터 쪽에 문제가 생기면
            # env 하나로 되돌린다 — 배포 없이 원래 경로로 돌아갈 수 있어야 한다.
            "diary_backend": env.get("COUNSEL_DIARY_BACKEND", "sql"),
        },
        "db": {
            "host": env.get("DB_HOST", "localhost"),
            "port": int(env.get("DB_PORT", "5432")),
            "dbname": env.get("DB_NAME", "mediary"),
            "user": env.get("DB_USER", ""),
            "password": env.get("DB_PASSWORD", ""),
        },
    }
