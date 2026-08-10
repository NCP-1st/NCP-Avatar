import base64
import binascii
from datetime import date
from uuid import uuid4

from backend.api.schemas import (
    DiarySession,
    InputItemRequest,
    InputType,
    NormalizedInputItem,
    PreprocessResult,
    ProcessingStatus,
)
from backend.services.speech import SpeechToTextAdapter
from backend.services.storage import StorageAdapter
from backend.repositories import DiaryRepository

MAX_IMAGE_BYTES = 20 * 1024 * 1024
SUPPORTED_IMAGE_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp", "image/bmp"}
SUPPORTED_AUDIO_TYPES = {"audio/wav", "audio/mpeg", "audio/mp4", "audio/x-m4a", "audio/aac"}


class DiaryPipeline:
    def __init__(self, repository: DiaryRepository, storage: StorageAdapter,
                 stt: SpeechToTextAdapter) -> None:
        self.repo, self.storage, self.stt = repository, storage, stt

    def create_session(self, user_id: str, diary_date: date) -> DiarySession:
        session = DiarySession(session_id=str(uuid4()), user_id=user_id, diary_date=diary_date)
        self.repo.sessions[session.session_id] = session
        return session

    async def preprocess(self, session_id: str, requests: list[InputItemRequest]) -> PreprocessResult:
        items = [await self._preprocess_one(request) for request in requests]
        existing = {item.input_id: item for item in self.repo.inputs.get(session_id, [])}
        existing.update({item.input_id: item for item in items})  # D-01: same input_id retries one item.
        self.repo.inputs[session_id] = list(existing.values())
        return PreprocessResult(session_id=session_id, items=items,
                                error_count=sum(item.status is ProcessingStatus.FAILED for item in items))

    async def _preprocess_one(self, request: InputItemRequest) -> NormalizedInputItem:
        stored = None
        try:
            if request.type is InputType.TEXT:
                normalized = " ".join((request.text or "").split())
                return NormalizedInputItem(input_id=request.input_id, type=request.type, transcript=normalized,
                                           captured_at=request.captured_at, status=ProcessingStatus.OK)
            try:
                media = base64.b64decode(request.file_base64 or "", validate=True)
            except (binascii.Error, ValueError) as exc:
                raise ValueError("invalid base64 media payload") from exc
            mime_type = request.mime_type or ("audio/wav" if request.type is InputType.AUDIO else "image/jpeg")
            self._validate_media(request.type, media, mime_type)
            stored = await self.storage.upload(media, object_name=request.input_id, mime_type=mime_type)
            transcript, meta = (await self.stt.transcribe(media, mime_type=mime_type)
                                if request.type is InputType.AUDIO else (None, {}))
            return NormalizedInputItem(input_id=request.input_id, type=request.type, storage_url=stored.url,
                                       content_hash=stored.content_hash, size_bytes=stored.size_bytes,
                                       mime_type=stored.mime_type, transcript=transcript,
                                       captured_at=request.captured_at, status=ProcessingStatus.OK,
                                       transcript_confirmed=False, provider_meta=meta)
        except Exception as exc:
            return NormalizedInputItem(input_id=request.input_id, type=request.type,
                                       storage_url=stored.url if stored else None,
                                       content_hash=stored.content_hash if stored else None,
                                       size_bytes=stored.size_bytes if stored else None,
                                       mime_type=stored.mime_type if stored else request.mime_type,
                                       captured_at=request.captured_at, status=ProcessingStatus.FAILED,
                                       error_code=type(exc).__name__, error_reason=str(exc))

    @staticmethod
    def _validate_media(input_type: InputType, media: bytes, mime_type: str) -> None:
        if input_type is InputType.AUDIO:
            if mime_type not in SUPPORTED_AUDIO_TYPES:
                raise ValueError(f"unsupported audio MIME type: {mime_type}")
            return
        if mime_type not in SUPPORTED_IMAGE_TYPES:
            raise ValueError(f"unsupported image MIME type: {mime_type}")
        if not media or len(media) > MAX_IMAGE_BYTES:
            raise ValueError("image size must be between 1 byte and 20 MB")
        signatures = {
            "image/jpeg": (b"\xff\xd8\xff",),
            "image/jpg": (b"\xff\xd8\xff",),
            "image/png": (b"\x89PNG\r\n\x1a\n",),
            "image/webp": (b"RIFF",),
            "image/bmp": (b"BM",),
        }
        if not any(media.startswith(signature) for signature in signatures[mime_type]):
            raise ValueError("image bytes do not match the declared MIME type")
