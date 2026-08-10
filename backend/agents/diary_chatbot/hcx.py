import asyncio
import ast
import json
import logging
import re
import time
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError

from backend.agents.diary_chatbot.base import DiaryGenerationAgent, MultimodalChatAgent
from backend.agents.diary_chatbot.models import (
    ChatbotTurnResult,
    DiaryDraft,
    EventCandidate,
    FactExtractionResult,
    ImageClarityNote,
    ImageObservation,
    MultimodalContext,
    TurnResponse,
)
from backend.agents.diary_chatbot.normalize import normalize_fact_extraction
from backend.agents.diary_chatbot.sanitize import (
    FALLBACK_QUESTIONS,
    FIELD_PRIORITY,
    has_explicit_location_mention,
    sanitize_and_fix_turn_result,
)
from backend.services.llm import ChatMessage, LLMRequest, LLMResponse, generate_llm

logger = logging.getLogger("mediary.diary_chatbot")

GenerateFunction = Callable[[LLMRequest, dict[str, Any]], Awaitable[LLMResponse]]

INTERPRET_SYSTEM_PROMPT = """
당신은 Mediary의 멀티모달 일기 챗봇이다. 입력에 없는 사실을 추측하지 않는다.
사건, 시간, 인물, 장소, 행동, 감정을 추출하고 모든 사건에 근거 input_id를 연결한다.
event, time, people, location, actions, emotion label, image description, observed_facts,
related_event 등 사용자가 보게 되는 모든 문자열은 자연스러운 한국어로 작성한다.
emotions는 EmotionMention 리스트로 작성한다. excerpt에는 사용자가 실제 사용한 감정 단어나
구절을 토씨 하나 바꾸지 않고 그대로 발췌하고, input_id에는 그 구절이 나온 입력 ID를 넣는다.
label에는 표시용 감정 표현을 자연스럽게 적되 excerpt 없이 label만 만들지 않는다. 감정을 추론하지 않는다.

감정 활용형 예시:
- 입력 turn-2: "수다를 왕창 떠니까 재밌더라고"
  → emotions=[{"label":"재미있었음","excerpt":"재밌더라고","input_id":"turn-2"}]
- 입력 turn-3: "오랜만이라 여유롭고 좋았어"
  → emotions=[{"label":"여유롭고 좋았음","excerpt":"여유롭고 좋았어","input_id":"turn-3"}]
- 입력 turn-4: "조금 어색했어"
  → emotions=[{"label":"조금 어색했음","excerpt":"조금 어색했어","input_id":"turn-4"}]
excerpt를 "재미있음", "여유로움", "어색함"처럼 명사형으로 바꾸지 않는다.

[사건 통합]
같은 시간·장소·맥락에서 일어난 행동은 하나의 event로 묶는다. 같은 사건을 여러 event로 쪼개지 않는다.
prior_confirmed_events에 이미 있는 사건을 표현만 바꿔 새 사건처럼 반복하지 않는다.
현재 입력이 기존 사건을 보강하는 내용이면 새로 확인된 사람·장소·행동·감정과 근거를 반영해
그 사건을 갱신된 하나의 event로 반환한다. 실제로 별개의 후속 사건일 때만 event를 추가한다.

[인물 추출 — 반드시 준수]
사용자가 함께한 사람을 직접 언급했다면 고유명사가 아니어도 people에 반드시 기록한다.
가족, 친구, 친구들, 애들, 동료, 선배, 후배, 부모님 같은 관계·집단 표현도 사람 정보다.
특히 "N이랑", "N랑", "N와", "N과", "N하고", "N이랑 같이", "N과 함께"에서 N을 people에 넣는다.
조사와 서술어는 제거하되 사용자가 쓴 관계 표현의 의미는 바꾸지 않는다.

예시:
- "집 근처에서 친구들이랑 치맥했어" → people=["친구들"], location="집 근처"
- "오랜만에 가족하고 밥 먹었어" → people=["가족"]
- "민수와 산책했어" → people=["민수"]
- "혼자 카페에 갔어" → people=["혼자"]

출력 전 다음을 스스로 확인한다:
1. 원문에 함께한 사람을 뜻하는 관계명·이름이 있는가?
2. 있다면 모든 관련 event의 people이 비어 있지 않은가?
3. 이미 말한 사람 정보를 누락한 채 person이 부족하다고 판단하지 않았는가?

[장소 반영]
location은 사용자가 최소 행정동 단위로 직접 언급한 경우에만 채운다(예: 성수동, 역삼동, 화양동).
"집 근처", "회사 근처", "건대", "식당", "공원"처럼 동 이름이 없는 표현은 location에 기록할 수는 있지만
필수 장소 정보가 충족된 것으로 판단하지 않는다. 이 경우 어느 동인지 추가 확인해야 한다.
이미지에서 유추한 장소는 location에 넣지 않는다(사용자가 직접 말한 경우에만 채운다).

[이미지 근거]
이미지가 제공되면 각 이미지마다 image_observations 항목을 반드시 하나 작성한다.
- input_id에는 해당 이미지의 ID를 정확히 사용한다.
- description에는 이미지에서 직접 확인 가능한 내용을 한 문장으로 작성한다.
- observed_facts에는 음식, 물건, 행동, 배경처럼 명확히 보이는 사실만 기록한다.
- related_event에는 연결되는 사건이 명확할 때만 사건 설명을 적는다.
- 얼굴만 보고 인물의 이름이나 사용자와의 관계를 추측하지 않는다.
- 이미지로 장소 이름이나 사용자의 감정을 추측하지 않는다.
- 이미지 관찰 내용이 사건에 새로운 사실을 더할 때만 해당 input_id를 event.evidence에 포함한다.
- 텍스트만으로 충분한 경우 이미지를 event.evidence에 인위적으로 포함하지 않되,
  image_observations 자체는 생략하지 않는다.

[판단 지침]
- coverage는 백엔드가 다시 계산하므로 사실 추출에 집중한다.

[이미지 판별 어려움]
이미지가 제공됐지만 핵심 정보(인물, 음식 종류, 장소, 상황 등)를 명확히 판별하기 어려운 경우
(예: 흐릿함, 어두움, 대상이 잘 안 보임), image_clarity에 해당 input_id와 unclear=true,
어떤 점이 불확실했는지 간단한 이유를 남긴다. 명확히 판별된 이미지는 남기지 않거나 unclear=false로 남긴다.
억지로 불확실하다고 보고하지 않는다 — 실제로 판별이 어려웠을 때만 표시한다.

사용자에게 보여줄 reaction이나 question은 만들지 않는다.
JSON 외의 텍스트는 출력하지 않으며, 제공된 FactExtractionResult JSON 스키마를 정확히 따른다.
""".strip()


