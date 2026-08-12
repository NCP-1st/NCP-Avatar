"""💬 나만의 상담사 — 상담 채팅, 기억 범위 제어, 안전 안내.

감정은 사용자가 고르지 않는다. 대화 내용에서 분석한 결과를 보여준다.

상태 처리: 빈 화면 / 전송중 / 완료 / 실패 / 위기.
"""

from datetime import date, datetime

import streamlit as st

from api.counsel import CounselApiError, list_sessions, load_session, send_message


# TODO: 로그인 붙기 전까지 임시 사용자.
#
# 캘린더 페이지(`calendar.py`)의 기본값과 **같아야 한다.** 어긋나면 상담이
# 이 사용자의 일기를 하나도 못 찾는다 — 검색은 user_id 로 소유권을 거르므로,
# 일기는 A 앞으로 쌓이는데 상담은 B 로 물어보는 꼴이 된다.
USER_ID = "streamlit-test-user"

# 확신도가 이 아래면 단정적으로 보여주지 않는다.
LOW_CONFIDENCE = 0.3

st.title("💬 나만의 상담사")

if "counsel_turns" not in st.session_state:
    st.session_state.counsel_turns = []  # [{role, content, reply}]
if "counsel_id" not in st.session_state:
    st.session_state.counsel_id = None

def format_last_active(raw: str) -> str:
    """'2026-08-12T10:47:01' → '오늘 10:47' / '8월 11일'.

    `strftime("%-d")`은 POSIX 전용이라 Windows에서 터진다. 직접 만든다.
    """
    stamp = datetime.fromisoformat(raw)
    today = date.today()
    if stamp.date() == today:
        return f"오늘 {stamp.hour:02d}:{stamp.minute:02d}"
    if (today - stamp.date()).days == 1:
        return "어제"
    if stamp.year != today.year:
        return f"{stamp.year}년 {stamp.month}월 {stamp.day}일"
    return f"{stamp.month}월 {stamp.day}일"


def open_session(counsel_id: str) -> None:
    """지난 상담을 화면에 되살린다.

    저장된 건 대화 본문과 근거뿐이다. 감정 분석(`state`)은 그 턴에서만 쓰고
    버리는 값이라 다시 그리지 않는다 — 없는 걸 지어내느니 접어둔 분석이
    지난 대화에는 안 보이는 편이 낫다.
    """
    history = load_session(user_id=USER_ID, counsel_id=counsel_id)
    st.session_state.counsel_id = history["counsel_id"]
    st.session_state.counsel_turns = [
        {
            "role": turn["role"],
            "content": turn["content"],
            "reply": {
                "message": turn["content"],
                "safety_level": "normal",
                "evidences": turn.get("evidences") or [],
            },
        }
        for turn in history["turns"]
    ]


# --- 사이드바: 지난 상담 + 기억 제어 (C-03) ---------------------------------
with st.sidebar:
    st.subheader("지난 상담")
    if st.button("새 대화 시작", use_container_width=True, type="primary"):
        st.session_state.counsel_turns = []
        st.session_state.counsel_id = None
        st.rerun()

    sessions = list_sessions(user_id=USER_ID)
    if not sessions:
        st.caption("아직 나눈 대화가 없어요.")
    for item in sessions:
        current = item["counsel_id"] == st.session_state.counsel_id
        mark = "🔴 " if item["is_crisis"] else ""
        label = f"{mark}{item['title']}"
        if st.button(
            label,
            key=f"open-{item['counsel_id']}",
            use_container_width=True,
            disabled=current,
            help=f"{format_last_active(item['last_active_at'])} · {item['turn_count']}개 대화",
        ):
            try:
                open_session(item["counsel_id"])
            except CounselApiError as exc:
                st.error(str(exc))
            else:
                st.rerun()

    st.divider()
    st.subheader("기억 범위")
    st.caption("상담에 활용할 기록 범위를 직접 정할 수 있어요.")
    memory_enabled = st.toggle("과거 기록 참조하기", value=True)
    period_days = st.slider(
        "기간", min_value=7, max_value=365, value=30, step=7,
        format="최근 %d일", disabled=not memory_enabled,
    )
    st.caption("감정은 고르지 않아도 돼요. 나눈 이야기에서 알아서 읽어냅니다.")
    st.caption("설정한 기간 안의 일기 중, 지금 이야기와 관련 있는 것만 참고합니다.")

# max_items 는 보내지 않는다. 몇 건을 참고할지는 사용자가 정할 일이 아니라
# 관련도가 정한다 — 관련 있는 게 두 건뿐인데 10으로 올려도 두 건이고, 1로
# 낮추면 똑같이 관련 있는 기록이 임의로 잘린다. 서버 기본값(5)이 상한이다.
memory_scope = {
    "enabled": memory_enabled,
    "period_days": period_days,
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


def format_diary_date(raw: str) -> str:
    """'2026-08-05' → '8월 5일'.

    `strftime("%-m")`은 POSIX 전용이라 Windows에서 터진다. 직접 만든다.
    """
    parsed = date.fromisoformat(raw)
    if parsed.year != date.today().year:
        return f"{parsed.year}년 {parsed.month}월 {parsed.day}일"
    return f"{parsed.month}월 {parsed.day}일"


def render_evidences(reply: dict) -> None:
    """이번 답변이 참고한 일기가 언제 것인지 밝힌다 (H-02).

    상담사가 과거를 언급하면 사용자는 "이걸 어떻게 알지?"라고 생각한다. 출처를
    보여주면 그 자리에서 확인된다.

    참고한 게 없으면 아무것도 그리지 않는다. 빈 근거 영역이 매번 보이면
    그것대로 "오늘은 왜 없지"라는 오해를 만든다.
    """
    evidences = reply.get("evidences") or []
    if not evidences:
        return

    labels = []
    for item in evidences:
        raw = item.get("diary_date")
        try:
            labels.append(format_diary_date(raw))
        except (TypeError, ValueError):
            # 날짜를 못 읽어도 근거가 있었다는 사실은 남긴다.
            if raw:
                labels.append(str(raw))

    if not labels:
        return
    st.caption(f"📖 {', '.join(labels)}자 일기를 참고했어요")


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

    render_evidences(reply)

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
