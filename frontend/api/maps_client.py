"""지도 일기 백엔드 API 클라이언트.

페이지에서 직접 HTTP를 호출하지 않고 이 모듈을 경유한다 (CLAUDE.md 배치 원칙).
백엔드 주소는 MEDIARY_API_URL 환경변수로 바꿀 수 있다 (기본 localhost:8000).
"""

from __future__ import annotations

import os

import requests

BASE_URL = os.environ.get("MEDIARY_API_URL", "http://127.0.0.1:8000")
_TIMEOUT_S = 5


class MapsApiError(RuntimeError):
    """지도 일기 API 호출 실패."""


def fetch_diaries() -> list[dict]:
    """저장된 일기 목록을 조회한다."""
    try:
        res = requests.get(f"{BASE_URL}/api/maps/diaries", timeout=_TIMEOUT_S)
        res.raise_for_status()
        return res.json()
    except requests.RequestException as e:
        raise MapsApiError(f"일기 목록 조회 실패: {e}") from e


def create_diary(
    title: str, summary: str, emotion: str, lat: float, lng: float
) -> dict:
    """지정한 위치에 일기를 저장하고, 서버가 부여한 id/날짜가 포함된 일기를 반환한다."""
    payload = {
        "title": title,
        "summary": summary,
        "emotion": emotion,
        "lat": round(lat, 6),
        "lng": round(lng, 6),
    }
    try:
        res = requests.post(
            f"{BASE_URL}/api/maps/diaries", json=payload, timeout=_TIMEOUT_S
        )
        res.raise_for_status()
        return res.json()
    except requests.RequestException as e:
        raise MapsApiError(f"일기 저장 실패: {e}") from e
