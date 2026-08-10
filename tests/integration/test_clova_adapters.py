import asyncio
import httpx

from backend.services.speech.clova import ClovaSpeechToTextAdapter


def test_clova_speech_request_and_response_mapping() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["X-NCP-APIGW-API-KEY-ID"] == "client-id"
        assert request.url.params["lang"] == "Kor"
        assert await request.aread() == b"audio"
        return httpx.Response(200, json={"text": "실제 음성 인식 결과"})

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            adapter = ClovaSpeechToTextAdapter("client-id", "secret", client=client)
            text, metadata = await adapter.transcribe(b"audio", mime_type="audio/wav")
            assert text == "실제 음성 인식 결과"
            assert metadata["provider"] == "clova-csr"

    asyncio.run(run())
