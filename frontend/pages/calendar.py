"""Streamlit calendar page for diary history browsing."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any

import streamlit as st

from api.calendar import fetch_calendar_data, fetch_calendar_entry_detail, fetch_calendar_emotions
from api.diary import download_video


@st.cache_data(show_spinner=False, ttl=300)
def load_calendar_avatar_video(session_id: str, version_id: str) -> bytes:
    return download_video(session_id, version_id)


def get_calendar_video_version_id(detail: dict[str, Any]) -> str | None:
    versions = detail.get("versions") or []
    approved_versions = [version for version in versions if version.get("approved")]
    candidates = approved_versions or versions
    if not candidates:
        return None
    return candidates[0].get("version_id")


def svg_icon(name: str, *, size: int = 18, stroke: str = "#36536B") -> str:
    icons = {
        "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4"/><path d="M8 3v4"/><path d="M3 11h18"/>',
        "search": '<circle cx="11" cy="11" r="6"/><path d="m20 20-3.5-3.5"/>',
        "map-pin": '<path d="M12 21s6-4.35 6-10a6 6 0 1 0-12 0c0 5.65 6 10 6 10Z"/><circle cx="12" cy="11" r="2.5"/>',
        "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
        "check": '<circle cx="12" cy="12" r="9"/><path d="m8.5 12 2.2 2.2 4.8-4.8"/>',
        "edit": '<path d="M12 20h9"/><path d="m16.5 3.5 4 4L8 20l-5 1 1-5Z"/>',
        "warning": '<path d="M12 3 2.8 19h18.4L12 3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/>',
        "sparkle": '<path d="m12 3 1.8 4.2L18 9l-4.2 1.8L12 15l-1.8-4.2L6 9l4.2-1.8L12 3Z"/><path d="M19 15l.9 2.1L22 18l-2.1.9L19 21l-.9-2.1L16 18l2.1-.9L19 15Z"/><path d="M5 14l.7 1.6L7.3 16l-1.6.7L5 18.3l-.7-1.6L2.7 16l1.6-.7L5 14Z"/>',
        "image": '<rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="9" cy="10" r="1.5"/><path d="m21 16-5-5-7 7"/><path d="m13 18-2.5-2.5"/>',
        "file-text": '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"/><path d="M14 3v5h5"/><path d="M9 13h6"/><path d="M9 17h6"/><path d="M9 9h1"/>',
        "mic": '<rect x="9" y="3" width="6" height="11" rx="3"/><path d="M6 11a6 6 0 0 0 12 0"/><path d="M12 17v4"/><path d="M9 21h6"/>',
        "video": '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="m16 10 5-3v10l-5-3Z"/>',
        "layers": '<path d="m12 3 9 4.5-9 4.5-9-4.5L12 3Z"/><path d="m3 12 9 4.5 9-4.5"/><path d="m3 16.5 9 4.5 9-4.5"/>',
        "chevron-right": '<path d="m9 6 6 6-6 6"/>',
        "filter": '<path d="M4 6h16"/><path d="M7 12h10"/><path d="M10 18h4"/>',
        "grid": '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/><rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    }
    body = icons[name]
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        f'xmlns="http://www.w3.org/2000/svg" stroke="{stroke}" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round">'
        f"{body}</svg>"
    )


def icon_text(name: str, text: str, *, size: int = 18, stroke: str = "#36536B") -> str:
    return (
        '<span class="icon-text">'
        f"{svg_icon(name, size=size, stroke=stroke)}"
        f"<span>{text}</span>"
        "</span>"
    )


st.markdown(
    """
    <style>
    .calendar-shell {
        background:
            radial-gradient(circle at top left, rgba(200, 232, 255, 0.75), transparent 28%),
            linear-gradient(180deg, #fbfdff 0%, #eef6ff 100%);
        border: 1px solid #d8e6f3;
        border-radius: 30px;
        padding: 30px;
        margin-top: 18px;
        margin-bottom: 28px;
        box-shadow: 0 18px 50px rgba(27, 59, 90, 0.06);
    }
    .hero-row {
        display: flex;
        justify-content: space-between;
        gap: 16px;
        align-items: flex-start;
        margin-bottom: 20px;
    }
    .hero-title {
        font-size: 2.7rem;
        font-weight: 900;
        color: #14324A;
        letter-spacing: -0.02em;
        margin-bottom: 8px;
    }
    .hero-subtitle {
        color: #587187;
        font-size: 1rem;
        line-height: 1.6;
        max-width: 760px;
    }
    .hero-chip {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        border: 1px solid #d9e4ef;
        background: rgba(255,255,255,0.9);
        border-radius: 999px;
        padding: 10px 14px;
        color: #36536B;
        font-size: 0.9rem;
        font-weight: 700;
        white-space: nowrap;
    }
    .icon-text {
        display: inline-flex;
        align-items: center;
        gap: 8px;
    }
    .toolbar-card {
        background: rgba(255,255,255,0.9);
        border: 1px solid #d8e6f3;
        border-radius: 22px;
        padding: 16px 18px 14px 18px;
        margin-top: 12px;
        margin-bottom: 18px;
        box-shadow: 0 8px 22px rgba(27, 59, 90, 0.04);
    }
    .section-label {
        font-size: 0.9rem;
        font-weight: 800;
        color: #36536B;
        margin-bottom: 10px;
    }
    .summary-card {
        background: rgba(255, 255, 255, 0.92);
        border: 1px solid #d9e6f2;
        border-radius: 20px;
        padding: 18px;
        min-height: 118px;
        margin-top: 10px;
        margin-bottom: 10px;
        box-shadow: 0 10px 24px rgba(27, 59, 90, 0.05);
    }
    .summary-card .top {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 10px;
    }
    .summary-label {
        color: #5A7184;
        font-size: 0.92rem;
        font-weight: 700;
    }
    .summary-value {
        color: #12324A;
        font-size: 1.85rem;
        font-weight: 900;
        line-height: 1.05;
    }
    .summary-caption {
        color: #778B9C;
        font-size: 0.82rem;
        line-height: 1.5;
    }
    .legend-wrap {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        margin-bottom: 14px;
    }
    .legend-chip {
        display: inline-flex;
        align-items: center;
        gap: 8px;
        background: rgba(255,255,255,0.94);
        border: 1px solid #d7e3ee;
        color: #36536B;
        border-radius: 999px;
        padding: 8px 12px;
        font-size: 0.85rem;
        font-weight: 800;
    }
    .weekday-header {
        text-align: center;
        padding: 10px 0;
        color: #4F6579;
        font-size: 0.92rem;
        font-weight: 800;
    }
    .detail-panel {
        background: rgba(255,255,255,0.95);
        border: 1px solid #d8e6f3;
        border-radius: 22px;
        padding: 20px;
        margin-top: 12px;
        margin-bottom: 16px;
        box-shadow: 0 14px 32px rgba(27, 59, 90, 0.06);
    }
    .detail-shell {
        background: linear-gradient(180deg, rgba(248, 251, 255, 0.96), rgba(255, 255, 255, 0.98));
        border: 1px solid #d7e6f3;
        border-radius: 24px;
        padding: 20px;
        margin-bottom: 18px;
    }
    .detail-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        flex-wrap: wrap;
        margin-bottom: 14px;
    }
    .detail-title {
        display: flex;
        align-items: center;
        gap: 10px;
        font-size: 1.2rem;
        font-weight: 900;
        color: #14324A;
        margin-bottom: 8px;
    }
    .detail-date {
        color: #B7B8C0;
        font-size: 0.88rem;
        white-space: nowrap;
    }
    .section-title {
        display: flex;
        align-items: center;
        gap: 8px;
        color: #14324A;
        font-size: 0.98rem;
        font-weight: 900;
        margin-top: 0.9rem;
        margin-bottom: 0.5rem;
    }
    .record-list-shell {
        display: grid;
        gap: 10px;
        margin-top: 12px;
        margin-bottom: 16px;
    }
    .record-list-card {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        width: 100%;
        padding: 12px 14px;
        border-radius: 16px;
        border: 1px solid #d9e6f2;
        background: linear-gradient(180deg, rgba(255,255,255,0.97), rgba(245,249,255,0.96));
        box-shadow: 0 6px 14px rgba(18, 50, 74, 0.025);
        transition: all 0.22s ease;
    }
    .record-list-card:hover {
        border-color: #9dc0df;
        transform: translateY(-2px);
        box-shadow: 0 12px 24px rgba(18, 50, 74, 0.08);
        background: linear-gradient(180deg, rgba(245,250,255,1), rgba(235,244,255,1));
    }
    .record-list-card.is-selected {
        border-color: #7aa9d6;
        background: linear-gradient(180deg, rgba(232,243,255,1), rgba(245,250,255,1));
        box-shadow: 0 0 0 3px rgba(110, 168, 216, 0.16), 0 12px 24px rgba(18, 50, 74, 0.08);
    }
    .record-list-main {
        flex: 1;
        min-width: 0;
    }
    .record-list-title {
        font-size: 1rem;
        font-weight: 800;
        color: #14324A;
        margin-bottom: 4px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    .record-list-sub {
        color: #5c7387;
        font-size: 0.83rem;
        line-height: 1.5;
    }
    .record-badge {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        padding: 6px 10px;
        border-radius: 999px;
        font-size: 0.75rem;
        font-weight: 800;
        border: 1px solid transparent;
        letter-spacing: 0.02em;
    }
    .record-badge.completed { background: linear-gradient(135deg, #eafcf0, #d5f2df); color: #166b46; border-color: #cfe9d8; box-shadow: inset 0 1px 0 rgba(255,255,255,0.7); }
    .record-badge.processing { background: linear-gradient(135deg, #fff8e7, #f9ebc4); color: #8a5d00; border-color: #f1d494; box-shadow: inset 0 1px 0 rgba(255,255,255,0.7); }
    .record-badge.failed { background: linear-gradient(135deg, #fff0ee, #f9d5d0); color: #a1362f; border-color: #f2c8c2; box-shadow: inset 0 1px 0 rgba(255,255,255,0.7); }
    .record-badge.active { background: linear-gradient(135deg, #eef5ff, #dfeeff); color: #2d5e9a; border-color: #d5e5ff; box-shadow: inset 0 1px 0 rgba(255,255,255,0.7); }
    [data-testid="stPopover"] > button {
        width: 100%;
        min-height: 2.5rem;
        background: #0E1117;
        border: 1px solid #3A3C46;
        border-radius: 8px;
        color: #F7F7F8;
        font-weight: 400;
        box-shadow: none;
        justify-content: space-between;
    }
    .st-key-calendar_month_trigger button[data-testid^="stBaseButton"] {
        width: 100% !important;
        height: 2.5rem !important;
        min-height: 2.5rem !important;
        margin: 0 !important;
        padding: 0 0.75rem !important;
        border: 1px solid #3A3C46 !important;
        border-radius: 8px !important;
        background: #0E1117 !important;
        color: #F7F7F8 !important;
        box-shadow: none !important;
        display: flex !important;
        flex-direction: row !important;
        align-items: center !important;
        justify-content: space-between !important;
        font-weight: 400 !important;
        text-align: left !important;
    }
    .st-key-calendar_month_trigger button[data-testid^="stBaseButton"] > div,
    .st-key-calendar_month_trigger button[data-testid^="stBaseButton"] span {
        width: 100% !important;
    }
    .st-key-calendar_month_trigger button[data-testid^="stBaseButton"] p {
        width: 100% !important;
        margin: 0 !important;
        text-align: left !important;
    }
    [data-testid="stPopover"] > button:hover {
        border-color: #6B6D78;
        box-shadow: none;
    }
    [data-testid="stPopover"] > div {
        border-radius: 18px;
        padding: 8px;
        background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(244,249,255,0.99));
    }
    [data-testid="stPopoverBody"] div.stButton > button {
        width: auto !important;
        min-height: 2.5rem !important;
        padding: 0.45rem 1rem !important;
        border-radius: 10px !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    [data-testid="stPopoverBody"] div[data-testid="stHorizontalBlock"]:last-of-type {
        justify-content: flex-end;
    }
    [data-testid="stPopoverBody"] div.stButton > button[kind="secondary"] {
        background: #FFFFFF !important;
        border-color: #FFFFFF !important;
        color: #111218 !important;
    }
    .st-key-calendar_month_dialog_apply div.stButton > button {
        width: 100% !important;
        height: 2.65rem !important;
        min-height: 2.65rem !important;
        margin: 0 !important;
        padding: 0.45rem 1rem !important;
        border-radius: 10px !important;
        background: #FFFFFF !important;
        border: 1px solid #FFFFFF !important;
        color: #111218 !important;
        display: inline-flex !important;
        flex-direction: row !important;
        align-items: center !important;
        justify-content: center !important;
        font-weight: 800 !important;
    }
    div[role="dialog"] {
        border-radius: 22px !important;
        box-shadow: 0 18px 44px rgba(18, 50, 74, 0.12) !important;
        border: 1px solid #d9e6f2 !important;
        background: linear-gradient(180deg, rgba(255,255,255,0.99), rgba(244,249,255,0.99)) !important;
    }
    div[role="dialog"]:has(> div:empty) {
        display: none !important;
    }
    div[role="dialog"] > div[data-testid="stDialog"] {
        background: transparent !important;
    }
    .metric-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 7px 11px;
        border-radius: 999px;
        font-size: 0.84rem;
        font-weight: 800;
        margin-right: 6px;
        margin-bottom: 6px;
        letter-spacing: 0.01em;
    }
    .pill-completed {
        background: linear-gradient(135deg, #ebfdf0, #d5f2df);
        color: #166b46;
        border: 1px solid #cfe9d8;
    }
    .pill-processing {
        background: linear-gradient(135deg, #fff7e7, #f9e7ba);
        color: #8a5d00;
        border: 1px solid #f1d596;
    }
    .pill-failed {
        background: linear-gradient(135deg, #fff0ee, #f9d5d0);
        color: #a1362f;
        border: 1px solid #f2c8c2;
    }
    .pill-active {
        background: linear-gradient(135deg, #eef5ff, #dfeeff);
        color: #2d5e9a;
        border: 1px solid #d5e5ff;
    }
    .emotion-badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        margin-right: 6px;
        margin-bottom: 6px;
        padding: 7px 11px;
        border-radius: 999px;
        background: #EDF6FF;
        color: #234767;
        border: 1px solid #D4E6F8;
        font-weight: 800;
        font-size: 0.84rem;
    }
    .empty-state {
        background: rgba(248, 251, 255, 0.92);
        border: 1px dashed #C8D7E5;
        border-radius: 16px;
        padding: 16px;
        text-align: center;
        color: #61798D;
    }
    .quick-summary {
        color: #4F6579;
        font-size: 0.92rem;
        line-height: 1.6;
    }
    div.stButton > button {
        width: 100%;
        min-height: 154px;
        border-radius: 20px;
        border: 1px solid #d8e5ef;
        background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(246,250,255,0.98) 100%);
        color: #14324A;
        font-weight: 800;
        font-size: 0.97rem;
        line-height: 1.45;
        padding: 14px 12px;
        margin: 4px 0 10px 0;
        box-shadow: 0 10px 22px rgba(18, 50, 74, 0.045);
        transition: all 0.18s ease;
        text-align: left;
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        justify-content: flex-start;
        white-space: normal;
    }
    div[class*="st-key-calendar_20"] div.stButton button,
    div[class*="st-key-calendar_20"] button[data-testid^="stBaseButton"] {
        height: 154px !important;
        min-height: 154px !important;
        width: 100% !important;
        box-sizing: border-box !important;
        border-radius: 20px !important;
        padding: 15px 13px !important;
        margin: 4px 0 10px !important;
        background: #191A20 !important;
        border: 1px solid #343640 !important;
        color: #F7F7F8 !important;
        box-shadow: none !important;
        display: flex !important;
        flex-direction: column !important;
        align-items: flex-start !important;
        justify-content: flex-start !important;
        text-align: left !important;
        line-height: 1.45 !important;
        white-space: pre-line !important;
    }
    div[class*="st-key-calendar_20"] div.stButton button:hover,
    div[class*="st-key-calendar_20"] button[data-testid^="stBaseButton"]:hover {
        border-color: #62646F !important;
        background: #22242C !important;
        color: #FFFFFF !important;
    }
    div.stButton > button[kind="secondary"] {
        background-color: #ffffff !important;
        background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(246,250,255,0.98) 100%) !important;
        border: 1px solid #d8e5ef !important;
        color: #14324A !important;
    }
    div.stButton > button:hover {
        border-color: #c5d9ed !important;
        box-shadow: 0 14px 28px rgba(18, 50, 74, 0.08);
        transform: translateY(-2px);
    }
    div.stButton > button:focus {
        box-shadow: 0 0 0 3px rgba(76, 132, 182, 0.18);
        outline: none;
    }
    .calendar-target-marker {
        display: block;
        width: 100%;
        height: 0;
    }
    .calendar-empty-day {
        width: 100%;
        height: 154px;
        min-height: 154px;
        box-sizing: border-box;
        border: 1px solid #343640;
        border-radius: 20px;
        padding: 15px 13px;
        margin: 4px 0 10px;
        color: #D7D8DC;
        background: #191A20;
        font-size: 1rem;
        font-weight: 800;
    }
    .st-key-weekly_records div.stButton > button {
        width: auto !important;
        min-height: 2.5rem !important;
        padding: 0.45rem 0.9rem !important;
        margin: 0 !important;
        border-radius: 10px !important;
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
    }
    /* 필터·목록·상세 팝업을 다른 Mediary 페이지의 다크 톤과 통일한다. */
    .toolbar-card,
    .summary-card,
    .detail-panel,
    .detail-shell,
    .record-list-card,
    .legend-chip,
    .hero-chip {
        background: #1E1F26 !important;
        border-color: #343640 !important;
        box-shadow: none !important;
    }
    .section-label,
    .detail-title,
    .section-title,
    .record-list-title,
    .summary-value {
        color: #F7F7F8 !important;
    }
    .section-label svg,
    .detail-title svg,
    .section-title svg {
        stroke: #F7F7F8 !important;
    }
    .record-list-sub,
    .summary-label,
    .summary-caption,
    .weekday-header,
    .quick-summary {
        color: #B7B8C0 !important;
    }
    .emotion-badge {
        background: #292B34;
        color: #F1F1F3;
        border-color: #41434E;
    }
    [data-testid="stPopover"] > button,
    [data-testid="stPopover"] > div,
    div[role="dialog"] {
        background: #1E1F26 !important;
        color: #F7F7F8 !important;
        border-color: #3A3C46 !important;
    }
    .empty-state {
        background: #1E1F26;
        border-color: #454751;
        color: #B7B8C0;
    }
    div.stButton > button[kind="secondary"] {
        background: #24262E !important;
        border-color: #3A3C46 !important;
        color: #F7F7F8 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

EMOTION_LABELS = {
    "happy": "기쁨",
    "excited": "신남",
    "calm": "평온",
    "tired": "피곤",
    "sad": "슬픔",
}

EMOTION_ICON_NAMES = {
    "happy": "sparkle",
    "excited": "sparkle",
    "calm": "clock",
    "tired": "clock",
    "sad": "warning",
}

def format_emotion_label(tag: str) -> str:
    return EMOTION_LABELS.get(tag.lower(), tag)


def render_emotion_badges(emotion_tags: list[str] | None) -> None:
    if not emotion_tags:
        st.caption("감정 태그 없음")
        return

    html = "".join(
        f'<span class="emotion-badge">{svg_icon(EMOTION_ICON_NAMES.get(tag.lower(), "sparkle"), size=14, stroke="#234767")}<span>{format_emotion_label(tag)}</span></span>'
        for tag in emotion_tags
    )
    st.markdown(html, unsafe_allow_html=True)


def get_month_range(year: int, month: int) -> tuple[date, date]:
    start = date(year, month, 1)
    if month == 12:
        return start, date(year + 1, 1, 1) - timedelta(days=1)
    return start, date(year, month + 1, 1) - timedelta(days=1)


def build_entries_by_date(entries: list[dict[str, Any]]) -> dict[date, list[dict[str, Any]]]:
    mapped: dict[date, list[dict[str, Any]]] = {}
    for entry in entries:
        mapped.setdefault(date.fromisoformat(entry["diary_date"]), []).append(entry)
    return mapped


def pick_primary_entry(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return entries[0]


def get_preview_line(entry: dict[str, Any] | None) -> str:
    if not entry:
        return "기록 없음"
    if entry.get("title"):
        title = str(entry["title"]).strip()
        return title if len(title) <= 14 else f"{title[:14]}…"
    if entry.get("summary"):
        summary = str(entry["summary"]).strip()
        return summary if len(summary) <= 14 else f"{summary[:14]}…"
    return "기록 있음"


def detect_asset_label(asset_type: str) -> str:
    return {
        "image": "이미지",
        "photo": "이미지",
        "voice": "음성",
        "audio": "음성",
        "text": "텍스트",
    }.get(asset_type, asset_type)


def detect_asset_icon(asset_type: str) -> str:
    return {
        "image": "image",
        "photo": "image",
        "voice": "mic",
        "audio": "mic",
        "text": "file-text",
    }.get(asset_type, "file-text")


def open_entry_dialog(entry: dict[str, Any], user_id: str) -> None:
    detail, detail_error = fetch_calendar_entry_detail(user_id, entry["session_id"])
    if detail_error:
        st.warning(f"상세 정보를 불러오지 못했습니다. 미리보기 데이터를 표시합니다. ({detail_error})")
        detail = entry
    elif detail:
        detail = {**entry, **detail}
    else:
        detail = entry

    @st.dialog(detail.get("title") or "제목 없는 기록", width="medium")
    def _dialog() -> None:
        st.caption(f"작성일: {detail.get('diary_date') or '미기록'}")

        st.markdown(
            f"<div class='section-title'>{svg_icon('video', size=16, stroke='#F7F7F8')}<span>아바타 영상</span></div>",
            unsafe_allow_html=True,
        )
        if detail.get("video_status") == "completed" and detail.get("video_url"):
            video_version_id = get_calendar_video_version_id(detail)
            if video_version_id:
                try:
                    video_bytes = load_calendar_avatar_video(
                        detail["session_id"], video_version_id
                    )
                    st.video(video_bytes)
                except RuntimeError as exc:
                    st.error(str(exc))
            else:
                st.caption("영상에 연결된 일기 버전을 찾을 수 없습니다.")
        elif detail.get("video_status") == "processing":
            st.info("아바타 영상 렌더링이 진행 중입니다.")
        elif detail.get("video_status") == "failed":
            st.error("아바타 영상 생성에 실패했습니다.")
        elif detail.get("video_status") == "pending":
            st.info("아바타 영상 생성 대기 중입니다.")
        else:
            st.caption("연결된 영상이 없습니다.")

        summary_col, emotion_col = st.columns(2, gap="medium")
        with summary_col:
            st.markdown(
                f"<div class='section-title'>{svg_icon('file-text', size=16, stroke='#F7F7F8')}<span>일기 요약</span></div>",
                unsafe_allow_html=True,
            )
            st.write(detail.get("summary") or "요약이 없습니다.")
        with emotion_col:
            st.markdown(
                f"<div class='section-title'>{svg_icon('sparkle', size=16, stroke='#F7F7F8')}<span>감정 태그</span></div>",
                unsafe_allow_html=True,
            )
            render_emotion_badges(detail.get("emotion_tags"))

        paragraphs = detail.get("paragraphs") or []
        diary_content = (
            detail.get("content")
            or detail.get("script")
            or "\n\n".join(paragraphs)
        )
        if diary_content:
            st.markdown(
                f"<div class='section-title'>{svg_icon('file-text', size=16, stroke='#F7F7F8')}<span>일기 본문</span></div>",
                unsafe_allow_html=True,
            )
            st.write(diary_content)

        narration_text = detail.get("narration_text")
        if narration_text:
            st.markdown(
                f"<div class='section-title'>{svg_icon('mic', size=16, stroke='#F7F7F8')}<span>나레이션 대본</span></div>",
                unsafe_allow_html=True,
            )
            st.write(narration_text)
        elif detail.get("narration_status") == "failed":
            st.error("나레이션 대본 생성에 실패했습니다.")

        media_inputs = [
            asset
            for asset in detail.get("diary_inputs", [])
            if asset.get("type") in {"image", "photo", "voice", "audio"}
        ]
        if media_inputs:
            st.markdown(
                f"<div class='section-title'>{svg_icon('layers', size=16, stroke='#F7F7F8')}<span>첨부한 사진·음성</span></div>",
                unsafe_allow_html=True,
            )
            for asset in media_inputs:
                asset_time = asset.get("captured_at") or asset.get("created_at") or ""
                asset_title = f"{detect_asset_label(asset['type'])} · {asset_time}"
                with st.expander(asset_title.strip(), expanded=False):
                    if asset.get("transcript"):
                        st.write(asset["transcript"])
                    storage_url = asset.get("storage_url")
                    if storage_url and asset["type"] in {"image", "photo"}:
                        st.image(storage_url, use_container_width=True)
                    elif storage_url and asset["type"] in {"voice", "audio"}:
                        st.audio(storage_url)
                    else:
                        st.caption("원본 파일은 현재 세션에서만 임시로 사용됐어요.")

    _dialog()


def render_calendar_grid(
    year: int,
    month: int,
    entries_by_date: dict[date, list[dict[str, Any]]],
) -> None:
    selected_date = st.session_state.get("selected_date")
    st.markdown('<div class="calendar-grid-wrap">', unsafe_allow_html=True)
    week_headers = ["일", "월", "화", "수", "목", "금", "토"]
    header_cols = st.columns(7, gap="small")
    for idx, header in enumerate(week_headers):
        header_cols[idx].markdown(
            f'<div class="weekday-header">{header}</div>',
            unsafe_allow_html=True,
        )

    first_weekday, num_days = calendar.monthrange(year, month)
    first_weekday_pad = (first_weekday + 1) % 7
    current_day = 1

    for week in range(6):
        if current_day > num_days:
            break
        cols = st.columns(7, gap="small")
        for weekday in range(7):
            if week == 0 and weekday < first_weekday_pad:
                cols[weekday].write("")
                continue
            if current_day > num_days:
                cols[weekday].write("")
                continue

            current_date = date(year, month, current_day)
            day_entries = entries_by_date.get(current_date, [])
            entry = pick_primary_entry(day_entries) if day_entries else None
            if entry:
                emotion_tags = entry.get("emotion_tags") or []
                emotion_label = format_emotion_label(emotion_tags[0]) if emotion_tags else "감정 없음"
                preview_line = get_preview_line(entry)
                if len(day_entries) > 1:
                    preview_line = f"{len(day_entries)}건 · {preview_line}"
                label = f"{current_day}\n\n{preview_line}"
                help_text = f"{emotion_label} · 기록 {len(day_entries)}건 · 클릭해서 상세 보기"
            else:
                label = str(current_day)
                help_text = ""

            button_key = f"calendar_{current_date.isoformat()}"
            cols[weekday].markdown(
                f"<div id='calendar-target-{current_date.isoformat()}' class='calendar-target-marker'></div>",
                unsafe_allow_html=True,
            )

            if entry:
                if cols[weekday].button(
                    label,
                    key=button_key,
                    help=help_text,
                    type="secondary",
                ):
                    st.session_state["selected_date"] = current_date
                    st.session_state["selected_entry"] = entry
                    st.session_state["selected_session_id"] = entry.get("session_id")
                    st.session_state["open_dialog"] = True
            else:
                cols[weekday].markdown(
                    f"<div class='calendar-empty-day'>{label}</div>",
                    unsafe_allow_html=True,
                )

            current_day += 1

    st.markdown("</div>", unsafe_allow_html=True)


st.title("📅 캘린더 조회")
st.caption("기간별 일기 기록을 살펴보고 날짜를 선택해 상세 내용을 확인하세요.")

today = date.today()
if "selected_date" not in st.session_state:
    st.session_state["selected_date"] = today
if "selected_entry" not in st.session_state:
    st.session_state["selected_entry"] = None
if "open_dialog" not in st.session_state:
    st.session_state["open_dialog"] = False
if "calendar_anchor_date" not in st.session_state:
    st.session_state["calendar_anchor_date"] = today.replace(day=1)
if "selected_session_id" not in st.session_state:
    st.session_state["selected_session_id"] = None
if "calendar_month_dialog_open" not in st.session_state:
    st.session_state["calendar_month_dialog_open"] = False


def close_month_dialog() -> None:
    st.session_state["calendar_month_dialog_open"] = False


@st.dialog("조회할 월 선택", width="small", on_dismiss=close_month_dialog)
def show_month_dialog() -> None:
    anchor = st.session_state["calendar_anchor_date"]
    year_options = list(range(2024, 2036))
    month_options = list(range(1, 13))
    selected_year = st.selectbox(
        "년도",
        options=year_options,
        index=year_options.index(anchor.year),
        key="calendar_year_select",
    )
    selected_month = st.selectbox(
        "월",
        options=month_options,
        index=month_options.index(anchor.month),
        key="calendar_month_select",
    )
    st.write("")
    with st.container(key="calendar_month_dialog_apply"):
        if st.button("조회 적용", type="secondary", use_container_width=True):
            selected_anchor = date(selected_year, selected_month, 1)
            st.session_state["calendar_anchor_date"] = selected_anchor
            st.session_state["selected_date"] = selected_anchor
            st.session_state["selected_entry"] = None
            st.session_state["calendar_month_dialog_open"] = False
            st.rerun()


st.info("월 선택과 필터를 변경하면 아래 캘린더와 기록 목록에 함께 반영됩니다.")

user_id = "streamlit-test-user"
selected_anchor = st.session_state["calendar_anchor_date"]
start_date, end_date = get_month_range(selected_anchor.year, selected_anchor.month)
emotion_options, _emotion_error = fetch_calendar_emotions(user_id, start_date, end_date)

toolbar_cols = st.columns(3, gap="medium")
with toolbar_cols[0]:
    st.markdown(
        f"<div class='section-label'>{icon_text('calendar', '월 선택')}</div>",
        unsafe_allow_html=True,
    )
    month_trigger = f"{selected_anchor.year}년 {selected_anchor.month}월　⌄"
    with st.container(key="calendar_month_trigger"):
        if st.button(month_trigger, use_container_width=True, type="secondary"):
            st.session_state["calendar_month_dialog_open"] = True

with toolbar_cols[1]:
    st.markdown(
        f"<div class='section-label'>{icon_text('search', '키워드 검색')}</div>",
        unsafe_allow_html=True,
    )
    keyword = st.text_input(
        "키워드 검색",
        placeholder="제목, 요약, 대본 검색",
        label_visibility="collapsed",
    )

with toolbar_cols[2]:
    st.markdown(
        f"<div class='section-label'>{icon_text('sparkle', '감정')}</div>",
        unsafe_allow_html=True,
    )
    emotion_labels = {
        tag: EMOTION_LABELS.get(tag.lower(), tag) for tag in emotion_options
    } or EMOTION_LABELS
    emotion_choice = st.selectbox(
        "감정",
        options=["전체"] + list(emotion_labels.values()),
        label_visibility="collapsed",
    )

if st.session_state["calendar_month_dialog_open"]:
    show_month_dialog()

selected_emotion_key = None
if emotion_choice != "전체":
    label_map = {
        tag: EMOTION_LABELS.get(tag.lower(), tag) for tag in emotion_options
    } if emotion_options else EMOTION_LABELS
    selected_emotion_key = next(
        (key for key, label in label_map.items() if label == emotion_choice),
        None,
    )

with st.spinner("캘린더 데이터를 불러오는 중입니다..."):
    api_result, api_error = fetch_calendar_data(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        status=None,
        emotion=selected_emotion_key,
        keyword=keyword or None,
        latitude=None,
        longitude=None,
        radius=1000.0,
    )

if api_error:
    st.error(api_error)
    entries = []
else:
    entries = api_result.get("entries", []) if api_result else []

filtered_entries = entries

entries_by_date = build_entries_by_date(filtered_entries)
selected_date = st.session_state.get("selected_date", today)
selected_entry = None
if filtered_entries:
    if start_date <= selected_date <= end_date:
        day_entries = entries_by_date.get(selected_date, [])
        if day_entries:
            selected_session_id = st.session_state.get("selected_session_id")
            selected_entry = next(
                (item for item in day_entries if item.get("session_id") == selected_session_id),
                pick_primary_entry(day_entries),
            )
    if selected_entry is None:
        selected_entry = filtered_entries[0]
        selected_date = date.fromisoformat(selected_entry["diary_date"])
        st.session_state["selected_date"] = selected_date
        st.session_state["selected_session_id"] = selected_entry.get("session_id")
else:
    st.session_state["selected_date"] = selected_date

st.markdown(
    f"<div style='font-size:1.55rem; font-weight:850; color:#F7F7F8; margin:1.2rem 0 0.4rem;'>{selected_anchor.year}년 {selected_anchor.month}월</div>",
    unsafe_allow_html=True,
)
render_calendar_grid(selected_anchor.year, selected_anchor.month, entries_by_date)

week_start = selected_date - timedelta(days=(selected_date.weekday() + 1) % 7)
week_end = week_start + timedelta(days=6)
weekly_entries = [
    entry
    for entry in filtered_entries
    if week_start <= date.fromisoformat(entry["diary_date"]) <= week_end
]

st.markdown("### 이번 주 기록")
with st.container(key="weekly_records"):
    if weekly_entries:
        for index, entry in enumerate(weekly_entries):
            entry_date = date.fromisoformat(entry["diary_date"])
            title = entry.get("title") or "제목 없는 기록"
            summary_text = entry.get("summary") or "요약 내용이 아직 없습니다."
            content_col, action_col = st.columns([7, 1], vertical_alignment="center")
            with content_col:
                st.markdown(f"**{entry_date.day}일 · {title}**")
                st.caption(
                    summary_text[:100] + ("…" if len(summary_text) > 100 else "")
                )
            with action_col:
                if st.button(
                    "상세 보기",
                    key=f"week_entry_{entry['session_id']}",
                    type="secondary",
                ):
                    st.session_state["selected_date"] = entry_date
                    st.session_state["selected_entry"] = entry
                    st.session_state["selected_session_id"] = entry.get("session_id")
                    st.session_state["open_dialog"] = True
            if index < len(weekly_entries) - 1:
                st.divider()
    else:
        st.caption("선택한 주에는 저장된 일기 기록이 없습니다.")

if st.session_state.get("open_dialog") and st.session_state.get("selected_entry"):
    open_entry_dialog(st.session_state["selected_entry"], user_id)
    st.session_state["open_dialog"] = False
