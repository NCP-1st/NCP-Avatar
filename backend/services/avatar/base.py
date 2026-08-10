from abc import ABC, abstractmethod


class AvatarAdapter(ABC):
    @abstractmethod
    async def render(self, audio: bytes, *, version_id: str) -> bytes: ...
