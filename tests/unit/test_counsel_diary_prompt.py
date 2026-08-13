"""과거 일기가 프롬프트에 어떤 모양으로 들어가는지.

날짜와 요약만 넘기면 상담사가 "8월 9일 일기를 참고했어요"로 끝내 버린다.
사용자가 받는 건 자기 기록을 읽었다는 통보뿐이고, 그때 무슨 일이 있었는지는
여전히 자기가 다시 말해야 한다.

그래서 제목과 그때의 감정까지 넘긴다. 이미 `diary_versions`에 있고 사용자가
승인한 값이라 새로 만들어 내는 것이 없다 — 본문은 여전히 넣지 않는다.
"""

from __future__ import annotations

from datetime import date

from backend.agents.counsel_chatbot.prompts import (
    COUNSELOR_SYSTEM_PROMPT,
    build_counselor_prompt,
    build_stage_guide,
)
from backend.agents.counsel_chatbot.schemas import CounselStage
from backend.services.knowledge.base import DiaryReference


def _ref(**overrides: object) -> DiaryReference:
    fields: dict[str, object] = {
        "session_id": "s-1",
        "diary_date": date(2026, 8, 9),
        "title": "긴 호흡으로 달린 일요일",
        "summary": "아침 장거리 러닝을 완주하고 오후에는 독서로 쉬었다",
        "emotion_tags": ["성취", "평온"],
        "score": 0.64,
    }
    fields.update(overrides)
    return DiaryReference(**fields)  # type: ignore[arg-type]


def _prompt(*refs: DiaryReference) -> str:
    return build_counselor_prompt(
        message="요즘 달리기를 하는데 그때만 숨통이 트여요",
        state=None,
        facts=[],
        history=[],
        diary_refs=list(refs),
    )


# --- DiaryReference 계약 -------------------------------------------------------


def test_title_is_carried_and_serialized() -> None:
    """검색 구현이 채운 제목이 그대로 실려야 프롬프트가 쓸 수 있다."""
    dumped = _ref().model_dump()

    assert dumped["title"] == "긴 호흡으로 달린 일요일"
    assert dumped["summary"]
    assert dumped["emotion_tags"] == ["성취", "평온"]


def test_title_is_optional() -> None:
    """옛 데이터·스텁에서 비어 올 수 있다. 없다고 터지면 안 된다."""
    assert _ref(title=None).title is None
    assert DiaryReference(
        session_id="s-1", diary_date=date(2026, 8, 9), summary="요약"
    ).title is None


def test_reference_never_carries_the_diary_body() -> None:
    """본문·발췌는 담지 않는다. 담으면 상담이 일기 낭독이 된다."""
    fields = set(DiaryReference.model_fields)

    assert not fields & {"content", "excerpt", "body", "paragraphs"}


# --- 프롬프트 렌더 -------------------------------------------------------------


def test_prompt_shows_the_title_and_the_feeling_of_that_day() -> None:
    rendered = _prompt(_ref())

    assert "긴 호흡으로 달린 일요일" in rendered
    assert "성취, 평온" in rendered
    assert "아침 장거리 러닝을 완주하고" in rendered


def test_prompt_is_not_the_old_date_and_summary_only_format() -> None:
    """옛 포맷은 "- [날짜] 요약" 한 줄이었다. 되돌아가면 여기서 걸린다."""
    ref = _ref()
    rendered = _prompt(ref)

    assert f"- [{ref.diary_date}] {ref.summary}" not in rendered
    assert f"- [{ref.diary_date}] {ref.title}" in rendered


def test_prompt_tells_the_model_to_connect_not_to_cite_a_date() -> None:
    """지시문이 빠지면 모델은 날짜만 대고 끝낸다."""
    rendered = _prompt(_ref())

    assert "날짜만" in rendered
    assert "지어내지 않는다" in rendered


def test_the_diary_body_never_reaches_the_prompt() -> None:
    rendered = _prompt(_ref())

    assert "본문" not in rendered.split("# 사용자의 과거 기록")[1]


# --- 감정 태그가 없을 때 -------------------------------------------------------


def test_missing_emotion_tags_drop_the_line_instead_of_leaving_an_empty_one() -> None:
    """빈 괄호가 남으면 모델이 그걸 내용으로 읽는다.

    감정 태그를 안 단 일기가 실제로 있다(국밥 일기 두 건).
    """
    rendered = _prompt(_ref(emotion_tags=[]))

    assert "그때 감정" not in rendered
    assert "()" not in rendered
    assert "긴 호흡으로 달린 일요일" in rendered


def test_missing_title_falls_back_to_the_summary_without_a_dangling_dash() -> None:
    ref = _ref(title=None)
    rendered = _prompt(ref)

    assert f"- [{ref.diary_date}] {ref.summary}" in rendered
    assert "—" not in rendered.split("# 사용자의 과거 기록")[1]


