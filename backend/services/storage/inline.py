import base64
import hashlib

from backend.services.storage.base import StorageAdapter, StoredObject


class InlineDataUrlStorageAdapter(StorageAdapter):
    """Local development storage that keeps media in an inline data URL."""

    async def upload(self, data: bytes, *, object_name: str, mime_type: str) -> StoredObject:
        digest = hashlib.sha256(data).hexdigest()
        encoded = base64.b64encode(data).decode("ascii")
        return StoredObject(
            url=f"data:{mime_type};base64,{encoded}",
            content_hash=digest,
            size_bytes=len(data),
            mime_type=mime_type,
        )