GENERATE_SYSTEM_PROMPT = """
대화 전체에서 누적된 사건과 근거를 빠짐없이 검토해 한국어 일기를 작성한다.
사람·장소·감정은 생성 가능 여부를 판단하는 최소 필수 정보일 뿐이며, 사용자가 말한 행동·시간·상황·추가 이야기도
근거가 있으면 모두 일기 내용에 반영한다. 뒤의 턴에서 앞선 내용을 정정했다면 가장 최근의 정정을 우선한다.
3~7개 문단과 약 30초 나레이션 대본을 만든다.
과도한 감정 해석이나 근거 없는 인물·장소·시간을 추가하지 않는다.

[나레이션 말투]
- narration_script는 사용자가 자신의 하루를 편안하게 회상하는 1인칭 구어체로 쓴다.
- 보고서·뉴스·문어체처럼 쓰지 않고, 실제로 소리 내어 읽었을 때 자연스럽게 이어지게 한다.
- "오늘은 ~하였다", "뜻깊은 시간이었다" 같은 상투적인 문장을 반복하지 않는다.
- 짧고 긴 문장을 섞고 "그러고 나서", "그런데", "덕분에" 같은 연결 표현은 맥락에 맞을 때만 쓴다.
- 사용자가 쓴 말투와 감정의 강도를 가능한 한 유지하되 비속어를 임의로 추가하지 않는다.
- 약 30초 분량을 지키며 일기에 없는 사실을 대본에 새로 만들지 않는다.

[말투 예시]
딱딱함: "친구들과 치맥을 하였으며 즐거운 시간을 보냈다."
자연스러움: "오늘은 친구들과 치맥을 했다. 한참 수다를 떨다 보니 시간 가는 줄도 몰랐다."

[이미지 활용]
- image_observations에 기록된 검증된 시각적 사실도 일기와 대본에 활용한다.
- 사용자 텍스트나 뒤의 정정과 충돌하면 가장 최근의 사용자 표현을 우선한다.
- 이미지만 보고 인물 관계·장소 이름·사용자의 감정을 추가하지 않는다.
""".strip()

