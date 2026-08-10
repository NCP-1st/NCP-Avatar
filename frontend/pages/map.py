import sys
from pathlib import Path

import streamlit as st
import folium
from streamlit_folium import st_folium

# frontend/를 임포트 경로에 추가 (pages 단독 실행 대비)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from api.maps_client import MapsApiError, create_diary, fetch_diaries

DEFAULT_CENTER = (37.5512 , 126.9882)
DEFAULT_ZOOM = 12


EMOTION_COLORS = {
    "행복" : "orange",
    "설렘" : "pink",
    "평온" : "green",
    "우울" : "blue",
    "화남" : "red"
}

EMOTIONS = list(EMOTION_COLORS.keys())


def init_state() -> None:
    if "diaries" not in st.session_state:
        try:
            st.session_state.diaries = fetch_diaries()
            st.session_state.api_error = None
        except MapsApiError as e:
            st.session_state.diaries = []
            st.session_state.api_error = str(e)
    if "picked" not in st.session_state:
        st.session_state.picked = None       # 저장 대기 좌표 (lat, lng)
    if "click_sig" not in st.session_state:
        st.session_state.click_sig = None    # 마지막 처리한 클릭 (재실행 중복 방지)
    if "center" not in st.session_state:
        st.session_state.center = DEFAULT_CENTER


# map 생성

def build_map(diaries: list[dict] , center, picked) -> folium.Map:
    m = folium.Map(location = center, zoom_start = DEFAULT_ZOOM, tiles = "OpenStreetMap")

    for d in diaries:
        color = EMOTION_COLORS.get(d.get("emotion"), "gray")
        popup_html  = (
            f"<b>{d['title']}</b><br>"
            f"{d['date']} · {d.get('emotion', '')}<br>"
            f"{d.get('summary', '')}"
        )

        folium.Marker(
            [d["lat"], d["lng"]],
            popup = folium.Popup(popup_html, max_width = 250),
            tooltip = d["title"],
            icon = folium.Icon(color=color, icon="book", prefix ="fa")
        ).add_to(m)

    if picked:
        folium.Marker(
            [picked[0],picked[1]],
            tooltip ="선택한 위치",
            icon = folium.Icon(color="gray", icon="plus", prefix = "fa")
        ).add_to(m)

    return m


def capture_click(map_data) -> None:
    """ 지도 클릭 좌표를 picked로 반영 """
    clicked = map_data.get("last_clicked") if map_data else None
    if not clicked:
        return

    sig = (clicked["lat"],clicked["lng"])

    if sig != st.session_state.click_sig:
        st.session_state.click_sig = sig
        st.session_state.picked = sig


# ---------------------------------------------------------------- panels
def render_save_form() -> None:
    picked = st.session_state.picked
    if not picked:
        st.info("지도를 클릭해 저장할 위치를 선택하세요.")
        return

    st.success(f"선택 위치 · {picked[0]:.5f}, {picked[1]:.5f}")
    title = st.text_input("제목", key="f_title")
    emotion = st.selectbox("감정", EMOTIONS, key="f_emotion")
    summary = st.text_area("요약", key="f_summary", height=80)

    c1, c2 = st.columns(2)
    if c1.button("이 위치에 일기 저장", type="primary", use_container_width=True):
        if not title.strip():
            st.warning("제목을 입력하세요.")
            return
        try:
            saved = create_diary(
                title.strip(), summary.strip(), emotion, picked[0], picked[1]
            )
        except MapsApiError as e:
            st.error(str(e))
            return
        st.session_state.diaries.append(saved)
        st.session_state.picked = None
        for k in ("f_title", "f_summary"):     # 입력값 초기화
            st.session_state.pop(k, None)
        st.rerun()

    if c2.button("선택 취소", use_container_width=True):
        st.session_state.picked = None
        st.rerun()


def render_diary_list() -> None:
    diaries = st.session_state.diaries
    st.subheader(f"저장된 일기 · {len(diaries)}개")
    for d in reversed(diaries):
        with st.container(border=True):
            st.markdown(f"**{d['title']}**  ·  {d['date']}")
            st.caption(f"{d.get('emotion', '')} · {d['lat']:.4f}, {d['lng']:.4f}")
            if d.get("summary"):
                st.write(d["summary"])
            if st.button("지도에서 보기", key=f"go_{d['id']}", use_container_width=True):
                st.session_state.center = (d["lat"], d["lng"])
                st.session_state.recenter = True
                st.rerun()


# ---------------------------------------------------------------- page
def main() -> None:
    st.set_page_config(page_title="MEDiary · 지도", layout="wide")
    init_state()
    st.title("🗺️ 위치 기반 일기")

    if st.session_state.api_error:
        st.error(
            f"백엔드에 연결할 수 없습니다 — {st.session_state.api_error}\n\n"
            "프로젝트 루트에서 `.venv\\Scripts\\python -m uvicorn backend.main:app --reload` 로 서버를 먼저 실행하세요."
        )
        if st.button("다시 연결"):
            st.session_state.pop("diaries", None)
            st.rerun()
        return

    left, right = st.columns([2, 1], gap="medium")

    with left:
        m = build_map(st.session_state.diaries, st.session_state.center, st.session_state.picked)

        # '지도에서 보기' 눌렀을 때만 강제 재중심 (평소엔 사용자 팬 유지)
        if st.session_state.pop("recenter", False):
            center_arg, zoom_arg = st.session_state.center, 15
        else:
            center_arg, zoom_arg = None, None

        map_data = st_folium(
            m,
            center=center_arg,
            zoom=zoom_arg,
            height=560,
            use_container_width=True,
            returned_objects=["last_clicked"],
        )
        capture_click(map_data)

    with right:
        st.metric("저장된 일기", f"{len(st.session_state.diaries)}개")
        render_save_form()
        st.divider()
        render_diary_list()


main()
