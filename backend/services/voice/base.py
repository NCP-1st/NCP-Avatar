from abc import ABC, abstractmethod


class VoiceAdapter(ABC):
    @abstractmethod
    async def synthesize(
        self,
        script: str,
        *,
        voice_id: str,
        emotion: str | None = None,
    ) -> bytes: ...
