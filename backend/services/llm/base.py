"""LangChain LLM 서비스의 요청/응답 스키마."""

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str | list[dict[str, Any]]


class LLMRequest(BaseModel):
    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    tools: list[dict[str, Any]] | None = None
    stream: bool = False
    response_schema: dict[str, Any] | None = None
    top_p: float = Field(default=0.8, gt=0, le=1)
    top_k: int = Field(default=0, ge=0, le=128)
    temperature: float = Field(default=0.5, ge=0, le=1)
    max_tokens: int | None = Field(default=None, gt=0)


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMResponse(BaseModel):
    model: str
    content: str
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
