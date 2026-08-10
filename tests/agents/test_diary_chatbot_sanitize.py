import pytest

from backend.agents.diary_chatbot.models import (
    FactExtractionResult,
    EmotionMention,
    EventCandidate,
    Evidence,
    InformationCoverage,
)
from backend.agents.diary_chatbot.sanitize import sanitize_and_fix_turn_result
from tests.agents.emotion_eval_cases import INFLECTED_EMOTION_CASES


def make_result(*, people: list[str], location: str | None,
                emotions: list[EmotionMention]) -> FactExtractionResult:
    return FactExtractionResult(
        events=[EventCandidate(
            event="점심 식사",
            people=people,
            location=location,
            emotions=emotions,
            evidence=[Evidence(input_id="text-1")],
        )],
        coverage=InformationCoverage(
            has_person=True,
            has_location=True,
            has_emotion=True,
            missing_fields=[],
            sufficient=True,
        ),
    )


def test_hallucinated_emotion_is_stripped() -> None:
    result = make_result(
        people=["친구"],
        location="회사 근처",
        emotions=[EmotionMention(label="만족스러움", excerpt="만족스러웠다", input_id="text-1")],
    )
    fixed = sanitize_and_fix_turn_result(
        result, {"text-1": "친구랑 회사 근처에서 밥 먹고 산책했다"}
    )
    assert fixed.events[0].emotions == []
    assert fixed.coverage.has_emotion is False
    assert fixed.coverage.sufficient is False
    assert fixed.coverage.missing_fields == ["location", "emotion"]


def test_explicit_emotion_word_is_kept() -> None:
    mention = EmotionMention(label="좋았음", excerpt="좋았다", input_id="text-1")
    result = make_result(people=["친구"], location="성수동 식당", emotions=[mention])
    fixed = sanitize_and_fix_turn_result(
        result, {"text-1": "친구랑 성수동 식당에서 밥 먹었는데 정말 좋았다"}
    )
    assert fixed.events[0].emotions == [mention]
    assert fixed.coverage.has_emotion is True
    assert fixed.coverage.sufficient is True


def test_missing_fields_follow_fixed_priority() -> None:
    result = make_result(people=[], location="성수동 공원", emotions=[])
    fixed = sanitize_and_fix_turn_result(result, {"text-1": "성수동 공원에 갔다"})
    assert fixed.coverage.missing_fields == ["person", "emotion"]


def test_relative_or_landmark_location_is_below_required_granularity() -> None:
    result = make_result(people=["친구"], location="집 근처", emotions=[])
    fixed = sanitize_and_fix_turn_result(
        result, {"text-1": "친구랑 집 근처에서 치맥했어"}
    )
    assert fixed.coverage.has_location is False
    assert "location" in fixed.coverage.missing_fields


def test_dong_mentioned_by_user_satisfies_location_requirement() -> None:
    result = make_result(people=["친구"], location="화양동", emotions=[])
    fixed = sanitize_and_fix_turn_result(
        result, {"text-1": "친구랑 화양동에서 치맥했어"}
    )
    assert fixed.coverage.has_location is True
    assert "location" not in fixed.coverage.missing_fields


def test_backend_overrides_all_llm_coverage_claims() -> None:
    result = make_result(
        people=[],
        location=None,
        emotions=[EmotionMention(label="신남", excerpt="신났다", input_id="text-1")],
    )
    fixed = sanitize_and_fix_turn_result(result, {"text-1": "혼자 걸었다"})
    assert fixed.coverage.has_person is False
    assert fixed.coverage.has_location is False
    assert fixed.coverage.has_emotion is False
    assert fixed.coverage.missing_fields == ["person", "location", "emotion"]


def test_inflected_emotion_expression_is_confirmed_via_excerpt() -> None:
    mention = EmotionMention(
        label="여유롭고 좋았음",
        excerpt="여유롭고 좋더라고",
        input_id="turn-2",
    )
    result = make_result(people=["가족"], location="집 근처", emotions=[mention])
    fixed = sanitize_and_fix_turn_result(
        result,
        {
            "turn-1": "집 근처에서 가족들과 밥을 먹었어",
            "turn-2": "오랜만에 가족들과 시간을 보내니까 여유롭고 좋더라고",
        },
    )

    assert fixed.events[0].emotions == [mention]
    assert fixed.coverage.has_emotion is True
    assert "emotion" not in fixed.coverage.missing_fields


def test_emotion_excerpt_must_match_the_referenced_input() -> None:
    result = make_result(
        people=["가족"],
        location="집 근처",
        emotions=[EmotionMention(
            label="여유롭고 좋았음",
            excerpt="여유롭고 좋더라고",
            input_id="turn-1",
        )],
    )
    fixed = sanitize_and_fix_turn_result(
        result,
        {
            "turn-1": "집 근처에서 가족들과 밥을 먹었어",
            "turn-2": "오랜만에 가족들과 시간을 보내니까 여유롭고 좋더라고",
        },
    )

    assert fixed.events[0].emotions == []
    assert fixed.coverage.has_emotion is False


@pytest.mark.parametrize("case", INFLECTED_EMOTION_CASES, ids=lambda case: case["id"])
def test_inflected_emotion_evaluation_cases(case: dict[str, str]) -> None:
    mention = EmotionMention(
        label=case["label"],
        excerpt=case["excerpt"],
        input_id="text-1",
    )
    result = make_result(people=["지인"], location="장소", emotions=[mention])
    fixed = sanitize_and_fix_turn_result(result, {"text-1": case["text"]})

    assert fixed.events[0].emotions == [mention]
    assert fixed.coverage.has_emotion is True
