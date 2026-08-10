"""LangChain 기반 채팅 모델 팩토리.

전역 모델을 보관하지 않는다. 그래프 실행이나 작업 단위에서 호출해 새
ChatClovaX 인스턴스를 만든 뒤 에이전트/노드에 주입한다.
"""

from __future__ import annotations

from typing import Any, Literal


ModelPurpose = Literal["vision", "reasoning"]


def create_chat_model(
    config: dict[str, Any],
    *,
    purpose: ModelPurpose = "vision",
    model: str | None = None,
    temperature: float = 0.3,
    max_tokens: int | None = None,
    top_p: float | None = None,
    top_k: int | None = None,
    thinking_effort: Literal["none", "low", "medium", "high"] | None = None,
) -> Any:
    """설정에 맞는 새 ChatClovaX 인스턴스를 반환한다.

    ``langchain_naver``는 실제 모델을 만들 때만 import한다. 따라서 네이티브
    fallback만 사용하는 환경에서는 LangChain 의존성이 강제되지 않는다.
    """
    try:
        from langchain_naver import ChatClovaX
    except ImportError as exc:
        raise RuntimeError(
            "ChatClovaX 사용을 위해 langchain-naver를 설치해야 합니다"
        ) from exc

    llm_config = config["llm"]
    selected_model = model or (
        llm_config["model_reasoning"]
        if purpose == "reasoning"
        else llm_config["model_vision"]
    )

    options: dict[str, Any] = {
        "model": selected_model,
        "api_key": llm_config["api_key"],
        "temperature": temperature,
        "max_tokens": max_tokens or llm_config["max_tokens"],
        "timeout": llm_config["timeout_s"],
    }
    if top_p is not None:
        options["top_p"] = top_p
    if top_k is not None:
        options["top_k"] = top_k
    if thinking_effort is not None:
        options["thinking"] = {"effort": thinking_effort}

    return ChatClovaX(**options)
