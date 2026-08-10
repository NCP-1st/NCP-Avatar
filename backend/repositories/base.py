from typing import Protocol

from backend.api.schemas import DiarySession, NormalizedInputItem


class DiaryRepository(Protocol):
    """Minimal persistence contract required by the diary pipeline."""

    sessions: dict[str, DiarySession]
    inputs: dict[str, list[NormalizedInputItem]]

    def clear(self) -> None: ...
