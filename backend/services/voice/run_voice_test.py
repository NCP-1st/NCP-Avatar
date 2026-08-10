"""CLOVA Voice 연결을 확인하는 수동 실행 스크립트.

프로젝트 루트에서 다음과 같이 실행한다.

    python -m backend.services.voice.run_voice_test
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from backend.config import load_config
from backend.services.voice import (
    EMOTION_STRENGTH_VALUES,
    EMOTION_VALUES,
    synthesize_speech,
)


_VOICE_DIR = Path(__file__).resolve().parent
_TEST_DATA_PATH = _VOICE_DIR / "test.json"
_OUTPUT_PATH = _VOICE_DIR / "output" / "test_diary.mp3"


def load_test_script(path: Path = _TEST_DATA_PATH) -> dict[str, Any]:
    """대본 생성 결과 형식의 Voice 테스트 데이터를 읽는다."""
    script = json.loads(path.read_text(encoding="utf-8"))
    if not str(script.get("narration_text", "")).strip():
        raise ValueError("test.json에 narration_text가 필요합니다")
    return script


async def main() -> None:
    config = load_config()
    script = load_test_script()
    voice = script.get("voice", {})
    speaker = voice.get("speaker", "nara")
    emotion_name = script.get("emotion", "중립")
    strength_name = voice.get("emotion_strength")

    if emotion_name not in EMOTION_VALUES:
        raise ValueError(f"지원하지 않는 emotion 이름입니다: {emotion_name}")
    if strength_name is not None and strength_name not in EMOTION_STRENGTH_VALUES:
        raise ValueError(f"지원하지 않는 emotion_strength 이름입니다: {strength_name}")

    audio = await synthesize_speech(
        script["narration_text"],
        config,
        speaker=speaker,
        emotion=EMOTION_VALUES[emotion_name],
        emotion_strength=(
            EMOTION_STRENGTH_VALUES[strength_name]
            if strength_name is not None
            else None
        ),
    )

    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT_PATH.write_bytes(audio)
    print(
        "CLOVA Voice 연결 성공: "
        f"speaker={speaker}, emotion={emotion_name}, "
        f"output={_OUTPUT_PATH} ({len(audio):,} bytes)"
    )


if __name__ == "__main__":
    asyncio.run(main())
