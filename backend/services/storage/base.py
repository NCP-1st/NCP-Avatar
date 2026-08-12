from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class StoredObject:
    url: str
    content_hash: str
    size_bytes: int
    mime_type: str
    object_key: str | None = None


class StorageAdapter(ABC):
    @abstractmethod
    async def upload(self, data: bytes, *, object_name: str, mime_type: str) -> StoredObject: ...

    async def download(self, *, object_name: str) -> bytes:
        """Read an object back for a downstream media-processing step."""
        raise NotImplementedError("storage download is not configured")

    async def delete(self, *, object_name: str) -> None:
        """Delete an object; implementations must treat an absent key as success."""
        raise NotImplementedError("storage delete is not configured")
