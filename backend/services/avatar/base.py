from abc import ABC, abstractmethod
from pathlib import Path


class AvatarAdapter(ABC):
    @abstractmethod
    async def render(
        self,
        audio: bytes,
        *,
        version_id: str,
        source_image: str | Path | None = None,
    ) -> bytes: ...
