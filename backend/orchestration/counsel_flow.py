

from __future__ import annotations

import asyncio
import logging
import time
import uuid

from backend.agents.counsel_chatbot import safety, style
from backend.agents.counsel_chatbot.context_agent import ContextAgent
from backend.agents.counsel_chatbot.counselor_agent import CounselorAgent
from backend.repositories import ConversationStore
from backend.services.knowledge import (
    CounselKnowledgePort,
    DiaryLookup,
    DiaryMemoryPort,
    DiaryReference,
    KnowledgeSnippet,
    OntologyFact,
    PersonalOntologyPort,
)
from backend.agents.counsel_chatbot.schemas import (
    ConversationState,
    CounselDraft,
    CounselEvidenceRef,
    CounselReply,
    CounselRequest,
    CounselStage,
    CounselTrace,
    CounselTurn,
    ResultCode,
    SafetyLevel,
)

logger = logging.getLogger(__name__)

_MAX_GUARDRAIL_RETRIES = 1
_HISTORY_LIMIT = 20  # 저장소에서 읽어올 최근 대화 수
_KNOWLEDGE_TOP_K = 3
_ONTOLOGY_MAX = 5


class CounselFlow:
    """상담 대화 한 턴을 끝까지 처리한다."""

    def __init__(
        self,
        *,
        context_agent: ContextAgent,
        counselor_agent: CounselorAgent,
        knowledge: CounselKnowledgePort,
        ontology: PersonalOntologyPort,
        store: ConversationStore,
        diary: DiaryMemoryPort | None = None,
    ) -> None:
        self._context = context_agent
        self._counselor = counselor_agent
        self._knowledge = knowledge
        self._ontology = ontology
        self._store = store
        # 일기 검색이 없으면 과거를 말할 근거가 없다는 뜻이다. 그 경우
        # `safety.review_past_claims`가 계속 걸린다 (아래 5~6단계).
        self._diary = diary

    async def run(self, request: CounselRequest) -> CounselReply:
        started = time.perf_counter()
        trace_id = uuid.uuid4().hex
        counsel_id = request.counsel_id or uuid.uuid4().hex
        stage_ms: dict[str, int] = {}

        # 대화 이력은 서버가 보관한 것만 믿는다.
        history = await self._store.load_turns(
            counsel_id=counsel_id, user_id=request.user_id, limit=_HISTORY_LIMIT
        )
        await self._store.append_turn(
            counsel_id=counsel_id,
            user_id=request.user_id,
            turn=CounselTurn(role="user", content=request.message),
        )

        # 1. 입력 선검사 — 위기면 일반 상담 흐름을 중단한다.
        screening = safety.screen_user_message(request.message)
        if screening.level is SafetyLevel.CRISIS:
            logger.warning(
                "counsel crisis detected trace=%s rules=%s",
                trace_id,
                screening.matched_rules,
            )
            # 세션에 표시를 남긴다. 사용자가 뒤에 화제를 돌려도 제안 경로를
            # 열지 않기 위해서다.
            await self._store.mark_crisis(
                counsel_id=counsel_id, user_id=request.user_id
            )
            crisis_message, crisis_notice = safety.crisis_response(
                screening.matched_rules
            )
            return await self._finish(
                counsel_id=counsel_id,
                user_id=request.user_id,
                message=crisis_message,
                draft=None,
                state=None,
                stage=None,
                safety_level=SafetyLevel.CRISIS,
                notice=crisis_notice,
                trace=CounselTrace(
                    trace_id=trace_id,
                    model="none",
                    latency_ms=_elapsed_ms(started),
                    result_code="crisis_redirect",
                    guardrail_hits=screening.matched_rules,
                ),
            )

        # 2. 챗봇 에이전트 — 사건·감정 구조화.
        #    실패해도 상담 자체는 이어져야 하므로 구조화 없이 진행한다.
        state: ConversationState | None = None
        stage_started = time.perf_counter()
        try:
            state = await self._context.structure(request.message, history)
        except Exception:
            logger.warning(
                "counsel context agent failed trace=%s — 구조화 없이 진행",
                trace_id,
                exc_info=True,
            )
        stage_ms["context"] = _elapsed_ms(stage_started)

        # 3. 이번 턴에 어디까지 할지 정한다.
        #
        # 이 세션에서 위기가 한 번이라도 있었으면 정리·제안 단계로 올리지
        # 않는다. 화제를 돌렸다고 해서 "따뜻한 차 한 잔 어떠세요"로 넘어가면
        # 안 된다. 계속 듣기만 한다.
        session_crisis = await self._store.is_crisis(
            counsel_id=counsel_id, user_id=request.user_id
        )
        if session_crisis:
            stage = CounselStage.EXPLORING
            logger.info("counsel crisis session — 제안 경로 차단 trace=%s", trace_id)
        else:
            stage = _decide_stage(history, state)

        # 4. 검색 세 갈래를 동시에. 단계가 정해진 뒤라야 한다 — 일기 검색이
        #    단계(opening 제외)를 보고 걸러진다.
        stage_started = time.perf_counter()
        snippets, facts, diary = await self._gather_context(
            request, state, stage=stage, session_crisis=session_crisis
        )
        # 아래는 "프롬프트에 들어갈 일기"만 본다. 걸러지기 전 최고점은 트레이스
        # 전용이라 `diary`에 남겨 두고 `_trace`에만 넘긴다.
        diary_refs = diary.references
        stage_ms["retrieval"] = _elapsed_ms(stage_started)

        # 5~6. 생성 + 출력 검사(위반 시 1회 재생성).
        stage_started = time.perf_counter()
        result_code: ResultCode = "ok"
        guardrail_hits: list[str] = []
        draft: CounselDraft | None = None
        violations: list[str] = []

        for attempt in range(_MAX_GUARDRAIL_RETRIES + 1):
            try:
                draft = await self._counselor.draft(
                    message=request.message,
                    stage=stage,
                    state=state,
                    snippets=snippets,
                    facts=facts,
                    history=history,
                    diary_refs=diary_refs,
                    violations=violations if attempt else None,
                )
            except Exception as exc:  # 모델·네트워크 실패
                # 삼키지 않고 사유를 trace에 남긴다. 상담 화면은 500 대신
                # 재시도 안내를 받아야 하므로 폴백 응답으로 되돌린다.
                logger.exception("counsel llm failed trace=%s", trace_id)
                stage_ms["counselor"] = _elapsed_ms(stage_started)
                return await self._finish(
                    counsel_id=counsel_id,
                    user_id=request.user_id,
                    message=safety.LLM_FALLBACK,
                    draft=None,
                    state=state,
                    stage=stage,
                    safety_level=screening.level,
                    notice=_notice_for(screening.level),
                        trace=self._trace(
                        trace_id=trace_id,
                        started=started,
                        result_code="llm_failed",
                        state=state,
                        stage=stage,
                        snippets=snippets,
                        facts=facts,
                        diary=diary,
                        guardrail_hits=guardrail_hits,
                        stage_ms=stage_ms,
                        error_detail=f"{type(exc).__name__}: {exc}"[:300],
                    ),
                )

            # 단계에 맞지 않는 필드는 여기서 잘라낸다. 프롬프트로 "null로 두라"고
            # 해도 모델은 채워 넣는다. 사용자에게 나가기 전에 지운다.
            draft = _enforce_stage(draft, stage, trace_id)

            reply_text = _flatten(draft)
            violations = safety.review_reply(reply_text)
            # 일기가 주입되지 않은 턴에서만 과거 단정을 막는다.
            #
            # 주입됐으면 과거를 말할 근거가 있는 것이므로 걸면 안 된다. 걸어
            # 버리면 근거가 확실한 문장까지 막혀서 일기를 붙인 의미가 사라진다.
            # 반대로 임계값에 걸려 아무것도 안 들어간 턴은 근거가 없는 것이니
            # 예전과 똑같이 막는다.
            if not diary_refs:
                violations += safety.review_past_claims(
                    reply_text, grounded=_user_said(history, request.message)
                )

            guardrail_hits = list(dict.fromkeys(guardrail_hits + violations))

            # 채워야 할 걸 안 채운 경우(마무리인데 작은 행동이 없는 등)와
            # 스타일 위반(너무 김·질문 2개·불릿·이모지·공감 반복)도 다시
            # 시켜본다. 다만 안전 위반과 달리 답변을 버릴 사유는 아니다.
            gaps = _stage_gaps(draft, stage, state) + style.review_style(
                _compose(draft),
                user_message=request.message,
                previous_reply=_last_assistant_reply(history),
            )

            if not violations and not gaps:
                if attempt:
                    result_code = "guardrail_rewrite"
                break

            if violations:
                logger.warning(
                    "counsel guardrail hit trace=%s attempt=%s rules=%s",
                    trace_id,
                    attempt,
                    violations,
                )
            violations += gaps
        else:
            stage_ms["counselor"] = _elapsed_ms(stage_started)

            # 단계 계약만 못 맞춘 경우 — 답변 자체엔 문제가 없으니 그대로 쓴다.
            # 마무리에 작은 행동 하나가 빠진 것 때문에 답변을 통째로 버리면
            # 사용자만 손해다.
            if not guardrail_hits:
                logger.info(
                    "counsel stage contract unmet trace=%s stage=%s — 그대로 사용",
                    trace_id,
                    stage.value,
                )
                result_code = "guardrail_rewrite"
                return await self._respond(
                    counsel_id=counsel_id,
                    request=request,
                    draft=draft,
                    state=state,
                    stage=stage,
                    screening=screening,
                    snippets=snippets,
                    facts=facts,
                    diary=diary,
                    guardrail_hits=guardrail_hits,
                    stage_ms=stage_ms,
                    trace_id=trace_id,
                    started=started,
                    result_code=result_code,
                )

            # 재생성 후에도 안전 위반 — 모델 답변을 버리고 안전 폴백을 쓴다.
            #
            # 근거 없는 과거 단정만 걸린 경우는 의료·의존 위반과 성격이 다르다.
            # 같은 폴백을 쓰면 "매번"이라고 말했다는 이유로 자살예방 상담전화가
            # 뜬다. 위반 종류에 맞는 문구와 등급을 쓴다.
            only_past_claim = set(guardrail_hits) == {"past_speculation"}
            fallback_level = screening.level if only_past_claim else SafetyLevel.CAUTION
            return await self._finish(
                counsel_id=counsel_id,
                user_id=request.user_id,
                message=(
                    safety.PAST_CLAIM_FALLBACK
                    if only_past_claim
                    else safety.GUARDRAIL_FALLBACK
                ),
                draft=None,
                state=state,
                stage=stage,
                safety_level=fallback_level,
                notice=_notice_for(fallback_level),
                trace=self._trace(
                    trace_id=trace_id,
                    started=started,
                    result_code="guardrail_blocked",
                    state=state,
                    stage=stage,
                    snippets=snippets,
                    facts=facts,
                    diary=diary,
                    guardrail_hits=guardrail_hits,
                    stage_ms=stage_ms,
                ),
            )

        stage_ms["counselor"] = _elapsed_ms(stage_started)
        assert draft is not None  # 루프는 draft를 채우거나 위에서 반환한다

        return await self._respond(
            counsel_id=counsel_id,
            request=request,
            draft=draft,
            state=state,
            stage=stage,
            screening=screening,
            snippets=snippets,
            facts=facts,
            diary=diary,
            guardrail_hits=guardrail_hits,
            stage_ms=stage_ms,
            trace_id=trace_id,
            started=started,
            result_code=result_code,
        )

    async def _respond(
        self,
        *,
        counsel_id: str,
        request: CounselRequest,
        draft: CounselDraft,
        state: ConversationState | None,
        stage: CounselStage,
        screening: safety.SafetyScreening,
        snippets: list[KnowledgeSnippet],
        facts: list[OntologyFact],
        diary: DiaryLookup,
        guardrail_hits: list[str],
        stage_ms: dict[str, int],
        trace_id: str,
        started: float,
        result_code: ResultCode,
    ) -> CounselReply:
        """초안을 답변으로 만들어 반환한다."""
        return await self._finish(
            counsel_id=counsel_id,
            user_id=request.user_id,
            message=_compose(draft),
            draft=draft,
            state=state,
            stage=stage,
            safety_level=screening.level,
            notice=_notice_for(screening.level),
            diary_refs=diary.references,
            trace=self._trace(
                trace_id=trace_id,
                started=started,
                result_code=result_code,
                state=state,
                stage=stage,
                snippets=snippets,
                facts=facts,
                diary=diary,
                guardrail_hits=guardrail_hits,
                stage_ms=stage_ms,
            ),
        )

    async def _gather_context(
        self,
        request: CounselRequest,
        state: ConversationState | None,
        *,
        stage: CounselStage,
        session_crisis: bool,
    ) -> tuple[list[KnowledgeSnippet], list[OntologyFact], DiaryLookup]:
        """상담 지식·관계 정보·과거 일기를 동시에 모은다.

        한 갈래가 실패해도 나머지로 답변한다. 검색 실패가 상담 실패가 되면
        안 된다.

        일기만 `DiaryLookup`으로 온다. 프롬프트에 들어갈 목록 외에 걸러지기 전
        최고점을 트레이스가 써야 해서다 — 임계값을 실측으로 옮기려면 참조에
        실패한 턴이 몇 점이었는지가 필요하다.
        """
        knowledge_result, ontology_result, diary_result = await asyncio.gather(
            self._search_knowledge(request, state),
            self._search_ontology(request, state),
            self._search_diary(
                request, state, stage=stage, session_crisis=session_crisis
            ),
            return_exceptions=True,
        )

        snippets: list[KnowledgeSnippet] = []
        facts: list[OntologyFact] = []
        for name, result, sink in zip(
            ("knowledge", "ontology"), (knowledge_result, ontology_result), (snippets, facts)
        ):
            if isinstance(result, BaseException):
                logger.warning("counsel %s search failed: %r", name, result)
                continue
            sink.extend(result)

        if isinstance(diary_result, BaseException):
            logger.warning("counsel diary search failed: %r", diary_result)
            diary_result = DiaryLookup()

        return snippets, facts, diary_result

    async def _search_knowledge(
        self,
        request: CounselRequest,
        state: ConversationState | None,
    ) -> list[KnowledgeSnippet]:
        query = " ".join(state.topics) if state and state.topics else request.message
        return await self._knowledge.search(
            query=query,
            emotion=state.emotion.primary if state else None,
            top_k=_KNOWLEDGE_TOP_K,
        )

    async def _search_ontology(
        self,
        request: CounselRequest,
        state: ConversationState | None,
    ) -> list[OntologyFact]:
        # 개인 관계 정보도 기억 제어(C-03) 대상이다. 일기 참조를 끈 사용자에게
        # 일기에서 뽑은 관계를 들이밀면 안 된다.
        if state is None or not request.memory_scope.enabled:
            return []
        return await self._ontology.related(
            user_id=request.user_id,
            entities=state.entities,
            max_items=_ONTOLOGY_MAX,
        )

    async def _search_diary(
        self,
        request: CounselRequest,
        state: ConversationState | None,
        *,
        stage: CounselStage,
        session_crisis: bool,
    ) -> DiaryLookup:
        """지금 대화와 관련 있는 과거 일기를 찾는다 (H-02).

        게이트가 넷이다. 매 턴 일기를 들이대지 않기 위한 것이다.

        - 구조화 실패(`state is None`): 무엇에 대한 이야기인지 모르는 상태다.
          사용자 원문으로 검색하면 군말까지 섞여 엉뚱한 일기가 걸린다.
        - 기억 제어 꺼짐(C-03): `_search_ontology`와 같은 기준이다.
        - 위기 세션: 제안 경로를 막는 것과 같은 이유다. 지금 당장 위험한
          사람에게 과거 기록을 들이밀면, 좋았던 기억이든 힘들었던 기억이든
          지금 필요한 안전 안내에서 주의를 돌린다.
        - opening 단계: 첫 마디에 과거부터 꺼내면 듣기 전에 아는 척하는 게
          된다. 무슨 이야기인지 들어본 뒤에 찾는다.

        관련도 판정은 검색 구현이 한다. 여기서 돌려받은 것은 그대로 프롬프트에
        들어간다.
        """
        if self._diary is None:
            return DiaryLookup()
        if (
            state is None
            or not request.memory_scope.enabled
            or session_crisis
            or stage is CounselStage.OPENING
        ):
            # 게이트에 막힌 턴은 검색 자체를 하지 않았다. 후보 최고점도 None이라
            # 관측에서 "후보가 없었다"와 구분되지 않는다 — 어느 쪽이든 임계값
            # 조정에 쓸 표본이 아니므로 굳이 나누지 않는다.
            return DiaryLookup()

        # 구조화가 뽑은 핵심어를 우선한다. 사용자 원문은 조사·군말이 섞인다.
        query = " ".join(state.topics) if state.topics else request.message
        return await self._diary.search(
            user_id=request.user_id,
            query=query,
            period_days=request.memory_scope.period_days,
            max_items=request.memory_scope.max_items,
            emotion=state.emotion.primary,
        )

    async def _finish(
        self,
        *,
        counsel_id: str,
        user_id: str,
        message: str,
        draft: CounselDraft | None,
        state: ConversationState | None,
        stage: CounselStage | None,
        safety_level: SafetyLevel,
        notice: str | None,
        trace: CounselTrace,
        diary_refs: list[DiaryReference] | None = None,
    ) -> CounselReply:
        """응답을 저장하고 반환한다.

        어시스턴트 턴·트레이스·근거는 1:1이고 여기서 같은 순간에 만들어지므로
        한 번에 넘겨 같은 트랜잭션으로 남긴다. 저장소가 트레이스를 버려도
        (인메모리 스텁) 상담은 그대로 동작한다.

        `diary_refs`는 성공 경로에서만 온다. 위기·폴백 답변은 모델이 쓴 문장을
        버리고 고정 문구로 대체한 것이라 일기를 근거로 삼지 않았다. 쓰지 않은
        것을 근거로 기록하면 감사 기록이 거짓이 된다.
        """
        await self._store.append_turn(
            counsel_id=counsel_id,
            user_id=user_id,
            turn=CounselTurn(
                role="assistant",
                content=message,
                stage=stage.value if stage else None,
            ),
            trace=trace,
            safety_level=safety_level.value,
            diary_refs=diary_refs,
        )
        return CounselReply(
            counsel_id=counsel_id,
            message=message,
            sections=draft,
            state=state,
            stage=stage,
            safety_level=safety_level,
            safety_notice=notice,
            trace=trace,
            evidences=[
                CounselEvidenceRef(
                    session_id=ref.session_id, diary_date=ref.diary_date
                )
                for ref in (diary_refs or [])
            ],
        )

    def _trace(
        self,
        *,
        trace_id: str,
        started: float,
        result_code: ResultCode,
        state: ConversationState | None,
        stage: CounselStage | None,
        snippets: list[KnowledgeSnippet],
        facts: list[OntologyFact],
        guardrail_hits: list[str],
        stage_ms: dict[str, int],
        diary: DiaryLookup | None = None,
        error_detail: str | None = None,
    ) -> CounselTrace:
        diary = diary or DiaryLookup()
        refs = diary.references
        return CounselTrace(
            trace_id=trace_id,
            model=self._counselor.model,
            latency_ms=_elapsed_ms(started),
            result_code=result_code,
            stage=stage.value if stage else None,
            knowledge_count=len(snippets),
            ontology_count=len(facts),
            # 임계값 보정용. 무엇이 들어갔는지가 아니라 몇 건·얼마나 관련 있었는지만
            # 남긴다 — 일기 내용은 트레이스에 넣지 않는다.
            #
            # top_score 는 실제로 쓴 일기, top_candidate 는 걸러지기 전 최고점이다.
            # 참조가 0건인 턴은 top_score 가 없고 top_candidate 만 남는데,
            # 임계값을 옮길지 정하는 건 그 값이다.
            diary_count=len(refs),
            diary_top_score=max((ref.score for ref in refs), default=None),
            diary_top_candidate=diary.top_candidate_score,
            event_count=len(state.events) if state else 0,
            emotion=state.emotion.primary if state else None,
            guardrail_hits=guardrail_hits,
            stage_ms=stage_ms,
            error_detail=error_detail,
        )


