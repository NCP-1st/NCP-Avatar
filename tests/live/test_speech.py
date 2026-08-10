import os
import pytest
from dotenv import load_dotenv  # ← 추가

from backend.services.speech.clova import ClovaSpeechToTextAdapter
from backend.services.speech.dummy import DummySpeechToTextAdapter

# .env 파일 명시적 로드
load_dotenv()


@pytest.mark.anyio
async def test_dummy_stt_adapter():
    adapter = DummySpeechToTextAdapter()
    text, meta = await adapter.transcribe(b"fake-audio-bytes", mime_type="audio/mp3")

    assert text == "[임시 음성 텍스트]"
    assert meta["provider"] == "dummy-stt"


@pytest.mark.live
@pytest.mark.skipif(
    os.getenv("RUN_LIVE_STT_TESTS") != "1",
    reason="RUN_LIVE_STT_TESTS=1 환경변수가 설정되었을 때만 실행",
)
@pytest.mark.anyio
async def test_clova_csr_live():
    client_id = os.getenv("CLOVA_SPEECH_CLIENT_ID") or os.getenv("NCP_CLIENT_ID")
    client_secret = os.getenv("CLOVA_SPEECH_SECRET_KEY") or os.getenv("NCP_CLIENT_SECRET")

    if not client_id or not client_secret:
        pytest.fail("CLOVA_SPEECH_CLIENT_ID 및 CLOVA_SPEECH_SECRET_KEY 환경 변수가 필요합니다.")

    sample_audio_path = "tests/assets/sample.wav"
    if not os.path.exists(sample_audio_path):
        pytest.fail(f"테스트용 음성 파일이 필요합니다: {sample_audio_path}")

    with open(sample_audio_path, "rb") as f:
        audio_bytes = f.read()

    adapter = ClovaSpeechToTextAdapter(client_id=client_id, client_secret=client_secret)
    text, meta = await adapter.transcribe(audio_bytes, mime_type="audio/wav")

    print("\n" + "=" * 50)
    print(f"[CLOVA CSR STT 변환 성공 결과]: {text}")
    print(f"[메타데이터]: {meta}")
    print("=" * 50 + "\n")

    assert isinstance(text, str)
    assert len(text) > 0
    assert meta["provider"] == "clova-csr"
