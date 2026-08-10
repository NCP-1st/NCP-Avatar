"""💬 나만의 상담사 — 상담 채팅, 기억 범위 제어, 안전 안내.

감정은 사용자가 고르지 않는다. 대화 내용에서 분석한 결과를 보여준다.

상태 처리: 빈 화면 / 전송중 / 완료 / 실패 / 위기.
"""

import streamlit as st

from api.counsel import CounselApiError, send_message


# TODO: 로그인 붙기 전까지 임시 사용자
USER_ID = "demo-user"

# 확신도가 이 아래면 단정적으로 보여주지 않는다.
LOW_CONFIDENCE = 0.3

st.title("💬 나만의 상담사")

if "counsel_turns" not in st.session_state:
    st.session_state.counsel_turns = []  # [{role, content, reply}]
if "counsel_id" not in st.session_state:
    st.session_state.counsel_id = None

# --- 기억 제어 (C-03) ------------------------------------------------------
with st.sidebar:
    st.subheader("기억 범위")
    st.caption("상담에 활용할 기록 범위를 직접 정할 수 있어요.")
    memory_enabled = st.toggle("과거 기록 참조하기", value=True)
    period_days = st.slider(
        "기간", min_value=7, max_value=365, value=30, step=7,
        format="최근 %d일", disabled=not memory_enabled,
    )
    max_items = st.slider(
        "참조 개수", min_value=1, max_value=10, value=5, disabled=not memory_enabled,
    )
    st.caption("감정은 고르지 않아도 돼요. 나눈 이야기에서 알아서 읽어냅니다.")
    st.caption("일기 검색은 아직 연결 전이라 지금은 관계 정보에만 적용됩니다.")
    if st.button("대화 새로 시작", use_container_width=True):
        st.session_state.counsel_turns = []
        st.session_state.counsel_id = None
        st.rerun()

memory_scope = {
    "enabled": memory_enabled,
    "period_days": period_days,
    "max_items": max_items,
}


def render_analysis(reply: dict) -> None:
    """분석 결과는 접어둔다.

    감정과 사건을 매 답변 아래 펼쳐두면 대화가 아니라 보고서로 읽힌다.
    한 줄 요약만 남기고 자세한 건 펼쳐볼 사람만 보게 한다.
    """
    state = reply.get("state") or {}
    emotion = state.get("emotion")
    events = state.get("events") or []

    if not emotion and not events:
        return

    if emotion:
        labels = " · ".join([emotion["primary"], *emotion.get("secondary", [])])
        intensity = "●" * emotion["intensity"] + "○" * (5 - emotion["intensity"])
        hedge = "?" if emotion["confidence"] < LOW_CONFIDENCE else ""
        label = f"{labels}{hedge} {intensity}"
    else:
        label = "분석 결과"

    with st.expander(label):
        if emotion and emotion.get("evidence"):
            st.caption(f"그렇게 본 부분: “{emotion['evidence']}”")

        for event in events:
            detail = " · ".join(
                part
                for part in (
                    event.get("when_hint"),
                    event.get("place"),
                    ", ".join(event.get("people", [])) or None,
                )
                if part
            )
            st.markdown(f"- {event['summary']}" + (f" ({detail})" if detail else ""))


def render_reply(reply: dict) -> None:
    """응답 본문 + 접어둔 분석 + 안전 안내."""
    if reply.get("safety_level") == "crisis":
        st.error(reply["message"])
        st.warning(reply["safety_notice"])
        return

    st.markdown(reply["message"])

    # 음악 제안임을 여기서 표시한다. 응답 본문에는 이모지를 넣지 않는다.
    sections = reply.get("sections") or {}
    if sections.get("suggestion_kind") == "music":
        st.caption("🎵 지금 마음에 어울릴 만한 음악이에요")

    if reply.get("safety_notice"):
        st.info(reply["safety_notice"])
    render_analysis(reply)


# --- 대화 이력 -------------------------------------------------------------
if not st.session_state.counsel_turns:
    st.info(
        "오늘 마음이 어땠는지 편하게 적어주세요. "
        "진단이나 치료 조언은 드릴 수 없지만, 이야기를 정리하는 건 함께할 수 있어요."
    )

for turn in st.session_state.counsel_turns:
    with st.chat_message(turn["role"]):
        if turn["role"] == "user":
            st.markdown(turn["content"])
        else:
            render_reply(turn["reply"])

# --- 입력 -----------------------------------------------------------------
if user_message := st.chat_input("지금 마음을 이야기해 주세요"):
    st.session_state.counsel_turns.append({"role": "user", "content": user_message})
    with st.chat_message("user"):
        st.markdown(user_message)

    with st.chat_message("assistant"):
        with st.spinner("마음을 정리하는 중이에요…"):
            try:
                reply = send_message(
                    user_id=USER_ID,
                    message=user_message,
                    counsel_id=st.session_state.counsel_id,
                    memory_scope=memory_scope,
                )
            except CounselApiError as exc:
                # 실패한 턴은 이력에서 빼서 같은 메시지를 다시 보낼 수 있게 한다.
                st.session_state.counsel_turns.pop()
                st.error(f"{exc}\n\n메시지를 다시 보내주세요.")
                st.stop()

    st.session_state.counsel_id = reply["counsel_id"]
    st.session_state.counsel_turns.append(
        {"role": "assistant", "content": reply["message"], "reply": reply}
    )
    st.rerun()