def _notice_for(level: SafetyLevel) -> str | None:
    if level is SafetyLevel.CRISIS:
        return safety.CRISIS_NOTICE
    if level is SafetyLevel.CAUTION:
        return safety.CAUTION_NOTICE
    return None


# 정리·제안으로 넘어가기 전에 최소한 이만큼은 듣는다. 첫 마디가 아무리
# 구체적이어도 바로 정리해 버리면 듣지도 않고 결론 낸 것이 된다.
_MIN_TURNS_BEFORE_CARING = 3

def _decide_stage(
    history: list[CounselTurn],
    state: ConversationState | None,
) -> CounselStage:
    """이번 턴에 어디까지 할지 정한다.

    모델에게 맡기면 매번 "이제 정리할 때"라고 판단해 첫 턴부터 요약과 해결책을
    내놓는다. 흐름 쪽에서 정해서 내려준다.

    기준은 턴 수가 아니라 **상황과 감정이 잡혔는지**다. 아직 흐릿하면 계속
    듣고, 그림이 그려지면 정리하고 하나 권한다.
    """
    if state is not None and state.wants_closure:
        return CounselStage.CLOSING

    # history는 이번 발화가 저장되기 전에 읽은 것이라 +1 한다.
    user_turns = sum(1 for turn in history if turn.role == "user") + 1
    if user_turns <= 1:
        return CounselStage.OPENING

    # 직전에 이미 정리했으면 연달아 정리하지 않는다. 매 턴 요약과 제안이
    # 따라붙으면 그것대로 대화가 아니다.
    last_stage = next(
        (turn.stage for turn in reversed(history) if turn.role == "assistant"), None
    )
    if last_stage == CounselStage.CARING.value:
        return CounselStage.EXPLORING

    if user_turns >= _MIN_TURNS_BEFORE_CARING and _is_concrete(state):
        return CounselStage.CARING
    return CounselStage.EXPLORING


