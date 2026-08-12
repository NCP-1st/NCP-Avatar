"""CLOVA Studio OpenAI-compatible embedding adapter."""

from typing import Protocol

from openai import AsyncOpenAI


EMBEDDING_DIMENSIONS = 1024


class EmbeddingAdapter(Protocol):
    async def embed(self, text: str) -> list[float]: ...


class ClovaEmbeddingAdapter:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str = "bge-m3",
        *,
        timeout_seconds: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._base_url = _openai_base_url(base_url)
        self._timeout_seconds = timeout_seconds
        self._model = model

    async def embed(self, text: str) -> list[float]:
        normalized = text.strip()
        if not normalized:
            raise ValueError("embedding text must not be empty")
        if not self._api_key:
            raise ValueError("CLOVA Studio API key is required")
        client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=self._timeout_seconds,
        )
        response = await client.embeddings.create(
            model=self._model,
            input=normalized,
            encoding_format="float",
        )
        vector = response.data[0].embedding
        if len(vector) != EMBEDDING_DIMENSIONS:
            raise ValueError("unexpected embedding dimensions")
        return vector


def _openai_base_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/v1/openai"):
        return base
    return f"{base}/v1/openai"
