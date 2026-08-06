from backend.api.schemas import DiarySession, NormalizedInputItem


class InMemoryRepository:
    """Development-only persistence boundary; replace with a MySQL implementation."""

    def __init__(self) -> None:
        self.sessions: dict[str, DiarySession] = {}
        self.inputs: dict[str, list[NormalizedInputItem]] = {}

    def clear(self) -> None:
        self.__init__()
