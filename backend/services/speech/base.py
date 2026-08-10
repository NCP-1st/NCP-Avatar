from abc import ABC, abstractmethod


class SpeechToTextAdapter(ABC):
    @abstractmethod
    async def transcribe(self, audio: bytes, *, mime_type: str) -> tuple[str, dict[str, str | float]]: ...
