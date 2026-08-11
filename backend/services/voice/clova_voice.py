"""CLOVA Voice TTS REST API 어댑터."""

from __future__ import annotations

from typing import Any

import httpx

from backend.services.voice.base import VoiceAdapter


EMOTION_SUPPORTED_SPEAKERS = (
    "nara",
    "vara",
    "vmikyung",
    "vdain",
    "vyuna",
    "vgoeun",
    "vdaeseong",
)

EMOTION_VALUES = {
    "중립": 0,
    "슬픔": 1,
    "기쁨": 2,
    "분노": 3,
}

EMOTION_STRENGTH_VALUES = {
    "약함": 0,
    "보통": 1,
    "강함": 2,
}

_EMOTION_STRENGTH_SUPPORTED_SPEAKERS = frozenset(
    speaker for speaker in EMOTION_SUPPORTED_SPEAKERS if speaker != "nara"
)


def _resolve_tts_url(api_url: str) -> str:
    """CLOVA Voice base URL 또는 전체 TTS URL을 호출 URL로 정규화한다."""
    normalized = api_url.rstrip("/")
    if not normalized.endswith("/tts"):
        normalized = f"{normalized}/tts"
    return normalized


def _validate_voice_options(
    *,
    speaker: str,
    emotion: int,
    emotion_strength: int | None,
    audio_format: str,
) -> None:
    if speaker not in EMOTION_SUPPORTED_SPEAKERS:
        raise ValueError(f"감정 표현을 지원하지 않는 speaker입니다: {speaker}")
    if emotion not in EMOTION_VALUES.values():
        raise ValueError("emotion은 0~3이어야 합니다")
    if speaker == "nara" and emotion == EMOTION_VALUES["분노"]:
        raise ValueError("nara는 분노 감정을 지원하지 않습니다")
    if emotion_strength is not None:
        if speaker not in _EMOTION_STRENGTH_SUPPORTED_SPEAKERS:
            raise ValueError(f"{speaker}는 emotion-strength를 지원하지 않습니다")
        if emotion_strength not in EMOTION_STRENGTH_VALUES.values():
            raise ValueError("emotion_strength는 0~2여야 합니다")
    if audio_format not in {"mp3", "wav"}:
        raise ValueError("audio_format은 mp3 또는 wav여야 합니다")


async def synthesize_speech(
    text: str,
    config: dict[str, Any],
    *,
    speaker: str | None = None,
    emotion: int = 0,
    emotion_strength: int | None = None,
    audio_format: str | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> bytes:
    """텍스트를 음성으로 합성하고 오디오 바이트를 반환한다.

    기본 음성은 ``nara``, 기본 감정은 중립(0), 기본 반환 형식은 ``mp3``다.
    인증 정보는 main의 ``voice`` 설정에서 주입받는다.
    """
    if not text.strip():
        raise ValueError("합성할 text는 비어 있을 수 없습니다")

    voice_config = config["voice"]
    selected_speaker = speaker or voice_config.get("speaker", "nara")
    selected_format = audio_format or voice_config.get("format", "mp3")

    _validate_voice_options(
        speaker=selected_speaker,
        emotion=emotion,
        emotion_strength=emotion_strength,
        audio_format=selected_format,
    )

    client_id = voice_config["client_id"]
    client_secret = voice_config["client_secret"]
    if not client_id or not client_secret:
        raise ValueError("CLOVA API Client ID와 Client Secret이 필요합니다")

    request_data: dict[str, str | int] = {
        "speaker": selected_speaker,
        "text": text,
        "volume": "0",
        "emotion": emotion,
        "speed": "0",
        "pitch": "0",
        "format": selected_format,
    }
    if emotion_strength is not None:
        request_data["emotion-strength"] = emotion_strength

    owns_client = http_client is None
    client = http_client or httpx.AsyncClient(
        timeout=voice_config.get("timeout_s", 30.0)
    )
    try:
        response = await client.post(
            _resolve_tts_url(voice_config["api_url"]),
            headers={
                "X-NCP-APIGW-API-KEY-ID": client_id,
                "X-NCP-APIGW-API-KEY": client_secret,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=request_data,
        )
        response.raise_for_status()
        return response.content
    finally:
        if owns_client:
            await client.aclose()


class ClovaVoiceAdapter(VoiceAdapter):
    """CLOVA Voice implementation used by diary media orchestration."""

    def __init__(self, config: dict[str, Any]) -> None:
        self._config = config

    async def synthesize(
        self,
        script: str,
        *,
        voice_id: str,
        emotion: str | None = None,
    ) -> bytes:
        selected_emotion = EMOTION_VALUES.get(emotion or "중립", 0)
        if voice_id == "nara" and emotion == "분노":
            selected_emotion = EMOTION_VALUES["중립"]

        return await synthesize_speech(
            script,
            self._config,
            speaker=voice_id,
            emotion=selected_emotion,
        )
