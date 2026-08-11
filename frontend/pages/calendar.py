"""Streamlit calendar page for diary history browsing."""

from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta
from typing import Any

import streamlit as st

from api.calendar import fetch_calendar_data


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
        background: linear-gradient(180deg, #ffffff, #f4f9ff);
        border: 1px solid #d7e3ee;
        border-radius: 16px;
        color: #14324A;
        font-weight: 800;
        box-shadow: 0 10px 20px rgba(19, 50, 74, 0.04);
    }
    [data-testid="stPopover"] > button:hover {
        border-color: #accae3;
        box-shadow: 0 12px 24px rgba(19, 50, 74, 0.08);
    }
    [data-testid="stPopover"] > div {
        border-radius: 18px;
        padding: 8px;
        background: linear-gradient(180deg, rgba(255,255,255,0.98), rgba(244,249,255,0.99));
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
        min-height: 132px;
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
    div.stButton > button[kind="primary"] {
        border: 2px solid #bfe5c9 !important;
        box-shadow: 0 0 0 3px rgba(191, 229, 201, 0.45), 0 10px 22px rgba(18, 50, 74, 0.08) !important;
        background: linear-gradient(180deg, rgba(250, 255, 251, 1) 0%, rgba(239, 247, 242, 1) 100%) !important;
        color: #14324A !important;
    }
    div.stButton > button[kind="secondary"] {
        border: 1px solid #d8e5ef !important;
        background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(246,250,255,0.98) 100%) !important;
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
    .calendar-target-marker.calendar-focus-flash {
        animation: calendarFocusPulse 1.6s ease-in-out 1;
    }
    @keyframes calendarFocusPulse {
        0% { box-shadow: 0 0 0 rgba(61, 122, 184, 0); }
        30% { box-shadow: 0 0 0 6px rgba(61, 122, 184, 0.18); }
        70% { box-shadow: 0 0 0 12px rgba(75, 179, 200, 0.12); }
        100% { box-shadow: 0 0 0 rgba(61, 122, 184, 0); }
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

STATUS_OPTIONS = {
    "전체": None,
    "작성 중": "active",
    "처리 중": "processing",
    "완료": "completed",
    "실패": "failed",
}

STATUS_META = {
    "active": ("작성 중", "pill-active", "edit"),
    "processing": ("처리 중", "pill-processing", "clock"),
    "completed": ("완료", "pill-completed", "check"),
    "failed": ("실패", "pill-failed", "warning"),
}

SUMMARY_FILTERS = {
    "all": ("전체기록", None),
    "completed": ("완료", "completed"),
    "processing": ("처리 중", "processing"),
    "failed": ("실패", "failed"),
    "approved": ("승인 완료", "approved"),
}

LOCATION_PRESETS = {
    "직접 입력": None,
    "서울시청": (37.5665, 126.9780),
    "부산시청": (35.1796, 129.0756),
    "제주도청": (33.4890, 126.4983),
}


def format_emotion_label(tag: str) -> str:
    return EMOTION_LABELS.get(tag.lower(), tag)


def format_status(status: str) -> tuple[str, str, str]:
    return STATUS_META.get(status, ("알 수 없음", "pill-active", "grid"))


def render_summary_card(
    label: str,
    value: int,
    caption: str,
    icon_name: str,
    filter_key: str,
    active_filter: str,
) -> None:
    is_active = filter_key == active_filter
    card_style = "background: linear-gradient(180deg,#f9fbff,#eef5ff); border: 1px solid #cfe1f2;" if is_active else ""
    button_label = f"{label}\n{value}"
    clicked = st.button(
        button_label,
        key=f"summary_{filter_key}",
        help=caption,
        use_container_width=True,
    )
    if clicked:
        st.session_state["summary_filter"] = filter_key
        st.session_state["scroll_to_record"] = True
    if is_active:
        st.markdown(
            "<style>div[data-testid='stButton'] > button:focus { box-shadow: 0 0 0 3px rgba(89, 140, 204, 0.2); }</style>",
            unsafe_allow_html=True,
        )
    st.markdown(
        f"""
        <div class="summary-card" style="{card_style}">
            <div class="top">
                <div class="summary-label">{label}</div>
                {svg_icon(icon_name, size=20, stroke="#4F6579")}
            </div>
            <div class="summary-value">{value}</div>
            <div class="summary-caption">{caption}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


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


def build_entries_map(entries: list[dict[str, Any]]) -> dict[date, dict[str, Any]]:
    mapped: dict[date, dict[str, Any]] = {}
    for entry in entries:
        mapped[date.fromisoformat(entry["diary_date"])] = entry
    return mapped


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


def filter_entries_by_summary(entries: list[dict[str, Any]], summary_filter: str) -> list[dict[str, Any]]:
    if summary_filter == "all":
        return entries
    if summary_filter == "approved":
        return [entry for entry in entries if entry.get("approved") is True]
    return [entry for entry in entries if entry.get("status") == summary_filter]


def detect_asset_label(asset_type: str) -> str:
    return {
        "image": "이미지",
        "voice": "음성",
        "text": "텍스트",
    }.get(asset_type, asset_type)


def detect_asset_icon(asset_type: str) -> str:
    return {
        "image": "image",
        "voice": "mic",
        "text": "file-text",
    }.get(asset_type, "file-text")


def open_entry_dialog(entry: dict[str, Any]) -> None:
    @st.dialog(entry["diary_date"], width="large")
    def _dialog() -> None:
        status_label, status_class, status_icon = format_status(entry["status"])
        st.markdown('<div class="detail-shell">', unsafe_allow_html=True)
        st.markdown(
            f"<div class='detail-header'><div class='detail-title'>{svg_icon('calendar', size=20, stroke='#14324A')}<span>{entry.get('title') or '제목 없는 기록'}</span></div><div><span class='metric-pill {status_class}'>{svg_icon(status_icon, size=14, stroke='currentColor')}<span>{status_label}</span></span></div></div>",
            unsafe_allow_html=True,
        )
        meta_cols = st.columns([1.6, 1.0, 1.0], gap="small")
        with meta_cols[0]:
            if entry.get("approved"):
                st.markdown(
                    f"<span class='metric-pill pill-completed'>{svg_icon('check', size=14, stroke='currentColor')}<span>승인 완료</span></span>",
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"<span class='metric-pill pill-processing'>{svg_icon('clock', size=14, stroke='currentColor')}<span>미승인 초안</span></span>",
                    unsafe_allow_html=True,
                )
        with meta_cols[1]:
            if entry.get("location_name"):
                st.caption(f"위치: {entry['location_name']}")
        with meta_cols[2]:
            st.caption(f"작성일: {entry.get('diary_date') or '미기록'}")

        st.markdown(
            f"<div class='section-title'>{svg_icon('sparkle', size=16, stroke='#14324A')}<span>감정 태그</span></div>",
            unsafe_allow_html=True,
        )
        render_emotion_badges(entry.get("emotion_tags"))

        if entry.get("summary"):
            st.markdown(
                f"<div class='section-title'>{svg_icon('file-text', size=16, stroke='#14324A')}<span>일기 요약</span></div>",
                unsafe_allow_html=True,
            )
            st.write(entry["summary"])

        if entry.get("script"):
            st.markdown(
                f"<div class='section-title'>{svg_icon('mic', size=16, stroke='#14324A')}<span>나레이션 대본</span></div>",
                unsafe_allow_html=True,
            )
            st.write(entry["script"])

        diary_inputs = entry.get("diary_inputs", [])
        st.markdown(
            f"<div class='section-title'>{svg_icon('layers', size=16, stroke='#14324A')}<span>일기 입력 산출물</span></div>",
            unsafe_allow_html=True,
        )
        if diary_inputs:
            for asset in diary_inputs:
                asset_time = asset.get("captured_at") or asset.get("created_at") or ""
                asset_title = f"{detect_asset_label(asset['type'])} · {asset_time}"
                with st.expander(asset_title.strip(), expanded=False):
                    st.markdown(
                        icon_text(detect_asset_icon(asset["type"]), detect_asset_label(asset["type"])),
                        unsafe_allow_html=True,
                    )
                    if asset.get("transcript"):
                        st.write(asset["transcript"])
                    storage_url = asset.get("storage_url")
                    if storage_url and asset["type"] in {"image", "photo"}:
                        st.image(storage_url, use_container_width=True)
                    elif storage_url and asset["type"] in {"voice", "audio"}:
                        st.audio(storage_url)
                    elif storage_url:
                        st.link_button("원본 보기", storage_url)
                    elif asset["type"] in {"image", "photo", "voice", "audio"}:
                        st.caption("원본 파일은 현재 세션에서만 임시로 사용됐어요.")
        else:
            st.markdown(
                "<div class='empty-state'>아직 연결된 입력 산출물이 없습니다. 추후 일기 채팅 결과가 저장되면 이곳에서 날짜별로 바로 조회할 수 있습니다.</div>",
                unsafe_allow_html=True,
            )

        versions = entry.get("versions", [])
        st.markdown(
            f"<div class='section-title'>{svg_icon('layers', size=16, stroke='#14324A')}<span>버전 기록</span></div>",
            unsafe_allow_html=True,
        )
        if versions:
            for version in versions:
                version_label = "승인본" if version["approved"] else "초안"
                with st.expander(f"{version_label} · {version.get('title') or '제목 없음'}", expanded=False):
                    render_emotion_badges(version.get("emotion_tags"))
                    st.write(version.get("summary") or "요약 없음")
                    if version.get("script"):
                        st.caption("나레이션")
                        st.write(version["script"])
        else:
            st.caption("버전 기록이 없습니다.")

        st.markdown(
            f"<div class='section-title'>{svg_icon('video', size=16, stroke='#14324A')}<span>아바타 영상</span></div>",
            unsafe_allow_html=True,
        )
        if entry.get("video_status") == "completed" and entry.get("video_url"):
            st.video(entry["video_url"])
        elif entry.get("video_status") == "processing":
            st.info("아바타 영상 렌더링이 진행 중입니다.")
        elif entry.get("video_status") == "failed":
            st.error("아바타 영상 생성에 실패했습니다.")
        elif entry.get("video_status") == "pending":
            st.info("아바타 영상 생성 대기 중입니다.")
        else:
            st.caption("연결된 영상이 없습니다.")
        st.markdown('</div>', unsafe_allow_html=True)

    _dialog()


def render_calendar_grid(year: int, month: int, entries_map: dict[date, dict[str, Any]]) -> None:
    selected_date = st.session_state.get("selected_date")
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
            entry = entries_map.get(current_date)
            if entry:
                status_label, _, _ = format_status(entry["status"])
                emotion_tags = entry.get("emotion_tags") or []
                emotion_label = format_emotion_label(emotion_tags[0]) if emotion_tags else "감정 없음"
                preview_line = get_preview_line(entry)
                label = f"{current_day}\n{status_label}\n{preview_line}"
                help_text = f"{emotion_label} · 기록 있음 · 클릭해서 상세 보기"
            else:
                label = f"{current_day}\n기록 없음"
                help_text = "이 날짜에는 아직 기록이 없습니다."

            button_key = f"calendar_{current_date.isoformat()}"
            target_marker = "calendar-focus-flash" if selected_date == current_date else ""
            cols[weekday].markdown(
                f"<div id='calendar-target-{current_date.isoformat()}' class='calendar-target-marker {target_marker}'></div>",
                unsafe_allow_html=True,
            )
            if entry:
                cols[weekday].markdown(
                    "<style>button[kind='primary'] { color: #12314a !important; }</style>",
                    unsafe_allow_html=True,
                )
            else:
                cols[weekday].markdown(
                    "<style>button[kind='primary'] { color: #7a8c9a !important; }</style>",
                    unsafe_allow_html=True,
                )

            if cols[weekday].button(
                label,
                key=button_key,
                help=help_text,
                type="primary" if entry else "secondary",
            ):
                st.session_state["selected_date"] = current_date
                st.session_state["selected_entry"] = entry
                st.session_state["open_dialog"] = bool(entry)

            current_day += 1


def render_today_panel(entry: dict[str, Any] | None, selected_date: date) -> None:
    if not entry:
        st.info("선택한 날짜에는 아직 저장된 일기 기록이 없습니다.")
        return

    st.markdown('<div class="detail-panel">', unsafe_allow_html=True)
    st.markdown(
        f"<div class='detail-title'>{svg_icon('calendar', size=18, stroke='#14324A')}<span>{selected_date.strftime('%Y년 %m월 %d일')} 빠른 보기</span></div>",
        unsafe_allow_html=True,
    )

    status_label, status_class, status_icon = format_status(entry["status"])
    st.markdown(
        f"<span class='metric-pill {status_class}'>{svg_icon(status_icon, size=14, stroke='currentColor')}<span>{status_label}</span></span>",
        unsafe_allow_html=True,
    )
    if entry.get("approved"):
        st.markdown(
            f"<span class='metric-pill pill-completed'>{svg_icon('check', size=14, stroke='currentColor')}<span>승인 완료</span></span>",
            unsafe_allow_html=True,
        )

    st.write("")
    st.markdown(
        f"<div style='font-size:1.2rem; font-weight:900; background:linear-gradient(90deg,#173d5e,#4d90c9,#5bb0c1); -webkit-background-clip:text; background-clip:text; color:transparent; margin-bottom:0.5rem;'>{entry.get('title') or '제목 없는 기록'}</div>",
        unsafe_allow_html=True,
    )
    render_emotion_badges(entry.get("emotion_tags"))
    st.markdown(
        f"<div class='quick-summary' style='color:#34526d; font-weight:600;'>{(entry.get('summary') or '요약 없음')[:130]}{'…' if entry.get('summary') and len(entry['summary']) > 130 else ''}</div>",
        unsafe_allow_html=True,
    )

    input_count = len(entry.get("diary_inputs", []))
    version_count = len(entry.get("versions", []))
    st.caption(f"입력 산출물 {input_count}개 · 버전 기록 {version_count}개")
    st.info("날짜 카드를 누르면 팝업에서 일기 내용과 산출물을 자세히 볼 수 있습니다.")
    st.markdown("</div>", unsafe_allow_html=True)


st.markdown('<div class="calendar-shell">', unsafe_allow_html=True)
st.markdown(
    f"""
    <div class="hero-row">
        <div>
            <div class="hero-title">나의 일기 캘린더</div>
            <div class="hero-subtitle">
                월 선택은 팝업에서 바로, 날짜별 기록은 넓은 카드로 한눈에 확인할 수 있게 정리했습니다.
                목록에서 일기 내역을 선택하면 상세 내용을 바로 확인할 수 있습니다.
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

today = date.today()
if "selected_date" not in st.session_state:
    st.session_state["selected_date"] = today
if "selected_entry" not in st.session_state:
    st.session_state["selected_entry"] = None
if "open_dialog" not in st.session_state:
    st.session_state["open_dialog"] = False
if "calendar_anchor_date" not in st.session_state:
    st.session_state["calendar_anchor_date"] = today.replace(day=1)
if "summary_filter" not in st.session_state:
    st.session_state["summary_filter"] = "all"
if "scroll_to_record" not in st.session_state:
    st.session_state["scroll_to_record"] = False

st.markdown('<div class="toolbar-card">', unsafe_allow_html=True)
toolbar_cols = st.columns([1.8, 1.4, 1.3, 1.1], gap="small")
with toolbar_cols[0]:
    st.markdown(
        f"<div class='section-label'>{icon_text('calendar', '월간 기록 탐색')}</div>",
        unsafe_allow_html=True,
    )
    with st.popover("월간 기록 탐색"):
        year_options = list(range(2024, 2036))
        month_options = list(range(1, 13))
        selected_year = st.selectbox("년도", options=year_options, index=year_options.index(st.session_state["calendar_anchor_date"].year), key="calendar_year_select")
        selected_month = st.selectbox("월", options=month_options, index=month_options.index(st.session_state["calendar_anchor_date"].month), key="calendar_month_select")
        if st.button("조회 적용", type="primary", use_container_width=True):
            st.session_state["calendar_anchor_date"] = date(selected_year, selected_month, 1)
            st.session_state["selected_date"] = date(selected_year, selected_month, 1)
            st.session_state["selected_entry"] = None
            st.session_state["scroll_to_record"] = True
            st.rerun()
    st.markdown(
        f"<div class='hero-chip' style='justify-content:center; width:100%;'>{st.session_state['calendar_anchor_date'].year}년 {st.session_state['calendar_anchor_date'].month}월</div>",
        unsafe_allow_html=True,
    )

selected_anchor = st.session_state["calendar_anchor_date"]
with toolbar_cols[1]:
    st.markdown(
        f"<div class='section-label'>{icon_text('file-text', '사용자 ID')}</div>",
        unsafe_allow_html=True,
    )
    user_id = st.text_input(
        "사용자 ID",
        value="streamlit-test-user",
        help="캘린더가 조회할 일기 세션 사용자 ID를 입력하세요.",
        label_visibility="collapsed",
    )
    if not user_id.strip():
        user_id = "streamlit-test-user"

with toolbar_cols[2]:
    st.markdown(
        f"<div class='section-label'>{icon_text('filter', '상태 필터')}</div>",
        unsafe_allow_html=True,
    )
    status_label = st.selectbox(
        "상태 필터",
        options=list(STATUS_OPTIONS.keys()),
        label_visibility="collapsed",
    )

with toolbar_cols[3]:
    selected_year = selected_anchor.year
    selected_month = selected_anchor.month
    st.markdown(
        f"<div class='section-label'>{icon_text('grid', '현재 조회')}</div>",
        unsafe_allow_html=True,
    )
    st.markdown(
        f"<div class='hero-chip' style='justify-content:center; width:100%;'>{selected_year}년 {selected_month}월</div>",
        unsafe_allow_html=True,
    )
st.markdown("</div>", unsafe_allow_html=True)

with st.expander("상세 검색 및 위치 필터", expanded=False):
    filter_cols = st.columns([1.4, 1.0, 1.0], gap="small")
    with filter_cols[0]:
        st.markdown(
            f"<div class='section-label'>{icon_text('search', '키워드')}</div>",
            unsafe_allow_html=True,
        )
        keyword = st.text_input(
            "키워드",
            placeholder="제목, 요약, 대본 검색",
            label_visibility="collapsed",
        )
    with filter_cols[1]:
        st.markdown(
            f"<div class='section-label'>{icon_text('sparkle', '감정')}</div>",
            unsafe_allow_html=True,
        )
        emotion_choice = st.selectbox(
            "감정",
            options=["전체"] + list(EMOTION_LABELS.values()),
            label_visibility="collapsed",
        )
    with filter_cols[2]:
        st.markdown(
            f"<div class='section-label'>{icon_text('map-pin', '위치 반경')}</div>",
            unsafe_allow_html=True,
        )
        use_location_filter = st.checkbox("위치 반경 필터 사용", value=False)

    latitude = None
    longitude = None
    radius = 1000.0
    if use_location_filter:
        preset_cols = st.columns([1.4, 1.0, 1.0, 1.0], gap="small")
        preset = preset_cols[0].selectbox("위치 프리셋", options=list(LOCATION_PRESETS.keys()))
        preset_coords = LOCATION_PRESETS[preset]
        if preset_coords is None:
            latitude = preset_cols[1].number_input("위도", value=37.5665, format="%.6f")
            longitude = preset_cols[2].number_input("경도", value=126.9780, format="%.6f")
        else:
            latitude, longitude = preset_coords
            preset_cols[1].text(f"위도 {latitude}")
            preset_cols[2].text(f"경도 {longitude}")
        radius = preset_cols[3].number_input("반경(m)", min_value=100.0, value=1000.0, step=100.0)

st.markdown(
    f"""
    <div class="legend-wrap">
        <span class="legend-chip">{svg_icon("check", size=14, stroke="#1B6C45")}<span>완료</span></span>
        <span class="legend-chip">{svg_icon("clock", size=14, stroke="#9C6B05")}<span>처리 중</span></span>
        <span class="legend-chip">{svg_icon("edit", size=14, stroke="#2E5B9A")}<span>작성 중</span></span>
        <span class="legend-chip">{svg_icon("warning", size=14, stroke="#A63831")}<span>실패</span></span>
        <span class="legend-chip">{svg_icon("chevron-right", size=14, stroke="#36536B")}<span>날짜 클릭 시 팝업 조회</span></span>
    </div>
    """,
    unsafe_allow_html=True,
)

start_date, end_date = get_month_range(selected_year, selected_month)
selected_emotion_key = None
if emotion_choice != "전체":
    selected_emotion_key = next(
        key for key, label in EMOTION_LABELS.items() if label == emotion_choice
    )

with st.spinner("캘린더 데이터를 불러오는 중입니다..."):
    api_result, api_error = fetch_calendar_data(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        status=STATUS_OPTIONS[status_label],
        emotion=selected_emotion_key,
        keyword=keyword or None,
        latitude=latitude,
        longitude=longitude,
        radius=radius,
    )

if api_error:
    st.error(api_error)
    entries = []
    summary = {
        "total_entries": 0,
        "completed_entries": 0,
        "processing_entries": 0,
        "failed_entries": 0,
        "approved_entries": 0,
    }
else:
    entries = api_result.get("entries", []) if api_result else []
    summary = api_result.get("summary", {}) if api_result else {}

summary_filter = st.session_state.get("summary_filter", "all")
filtered_entries = filter_entries_by_summary(entries, summary_filter)

summary_cols = st.columns(5, gap="small")
summary_items = [
    ("전체 기록", summary.get("total_entries", 0), "이 달에 조회 가능한 일기 기록 수", "grid", "all"),
    ("완료", summary.get("completed_entries", 0), "작성과 생성이 끝난 기록", "check", "completed"),
    ("처리 중", summary.get("processing_entries", 0), "아직 생성 또는 정리 중인 기록", "clock", "processing"),
    ("실패", summary.get("failed_entries", 0), "재시도가 필요한 기록", "warning", "failed"),
    ("승인 완료", summary.get("approved_entries", 0), "사용자가 최종 승인한 기록", "sparkle", "approved"),
]
for idx, (label, value, caption, icon_name, filter_key) in enumerate(summary_items):
    with summary_cols[idx]:
        render_summary_card(label, int(value), caption, icon_name, filter_key, summary_filter)

entries_map = build_entries_map(filtered_entries)
selected_date = st.session_state.get("selected_date", today)
selected_entry = None
if filtered_entries:
    first_matching_date = date.fromisoformat(filtered_entries[0]["diary_date"])
    if start_date <= selected_date <= end_date:
        selected_entry = entries_map.get(selected_date)
    if selected_entry is None:
        selected_entry = filtered_entries[0]
        selected_date = first_matching_date
        st.session_state["selected_date"] = selected_date
    elif summary_filter != "all":
        st.session_state["selected_date"] = selected_date
else:
    st.session_state["selected_date"] = selected_date

if summary_filter != "all" and filtered_entries:
    st.caption(f"{SUMMARY_FILTERS[summary_filter][0]}에 해당하는 기록 {len(filtered_entries)}건")
    for entry in filtered_entries[:3]:
        entry_date = entry.get("diary_date")
        entry_title = entry.get("title") or "제목 없는 기록"
        st.markdown(f"- {entry_date}: {entry_title}")

month_entries = filtered_entries
if month_entries:
    st.markdown(
        f"<div class='section-label'>{icon_text('file-text', f'{selected_year}년 {selected_month}월 기록 목록')}</div>",
        unsafe_allow_html=True,
    )
    st.markdown('<div class="record-list-shell">', unsafe_allow_html=True)
    for entry in month_entries:
        entry_date = date.fromisoformat(entry["diary_date"])
        status_label, _, _ = format_status(entry["status"])
        title = entry.get("title") or "제목 없는 기록"
        summary_text = entry.get("summary") or "요약 내용이 아직 없습니다."
        status_key = entry.get("status") or "active"
        status_class = "completed" if status_key == "completed" else "processing" if status_key == "processing" else "failed" if status_key == "failed" else "active"
        is_selected = selected_entry is not None and entry_date == date.fromisoformat(selected_entry["diary_date"])
        card_key = f"month_entry_{entry['diary_date']}_{entry.get('id', 'noid')}"
        card_html = f"""
        <div class="record-list-card {'is-selected' if is_selected else ''}" onclick="document.getElementById('{card_key}').click(); return false;" style="cursor:pointer;">
            <div class="record-list-main">
                <div class="record-list-title">{entry_date.day}일 · {title}</div>
                <div class="record-list-sub">{summary_text[:70]}{'…' if len(summary_text) > 70 else ''}</div>
            </div>
            <span class="record-badge {status_class}">{status_label}</span>
        </div>
        """
        st.markdown(card_html, unsafe_allow_html=True)
        if st.button(
            "상세 보기",
            key=card_key,
            use_container_width=False,
            type="secondary",
            help=f"{entry_date} 기록 상세 보기",
        ):
            st.session_state["selected_date"] = entry_date
            st.session_state["selected_entry"] = entry
            st.session_state["open_dialog"] = True
    st.markdown('</div>', unsafe_allow_html=True)
else:
    st.markdown(
        "<div class='empty-state'>이 달에는 저장된 일기 기록이 없습니다. 다른 월을 조회해보세요.</div>",
        unsafe_allow_html=True,
    )

st.write("")
wide_col, side_col = st.columns([5.8, 1.9], gap="medium")
with wide_col:
    render_calendar_grid(selected_year, selected_month, entries_map)
with side_col:
    render_today_panel(selected_entry, selected_date)

if st.session_state.get("scroll_to_record") and selected_date:
    st.components.v1.html(
        f"""
        <script>
        setTimeout(() => {{
            const target = document.getElementById('calendar-target-{selected_date.isoformat()}');
            if (target) {{
                target.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                target.classList.add('calendar-focus-flash');
                setTimeout(() => target.classList.remove('calendar-focus-flash'), 1800);
            }}
        }}, 160);
        </script>
        """,
        height=0,
    )
    st.session_state["scroll_to_record"] = False

st.markdown("</div>", unsafe_allow_html=True)

if st.session_state.get("open_dialog") and st.session_state.get("selected_entry"):
    open_entry_dialog(st.session_state["selected_entry"])
    st.session_state["open_dialog"] = False
