"""HTTP client for the map diary API."""

from __future__ import annotations

import os
from typing import Any, Literal

import requests

BASE_URL = os.environ.get(
    "MEDIARY_API_BASE_URL",
    os.environ.get("MEDIARY_API_URL", "http://127.0.0.1:8000"),
).rstrip("/")
_TIMEOUT_S = 10
LocationStatus = Literal["all", "located", "unlocated"]


class MapsApiError(RuntimeError):
    """Raised when the map diary API cannot complete a request."""


def _error_detail(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or f"HTTP {response.status_code}"
    detail = payload.get("detail") if isinstance(payload, dict) else payload
    return str(detail or f"HTTP {response.status_code}")


def fetch_diaries(
    user_id: str,
    *,
    location_status: LocationStatus = "all",
    keyword: str = "",
) -> list[dict[str, Any]]:
    params = {
        "user_id": user_id,
        "location_status": location_status,
        "keyword": keyword,
    }
    try:
        response = requests.get(
            f"{BASE_URL}/api/maps/diaries",
            params=params,
            timeout=_TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise MapsApiError(f"지도 일기 목록을 불러오지 못했습니다: {exc}") from exc
    if not response.ok:
        raise MapsApiError(f"지도 일기 조회 실패: {_error_detail(response)}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise MapsApiError("지도 API가 올바른 JSON을 반환하지 않았습니다.") from exc
    if not isinstance(payload, list):
        raise MapsApiError("지도 API 응답 형식이 올바르지 않습니다.")
    return payload


def create_diary_location(
    *,
    user_id: str,
    version_id: str,
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    payload = {
        "user_id": user_id,
        "version_id": version_id,
        "latitude": round(latitude, 8),
        "longitude": round(longitude, 8),
    }
    try:
        response = requests.post(
            f"{BASE_URL}/api/maps/diaries",
            json=payload,
            timeout=_TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise MapsApiError(f"일기 위치를 저장하지 못했습니다: {exc}") from exc
    if not response.ok:
        raise MapsApiError(f"일기 위치 저장 실패: {_error_detail(response)}")
    try:
        result = response.json()
    except ValueError as exc:
        raise MapsApiError("지도 API가 올바른 JSON을 반환하지 않았습니다.") from exc
    if not isinstance(result, dict):
        raise MapsApiError("지도 API 응답 형식이 올바르지 않습니다.")
    return result
