"""LangChain ChatClovaX를 이용한 단일 LLM 생성 함수."""

from __future__ import annotations

import json
from typing import Any

from backend.services.llm.base import LLMRequest, LLMResponse, TokenUsage
from backend.services.llm.factory import create_chat_model


async def generate_llm(
    request: LLMRequest,
    config: dict[str, Any],
) -> LLMResponse:
    """호출마다 새 ChatClovaX를 만들고 비동기로 한 번 생성한다."""
    if request.stream:
        raise NotImplementedError("Streaming은 별도 스트림 함수에서 구현해야 합니다")
    if request.tools is not None and request.response_schema is not None:
        raise ValueError("Tools and Structured Outputs cannot be used together")

    purpose = "reasoning" if request.model == "HCX-007" else "vision"
    thinking_effort = (
        "none"
        if purpose == "reasoning"
        and (request.tools is not None or request.response_schema is not None)
        else None
    )
    model = create_chat_model(
        config,
        purpose=purpose,
        model=request.model,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        top_p=request.top_p,
        top_k=request.top_k,
        thinking_effort=thinking_effort,
    )

    if request.tools is not None:
        model = model.bind_tools(request.tools)
    if request.response_schema is not None:
        if purpose != "reasoning":
            raise ValueError("Structured Outputs require the HCX-007 model")
        model = model.with_structured_output(
            request.response_schema,
            method="json_schema",
        )

    messages = [
        {"role": message.role, "content": message.content}
        for message in request.messages
    ]
    result = await model.ainvoke(messages)

    if request.response_schema is not None:
        return LLMResponse(
            model=request.model,
            content=json.dumps(result, ensure_ascii=False),
        )

    usage = getattr(result, "usage_metadata", None) or {}
    metadata = getattr(result, "response_metadata", None) or {}
    content = result.content
    if not isinstance(content, str):
        content = json.dumps(content, ensure_ascii=False)

    return LLMResponse(
        model=request.model,
        content=content,
        finish_reason=metadata.get("finish_reason"),
        tool_calls=getattr(result, "tool_calls", None) or [],
        usage=TokenUsage(
            prompt_tokens=usage.get("input_tokens", 0),
            completion_tokens=usage.get("output_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        ),
    )
