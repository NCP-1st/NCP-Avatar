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
    .calendar-shell {
        background:
            radial-gradient(circle at top left, rgba(202, 240, 248, 0.8), transparent 28%),
            linear-gradient(180deg, #f8fbff 0%, #edf6ff 100%);
        border: 1px solid #d9eaf7;
        border-radius: 28px;
        padding: 28px;
        margin-bottom: 18px;
    }
    .calendar-title {
        font-size: 2.65rem;
        font-weight: 900;
        color: #12355b;
        margin-bottom: 0.35rem;
        letter-spacing: -0.02em;
    }
    .calendar-subtitle {
        color: #4c6378;
        font-size: 1rem;
        margin-bottom: 1.3rem;
    }
    .summary-card {
        background: rgba(255, 255, 255, 0.88);
        border: 1px solid #d6e6f2;
        border-radius: 20px;
        padding: 18px 18px 16px 18px;
        min-height: 112px;
        box-shadow: 0 12px 30px rgba(18, 53, 91, 0.06);
    }
    .summary-label {
        color: #5f7488;
        font-size: 0.92rem;
        margin-bottom: 6px;
    }
    .summary-value {
        color: #102a43;
        font-size: 1.9rem;
        font-weight: 900;
        line-height: 1.05;
    }
    .summary-caption {
        color: #7b8794;
        font-size: 0.82rem;
        margin-top: 8px;
    }
    .calendar-header {
        text-align: center;
        font-weight: 800;
        color: #334e68;
        padding: 8px 0 10px 0;
        font-size: 0.96rem;
    }
    .legend-wrap {
        display: flex;
        gap: 12px;
        flex-wrap: wrap;
        margin: 8px 0 14px 0;
    }
    .legend-chip {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        background: rgba(255,255,255,0.92);
        border: 1px solid #d9e2ec;
        color: #334e68;
        border-radius: 999px;
        padding: 7px 12px;
        font-size: 0.86rem;
        font-weight: 700;
    }
    .metric-pill {
        display: inline-block;
        padding: 6px 11px;
        border-radius: 999px;
        font-size: 0.84rem;
        font-weight: 800;
        margin-right: 6px;
        margin-bottom: 6px;
    }
    .pill-completed { background: #d9fbe6; color: #136f3a; }
    .pill-processing { background: #fff3d6; color: #9a6700; }
    .pill-failed { background: #fde2e1; color: #a12622; }
    .pill-active { background: #e8f0fe; color: #1f4b75; }
    .emotion-badge {
        display: inline-block;
        margin-right: 6px;
        margin-bottom: 6px;
        padding: 7px 11px;
        border-radius: 999px;
        background: #e9f4ff;
        color: #0b3c5d;
        font-weight: 800;
        font-size: 0.84rem;
    }
    .detail-panel {
        background: #ffffff;
        border: 1px solid #d9e2ec;
        border-radius: 22px;
        padding: 18px;
        box-shadow: 0 16px 32px rgba(16, 42, 67, 0.05);
    }
    .detail-title {
        font-size: 1.2rem;
        font-weight: 900;
        color: #12355b;
        margin-bottom: 0.5rem;
    }
    .section-title {
        color: #12355b;
        font-size: 0.98rem;
        font-weight: 900;
        margin-top: 0.85rem;
        margin-bottom: 0.45rem;
    }
    div.stButton > button {
        width: 100%;
        min-height: 122px;
        border-radius: 18px;
        border: 1px solid #d8e5ef;
        background: linear-gradient(180deg, rgba(255,255,255,0.98) 0%, rgba(245,250,255,0.98) 100%);
        color: #102a43;
        font-weight: 800;
        font-size: 1rem;
        padding: 14px 10px;
        box-shadow: 0 10px 24px rgba(16, 42, 67, 0.04);
    }
    div.stButton > button:hover {
        border-color: #4f6d7a;
        box-shadow: 0 14px 28px rgba(16, 42, 67, 0.08);
        transform: translateY(-2px);
    }
    .empty-state {
        background: rgba(255,255,255,0.8);
        border: 1px dashed #c6d6e5;
        border-radius: 16px;
        padding: 16px;
        text-align: center;
        color: #5f7488;
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

EMOTION_ICONS = {
    "happy": "☀️",
    "excited": "🔥",
    "calm": "🍃",
    "tired": "💤",
    "sad": "🌧️",
}

STATUS_OPTIONS = {
    "전체": None,
    "작성 중": "active",
    "처리 중": "processing",
    "완료": "completed",
    "실패": "failed",
}

STATUS_META = {
    "active": ("작성 중", "pill-active", "✍️"),
    "processing": ("처리 중", "pill-processing", "⏳"),
    "completed": ("완료", "pill-completed", "✅"),
    "failed": ("실패", "pill-failed", "❌"),
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
    return STATUS_META.get(status, ("알 수 없음", "pill-active", "📝"))


def render_summary_card(label: str, value: int, caption: str) -> None:
    st.markdown(
        f"""
        <div class="summary-card">
            <div class="summary-label">{label}</div>
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
        f'<span class="emotion-badge">{EMOTION_ICONS.get(tag.lower(), "📝")} {format_emotion_label(tag)}</span>'
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


def detect_asset_label(asset_type: str) -> str:
    return {
        "image": "이미지",
        "voice": "음성",
        "text": "텍스트",
    }.get(asset_type, asset_type)


def open_entry_dialog(entry: dict[str, Any]) -> None:
    @st.dialog(entry["diary_date"])
    def _dialog() -> None:
        status_label, status_class, _ = format_status(entry["status"])
        st.markdown(
            f'<div class="detail-panel"><div class="detail-title">{entry.get("title") or "제목 없는 기록"}</div></div>',
            unsafe_allow_html=True,
        )
        st.markdown(
            f"<span class='metric-pill {status_class}'>{status_label}</span>",
            unsafe_allow_html=True,
        )
        if entry.get("approved"):
            st.markdown(
                "<span class='metric-pill pill-completed'>승인 완료</span>",
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                "<span class='metric-pill pill-processing'>미승인 초안</span>",
                unsafe_allow_html=True,
            )

        if entry.get("location_name"):
            st.caption(f"위치: {entry['location_name']}")

        st.markdown("<div class='section-title'>감정 태그</div>", unsafe_allow_html=True)
        render_emotion_badges(entry.get("emotion_tags"))

        if entry.get("summary"):
            st.markdown("<div class='section-title'>일기 요약</div>", unsafe_allow_html=True)
            st.write(entry["summary"])

        if entry.get("script"):
            st.markdown("<div class='section-title'>나레이션 대본</div>", unsafe_allow_html=True)
            st.write(entry["script"])

        diary_inputs = entry.get("diary_inputs", [])
        st.markdown("<div class='section-title'>일기 입력 산출물</div>", unsafe_allow_html=True)
        if diary_inputs:
            for asset in diary_inputs:
                asset_title = f"{detect_asset_label(asset['type'])} · {asset.get('captured_at') or asset.get('created_at') or ''}"
                with st.expander(asset_title.strip(), expanded=False):
                    if asset.get("transcript"):
                        st.write(asset["transcript"])
                    if asset["type"] == "image":
                        st.image(asset["storage_url"], use_container_width=True)
                    elif asset["type"] == "voice":
                        st.audio(asset["storage_url"])
                    else:
                        st.link_button("원본 보기", asset["storage_url"])
        else:
            st.markdown(
                "<div class='empty-state'>아직 연결된 입력 산출물이 없습니다. 추후 일기 채팅 결과가 저장되면 이곳에서 날짜별로 바로 조회할 수 있습니다.</div>",
                unsafe_allow_html=True,
            )

        versions = entry.get("versions", [])
        st.markdown("<div class='section-title'>버전 기록</div>", unsafe_allow_html=True)
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

        st.markdown("<div class='section-title'>아바타 영상</div>", unsafe_allow_html=True)
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

    _dialog()


def render_calendar_grid(year: int, month: int, entries_map: dict[date, dict[str, Any]]) -> None:
    week_headers = ["일", "월", "화", "수", "목", "금", "토"]
    header_cols = st.columns(7, gap="small")
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
                status_label, _, status_icon = format_status(entry["status"])
                emotion_tags = entry.get("emotion_tags") or []
                emotion_icon = EMOTION_ICONS.get(emotion_tags[0].lower(), "📝") if emotion_tags else "📝"
                preview_line = get_preview_line(entry)
                label = f"{current_day}\n{emotion_icon} {status_icon}\n{preview_line}"
                help_text = f"{status_label} · 클릭해서 상세 보기"
            else:
                label = f"{current_day}\n·\n기록 없음"
                help_text = "이 날짜에는 아직 기록이 없습니다."

            if cols[weekday].button(
                label,
                key=f"calendar_{current_date.isoformat()}",
                help=help_text,
            ):
                st.session_state["selected_date"] = current_date
                st.session_state["selected_entry"] = entry
                st.session_state["open_dialog"] = bool(entry)

            current_day += 1


def render_today_panel(entry: dict[str, Any] | None, selected_date: date) -> None:
    st.markdown('<div class="detail-panel">', unsafe_allow_html=True)
    st.markdown(
        f"<div class='detail-title'>{selected_date.strftime('%Y년 %m월 %d일')} 빠른 보기</div>",
        unsafe_allow_html=True,
    )
    if not entry:
        st.markdown(
            "<div class='empty-state'>선택한 날짜에 아직 저장된 일기 기록이 없습니다.</div>",
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)
        return

    status_label, status_class, _ = format_status(entry["status"])
    st.markdown(
        f"<span class='metric-pill {status_class}'>{status_label}</span>",
        unsafe_allow_html=True,
    )
    if entry.get("approved"):
        st.markdown(
            "<span class='metric-pill pill-completed'>승인 완료</span>",
            unsafe_allow_html=True,
        )

    st.write("")
    st.markdown(f"**{entry.get('title') or '제목 없는 기록'}**")
    render_emotion_badges(entry.get("emotion_tags"))
    st.caption(get_preview_line(entry))
    st.write((entry.get("summary") or "요약 없음")[:120] + ("…" if entry.get("summary") and len(entry["summary"]) > 120 else ""))

    input_count = len(entry.get("diary_inputs", []))
    version_count = len(entry.get("versions", []))
    st.caption(f"입력 산출물 {input_count}개 · 버전 기록 {version_count}개")
    st.info("날짜 칸을 누르면 팝업에서 일기 내용, 입력 이미지/텍스트/음성, 버전 기록을 자세히 볼 수 있습니다.")
    st.markdown("</div>", unsafe_allow_html=True)


st.markdown('<div class="calendar-shell">', unsafe_allow_html=True)
st.markdown('<div class="calendar-title">나의 일기 캘린더</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="calendar-subtitle">날짜별 기록을 넓은 카드형 캘린더로 확인하고, 날짜를 누르면 팝업에서 일기 내용과 산출물을 한 번에 조회할 수 있습니다.</div>',
    unsafe_allow_html=True,
)

today = date.today()
if "selected_date" not in st.session_state:
    st.session_state["selected_date"] = today
if "selected_entry" not in st.session_state:
    st.session_state["selected_entry"] = None
if "open_dialog" not in st.session_state:
    st.session_state["open_dialog"] = False

control_col1, control_col2, control_col3, control_col4 = st.columns([1.1, 1.0, 1.5, 1.4], gap="small")
selected_year = control_col1.selectbox(
    "년도",
    options=list(range(today.year - 2, today.year + 2)),
    index=2,
)
selected_month = control_col2.selectbox("월", options=list(range(1, 13)), index=today.month - 1)
user_id = control_col3.text_input("사용자 ID", value="test_user_1")
status_label = control_col4.selectbox("상태 필터", options=list(STATUS_OPTIONS.keys()))

with st.expander("상세 검색 및 위치 필터", expanded=False):
    filter_col1, filter_col2, filter_col3 = st.columns([1.3, 1.0, 1.1], gap="small")
    keyword = filter_col1.text_input("키워드", placeholder="제목, 요약, 대본 검색")
    emotion_choice = filter_col2.selectbox(
        "감정",
        options=["전체"] + list(EMOTION_LABELS.values()),
    )
    use_location_filter = filter_col3.checkbox("위치 반경 필터")

    latitude = None
    longitude = None
    radius = 1000.0
    if use_location_filter:
        preset_col1, preset_col2, preset_col3, preset_col4 = st.columns([1.4, 1.0, 1.0, 1.0], gap="small")
        preset = preset_col1.selectbox("위치 프리셋", options=list(LOCATION_PRESETS.keys()))
        preset_coords = LOCATION_PRESETS[preset]
        if preset_coords is None:
            latitude = preset_col2.number_input("위도", value=37.5665, format="%.6f")
            longitude = preset_col3.number_input("경도", value=126.9780, format="%.6f")
        else:
            latitude, longitude = preset_coords
            preset_col2.text(f"위도 {latitude}")
            preset_col3.text(f"경도 {longitude}")
        radius = preset_col4.number_input("반경(m)", min_value=100.0, value=1000.0, step=100.0)

st.markdown(
    """
    <div class="legend-wrap">
        <span class="legend-chip">✅ 완료</span>
        <span class="legend-chip">⏳ 처리 중</span>
        <span class="legend-chip">✍️ 작성 중</span>
        <span class="legend-chip">❌ 실패</span>
        <span class="legend-chip">날짜 클릭 시 팝업 상세보기</span>
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

summary_cols = st.columns(5, gap="small")
summary_items = [
    ("전체 기록", summary.get("total_entries", 0), "이 달에 캘린더에서 확인 가능한 일기 수"),
    ("완료", summary.get("completed_entries", 0), "작성과 생성이 끝난 기록"),
    ("처리 중", summary.get("processing_entries", 0), "아직 생성 또는 정리 중인 기록"),
    ("실패", summary.get("failed_entries", 0), "재시도가 필요한 기록"),
    ("승인 완료", summary.get("approved_entries", 0), "사용자가 최종 승인한 기록"),
]
for idx, (label, value, caption) in enumerate(summary_items):
    with summary_cols[idx]:
        render_summary_card(label, int(value), caption)

entries_map = build_entries_map(entries)
selected_date = st.session_state["selected_date"]
if start_date <= selected_date <= end_date:
    selected_entry = entries_map.get(selected_date)
else:
    selected_entry = st.session_state.get("selected_entry")

st.write("")
wide_col, side_col = st.columns([5.5, 1.8], gap="medium")
with wide_col:
    render_calendar_grid(selected_year, selected_month, entries_map)
with side_col:
    render_today_panel(selected_entry, selected_date)

st.markdown("</div>", unsafe_allow_html=True)

if st.session_state.get("open_dialog") and st.session_state.get("selected_entry"):
    open_entry_dialog(st.session_state["selected_entry"])
    st.session_state["open_dialog"] = False
