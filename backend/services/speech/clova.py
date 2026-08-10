import httpx

from backend.services.speech.base import SpeechToTextAdapter


class ClovaSpeechToTextAdapter(SpeechToTextAdapter):
    """CSR adapter for short voice memos. Long-form CLOVA Speech is a separate adapter."""

    API_URL = "https://naveropenapi.apigw.ntruss.com/recog/v1/stt"

    def __init__(self, client_id: str, client_secret: str, *, timeout_seconds: float = 30.0,
                 client: httpx.AsyncClient | None = None) -> None:
        self._headers = {
            "X-NCP-APIGW-API-KEY-ID": client_id,
            "X-NCP-APIGW-API-KEY": client_secret,
            "Content-Type": "application/octet-stream",
        }
        self._timeout = timeout_seconds
        self._client = client

    async def transcribe(self, audio: bytes, *, mime_type: str) -> tuple[str, dict[str, str | float]]:
        if self._client:
            response = await self._client.post(self.API_URL, params={"lang": "Kor"},
                                               headers=self._headers, content=audio)
        else:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.post(self.API_URL, params={"lang": "Kor"},
                                             headers=self._headers, content=audio)
        response.raise_for_status()
        text = response.json().get("text")
        if not text:
            raise ValueError("CLOVA Speech response did not contain text")
        return text, {"provider": "clova-csr"}
