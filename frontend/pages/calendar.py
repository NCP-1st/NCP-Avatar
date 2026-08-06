"""Streamlit calendar page for diary history browsing."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Any

import streamlit as st

from api.calendar import fetch_calendar_data

st.markdown(
    """
    <style>
    .calendar-title {
        font-size: 2.4rem;
        font-weight: 800;
        color: #13315c;
        margin-bottom: 0.4rem;
    }
    .calendar-subtitle {
        color: #4f6d7a;
        margin-bottom: 1.2rem;
    }
    .summary-card {
        background: linear-gradient(180deg, #f7fbff 0%, #edf6f9 100%);
        border: 1px solid #d9eaf4;
        border-radius: 16px;
        padding: 16px 18px;
        min-height: 110px;
    }
    .summary-label {
        color: #4f6d7a;
        font-size: 0.95rem;
    }
    .summary-value {
        color: #102a43;
        font-size: 1.8rem;
        font-weight: 800;
        line-height: 1.1;
    }
    .detail-card {
        background: #ffffff;
        border: 1px solid #d9e2ec;
        border-radius: 18px;
        padding: 20px;
    }
    .emotion-badge {
        display: inline-block;
        margin-right: 6px;
        margin-bottom: 6px;
        padding: 6px 10px;
        border-radius: 999px;
        background: #e3f2fd;
        color: #0b3c5d;
        font-weight: 700;
        font-size: 0.85rem;
    }
    .status-chip {
        display: inline-block;
        padding: 6px 10px;
        border-radius: 999px;
        font-size: 0.85rem;
        font-weight: 700;
    }
    .status-completed { background: #d9fbe6; color: #136f3a; }
    .status-processing { background: #fff3d6; color: #9a6700; }
    .status-failed { background: #fde2e1; color: #a12622; }
    .status-active { background: #e7eef7; color: #1f4b75; }
    div.stButton > button {
        width: 100%;
        min-height: 76px;
        border-radius: 12px;
        border: 1px solid #d9e2ec;
        background: #ffffff;
        color: #102a43;
        font-weight: 700;
    }
    div.stButton > button:hover {
        border-color: #486581;
        color: #102a43;
    }
    .calendar-header {
        text-align: center;
        font-weight: 800;
        color: #334e68;
        padding-bottom: 6px;
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

STATUS_OPTIONS = {
    "전체": None,
    "active": "active",
    "processing": "processing",
    "completed": "completed",
    "failed": "failed",
}

STATUS_META = {
    "active": ("작성 중", "status-active", "✍️"),
    "processing": ("처리 중", "status-processing", "⏳"),
    "completed": ("완료", "status-completed", "✅"),
    "failed": ("실패", "status-failed", "❌"),
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
    return STATUS_META.get(status, ("알 수 없음", "status-active", "📝"))


def render_summary_card(label: str, value: int) -> None:
    st.markdown(
        f"""
        <div class="summary-card">
            <div class="summary-label">{label}</div>
            <div class="summary-value">{value}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_emotion_badges(emotion_tags: list[str] | None) -> None:
    if not emotion_tags:
        st.caption("감정 태그 없음")
        return
    html = "".join(
        f'<span class="emotion-badge">{format_emotion_label(tag)}</span>'
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


def render_calendar_grid(year: int, month: int, entries_map: dict[date, dict[str, Any]]) -> None:
    week_headers = ["일", "월", "화", "수", "목", "금", "토"]
    header_cols = st.columns(7)
    for idx, header in enumerate(week_headers):
        header_cols[idx].markdown(
            f'<div class="calendar-header">{header}</div>',
            unsafe_allow_html=True,
        )

    first_weekday, num_days = calendar.monthrange(year, month)
    first_weekday_pad = (first_weekday + 1) % 7
    current_day = 1

    for week in range(6):
        if current_day > num_days:
            break
        cols = st.columns(7)
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
                _, _, icon = format_status(entry["status"])
                emotion_icon = "📝"
                if entry.get("emotion_tags"):
                    emotion_icon = {
                        "happy": "☀️",
                        "excited": "🔥",
                        "calm": "🍃",
                        "tired": "💤",
                        "sad": "🌧️",
                    }.get(entry["emotion_tags"][0].lower(), "📝")
                label = f"{current_day}\n{emotion_icon} {icon}"
            else:
                label = f"{current_day}\n·"

            if cols[weekday].button(label, key=f"calendar_{current_date.isoformat()}"):
                st.session_state["selected_date"] = current_date

            current_day += 1


def render_detail_card(selected_entry: dict[str, Any] | None, selected_date: date) -> None:
    st.markdown('<div class="detail-card">', unsafe_allow_html=True)
    st.subheader(selected_date.strftime("%Y년 %m월 %d일"))

    if not selected_entry:
        st.info("선택한 날짜에 작성된 일기가 없습니다.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    status_label, status_class, _ = format_status(selected_entry["status"])
    st.markdown(
        f"<span class='status-chip {status_class}'>{status_label}</span>",
        unsafe_allow_html=True,
    )
    st.write("")

    st.markdown(f"### {selected_entry.get('title') or '제목 없음'}")
    render_emotion_badges(selected_entry.get("emotion_tags"))

    if selected_entry.get("location_name"):
        st.caption(f"위치: {selected_entry['location_name']}")

    if selected_entry.get("summary"):
        st.markdown("**요약**")
        st.write(selected_entry["summary"])

    if selected_entry.get("script"):
        st.markdown("**나레이션 대본**")
        st.write(selected_entry["script"])

    approval_text = "승인 완료" if selected_entry.get("approved") else "미승인 초안"
    st.caption(f"버전 상태: {approval_text}")

    st.markdown("**아바타 영상**")
    if selected_entry.get("video_status") == "completed" and selected_entry.get("video_url"):
        st.video(selected_entry["video_url"])
    elif selected_entry.get("video_status") == "processing":
        st.warning("영상 렌더링이 진행 중입니다.")
    elif selected_entry.get("video_status") == "failed":
        st.error("영상 생성에 실패했습니다.")
    elif selected_entry.get("video_status") == "pending":
        st.info("영상 생성 대기 중입니다.")
    else:
        st.info("연결된 영상이 없습니다.")

    st.markdown("</div>", unsafe_allow_html=True)


st.markdown('<div class="calendar-title">캘린더 조회</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="calendar-subtitle">날짜별 일기 상태와 감정 흐름을 확인하고, 선택한 날짜의 초안과 영상을 조회합니다.</div>',
    unsafe_allow_html=True,
)

today = date.today()
if "selected_date" not in st.session_state:
    st.session_state["selected_date"] = today

top_left, top_right = st.columns([3, 2], gap="large")

with top_left:
    control_col1, control_col2, control_col3 = st.columns([1.2, 1.2, 1.6])
    selected_year = control_col1.selectbox(
        "년도",
        options=list(range(today.year - 2, today.year + 2)),
        index=2,
    )
    selected_month = control_col2.selectbox("월", options=list(range(1, 13)), index=today.month - 1)
    user_id = control_col3.text_input("사용자 ID", value="test_user_1")

    with st.expander("상세 검색"):
        filter_col1, filter_col2 = st.columns(2)
        keyword = filter_col1.text_input("키워드", placeholder="제목, 요약, 대본 검색")
        status_label = filter_col2.selectbox("상태", options=list(STATUS_OPTIONS.keys()))

        filter_col3, filter_col4 = st.columns(2)
        emotion_choice = filter_col3.selectbox(
            "감정",
            options=["전체"] + list(EMOTION_LABELS.values()),
        )
        use_location_filter = filter_col4.checkbox("위치 반경 필터")

        latitude = None
        longitude = None
        radius = 1000.0
        if use_location_filter:
            preset = st.selectbox("위치 프리셋", options=list(LOCATION_PRESETS.keys()))
            preset_coords = LOCATION_PRESETS[preset]
            loc_col1, loc_col2, loc_col3 = st.columns(3)
            if preset_coords is None:
                latitude = loc_col1.number_input("위도", value=37.5665, format="%.6f")
                longitude = loc_col2.number_input("경도", value=126.9780, format="%.6f")
            else:
                latitude, longitude = preset_coords
                loc_col1.text(f"위도 {latitude}")
                loc_col2.text(f"경도 {longitude}")
            radius = loc_col3.number_input("반경(m)", min_value=100.0, value=1000.0, step=100.0)

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
        entries: list[dict[str, Any]] = []
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

    summary_cols = st.columns(5)
    summary_items = [
        ("전체 일기", summary.get("total_entries", 0)),
        ("완료", summary.get("completed_entries", 0)),
        ("처리 중", summary.get("processing_entries", 0)),
        ("실패", summary.get("failed_entries", 0)),
        ("승인 완료", summary.get("approved_entries", 0)),
    ]
    for idx, (label, value) in enumerate(summary_items):
        with summary_cols[idx]:
            render_summary_card(label, int(value))

    st.write("")
    entries_map = build_entries_map(entries)
    render_calendar_grid(selected_year, selected_month, entries_map)

with top_right:
    selected_date = st.session_state["selected_date"]
    selected_entry = None
    if start_date <= selected_date <= end_date:
        selected_entry = build_entries_map(entries).get(selected_date)
    else:
        detail_result, detail_error = fetch_calendar_data(
            user_id=user_id,
            start_date=selected_date,
            end_date=selected_date,
        )
        if detail_error:
            st.error(detail_error)
        else:
            detail_entries = detail_result.get("entries", []) if detail_result else []
            selected_entry = detail_entries[0] if detail_entries else None

    render_detail_card(selected_entry, selected_date)
