"""CLOVA Voice 서비스 어댑터."""

from backend.services.voice.base import VoiceAdapter
from backend.services.voice.clova_voice import (
    EMOTION_STRENGTH_VALUES,
    EMOTION_SUPPORTED_SPEAKERS,
    EMOTION_VALUES,
    synthesize_speech,
)
from backend.services.voice.stub import NotImplementedVoiceAdapter

__all__ = [
    "EMOTION_STRENGTH_VALUES",
    "EMOTION_SUPPORTED_SPEAKERS",
    "EMOTION_VALUES",
    "NotImplementedVoiceAdapter",
    "VoiceAdapter",
    "synthesize_speech",
]
