import re

from backend.agents.diary_chatbot.models import FactExtractionResult

FIELD_PRIORITY = ("person", "location", "emotion")

FALLBACK_QUESTIONS = {
    "person": "그 자리에 누구랑 함께 있었나요?",
    "location": "어느 동에서 있었던 일인가요?",
    "emotion": "그때 기분은 어떠셨어요?",
}

EXPLICIT_LOCATION_PATTERN = re.compile(r"[가-힣]{2,}(?:역|동|구|시|입구)?(?:에서|에\s+갔|에\s+갔다)")
DONG_MENTION_PATTERN = re.compile(
    r"([가-힣A-Za-z0-9·-]{1,20}동)(?=$|[\s,./]|에서|에|으로|근처|부근)"
)


def has_explicit_location_mention(raw_text: str) -> bool:
    """Detect a likely explicit place mention for observability only; never fills location."""
    return bool(EXPLICIT_LOCATION_PATTERN.search(raw_text))


def has_dong_level_location(location: str | None, source_texts: dict[str, str]) -> bool:
    """Accept a location only when a matching administrative dong is in user input."""
    if not location:
        return False
    mentioned_dongs = {
        match.group(1)
        for source_text in source_texts.values()
        for match in DONG_MENTION_PATTERN.finditer(source_text)
    }
    return any(dong in location for dong in mentioned_dongs)


def sanitize_and_fix_turn_result(
    result: FactExtractionResult, source_texts: dict[str, str]
) -> FactExtractionResult:
    """Validate emotion excerpts against their exact source input and recompute coverage."""
    confirmed_emotion = False
    for event in result.events:
        event.emotions = [
            mention
            for mention in event.emotions
            if mention.input_id in source_texts
            and mention.excerpt in source_texts[mention.input_id]
        ]
        confirmed_emotion = confirmed_emotion or bool(event.emotions)

    has_person = any(event.people for event in result.events)
    has_location = any(
        has_dong_level_location(event.location, source_texts)
        for event in result.events
    )
    result.coverage.has_person = has_person
    result.coverage.has_location = has_location
    result.coverage.has_emotion = confirmed_emotion

    present = {"person": has_person, "location": has_location, "emotion": confirmed_emotion}
    missing = [field for field in FIELD_PRIORITY if not present[field]]
    result.coverage.missing_fields = missing
    result.coverage.sufficient = not missing

    return result
