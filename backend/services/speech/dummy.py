from backend.services.speech.base import SpeechToTextAdapter


class DummySpeechToTextAdapter(SpeechToTextAdapter):
    async def transcribe(self, audio: bytes, *, mime_type: str) -> tuple[str, dict[str, str | float]]:
        return "[임시 음성 텍스트]", {"provider": "dummy-stt", "confidence": 1.0}
