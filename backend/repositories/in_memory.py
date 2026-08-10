from backend.api.schemas import DiarySession, NormalizedInputItem


class InMemoryDiaryRepository:
    """Local development repository; replace with the MySQL implementation."""

    def __init__(self) -> None:
        self.sessions: dict[str, DiarySession] = {}
        self.inputs: dict[str, list[NormalizedInputItem]] = {}

    def clear(self) -> None:
        self.sessions.clear()
        self.inputs.clear()
