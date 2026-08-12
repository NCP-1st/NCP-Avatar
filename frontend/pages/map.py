"""Map page for browsing diaries and assigning a location."""

from __future__ import annotations

import html
import sys
from pathlib import Path
from typing import Any

import folium
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.calendar import fetch_calendar_entry_detail
from api.diary import download_video
from api.maps_client import MapsApiError, create_diary_location, fetch_diaries

USER_ID = "streamlit-test-user"
DEFAULT_CENTER = (37.5512, 126.9882)
DEFAULT_ZOOM = 12

FILTER_OPTIONS = {
    "전체 일기": "all",
    "위치 설정됨": "located",
    "위치 미설정": "unlocated",
}


st.markdown(
    """
    <style>
    .map-header {margin-bottom: .5rem;}
    .map-subtitle {color: #60778a; margin-top: -.6rem; margin-bottom: 1.2rem;}
    .diary-card {
        border: 1px solid #dce5eb; border-radius: 16px; padding: 14px 15px;
        margin-bottom: 10px; background: #fff;
    }
    .diary-title {font-size: 1rem; font-weight: 700; color: #17364d;}
    .diary-meta {font-size: .82rem; color: #738797; margin: 3px 0 8px;}
    .location-set {color: #287a55; font-weight: 600;}
    .location-empty {color: #9a6b25; font-weight: 600;}
    </style>
    """,
    unsafe_allow_html=True,
)


def _map_center(diaries: list[dict[str, Any]]) -> tuple[float, float]:
    located = [item for item in diaries if item.get("is_located")]
    if not located:
        return DEFAULT_CENTER
    return (
        sum(float(item["latitude"]) for item in located) / len(located),
        sum(float(item["longitude"]) for item in located) / len(located),
    )


def _build_diary_map(diaries: list[dict[str, Any]]) -> folium.Map:
    located = [item for item in diaries if item.get("is_located")]
    map_view = folium.Map(
        location=_map_center(located),
        zoom_start=DEFAULT_ZOOM,
        tiles="OpenStreetMap",
    )
    for item in located:
        tags = ", ".join(item.get("emotion_tags") or [])
        popup = (
            f"<b>{html.escape(item['title'])}</b><br>"
            f"{html.escape(str(item['diary_date']))}<br>"
            f"{html.escape(tags)}"
        )
        folium.Marker(
            [item["latitude"], item["longitude"]],
            tooltip=item["title"],
            popup=folium.Popup(popup, max_width=260),
            icon=folium.Icon(color="blue", icon="book", prefix="fa"),
        ).add_to(map_view)
    return map_view


def _clicked_diary(
    map_data: dict[str, Any] | None,
    diaries: list[dict[str, Any]],
) -> dict[str, Any] | None:
    clicked = map_data.get("last_object_clicked") if map_data else None
    if not clicked:
        return None
    for item in diaries:
        if not item.get("is_located"):
            continue
        if (
            abs(float(item["latitude"]) - float(clicked["lat"])) < 1e-7
            and abs(float(item["longitude"]) - float(clicked["lng"])) < 1e-7
        ):
            return item
    return None


@st.cache_data(show_spinner=False, ttl=300)
def _load_video(session_id: str, version_id: str) -> bytes:
    return download_video(session_id, version_id)


@st.dialog("일기 상세", width="large")
def show_diary_detail(entry: dict[str, Any]) -> None:
    detail, error = fetch_calendar_entry_detail(USER_ID, entry["session_id"])
    if error:
        st.warning(f"상세 정보를 불러오지 못해 목록 정보를 표시합니다. ({error})")
        detail = entry
    detail = detail or entry

    st.subheader(detail.get("title") or entry["title"])
    st.caption(f"{entry['diary_date']} · {', '.join(entry.get('emotion_tags') or [])}")
    if entry.get("is_located"):
        st.caption(
            f"저장 위치: {float(entry['latitude']):.5f}, "
            f"{float(entry['longitude']):.5f}"
        )
    st.write(detail.get("content") or entry.get("summary") or "일기 내용이 없습니다.")

    st.markdown("#### 아바타 영상")
    video_status = entry.get("video_status")
    if video_status == "completed":
        try:
            st.video(_load_video(entry["session_id"], entry["version_id"]))
        except RuntimeError as exc:
            st.error(str(exc))
    elif video_status == "processing":
        st.info("아바타 영상 렌더링이 진행 중입니다.")
    elif video_status == "failed":
        st.error("아바타 영상 생성에 실패했습니다.")
    else:
        st.caption("연결된 아바타 영상이 없습니다.")


