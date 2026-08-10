from backend.services.llm import LLMResponse


class SequencedGenerate:
    """Returns scripted LLM contents in order and fails on unexpected extra calls."""

    def __init__(self, responses: list[str], *, model: str = "HCX-005") -> None:
        self._responses = list(responses)
        self._model = model
        self.call_count = 0

    async def __call__(self, request, config) -> LLMResponse:
        self.call_count += 1
        if not self._responses:
            raise AssertionError("scripted responses exhausted: unexpected LLM call")
        return LLMResponse(model=self._model, content=self._responses.pop(0))

    @property
    def remaining(self) -> int:
        return len(self._responses)