# --- 과거를 물었을 때 답하라는 지시 -------------------------------------------
#
# 이게 빠지면 검색이 성공해도 답변이 달라지지 않는다. 실제로 그랬다 —
# "국밥 먹었던 날 얘기해줘"에 일기 2건이 붙었는데도 상담사가 "좀 더 자세히
# 들려주시겠어요?"로 되물었다. 기억나지 않아서 물은 사람에게 기억을 요구한
# 셈이다. 지시문이라 회귀해도 테스트가 아니면 안 걸린다.


def test_exploring_stage_tells_the_model_to_answer_before_empathizing() -> None:
    guide = build_stage_guide(CounselStage.EXPLORING)

    assert "예외" in guide
    assert "공감보다 기록의 내용을 먼저 답합니다" in guide
    # 이미 답이 있는 것을 되묻지 않는다.
    assert "되묻지 않습니다" in guide


def test_exploring_stage_also_covers_the_no_record_case() -> None:
    """system(스테이지 가이드)과 user(빈 기록 블록)가 다른 말을 하면 밀린다.

    실측: 가이드에 "물으면 답하라"만 있고 "없으면 없다고 하라"가 없던 판에서
    참조 0건인데도 "부모님과 함께한 여행이라니 멋진 추억이겠어요"가 나왔다.
    """
    guide = build_stage_guide(CounselStage.EXPLORING)

    assert "기록이 주어지지 않았는데" in guide
    assert "찾지 못했어요" in guide
    # 정리할 것이 없으므로 summary 도 닫는다.
    assert "summary는 null" in guide


def test_exploring_stage_keeps_the_default_empathy_first_rule() -> None:
    """예외를 넣느라 기본 규칙이 사라지면 매 턴이 정보 검색이 된다."""
    guide = build_stage_guide(CounselStage.EXPLORING)

    assert "질문은 필요할 때만 합니다" in guide
    assert "방금 한 말에 대한 공감" in guide
    assert "summary / suggestion / suggestion_kind: 반드시 null" in guide


def test_system_prompt_forbids_denying_a_capability_it_has() -> None:
    """"제가 알 수는 없지만"이 실제로 나왔다. 갖고 있는 걸 없다고 한 것이다."""
    assert "기록된 것만 답하고 되묻지 않습니다" in COUNSELOR_SYSTEM_PROMPT
    assert "제가 알 수는 없지만" in COUNSELOR_SYSTEM_PROMPT


def test_system_prompt_still_refuses_when_there_is_no_record() -> None:
    """답하라는 지시가 없는 과거까지 지어내라는 뜻이 되면 안 된다."""
    assert "기록이 없을 때만" in COUNSELOR_SYSTEM_PROMPT
    assert "확인 가능한 기록이 없어요" in COUNSELOR_SYSTEM_PROMPT
    # 지어내기 금지는 그대로여야 한다.
    assert "목록에 없는 과거는 여전히" in COUNSELOR_SYSTEM_PROMPT
    assert "상상해" in COUNSELOR_SYSTEM_PROMPT or "채워 넣지 않습니다" in COUNSELOR_SYSTEM_PROMPT


# --- 기록이 없을 때 -----------------------------------------------------------


def test_an_empty_result_tells_the_model_it_found_nothing() -> None:
    """"찾아봤는데 없었다"를 알려주지 않으면 기억나는 척한다.

    실측: "내가 부모님이랑 여행 갔던 거 알려줘" → 참조 0건인데도
    "어떤 여행이었는지 기억나는 부분이 있으신가요?"로 받았다. 없는 여행을
    있었던 것으로 확인해 준 셈이다.
    """
    rendered = build_counselor_prompt(
        message="내가 부모님이랑 여행 갔던 거 알려줘",
        state=None, facts=[], history=[], diary_refs=[],
    )

    assert "# 사용자의 과거 기록" in rendered
    assert "넘어온 기록이 없다" in rendered
    # 못 찾았다는 말이 **먼저** 나와야 한다. 질문부터 하면 사용자는 답을 들은
    # 줄 알고 넘어간다 — 실제로 그렇게 나왔다.
    assert "첫 문장" in rendered
    assert "순서를 바꾸지 않는다" in rendered
    # 사용자가 꺼낸 사건을 대신 확인해 주지 않는다.
    assert "확인해 주지 않는다" in rendered


def test_the_crisis_path_gets_no_diary_block_at_all() -> None:
    """None은 검색을 아예 안 한 경로다(위기·폴백). 빈 목록과 다르다."""
    rendered = build_counselor_prompt(
        message="힘들어요", state=None, facts=[], history=[], diary_refs=None,
    )

    assert "# 사용자의 과거 기록" not in rendered


def test_several_diaries_each_get_their_own_entry() -> None:
    rendered = _prompt(
        _ref(session_id="s-1", title="국밥 먹은 날", emotion_tags=[]),
        _ref(
            session_id="s-2",
            diary_date=date(2026, 8, 12),
            title="국밥 점심",
            emotion_tags=["기쁨"],
        ),
    )

    assert "국밥 먹은 날" in rendered
    assert "국밥 점심" in rendered
    assert rendered.count("그때 감정") == 1  # 태그가 있는 쪽만
