"""상담 API 클라이언트. 페이지에서 직접 HTTP를 호출하지 않는다."""

from __future__ import annotations

import os
from typing import Any

import requests


BASE_URL = os.getenv("MEDIARY_API_BASE_URL", "http://localhost:8000")

# 백엔드는 라우터를 `/api` 아래에 붙인다 (backend/main.py 규칙).
CHAT_PATH = "/api/counsel/chat"
SESSIONS_PATH = "/api/counsel/sessions"

TIMEOUT_S = 60  # 상담 응답은 모델 호출을 포함한다
# 목록·이력 조회는 DB만 읽는다. 모델 호출이 없으니 오래 기다릴 이유가 없다.
READ_TIMEOUT_S = 10


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


def list_sessions(*, user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """GET /counsel/sessions — 지난 상담 목록 (최근 활동 순).

    실패해도 예외를 올리지 않고 빈 목록을 준다. 목록은 곁다리라, 이것 때문에
    상담 화면 자체가 안 열리면 손해가 더 크다.
    """
    try:
        response = requests.get(
            f"{BASE_URL}{SESSIONS_PATH}",
            params={"user_id": user_id, "limit": limit},
            timeout=READ_TIMEOUT_S,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException:
        return []


def load_session(*, user_id: str, counsel_id: str) -> dict[str, Any]:
    """GET /counsel/sessions/{counsel_id} — 지난 상담 하나를 통째로."""
    try:
        response = requests.get(
            f"{BASE_URL}{SESSIONS_PATH}/{counsel_id}",
            params={"user_id": user_id},
            timeout=READ_TIMEOUT_S,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise CounselApiError(f"지난 상담을 불러오지 못했어요. ({exc})") from exc