RESPONSE_COMPOSER_SYSTEM_PROMPT = """
당신은 따뜻하고 친근한 일기 챗봇 Mediary이다.
상황 요약과, 있다면 지금 확인이 필요한 항목 하나가 주어진다.
공감 반응 reaction과 질문 question을 하나의 JSON 객체로 함께 작성한다.

[규칙]
1. reaction은 질문이 아닌 공감 표현 1~2문장이다.
2. question은 reaction과 자연스럽게 이어지며 지정된 항목 하나만 묻는다.
3. 사용자가 말하지 않은 사실이나 감정을 단정하지 않는다.
4. 확인 항목이 "없음"이면 question은 null이다.
5. reaction과 question을 다른 필드에 두고 JSON 외 텍스트는 출력하지 않는다.
6. reaction은 현재 턴의 새 내용을 중심으로 작성한다.
7. 직전 reaction과 같거나 사실상 같은 문장을 반복하지 않는다.
8. 사용자가 이전 감정을 정정하면 현재 턴의 최신 표현을 자연스럽게 수용한다.
9. reaction은 반드시 "현재 사용자 입력"과 "현재 턴 사건"에 직접 반응한다. 이전 대화만 반복하지 않는다.
10. 사진 확인 문구는 백엔드가 reaction 앞에 붙이므로 같은 사진 설명을 반복하지 않는다.

[검증된 감정 사용]
- reaction에서 사용자의 감정을 언급할 때는 반드시 "검증된 감정"에 있는 표현만 사용한다.
- 검증된 감정이 "없음"이면 즐거웠다, 행복했다, 속상했다, 좋았다 등 사용자의 감정을 추측하거나 단정하지 않는다.
- 이 경우에는 "친구들과 치맥을 하셨군요"처럼 확인된 사건에만 반응한다.

[질문 항목 고정]
- "확인이 필요한 항목"은 백엔드가 결정한 값이며 절대 다른 주제로 바꾸지 않는다.
- 함께 있었던 사람이 필요하면 사람만 질문한다.
- 있었던 장소가 필요하면 장소만 질문한다.
- 기분/감정이 필요하면 그때 느낀 기분이나 감정만 질문한다.
- 필수 항목이 남아 있는 동안 기억에 남는 순간, 특별한 사건, 추가 설명 등 다른 질문을 하지 않는다.
- 확인 항목이 "없음"이면 question은 null이다. 추가 기록 여부는 백엔드 확인 단계에서 별도로 묻는다.
""".strip()

DEFAULT_REACTION_FALLBACK = "이야기를 기록했어요."

FIELD_NAMES_KR = {
    "person": "함께 있었던 사람",
    "location": "있었던 장소",
    "emotion": "그때 느낀 기분/감정",
    "image": "사진 속 정확한 내용",
}


