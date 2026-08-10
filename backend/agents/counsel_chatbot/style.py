

from __future__ import annotations

import re

# 사용자가 한 줄 던졌다고 답도 한 줄일 수는 없다. 짧은 발화에는 바닥값을 둔다.
_LENGTH_FLOOR = 120
_LENGTH_RATIO = 1.5

_MARKUP_PATTERN = re.compile(r"^\s*[-*•]\s|^\s*\d+[.)]\s|^\s*#{1,6}\s|\*\*", re.MULTILINE)

# 이모지. 감정 표현을 그림으로 대신하지 않는다.
_EMOJI_PATTERN = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f1e6-\U0001f1ff]"
)

_SENTENCE_SPLIT = re.compile(r"[.!?…\n]+")


def review_style(
    reply: str,
    *,
    user_message: str,
    previous_reply: str | None = None,
) -> list[str]:
    issues: list[str] = []

    if len(reply) > max(_LENGTH_FLOOR, len(user_message) * _LENGTH_RATIO):
        issues.append("too_long")

    if reply.count("?") > 1:
        issues.append("multi_question")

    if _MARKUP_PATTERN.search(reply):
        issues.append("markup")

    if _EMOJI_PATTERN.search(reply):
        issues.append("emoji")

    if previous_reply and _repeats_opening(reply, previous_reply):
        issues.append("repeated_empathy")

    return issues


def _repeats_opening(reply: str, previous_reply: str) -> bool:
    current = _first_sentence(reply)
    previous = _first_sentence(previous_reply)
    if len(current) < 6 or len(previous) < 6:
        return False
    if current == previous:
        return True

    # 어미만 바꾼 경우까지 잡는다.
    current_tokens = set(current.split())
    previous_tokens = set(previous.split())
    if not current_tokens or not previous_tokens:
        return False
    overlap = len(current_tokens & previous_tokens)
    return overlap / min(len(current_tokens), len(previous_tokens)) >= 0.7


def _first_sentence(text: str) -> str:
    for part in _SENTENCE_SPLIT.split(text.strip()):
        cleaned = part.strip()
        if cleaned:
            return cleaned
    return ""
