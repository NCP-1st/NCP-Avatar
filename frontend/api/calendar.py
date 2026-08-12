"""Calendar API client used by the Streamlit calendar page."""

from __future__ import annotations

import os
from datetime import date
from typing import Any

import requests

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000/api")


def fetch_calendar_data(
    user_id: str,
    start_date: date,
    end_date: date,
    status: str | list[str] | None = None,
    emotion: str | None = None,
    keyword: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    radius: float = 1000.0,
) -> tuple[dict[str, Any] | None, str | None]:
    """Fetch lightweight calendar previews for a date range."""
    url = f"{BACKEND_URL}/calendar"
    params: list[tuple[str, Any]] = [
        ("user_id", user_id),
        ("start_date", start_date.isoformat()),
        ("end_date", end_date.isoformat()),
        ("radius", radius),
    ]

    if status:
        status_values = status if isinstance(status, list) else [status]
        for value in status_values:
            params.append(("status", value))
    if emotion:
        params.append(("emotion", emotion))
    if keyword:
        params.append(("keyword", keyword))
    if latitude is not None and longitude is not None:
        params.extend([("latitude", latitude), ("longitude", longitude)])

    return _request_json(url, params)


def fetch_calendar_entry_detail(
    user_id: str,
    session_id: str,
) -> tuple[dict[str, Any] | None, str | None]:
    """Fetch full diary detail for a calendar session."""
    url = f"{BACKEND_URL}/calendar/{session_id}"
    return _request_json(url, {"user_id": user_id})


def fetch_calendar_emotions(
    user_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> tuple[list[str], str | None]:
    """Fetch distinct emotion tags for filter dropdowns."""
    url = f"{BACKEND_URL}/calendar/emotions"
    params: dict[str, Any] = {"user_id": user_id}
    if start_date is not None:
        params["start_date"] = start_date.isoformat()
    if end_date is not None:
        params["end_date"] = end_date.isoformat()

    payload, error = _request_json(url, params)
    if error:
        return [], error
    return payload.get("emotions", []) if payload else [], None


def _request_json(
    url: str,
    params: dict[str, Any] | list[tuple[str, Any]],
) -> tuple[dict[str, Any] | None, str | None]:
    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
    except requests.Timeout:
        return None, "캘린더 조회 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요."
    except requests.HTTPError:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = response.text or "알 수 없는 오류"
        return None, f"백엔드 캘린더 조회 실패: {detail}"
    except requests.RequestException as exc:
        return None, f"백엔드 연결 실패: {exc}"

    return response.json(), None