def _is_concrete(state: ConversationState | None) -> bool:
    """정리해 줄 만큼 이야기가 잡혔는지.

    구조화가 실패해 state가 없으면 계속 듣는 쪽으로 둔다. 모르는 상태에서
    정리부터 하는 것보다 낫다.

    감정 확신도는 일부러 조건에 넣지 않는다. 허용 목록에 없는 감정 라벨이
    나오면 `context_agent`가 중립으로 떨어뜨리며 확신도까지 낮추는데, 그걸
    여기서 다시 보면 "목록에 없는 감정을 말한 사용자"는 영영 정리 단계로
    못 간다. 감정이 흐릿한지는 `unclear_point`로 이미 걸러진다.
    """
    if state is None:
        return False
    return state.situation_clear and state.unclear_point is None


# 단계별로 채워도 되는 필드. `reply`는 항상 채운다.
_STAGE_ALLOWED: dict[CounselStage, frozenset[str]] = {
    CounselStage.OPENING: frozenset({"question"}),
    CounselStage.EXPLORING: frozenset({"question"}),
    CounselStage.CARING: frozenset({"question", "summary", "suggestion"}),
    CounselStage.CLOSING: frozenset({"summary", "suggestion"}),
}

# 그 단계라면 반드시 있어야 하는 필드.
# EXPLORING에 question이 없는 건 의도적이다 — 물을 게 없으면 묻지 않는다.
_STAGE_REQUIRED: dict[CounselStage, frozenset[str]] = {
    CounselStage.OPENING: frozenset({"question"}),
    CounselStage.EXPLORING: frozenset(),
    CounselStage.CARING: frozenset({"summary", "suggestion"}),
    CounselStage.CLOSING: frozenset({"suggestion"}),
}

