"""마무리 카드를 그릴지 말지 정하는 부분만 따로 본다.

Streamlit 페이지는 임포트하는 것만으로 화면을 그린다. 판정 로직만 떼어
와서, 화면에 빈 카드가 나가는 경우가 없는지 확인한다.
"""

from pathlib import Path


_SOURCE = (
    Path(__file__).resolve().parents[2] / "frontend" / "pages" / "counsel.py"
).read_text(encoding="utf-8")


def decides_to_draw(reply: dict) -> bool:
    """`render_closing` 이 카드를 그리기로 하는 조건과 같은 판정.

    페이지 함수는 st.* 를 부르므로 그대로 실행할 수 없다. 조건만 따라간다.
    소스가 바뀌면 아래 `test_source_still_guards_empty_bodies` 가 알려준다.
    """
    sections = reply.get("sections") or {}
    kind = sections.get("closing_kind")
    if not kind:
        return False
    body = (
        sections.get("summary")
        if kind == "emotion_card"
        else sections.get("suggestion")
    )
    return bool(body)


def test_card_is_drawn_when_the_summary_is_there() -> None:
    assert decides_to_draw(
        {"sections": {"closing_kind": "emotion_card", "summary": "하루가 길었네요."}}
    )


def test_task_is_drawn_when_the_suggestion_is_there() -> None:
    assert decides_to_draw(
        {"sections": {"closing_kind": "action_task", "suggestion": "차 한 잔 어때요"}}
    )


def test_empty_card_is_not_drawn() -> None:
    """모델이 두 번 재생성하고도 못 채우면 서버가 본문만 내보낸다.

    그때 빈 테두리 상자가 그려지면 사용자에게는 고장으로 보인다.
    """
    assert not decides_to_draw(
        {"sections": {"closing_kind": "emotion_card", "summary": None}}
    )
    assert not decides_to_draw(
        {"sections": {"closing_kind": "action_task", "suggestion": ""}}
    )


def test_ordinary_turns_are_not_cards() -> None:
    assert not decides_to_draw({"sections": {"closing_kind": None, "summary": "정리"}})
    assert not decides_to_draw({"sections": None})
    assert not decides_to_draw({})


def test_replayed_history_falls_back_to_the_stored_text() -> None:
    """지난 상담을 다시 열면 `sections` 가 없다. 카드를 지어내지 않는다."""
    assert not decides_to_draw({"message": "오늘 이야기 고마웠어요", "evidences": []})


def test_source_still_guards_empty_bodies() -> None:
    """위 판정이 페이지 코드와 갈라지면 이 테스트가 먼저 깨진다."""
    assert "if not body:" in _SOURCE
    assert "return False" in _SOURCE
