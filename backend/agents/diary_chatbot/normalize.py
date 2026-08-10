from typing import Any

from backend.agents.diary_chatbot.models import FactExtractionResult


def normalize_fact_extraction(
    raw: Any,
    *,
    source_texts: dict[str, str],
    image_input_ids: set[str] | None = None,
    current_input_id: str | None = None,
) -> FactExtractionResult:
    """Convert recoverable HCX output into the canonical extraction contract.

    HCX-005 does not support Structured Outputs. This boundary therefore supplies
    harmless defaults, rejects invented provenance, and drops only unusable event
    fragments before strict Pydantic validation.
    """
    payload = _unwrap(raw)
    valid_input_ids = set(source_texts) | (image_input_ids or set())
    events: list[dict[str, Any]] = []

    for candidate in _as_list(payload.get("events")):
        if not isinstance(candidate, dict):
            continue
        event_text = _text(candidate.get("event"))
        if not event_text or not _contains_hangul(event_text):
            continue

        evidence = _normalize_evidence(candidate.get("evidence"), valid_input_ids)
        if not evidence and current_input_id in valid_input_ids:
            evidence = [{"input_id": current_input_id, "excerpt": None}]
        if not evidence:
            inferred_id = _unique_source_for_text(event_text, source_texts)
            if inferred_id:
                evidence = [{"input_id": inferred_id, "excerpt": event_text}]
        if not evidence:
            # An event without known provenance must not enter the diary.
            continue

        events.append({
            "event": event_text,
            "time": _optional_text(candidate.get("time")),
            "people": _text_list(candidate.get("people")),
            "location": _optional_text(candidate.get("location")),
            "actions": _text_list(candidate.get("actions")),
            "emotions": _normalize_emotions(candidate.get("emotions"), source_texts),
            "evidence": evidence,
        })

    has_person = any(event["people"] for event in events)
    has_location = any(event["location"] for event in events)
    has_emotion = any(event["emotions"] for event in events)
    present = {"person": has_person, "location": has_location, "emotion": has_emotion}
    missing_fields = [name for name in ("person", "location", "emotion") if not present[name]]

    image_clarity = []
    for note in _as_list(payload.get("image_clarity")):
        if not isinstance(note, dict) or note.get("input_id") not in (image_input_ids or set()):
            continue
        image_clarity.append({
            "input_id": note["input_id"],
            "unclear": bool(note.get("unclear", False)),
            "reason": _optional_text(note.get("reason")),
        })

    image_observations = []
    for observation in _as_list(payload.get("image_observations")):
        if not isinstance(observation, dict):
            continue
        input_id = observation.get("input_id")
        description = _text(observation.get("description"))
        if (
            input_id not in (image_input_ids or set())
            or not description
            or not _contains_hangul(description)
        ):
            continue
        image_observations.append({
            "input_id": input_id,
            "description": description,
            "observed_facts": [
                fact for fact in _text_list(observation.get("observed_facts"))
                if _contains_hangul(fact)
            ],
            "related_event": _optional_text(observation.get("related_event")),
        })

    return FactExtractionResult.model_validate({
        "events": events,
        "coverage": {
            "has_person": has_person,
            "has_location": has_location,
            "has_emotion": has_emotion,
            "sufficient": not missing_fields,
            "missing_fields": missing_fields,
        },
        "image_observations": image_observations,
        "image_clarity": image_clarity,
        "model": _text(payload.get("model")) or "HCX-005",
    })


def _unwrap(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    for key in ("fact_extraction_result", "FactExtractionResult", "chatbot_turn_result", "ChatbotTurnResult"):
        nested = raw.get(key)
        if isinstance(nested, dict):
            return nested
    return raw


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _optional_text(value: Any) -> str | None:
    return _text(value) or None


def _text_list(value: Any) -> list[str]:
    if isinstance(value, str):
        value = [value]
    return [text for item in _as_list(value) if (text := _text(item))]


def _normalize_evidence(value: Any, valid_input_ids: set[str]) -> list[dict[str, str | None]]:
    normalized = []
    for item in _as_list(value):
        if isinstance(item, str):
            input_id, excerpt = item, None
        elif isinstance(item, dict):
            input_id = item.get("input_id")
            excerpt = _optional_text(item.get("excerpt"))
        else:
            continue
        if input_id in valid_input_ids:
            normalized.append({"input_id": input_id, "excerpt": excerpt})
    return normalized


def _normalize_emotions(value: Any, source_texts: dict[str, str]) -> list[dict[str, str]]:
    normalized = []
    for item in _as_list(value):
        if isinstance(item, str):
            label = excerpt = _text(item)
            input_id = None
        elif isinstance(item, dict):
            label = _text(item.get("label")) or _text(item.get("excerpt"))
            excerpt = _text(item.get("excerpt")) or _text(item.get("label"))
            input_id = item.get("input_id")
        else:
            continue
        if not label or not excerpt:
            continue
        if input_id in source_texts and excerpt in source_texts[input_id]:
            normalized.append({"label": label, "excerpt": excerpt, "input_id": input_id})
            continue
        matching_ids = [key for key, text in source_texts.items() if excerpt in text]
        if len(matching_ids) == 1:
            normalized.append({"label": label, "excerpt": excerpt, "input_id": matching_ids[0]})
    return normalized


def _unique_source_for_text(text: str, source_texts: dict[str, str]) -> str | None:
    matches = [input_id for input_id, source in source_texts.items() if text in source or source in text]
    return matches[0] if len(matches) == 1 else None


def _contains_hangul(text: str) -> bool:
    return any("가" <= character <= "힣" for character in text)
