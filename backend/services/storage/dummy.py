import hashlib

from backend.services.storage.base import StorageAdapter, StoredObject


class DummyStorageAdapter(StorageAdapter):
    async def upload(self, data: bytes, *, object_name: str, mime_type: str) -> StoredObject:
        digest = hashlib.sha256(data).hexdigest()
        return StoredObject(
            url=f"dummy://object-storage/diary-inputs/{object_name}",
            content_hash=digest,
            size_bytes=len(data),
            mime_type=mime_type,
        )
