"""Voice 테스트 결과로 placeholder MP4를 만드는 수동 실행 스크립트."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.services.video import generate_placeholder_video


_VIDEO_DIR = Path(__file__).resolve().parent
_VOICE_DIR = _VIDEO_DIR.parent / "voice"
_AUDIO_PATH = _VOICE_DIR / "output" / "test_diary.mp3"
_TEST_DATA_PATH = _VOICE_DIR / "test.json"
_OUTPUT_PATH = _VIDEO_DIR / "output" / "test_diary.mp4"


async def main() -> None:
    diary = json.loads(_TEST_DATA_PATH.read_text(encoding="utf-8"))
    emotion = diary.get("voice", {}).get("emotion", "중립")
    output_path = await generate_placeholder_video(
        audio_path=_AUDIO_PATH,
        emotion=emotion,
        output_path=_OUTPUT_PATH,
    )
    print(f"placeholder 영상 생성 성공: emotion={emotion}, output={output_path}")


if __name__ == "__main__":
    asyncio.run(main())