_OPTIONAL_FIELDS = ("question", "summary", "suggestion")


def _enforce_stage(
    draft: CounselDraft,
    stage: CounselStage,
    trace_id: str,
) -> CounselDraft:
    """단계에 없는 필드를 지운다.

    프롬프트에 "반드시 null"이라고 써도 모델은 채워 넣는다. 첫 턴부터 정리와
    해결책이 딸려 나오는 걸 막으려면 코드에서 잘라내야 한다.
    """
    allowed = _STAGE_ALLOWED[stage]
    dropped = {
        field: None
        for field in _OPTIONAL_FIELDS
        if field not in allowed and getattr(draft, field)
    }
    # suggestion이 없으면 kind도 없어야 한다. 반대로 kind만 있는 것도 무의미하다.
    if "suggestion" in dropped or not draft.suggestion:
        if draft.suggestion_kind is not None:
            dropped["suggestion_kind"] = None
    elif draft.suggestion_kind is None:
        dropped["suggestion_kind"] = "action"  # 종류를 안 밝히면 행동으로 본다

    if dropped:
        logger.info(
            "counsel adjusted off-stage fields trace=%s stage=%s fields=%s",
            trace_id,
            stage.value,
            list(dropped),
        )
        return draft.model_copy(update=dropped)
    return draft