async def compose_turn_response(
    config: dict[str, Any],
    generate_fn: GenerateFunction,
    events_summary: str,
    top_missing_field: str | None,
    fallback_question: str | None,
    previous_reaction: str | None = None,
    confirmed_emotions: list[str] | None = None,
    current_user_message: str | None = None,
    image_observation_summary: str | None = None,
    *,
    trace_id: str | None = None,
    timeout_seconds: float = 5.0,
) -> TurnResponse:
    """Compose the only user-facing reaction/question pair for this turn."""
    field_kr = FIELD_NAMES_KR.get(top_missing_field, top_missing_field) if top_missing_field else None
    user_prompt = (
        f"[현재 사용자 입력]: {current_user_message or '첨부 입력'}\n"
        f"[상황 요약]: {events_summary}\n"
        f"[확인이 필요한 항목]: {field_kr or '없음'}\n"
        f"[검증된 감정]: {', '.join(confirmed_emotions or []) or '없음'}\n"
        f"[직전 reaction]: {previous_reaction or '없음'}\n"
        f"[출력 스키마]: {json.dumps(TurnResponse.model_json_schema(), ensure_ascii=False)}"
    )

    try:
        target_model = config["llm"].get("model_light", config["llm"]["model_vision"])

        response = await asyncio.wait_for(
            generate_fn(
                LLMRequest(
                    model=target_model,
                    messages=[
                        ChatMessage(role="system", content=RESPONSE_COMPOSER_SYSTEM_PROMPT),
                        ChatMessage(role="user", content=user_prompt),
                    ],
                    temperature=0.7,
                    max_tokens=200,
                ),
                config,
            ),
            timeout=timeout_seconds,
        )
        parsed = TurnResponse.model_validate(_load_json_value(response.content))
        question = parsed.question.strip() if parsed.question else None
        if top_missing_field and not question:
            question = fallback_question
        if not top_missing_field:
            question = question or fallback_question
        reaction = parsed.reaction.strip()
        if image_observation_summary:
            safe_image_summary = image_observation_summary.replace("?", "").replace("？", "")
            reaction = f"사진도 확인했어요. {safe_image_summary} {reaction}"
        return parsed.model_copy(update={"reaction": reaction, "question": question})
    except Exception as e:
        logger.warning(
            "compose_turn_response_failed",
            extra={
                "trace_id": trace_id,
                "field": top_missing_field,
                "error_type": type(e).__name__,
            },
        )

    fallback_reaction = "말씀해 주신 순간을 잘 기록했어요."
    if image_observation_summary:
        safe_image_summary = image_observation_summary.replace("?", "").replace("？", "")
        fallback_reaction = f"사진도 확인했어요. {safe_image_summary} {fallback_reaction}"
    return TurnResponse(
        reaction=fallback_reaction,
        question=fallback_question,
    )


