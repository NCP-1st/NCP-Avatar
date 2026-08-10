"""Live2D 연동 전 사용하는 감정 얼굴 placeholder 영상 렌더러."""

from __future__ import annotations

import asyncio
import math
import subprocess
import tempfile
from pathlib import Path

import imageio_ffmpeg
from PIL import Image, ImageDraw


SUPPORTED_EMOTIONS = ("중립", "슬픔", "기쁨", "분노")

_BACKGROUND_COLORS = {
    "중립": "#DDE7F2",
    "슬픔": "#BFD7EA",
    "기쁨": "#FFE4A3",
    "분노": "#F5B7B1",
}


async def generate_placeholder_video(
    *,
    audio_path: Path,
    emotion: str,
    output_path: Path,
) -> Path:
    """MP3와 감정 얼굴 애니메이션을 결합해 MP4를 생성한다."""
    return await asyncio.to_thread(
        _generate_placeholder_video,
        audio_path,
        emotion,
        output_path,
    )


def _generate_placeholder_video(
    audio_path: Path,
    emotion: str,
    output_path: Path,
) -> Path:
    if not audio_path.is_file():
        raise FileNotFoundError(f"오디오 파일을 찾을 수 없습니다: {audio_path}")
    if emotion not in SUPPORTED_EMOTIONS:
        raise ValueError(f"지원하지 않는 감정입니다: {emotion}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mediary-video-") as temp_dir:
        frame_dir = Path(temp_dir)
        _create_animation_frames(frame_dir, emotion)
        _combine_frames_and_audio(frame_dir, audio_path, output_path)

    return output_path


def _create_animation_frames(frame_dir: Path, emotion: str) -> None:
    frame_count = 12
    for index in range(frame_count):
        pulse = 1 + 0.035 * math.sin(2 * math.pi * index / frame_count)
        frame = _draw_face(emotion, pulse)
        frame.save(frame_dir / f"frame_{index:03d}.png")


def _draw_face(emotion: str, pulse: float) -> Image.Image:
    size = 512
    image = Image.new("RGB", (size, size), _BACKGROUND_COLORS[emotion])
    draw = ImageDraw.Draw(image)

    radius = int(155 * pulse)
    center_x, center_y = size // 2, size // 2
    face_box = (
        center_x - radius,
        center_y - radius,
        center_x + radius,
        center_y + radius,
    )
    draw.ellipse(face_box, fill="#FFD65A", outline="#3D3D3D", width=6)

    eye_y = center_y - 45
    if emotion == "분노":
        draw.line((180, eye_y - 10, 225, eye_y + 5), fill="#333333", width=10)
        draw.line((287, eye_y + 5, 332, eye_y - 10), fill="#333333", width=10)
    else:
        draw.ellipse((195, eye_y - 12, 220, eye_y + 18), fill="#333333")
        draw.ellipse((292, eye_y - 12, 317, eye_y + 18), fill="#333333")

    mouth_box = (195, center_y + 15, 317, center_y + 115)
    if emotion == "기쁨":
        draw.arc(mouth_box, start=0, end=180, fill="#A23B3B", width=10)
    elif emotion == "슬픔":
        draw.arc(mouth_box, start=180, end=360, fill="#4A4A4A", width=10)
        draw.ellipse((325, eye_y + 20, 342, eye_y + 48), fill="#5DADE2")
    elif emotion == "분노":
        draw.line((210, center_y + 85, 302, center_y + 70), fill="#7B241C", width=10)
    else:
        draw.line((215, center_y + 75, 297, center_y + 75), fill="#4A4A4A", width=8)

    return image


def _combine_frames_and_audio(
    frame_dir: Path,
    audio_path: Path,
    output_path: Path,
) -> None:
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    command = [
        ffmpeg_path,
        "-y",
        "-stream_loop",
        "-1",
        "-framerate",
        "12",
        "-i",
        str(frame_dir / "frame_%03d.png"),
        "-i",
        str(audio_path),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"placeholder 영상 생성 실패: {result.stderr.strip()}")
