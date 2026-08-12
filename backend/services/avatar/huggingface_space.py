"""Experimental talking-avatar adapter backed by a public Gradio Space."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol

from backend.services.avatar.base import AvatarAdapter


class HuggingFaceSpaceError(RuntimeError):
    """Raised when the remote Space cannot produce a usable video."""


class _GradioClient(Protocol):
    def predict(self, *args: Any, api_name: str) -> Any: ...


ClientFactory = Callable[[str, str | None], tuple[_GradioClient, Callable[[str], Any]]]


def _default_client_factory(
    space_id: str, token: str | None
) -> tuple[_GradioClient, Callable[[str], Any]]:
    try:
        from gradio_client import Client, handle_file
    except ImportError as exc:  # pragma: no cover - depends on optional runtime install
        raise HuggingFaceSpaceError(
            "gradio_client is required; install backend/requirements.txt"
        ) from exc

    return Client(space_id, token=token), handle_file


def _video_path(result: Any) -> Path:
    """Extract the downloaded video path returned by different Gradio versions."""
    if isinstance(result, (str, Path)):
        return Path(result)
    if isinstance(result, dict):
        if "video" in result:
            return _video_path(result["video"])
        if "path" in result:
            return Path(result["path"])
    if isinstance(result, (tuple, list)) and result:
        return _video_path(result[0])
    raise HuggingFaceSpaceError(f"Unsupported Gradio response shape: {type(result).__name__}")


class HuggingFaceSpaceAvatarAdapter(AvatarAdapter):

    def __init__(
        self,
        *,
        source_image: str | Path,
        space_id: str = "pragnakalp/Wav2lip-ZeroGPU",
        api_name: str = "/run_infrence",
        token: str | None = None,
        timeout_s: float = 180,
        audio_suffix: str = ".wav",
        extra_inputs: tuple[Any, ...] = (),
        client_factory: ClientFactory = _default_client_factory,
    ) -> None:
        self._source_image = Path(source_image)
        self._space_id = space_id
        self._api_name = api_name
        self._token = token or None
        self._timeout_s = timeout_s
        self._audio_suffix = audio_suffix if audio_suffix.startswith(".") else f".{audio_suffix}"
        self._extra_inputs = extra_inputs
        self._client_factory = client_factory

    async def render(
        self,
        audio: bytes,
        *,
        version_id: str,
        source_image: str | Path | None = None,
    ) -> bytes:
        selected_image = Path(source_image) if source_image else self._source_image
        if not selected_image.is_file():
            raise HuggingFaceSpaceError(f"Source image not found: {selected_image}")
        if not audio:
            raise HuggingFaceSpaceError("Audio is empty")

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._render_sync, audio, version_id, selected_image),
                timeout=self._timeout_s,
            )
        except TimeoutError as exc:
            raise HuggingFaceSpaceError(
                f"Space request exceeded {self._timeout_s:g} seconds"
            ) from exc
        except HuggingFaceSpaceError:
            raise
        except Exception as exc:
            raise HuggingFaceSpaceError(f"Space request failed: {exc}") from exc

    def _render_sync(self, audio: bytes, version_id: str, source_image: Path) -> bytes:
        client, handle_file = self._client_factory(self._space_id, self._token)
        safe_version_id = "".join(
            character for character in version_id if character.isalnum() or character in "-_"
        ) or "render"

        with tempfile.TemporaryDirectory(prefix="mediary-hf-avatar-") as temp_dir:
            audio_path = Path(temp_dir) / f"{safe_version_id}{self._audio_suffix}"
            audio_path.write_bytes(audio)
            result = client.predict(
                handle_file(str(source_image)),
                handle_file(str(audio_path)),
                *self._extra_inputs,
                api_name=self._api_name,
            )
            output_path = _video_path(result)
            if not output_path.is_file():
                raise HuggingFaceSpaceError(f"Downloaded video not found: {output_path}")
            video = output_path.read_bytes()
            if not video:
                raise HuggingFaceSpaceError("Space returned an empty video")
            return video
