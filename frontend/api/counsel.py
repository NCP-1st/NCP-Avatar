"""상담 API 클라이언트. 페이지에서 직접 HTTP를 호출하지 않는다."""

from __future__ import annotations

import os
from typing import Any

import requests


BASE_URL = os.getenv("MEDIARY_API_BASE_URL", "http://localhost:8000")

# 백엔드는 라우터를 `/api` 아래에 붙인다 (backend/main.py 규칙).
CHAT_PATH = "/api/counsel/chat"

TIMEOUT_S = 60  # 상담 응답은 모델 호출을 포함한다


class CounselApiError(RuntimeError):
    """백엔드 호출 실패. 페이지는 이 예외를 잡아 실패 상태를 그린다."""


def send_message(
    *,
    user_id: str,
    message: str,
    counsel_id: str | None,
    memory_scope: dict[str, Any],
) -> dict[str, Any]:
    """POST /counsel/chat — 상담 응답 한 턴을 받아온다.

    대화 이력은 보내지 않는다. 서버가 `counsel_id`로 저장소에서 읽는다.
    """
    payload = {
        "user_id": user_id,
        "message": message,
        "counsel_id": counsel_id,
        "memory_scope": memory_scope,
    }
    try:
        response = requests.post(
            f"{BASE_URL}{CHAT_PATH}",
            json=payload,
            timeout=TIMEOUT_S,
        )
        response.raise_for_status()
        return response.json()
    except requests.Timeout as exc:
        raise CounselApiError("응답이 너무 오래 걸려요. 다시 시도해 주세요.") from exc
    except requests.RequestException as exc:
        raise CounselApiError(f"상담 서버에 연결하지 못했어요. ({exc})") from exc