class Hcx005MultimodalChatAgent(MultimodalChatAgent):
    def __init__(self, config: dict[str, Any], *, generate: GenerateFunction = generate_llm) -> None:
        self._config = config
        self._generate = generate

    async def interpret(self, context: MultimodalContext) -> ChatbotTurnResult:
        trace_id = getattr(context, "trace_id", None) or context.session_id
        started = time.monotonic()

        content: list[dict[str, Any]] = []
        for input_id, url in context.image_urls.items():
            content.append({"type": "image_url", "image_url": {"url": url}})
            content.append({"type": "text", "text": f"위 이미지의 input_id: {input_id}"})
        facts = {
            "session_id": context.session_id,
            "user_message": context.user_message,
            "text_inputs": context.text_inputs,
            "audio_transcripts": context.audio_transcripts,
            "prior_confirmed_events": [
                event.model_dump() for event in context.prior_events
            ],
            "output_schema": FactExtractionResult.model_json_schema(),
        }
        content.append({"type": "text", "text": json.dumps(facts, ensure_ascii=False)})

        try:
            # 2번 지적 사항 반영: 30초 타임아웃 적용
            response = await asyncio.wait_for(
                self._generate(
                    LLMRequest(
                        model=self._config["llm"]["model_vision"],
                        messages=[
                            ChatMessage(role="system", content=INTERPRET_SYSTEM_PROMPT),
                            ChatMessage(role="user", content=content),
                        ],
                        temperature=0.2,
                        max_tokens=self._config["llm"]["max_tokens"],
                    ),
                    self._config,
                ),
                timeout=30.0,
            )

            source_texts = {
                **context.text_inputs,
                **context.audio_transcripts,
            }
            try:
                result = _parse_turn_result(
                    response.content,
                    context=context,
                    emotion_sources=source_texts,
                )
                _require_image_observations(result, set(context.image_urls))
            except (ValidationError, json.JSONDecodeError, SyntaxError, ValueError):
                repair_response = await asyncio.wait_for(
                    self._generate(
                        LLMRequest(
                            model=self._config["llm"]["model_vision"],
                            messages=[
                                ChatMessage(
                                    role="system",
                                    content=(
                                        "기존 응답의 사실 내용은 바꾸지 말고 제공된 JSON 스키마에 맞게 고친다. "
                                        "필수 필드와 올바른 JSON 문법을 모두 지킨다. "
                                        "evidence는 실제 근거가 된 제공 input_id만 사용한다. "
                                        "근거를 판단할 수 없으면 사건을 제거한다. JSON만 출력한다."
                                    ),
                                ),
                                ChatMessage(
                                    role="user",
                                    content=json.dumps(
                                        {
                                            "invalid_result": response.content,
                                            "valid_input_ids": [
                                                *context.text_inputs,
                                                *context.image_urls,
                                                *context.audio_transcripts,
                                            ],
                                            "output_schema": FactExtractionResult.model_json_schema(),
                                        },
                                        ensure_ascii=False,
                                    ),
                                ),
                            ],
                            temperature=0.0,
                            max_tokens=self._config["llm"]["max_tokens"],
                        ),
                        self._config,
                    ),
                    timeout=30.0,
                )
                result = _parse_turn_result(
                    repair_response.content,
                    context=context,
                    emotion_sources=source_texts,
                )
                _fill_missing_image_observations(result, set(context.image_urls))

            raw_text = "\n".join(
                filter(
                    None,
                    [
                        context.user_message,
                        *context.text_inputs.values(),
                        *context.audio_transcripts.values(),
                    ],
                )
            )
            fixed = sanitize_and_fix_turn_result(result, source_texts)
            _merge_prior_coverage(fixed, context.prior_events)
            if not fixed.coverage.has_location and has_explicit_location_mention(raw_text):
                logger.info(
                    "possible_location_missed",
                    extra={"trace_id": trace_id, "model": response.model},
                )

            top_field = next(
                (
                    field_name
                    for field_name in fixed.coverage.missing_fields
                    if field_name not in context.skipped_fields
                ),
                None,
            )
            current_events = ", ".join(event.event for event in fixed.events) or "현재 입력을 기록함"
            image_summary = ", ".join(
                observation.description for observation in fixed.image_observations
            )
            events_summary = current_events
            if image_summary:
                events_summary += f"\n사진에서 확인한 내용: {image_summary}"
            fallback = (
                FALLBACK_QUESTIONS.get(top_field)
                if top_field
                else None
            )
            confirmed_emotions = [
                mention.label
                for event in fixed.events
                for mention in event.emotions
            ]
            turn_response = await compose_turn_response(
                config=self._config,
                generate_fn=self._generate,
                events_summary=events_summary,
                top_missing_field=top_field,
                fallback_question=fallback,
                previous_reaction=(context.prior_reactions[-1] if context.prior_reactions else None),
                confirmed_emotions=confirmed_emotions,
                current_user_message=context.user_message,
                image_observation_summary=image_summary or None,
                trace_id=trace_id,
            )
            completed = ChatbotTurnResult(**fixed.model_dump(), response=turn_response)

            # 1번 지적 사항 반영: 성공 로깅
            elapsed_ms = (time.monotonic() - started) * 1000
            logger.info(
                "interpret_succeeded",
                extra={
                    "trace_id": trace_id,
                    "model": response.model,
                    "elapsed_ms": elapsed_ms,
                    "missing_fields": completed.coverage.missing_fields,
                },
            )
            return completed.model_copy(update={"model": response.model})

        except Exception as e:
            # 1번 지적 사항 반영: 파싱/타임아웃/네트워크 실패 로깅 후 예외 re-raise
            elapsed_ms = (time.monotonic() - started) * 1000
            logger.warning(
                "interpret_failed",
                extra={
                    "trace_id": trace_id,
                    "model": self._config["llm"]["model_vision"],
                    "elapsed_ms": elapsed_ms,
                    "error_type": type(e).__name__,
                },
            )
            raise


