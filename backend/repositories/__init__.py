"""Persistence adapters used by backend orchestration."""

from backend.repositories.base import DiaryRepository
from backend.repositories.in_memory import InMemoryDiaryRepository

__all__ = ["DiaryRepository", "InMemoryDiaryRepository"]
