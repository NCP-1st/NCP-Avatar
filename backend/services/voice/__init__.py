"""CLOVA Voice 서비스 어댑터."""

from backend.services.voice.clova_voice import (
    EMOTION_STRENGTH_VALUES,
    EMOTION_SUPPORTED_SPEAKERS,
    EMOTION_VALUES,
    synthesize_speech,
)

__all__ = [
    "EMOTION_STRENGTH_VALUES",
    "EMOTION_SUPPORTED_SPEAKERS",
    "EMOTION_VALUES",
    "synthesize_speech",
]
