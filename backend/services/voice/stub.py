from backend.services.voice.base import VoiceAdapter


class NotImplementedVoiceAdapter(VoiceAdapter):
    """Wiring probe used until CLOVA Voice is implemented."""

    def __init__(self) -> None:
        self.call_count = 0

    async def synthesize(
        self,
        script: str,
        *,
        voice_id: str,
        emotion: str | None = None,
    ) -> bytes:
        self.call_count += 1
        raise NotImplementedError("CLOVA Voice adapter is not implemented")
