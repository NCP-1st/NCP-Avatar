"""Narration script API client for Streamlit."""

from api.diary import _request


def generate_narration_script(
    diary_id: str,
    diary_result: dict,
    *,
    target_duration_seconds: int = 30,
) -> dict:
    """Generate a narration preview from a completed diary result."""
    return _request(
        "POST",
        "/api/script/ai_script",
        json={
            "diary_id": diary_id,
            "diary": {
                "title": diary_result["title"],
                "content": diary_result["content"],
                "paragraphs": diary_result["paragraphs"],
                "summary": diary_result["summary"],
                "emotion_tags": diary_result.get("emotion_tags", []),
                "evidence_input_ids": diary_result.get("evidence_input_ids", []),
            },
            "script_options": {
                "target_duration_seconds": target_duration_seconds,
                "tone": "따뜻한 회상",
            },
        },
    )
