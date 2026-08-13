"""opening 단계에서 일기를 찾을지 정하는 문자열 판정.

단계 라우팅은 구조화 LLM 이 한다(`ConversationState.intent` → RECALL,
`test_counsel_recall_stage.py`). 여기 판정은 그 앞을 받친다 — 구조화가
`intent="normal"`로 잘못 보거나 아예 실패해도, 첫 마디에 과거를 물었으면
일기는 찾아 둔다. 못 찾으면 있는 기록을 없다고 말하게 된다.

문자열로 판정하는 이유는 안정성이다. 감정 라벨을 검색 질의에 넣었다가 같은
문장이 실행마다 다른 점수를 받은 전례가 있다(`diary_vector.search` 주석).
"""

from __future__ import annotations

import pytest

from backend.orchestration.counsel_flow import _asks_about_past


# --- 과거를 묻는 말 -----------------------------------------------------------
#
# 전부 사용자가 Streamlit 에서 실제로 친 문장이거나 그 변형이다.


@pytest.mark.parametrize(
    "message",
    [
        "국밥 먹었던 거 기억나?",
        "국밥 먹었던 날 얘기해줘",
        "내가 뭐했는지 알려줘",
        "내가 뭐할 때 행복했었는지 알려줄래?",
        "아 행복하고 싶은데 내가 뭐할 때 행복했었더라",
        "옛날에 철수랑 어디서 놀았더라",
        "내 일기들 중에 찾아주라",
        "내가 전에 맛있게 먹었던 음식이 뭐지",
        "내가 부모님이랑 여행 갔던 거 알려줘",
    ],
)
def test_recall_requests_are_recognized(message: str) -> None:
    assert _asks_about_past(message)


# --- 과거를 묻지 않는 말 -------------------------------------------------------
#
# 여기가 더 중요하다. 잘못 걸리면 털어놓는 사람에게 기록을 들이밀게 된다.


@pytest.mark.parametrize(
    "message",
    [
        "요즘 좀 힘들어요",
        "회사에서 계속 치이는 기분이에요",
        "요즘 퇴근하고 청계천에서 달리기를 하는데 그때만 숨통이 트여요",
        # 과거 표지는 있지만 묻는 게 아니라 털어놓는 말이다.
        "지난주에 팀 앞에서 발표를 했는데 아직도 긴장돼요",
        "어제 동료들이랑 점심에 국밥을 먹었는데 그게 유난히 좋았어요",
    ],
)
def test_telling_a_story_is_not_a_recall_request(message: str) -> None:
    assert not _asks_about_past(message)
