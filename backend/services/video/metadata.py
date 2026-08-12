"""Video metadata extraction helpers."""

from __future__ import annotations

import asyncio
import math
import tempfile
from pathlib import Path

import imageio_ffmpeg


async def probe_video_duration_seconds(video: bytes) -> int:
    """Return the rounded-up MP4 duration, with a minimum of one second."""
    if not video:
        raise ValueError("video is empty")

    def probe() -> int:
        with tempfile.TemporaryDirectory(prefix="mediary-video-probe-") as temp_dir:
            video_path = Path(temp_dir) / "video.mp4"
            video_path.write_bytes(video)
            _, seconds = imageio_ffmpeg.count_frames_and_secs(str(video_path))
            if not math.isfinite(seconds) or seconds <= 0:
                raise ValueError(f"invalid video duration: {seconds}")
            return max(1, math.ceil(seconds))

    return await asyncio.to_thread(probe)
