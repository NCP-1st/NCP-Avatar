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
    status: str | None = None,
    emotion: str | None = None,
    keyword: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    radius: float = 1000.0,
) -> tuple[dict[str, Any] | None, str | None]:
    """Fetch calendar data and return either payload or a readable error."""
    url = f"{BACKEND_URL}/calendar"
    params: dict[str, Any] = {
        "user_id": user_id,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "radius": radius,
    }

    if status:
        params["status"] = status
    if emotion:
        params["emotion"] = emotion
    if keyword:
        params["keyword"] = keyword
    if latitude is not None and longitude is not None:
        params["latitude"] = latitude
        params["longitude"] = longitude

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