def _stage_gaps(
    draft: CounselDraft,
    stage: CounselStage,
    state: ConversationState | None,
) -> list[str]:
    """그 단계에 있어야 할 필드가 비었는지 본다.

    질문은 단계로 강제하지 않는다. 대신 챗봇 에이전트가 "아직 모르는 것"을
    짚었는데도 묻지 않았을 때만 다시 시킨다.
    """
    required = set(_STAGE_REQUIRED[stage])
    if (
        stage is CounselStage.EXPLORING
        and state is not None
        and state.unclear_point
    ):
        required.add("question")

    return [f"missing_{field}" for field in sorted(required) if not getattr(draft, field)]


def _last_assistant_reply(history: list[CounselTurn]) -> str | None:
    """직전 상담사 발화. 같은 공감 표현을 두 턴 연속 쓰는지 볼 때 쓴다."""
    return next(
        (turn.content for turn in reversed(history) if turn.role == "assistant"), None
    )


def _user_said(history: list[CounselTurn], message: str) -> str:
    """이 대화에서 **사용자가** 한 말을 모은다 (과거 단정 검사의 근거).

    어시스턴트 턴은 넣지 않는다. 상담사가 앞 턴에서 꺼낸 시점을 근거로 인정하면,
    한 번 지어낸 과거가 다음 턴부터 사실로 굳는다.
    """
    return " ".join(
        [turn.content for turn in history if turn.role == "user"] + [message]
    )


def _flatten(draft: CounselDraft) -> str:
    """출력 검사를 위해 텍스트 필드를 이어붙인다."""
    return " ".join(
        part
        for part in (draft.reply, draft.question, draft.summary, draft.suggestion)
        if part
    )


def _compose(draft: CounselDraft) -> str:
    """화면에 그대로 출력할 답변 텍스트를 만든다.

    대부분의 턴은 `reply` 하나, 물을 게 있으면 `question`까지 두 문단으로
    끝난다.

    이모지는 넣지 않는다. 음악 제안임을 알리는 표시는 화면 쪽에서
    `suggestion_kind`를 보고 붙인다.
    """
    suggestion = draft.suggestion
    if suggestion and draft.suggestion_kind == "music":
        suggestion = f"\U0001f3b5 {suggestion}"

    return "\n\n".join(
        part.strip()
        for part in (draft.reply, draft.summary, draft.question, suggestion)
        if part and part.strip()
    )


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