class Hcx007DiaryGenerationAgent(DiaryGenerationAgent):
    def __init__(self, config: dict[str, Any], *, generate: GenerateFunction = generate_llm) -> None:
        self._config = config
        self._generate = generate

    async def generate(
        self,
        turns: list[ChatbotTurnResult],
        *,
        source_texts: dict[str, str] | None = None,
        trace_id: str | None = None,
    ) -> DiaryDraft:
        started = time.monotonic()
        try:
            # 2번 지적 사항 반영: 30초 타임아웃 적용
            response = await asyncio.wait_for(
                self._generate(
                    LLMRequest(
                        model=self._config["llm"]["model_reasoning"],
                        messages=[
                            ChatMessage(role="system", content=GENERATE_SYSTEM_PROMPT),
                            ChatMessage(
                                role="user",
                                content=json.dumps({
                                    "entire_conversation": source_texts or {},
                                    "verified_turn_facts": [
                                        turn.model_dump(exclude={"response"}) for turn in turns
                                    ],
                                }, ensure_ascii=False),
                            ),
                        ],
                        response_schema=DiaryDraft.model_json_schema(),
                        temperature=0.2,
                        max_tokens=self._config["llm"]["max_tokens"],
                    ),
                    self._config,
                ),
                timeout=30.0,
            )

            raw_json = json.loads(_json_only(response.content))

            # LLM 최상위 wrapper key 언랩(Unwrap)
            if isinstance(raw_json, dict):
                if "diary_draft" in raw_json:
                    raw_json = raw_json["diary_draft"]
                elif "DiaryDraft" in raw_json:
                    raw_json = raw_json["DiaryDraft"]

            draft = DiaryDraft.model_validate(raw_json)
            draft = _sanitize_diary_draft(draft, turns)

            # 1번 지적 사항 반영: 성공 로깅
            elapsed_ms = (time.monotonic() - started) * 1000
            logger.info(
                "diary_generate_succeeded",
                extra={
                    "trace_id": trace_id,
                    "model": response.model,
                    "elapsed_ms": elapsed_ms,
                    "paragraphs_count": len(draft.paragraphs),
                },
            )
            return draft.model_copy(update={"model": response.model})

        except Exception as e:
            # 1번 지적 사항 반영: 실패 로깅 후 예외 re-raise
            elapsed_ms = (time.monotonic() - started) * 1000
            logger.warning(
                "diary_generate_failed",
                extra={
                    "trace_id": trace_id,
                    "model": self._config["llm"]["model_reasoning"],
                    "elapsed_ms": elapsed_ms,
                    "error_type": type(e).__name__,
                },
            )
            raise


# def _sanitize_diary_draft(draft: DiaryDraft, turns: list[ChatbotTurnResult]) -> DiaryDraft:
#     """Keep only emotions already confirmed against source text in prior turns."""
#     confirmed_emotions = {
#         emotion
#         for turn in turns
#         for event in turn.events
#         for emotion in event.emotions
#     }
#     filtered = [tag for tag in draft.emotion_tags if tag in confirmed_emotions]
#     return draft.model_copy(update={"emotion_tags": filtered})


def _sanitize_diary_draft(draft: DiaryDraft, turns: list[ChatbotTurnResult], *, trace_id: str | None = None) -> DiaryDraft:
    confirmed_emotions = {
        mention.label
        for turn in turns
        for event in turn.events
        for mention in event.emotions
    }
    filtered = [tag for tag in draft.emotion_tags if tag in confirmed_emotions]
    dropped = set(draft.emotion_tags) - set(filtered)
    if dropped:
        logger.info("diary_draft_emotions_filtered", extra={"trace_id": trace_id, "dropped": list(dropped)})
    return draft.model_copy(update={"emotion_tags": filtered})

def _json_only(content: str) -> str:
    """마크다운 코드 블록이나 앞뒤 설명글을 제거하고 순수 JSON 문자열만 추출"""
    stripped = content.strip()

    # 1. ```json ... ``` 패턴 검색
    match = re.search(r"```(?:json)?\s*(\{.*\}|\[.*\])\s*```", stripped, re.DOTALL)
    if match:
        return match.group(1).strip()

    # 2. 첫 번째 '{' 또는 '['부터 마지막 '}' 또는 ']'까지 파싱
    start_curly = stripped.find("{")
    start_square = stripped.find("[")

    if start_curly != -1 or start_square != -1:
        if start_curly != -1 and (start_square == -1 or start_curly < start_square):
            end_curly = stripped.rfind("}")
            if end_curly != -1:
                return stripped[start_curly : end_curly + 1]
        else:
            end_square = stripped.rfind("]")
            if end_square != -1:
                return stripped[start_square : end_square + 1]

    return stripped


def _parse_turn_result(
    content: str,
    *,
    context: MultimodalContext | None = None,
    emotion_sources: dict[str, str] | None = None,
) -> FactExtractionResult:
    raw_json = _load_json_value(content)
    return normalize_fact_extraction(
        raw_json,
        source_texts=emotion_sources or {},
        image_input_ids=set(context.image_urls) if context else set(),
        current_input_id=_single_unambiguous_input_id(context) if context else None,
    )