@st.dialog("일기 위치 설정", width="large")
def show_location_picker(entry: dict[str, Any]) -> None:
    state_key = f"map_picker_{entry['version_id']}"
    picked = st.session_state.get(state_key)
    center = picked or DEFAULT_CENTER
    picker_map = folium.Map(location=center, zoom_start=14, tiles="OpenStreetMap")
    if picked:
        folium.Marker(
            picked,
            tooltip="저장할 위치",
            icon=folium.Icon(color="red", icon="map-pin", prefix="fa"),
        ).add_to(picker_map)

    st.write(f"**{entry['title']}**을 저장할 위치를 지도에서 클릭하세요.")
    map_data = st_folium(
        picker_map,
        height=430,
        use_container_width=True,
        returned_objects=["last_clicked"],
        key=f"picker_map_{entry['version_id']}",
    )
    clicked = map_data.get("last_clicked") if map_data else None
    if clicked:
        next_position = (float(clicked["lat"]), float(clicked["lng"]))
        if picked != next_position:
            st.session_state[state_key] = next_position
            st.rerun()

    picked = st.session_state.get(state_key)
    if picked:
        st.success(f"선택 위치: {picked[0]:.6f}, {picked[1]:.6f}")
    if st.button(
        "현재 위치에 일기 저장",
        type="primary",
        use_container_width=True,
        disabled=picked is None,
    ):
        try:
            create_diary_location(
                user_id=USER_ID,
                version_id=entry["version_id"],
                latitude=picked[0],
                longitude=picked[1],
            )
        except MapsApiError as exc:
            st.error(str(exc))
        else:
            st.session_state.pop(state_key, None)
            st.session_state.pop("map_location_entry", None)
            st.session_state["map_location_saved"] = True
            st.rerun()

    if st.button("취소", use_container_width=True):
        st.session_state.pop(state_key, None)
        st.session_state.pop("map_location_entry", None)
        st.rerun()


def _render_diary_card(entry: dict[str, Any]) -> None:
    location_class = "location-set" if entry.get("is_located") else "location-empty"
    location_text = "위치 설정됨" if entry.get("is_located") else "위치 미설정"
    tags = ", ".join(entry.get("emotion_tags") or [])
    st.markdown(
        (
            "<div class='diary-card'>"
            f"<div class='diary-title'>{html.escape(entry['title'])}</div>"
            f"<div class='diary-meta'>{entry['diary_date']} · {html.escape(tags)}</div>"
            f"<span class='{location_class}'>{location_text}</span>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    col_detail, col_location = st.columns(2)
    if col_detail.button(
        "일기 보기",
        key=f"detail_{entry['version_id']}",
        use_container_width=True,
    ):
        show_diary_detail(entry)
    if not entry.get("is_located") and col_location.button(
        "위치 설정하기",
        key=f"locate_{entry['version_id']}",
        type="primary",
        use_container_width=True,
    ):
        st.session_state["map_location_entry"] = entry
        st.rerun()


def main() -> None:
    st.markdown("<h1 class='map-header'>일기 지도</h1>", unsafe_allow_html=True)
    st.markdown(
        "<div class='map-subtitle'>기억을 장소와 함께 저장하고 지도에서 다시 만나보세요.</div>",
        unsafe_allow_html=True,
    )

    filter_col, search_col = st.columns([1, 2], gap="medium")
    with filter_col:
        filter_label = st.selectbox("위치 설정 여부", list(FILTER_OPTIONS))
    with search_col:
        keyword = st.text_input(
            "일기 제목 검색",
            placeholder="찾고 싶은 일기 제목을 입력하세요",
        )

    try:
        diaries = fetch_diaries(
            USER_ID,
            location_status=FILTER_OPTIONS[filter_label],
            keyword=keyword,
        )
    except MapsApiError as exc:
        st.error(str(exc))
        return

    if st.session_state.pop("map_location_saved", False):
        st.success("일기 위치를 저장했습니다.")

    list_col, map_col = st.columns([1, 2], gap="large")
    with list_col:
        st.subheader(f"일기 목록 · {len(diaries)}개")
        if not diaries:
            st.info("조건에 맞는 승인된 일기가 없습니다.")
        for entry in diaries:
            _render_diary_card(entry)

    with map_col:
        st.subheader("저장된 위치")
        located = [entry for entry in diaries if entry.get("is_located")]
        map_data = st_folium(
            _build_diary_map(located),
            height=620,
            use_container_width=True,
            returned_objects=[
                "last_object_clicked",
                "last_object_clicked_count",
            ],
            key="diary_location_map",
        )
        clicked = _clicked_diary(map_data, located)
        if clicked:
            click_key = (
                f"{clicked['version_id']}:"
                f"{map_data.get('last_object_clicked_count')}"
            )
            if st.session_state.get("map_last_marker_click") != click_key:
                st.session_state["map_last_marker_click"] = click_key
                show_diary_detail(clicked)
        if not located:
            st.caption("위치가 설정된 일기가 아직 없습니다.")

    location_entry = st.session_state.get("map_location_entry")
    if location_entry:
        show_location_picker(location_entry)


main()
