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