def _normalize_raw_emotions(
    raw_result: dict[str, Any],
    source_texts: dict[str, str],
) -> None:
    """Normalize only emotion mentions whose excerpt has one exact source match."""
    for event in raw_result.get("events", []):
        if not isinstance(event, dict):
            continue
        normalized: list[dict[str, str]] = []
        for raw_mention in event.get("emotions", []):
            if isinstance(raw_mention, str):
                label = excerpt = raw_mention.strip()
                input_id = None
            elif isinstance(raw_mention, dict):
                label = str(raw_mention.get("label") or raw_mention.get("excerpt") or "").strip()
                excerpt = str(raw_mention.get("excerpt") or raw_mention.get("label") or "").strip()
                input_id = raw_mention.get("input_id")
            else:
                continue
            if not label or not excerpt:
                continue
            if input_id in source_texts and excerpt in source_texts[input_id]:
                normalized.append({"label": label, "excerpt": excerpt, "input_id": input_id})
                continue
            matching_ids = [
                source_id
                for source_id, source_text in source_texts.items()
                if excerpt in source_text
            ]
            if len(matching_ids) == 1:
                normalized.append({
                    "label": label,
                    "excerpt": excerpt,
                    "input_id": matching_ids[0],
                })
        event["emotions"] = normalized


def _load_json_value(content: str) -> dict[str, Any] | list[Any]:
    """Parse strict JSON, or a data-only Python literal sometimes emitted by HCX."""
    candidate = _json_only(content)
    try:
        value = json.loads(candidate)
    except json.JSONDecodeError:
        value = ast.literal_eval(candidate)
    if not isinstance(value, (dict, list)):
        raise ValueError("LLM output must be a JSON object or array")
    return value


def _single_unambiguous_input_id(context: MultimodalContext) -> str | None:
    """Return the sole source ID only when provenance cannot be ambiguous."""
    if context.user_message:
        current_matches = [
            input_id
            for input_id, text in context.text_inputs.items()
            if text.strip() == context.user_message.strip()
        ]
        if len(current_matches) == 1:
            return current_matches[0]
    input_ids = [
        *context.text_inputs,
        *context.image_urls,
        *context.audio_transcripts,
    ]
    return input_ids[0] if len(input_ids) == 1 else None


def _merge_prior_coverage(
    current: FactExtractionResult,
    prior_events: list[EventCandidate],
) -> None:
    """Carry forward only facts already validated in prior turns."""
    has_person = current.coverage.has_person or any(event.people for event in prior_events)
    has_location = current.coverage.has_location or any(event.location for event in prior_events)
    has_emotion = current.coverage.has_emotion or any(event.emotions for event in prior_events)
    present = {
        "person": has_person,
        "location": has_location,
        "emotion": has_emotion,
    }
    current.coverage.has_person = has_person
    current.coverage.has_location = has_location
    current.coverage.has_emotion = has_emotion
    current.coverage.missing_fields = [field for field in FIELD_PRIORITY if not present[field]]
    current.coverage.sufficient = not current.coverage.missing_fields


def _require_image_observations(
    result: FactExtractionResult,
    image_input_ids: set[str],
) -> None:
    observed_ids = {observation.input_id for observation in result.image_observations}
    if missing := image_input_ids - observed_ids:
        raise ValueError(f"missing image observations: {len(missing)}")


def _fill_missing_image_observations(
    result: FactExtractionResult,
    image_input_ids: set[str],
) -> None:
    """Keep every image visible in the result even after a failed repair."""
    observed_ids = {observation.input_id for observation in result.image_observations}
    clarity_ids = {note.input_id for note in result.image_clarity}
    for input_id in sorted(image_input_ids - observed_ids):
        result.image_observations.append(ImageObservation(
            input_id=input_id,
            description="이미지 내용을 명확히 확인하지 못했습니다.",
            observed_facts=[],
        ))
        if input_id not in clarity_ids:
            result.image_clarity.append(ImageClarityNote(
                input_id=input_id,
                unclear=True,
                reason="모델이 구조화된 이미지 관찰 결과를 반환하지 않았습니다.",
            ))
