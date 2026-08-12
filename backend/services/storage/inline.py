import base64
import hashlib

from backend.services.storage.base import StorageAdapter, StoredObject


class InlineDataUrlStorageAdapter(StorageAdapter):
    """Local development storage that keeps media in an inline data URL."""

    def __init__(self) -> None:
        self._objects: dict[str, bytes] = {}

    async def upload(self, data: bytes, *, object_name: str, mime_type: str) -> StoredObject:
        self._objects[object_name] = data
        digest = hashlib.sha256(data).hexdigest()
        encoded = base64.b64encode(data).decode("ascii")
        return StoredObject(
            url=f"data:{mime_type};base64,{encoded}",
            content_hash=digest,
            size_bytes=len(data),
            mime_type=mime_type,
            object_key=object_name,
        )

    async def download(self, *, object_name: str) -> bytes:
        try:
            return self._objects[object_name]
        except KeyError as exc:
            raise FileNotFoundError(f"inline object not found: {object_name}") from exc

    async def delete(self, *, object_name: str) -> None:
        self._objects.pop(object_name, None)
