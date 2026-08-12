"""과거 단정 가드레일 (H-02).

이 검사는 **일기가 하나도 검색되지 않은 턴에서만** 걸린다. 그래서 상담사가
"근거 없이 과거를 말했는가"를 판정하는 마지막 지점이고, 여기서 틀리면 둘 중
하나가 된다 — 지어낸 과거가 그대로 나가거나, 멀쩡한 반영이 폴백 문구로
대체되거나.

여기 있는 문장들은 대부분 운영 DB에 실제로 쌓인 답변에서 가져왔다.
"""

import pytest

from backend.agents.counsel_chatbot.safety import review_past_claims


# --- 1. 습관·반복 단정 --------------------------------------------------------
#
# 한 번 들은 이야기로 "늘 그렇다"고 일반화하는 것. 대화에 있든 없든 상담사가
# 알 수 없는 것이라 근거 대조와 무관하게 막는다.


@pytest.mark.parametrize(
    "reply",
    [
        "예전에도 이런 일로 힘들어하셨죠.",
        "늘 그렇게 참아오셨군요.",
        "매번 혼자 감당하시는군요.",
        "저번에도 비슷한 일로 힘들어하셨죠.",
    ],
)
def test_habitual_claims_are_blocked(reply: str) -> None:
    assert review_past_claims(reply, grounded="저번에 회사 얘기 했잖아요") == [
        "past_speculation"
    ]


# --- 2. 대화에 없는 시점을 단정 ------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "8월 5일에 발표 준비를 하셨네요.",
        "지난주에 친구분들과 시간을 보내셨죠.",
        "작년에 비슷한 일을 겪으셨군요.",
        "어제 잠을 못 주무셨군요.",
        "3일 전에 그 일이 있으셨죠.",
    ],
)
def test_time_anchors_the_user_never_mentioned_are_blocked(reply: str) -> None:
    """상담사가 스스로 꺼낸 시점은 지어낸 것이다."""
    assert review_past_claims(reply, grounded="요즘 좀 지쳐요") == ["past_fabrication"]


def test_the_same_sentence_passes_once_the_user_said_it() -> None:
    """같은 문장이라도 사용자가 꺼낸 시점이면 감정 반영이다.

    이 구분이 없으면 상담의 기본 기법인 반영이 전부 막힌다. 실측에서 시점
    표현만 보고 잡았더니 운영 답변에서 걸린 3건이 전부 이런 오탐이었다.
    """
    reply = "지난주에 친구분들과 시간을 보내셨죠."

    assert review_past_claims(reply, grounded="요즘 외로워요") == ["past_fabrication"]
    assert (
        review_past_claims(
            reply, grounded="지난주에 친구들이랑 놀러 갔던 거 기억나세요?"
        )
        == []
    )


def test_spacing_does_not_decide_the_verdict() -> None:
    """'지난 주'와 '지난주'가 다른 판정을 받으면 안 된다."""
    assert review_past_claims("지난 주에 그러셨군요.", grounded="지난주에 힘들었어요") == []
    assert review_past_claims("지난주에 그러셨군요.", grounded="지난 주에 힘들었어요") == []


# --- 3. 막으면 안 되는 것 ------------------------------------------------------


def test_questions_about_the_past_are_allowed() -> None:
    """묻는 건 단정이 아니다. 막으면 상담사가 과거를 물어볼 수 없다."""
    assert review_past_claims(
        "그때 어떤 상황이 특히 힘들게 했나요?", grounded="요즘 지쳐요"
    ) == []
    assert review_past_claims(
        "지난주에는 좀 어떠셨어요?", grounded="요즘 지쳐요"
    ) == []


@pytest.mark.parametrize("tail", ["?", ".", "", "…"])
def test_a_question_stays_a_question_whatever_it_ends_with(tail: str) -> None:
    """모델은 물음표를 빼먹는다. 부호로만 판정하면 멀쩡한 질문이 막힌다."""
    assert review_past_claims(
        f"지난주에는 어떠셨나요{tail}", grounded="요즘 지쳐요"
    ) == []


@pytest.mark.parametrize(
    "reply",
    [
        # 실제 운영 답변에서 가져온 것들
        "많이 힘드셨겠어요.",
        "회사 일 때문에 많이 피로하시겠어요.",
        "혼자만의 시간을 즐기면서 소소한 행복을 찾으셨군요.",
        "이야기해 주셔서 고마워요.",
    ],
)
def test_ordinary_replies_are_untouched(reply: str) -> None:
    """시점을 특정하지 않는 공감은 과거 단정이 아니다."""
    assert review_past_claims(reply, grounded="요즘 회사 일로 지쳐요") == []


def test_vague_time_words_are_not_anchors() -> None:
    """'요즘'·'가끔'은 사실을 특정하지 않는다. 인상을 말하는 것이다."""
    assert review_past_claims("요즘 계속 지치셨군요.", grounded="힘들어요") == []
    assert review_past_claims("가끔 그런 날이 있으셨군요.", grounded="힘들어요") == []


def test_empty_grounding_treats_every_anchor_as_unfounded() -> None:
    """호출부가 대화를 안 넘기면 보수적으로 막는다."""
    assert review_past_claims("지난주에 그러셨군요.") == ["past_fabrication"]
