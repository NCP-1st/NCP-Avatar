"""Diary session status helpers shared by calendar API and UI (K-01).

The diary workflow persists richer DB statuses than the calendar displays.
``awaiting_approval`` (draft ready, user review pending) maps to calendar
``processing`` so monthly summaries and filters stay aligned with PRD K-01.
"""

from __future__ import annotations

from enum import StrEnum


class CalendarSessionStatus(StrEnum):
    ACTIVE = "active"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


# DB values written by SQLAlchemyDiaryRepository and diary jobs.
DB_STATUS_TO_CALENDAR: dict[str, CalendarSessionStatus] = {
    "active": CalendarSessionStatus.ACTIVE,
    "awaiting_approval": CalendarSessionStatus.PROCESSING,
    "processing": CalendarSessionStatus.PROCESSING,
    "completed": CalendarSessionStatus.COMPLETED,
    "failed": CalendarSessionStatus.FAILED,
}

CALENDAR_FILTER_TO_DB: dict[str, list[str]] = {
    CalendarSessionStatus.ACTIVE: ["active"],
    CalendarSessionStatus.PROCESSING: ["processing", "awaiting_approval"],
    CalendarSessionStatus.COMPLETED: ["completed"],
    CalendarSessionStatus.FAILED: ["failed"],
}


def normalize_session_status(db_status: str) -> str:
    """Return the calendar-facing status for a persisted session status."""
    mapped = DB_STATUS_TO_CALENDAR.get(db_status)
    if mapped is not None:
        return mapped.value
    return CalendarSessionStatus.ACTIVE.value


def db_statuses_for_calendar_filter(calendar_status: str) -> list[str] | None:
    """Expand a calendar filter value into DB statuses, or None if unknown."""
    if calendar_status in CALENDAR_FILTER_TO_DB:
        return CALENDAR_FILTER_TO_DB[calendar_status]
    if calendar_status in DB_STATUS_TO_CALENDAR:
        return [calendar_status]
    return None
