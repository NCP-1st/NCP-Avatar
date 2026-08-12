import pytest

from backend.agents.diary_chatbot.base import DiaryGenerationAgent, MultimodalChatAgent
from backend.agents.diary_chatbot.models import (
    ChatbotTurnResult,
    DiaryDraft,
    DiaryVersion,
    MultimodalContext,
)
from backend.orchestration.diary_orchestrator import DiaryOrchestrator
from backend.agents.diary_chatbot.models import WorkflowStage
from backend.services.avatar.base import AvatarAdapter
from backend.services.storage.base import StorageAdapter
from backend.services.voice.stub import NotImplementedVoiceAdapter


class UnusedChatAgent(MultimodalChatAgent):
    async def interpret(self, context: MultimodalContext) -> ChatbotTurnResult:
        raise AssertionError("이 테스트에서는 챗봇이 호출되면 안 됩니다.")


class StubDiaryGenerator(DiaryGenerationAgent):
    def __init__(self) -> None:
        self.call_count = 0

    async def generate(
        self,
        turns: list[ChatbotTurnResult],
        *,
        source_texts: dict[str, str] | None = None,
    ) -> DiaryDraft:
        self.call_count += 1
        return DiaryDraft(
            title=f"일기 {self.call_count}",
            paragraphs=["아침 기록", "점심 기록", "저녁 기록"],
            summary="오늘의 기록",
            content="오늘의 기록입니다.",
            emotion_tags=[],
            evidence_input_ids=[],
        )


class RecordingEmbeddingService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def index_diary(self, *, version_id: str, content: str) -> None:
        self.calls.append((version_id, content))


class UnusedAvatarAdapter(AvatarAdapter):
    async def render(self, audio: bytes, *, version_id: str) -> bytes:
        raise AssertionError("Voice 실패 뒤 Avatar가 호출되면 안 됩니다.")


class UnusedStorageAdapter(StorageAdapter):
    async def upload(
        self,
        data: bytes,
        *,
        object_name: str,
        mime_type: str,
    ) -> object:
        raise AssertionError("Voice 실패 뒤 Storage가 호출되면 안 됩니다.")


def _orchestrator(
    *,
    generator: DiaryGenerationAgent | None = None,
    voice: NotImplementedVoiceAdapter | None = None,
) -> DiaryOrchestrator:
    return DiaryOrchestrator(
        chat_agent=UnusedChatAgent(),
        generation_agent=generator,
        voice_adapter=voice,
        avatar_adapter=UnusedAvatarAdapter(),
        storage_adapter=UnusedStorageAdapter(),
    )


@pytest.mark.anyio
async def test_render_is_blocked_before_approval_without_calling_voice() -> None:
    voice = NotImplementedVoiceAdapter()
    orchestrator = _orchestrator(voice=voice)
    version = DiaryVersion(
        version_id="version-unapproved",
        session_id="session-gate",
        title="승인 전 일기",
        paragraphs=["하나", "둘", "셋"],
        summary="본문",
        content="일기 본문",
        emotion_tags=[],
        evidence_input_ids=[],
    )

    with pytest.raises(PermissionError, match="approved diary version"):
        await orchestrator.render(version)

    assert voice.call_count == 0


@pytest.mark.anyio
async def test_approved_render_reaches_voice_stub_and_surfaces_not_implemented() -> None:
    voice = NotImplementedVoiceAdapter()
    orchestrator = _orchestrator(voice=voice)
    version = DiaryVersion(
        version_id="version-approved",
        session_id="session-gate",
        title="승인된 일기",
        paragraphs=["하나", "둘", "셋"],
        summary="본문",
        content="일기 본문",
        emotion_tags=[],
        evidence_input_ids=[],
        approved=True,
    )

    with pytest.raises(NotImplementedError, match="CLOVA Voice"):
        await orchestrator.render(version)

    assert voice.call_count == 1


@pytest.mark.anyio
async def test_new_chat_creates_new_version_without_rendering() -> None:
    voice = NotImplementedVoiceAdapter()
    generator = StubDiaryGenerator()
    orchestrator = _orchestrator(generator=generator, voice=voice)
    state = orchestrator.start_session("session-regenerate")
    state.workflow.stage = WorkflowStage.READY_TO_GENERATE

    first = await orchestrator.request_generation(state)
    orchestrator.start_new_version_chat(state)
    state.workflow.stage = WorkflowStage.READY_TO_GENERATE
    second = await orchestrator.request_generation(state)

    assert first.version_id != second.version_id
    assert len(state.versions) == 2
    assert generator.call_count == 2
    assert voice.call_count == 0


@pytest.mark.anyio
async def test_fourth_diary_version_is_rejected() -> None:
    generator = StubDiaryGenerator()
    orchestrator = _orchestrator(generator=generator)
    state = orchestrator.start_session("session-version-limit")
    state.workflow.stage = WorkflowStage.READY_TO_GENERATE

    first = await orchestrator.request_generation(state)
    orchestrator.start_new_version_chat(state)
    state.workflow.stage = WorkflowStage.READY_TO_GENERATE
    second = await orchestrator.request_generation(state)
    orchestrator.start_new_version_chat(state)
    state.workflow.stage = WorkflowStage.READY_TO_GENERATE
    await orchestrator.request_generation(state)

    with pytest.raises(ValueError, match="3개"):
        orchestrator.start_new_version_chat(state)

    assert len(state.versions) == 3
    assert generator.call_count == 3


@pytest.mark.anyio
async def test_approving_one_version_unapproves_the_others() -> None:
    generator = StubDiaryGenerator()
    orchestrator = _orchestrator(generator=generator)
    state = orchestrator.start_session("session-single-approval")
    state.workflow.stage = WorkflowStage.READY_TO_GENERATE

    first = await orchestrator.request_generation(state)
    orchestrator.start_new_version_chat(state)
    state.workflow.stage = WorkflowStage.READY_TO_GENERATE
    second = await orchestrator.request_generation(state)
    orchestrator.start_new_version_chat(state)
    state.workflow.stage = WorkflowStage.READY_TO_GENERATE
    await orchestrator.request_generation(state)
    approved = await orchestrator.approve(state, second)

    assert approved.approved is True
    assert [item.version_id for item in state.versions if item.approved] == [
        second.version_id
    ]

    changed = await orchestrator.approve(state, first)
    assert changed.approved is True
    assert [item.version_id for item in state.versions if item.approved] == [
        first.version_id
    ]


@pytest.mark.anyio
async def test_approved_session_can_start_another_candidate_below_limit() -> None:
    orchestrator = _orchestrator(generator=StubDiaryGenerator())
    state = orchestrator.start_session("session-approved-regenerate")
    state.workflow.stage = WorkflowStage.READY_TO_GENERATE
    first = await orchestrator.request_generation(state)
    await orchestrator.approve(state, first)

    orchestrator.start_new_version_chat(state)

    assert state.stage is WorkflowStage.COLLECTING


@pytest.mark.anyio
async def test_only_approval_indexes_generated_diary_content() -> None:
    orchestrator = _orchestrator(generator=StubDiaryGenerator())
    state = orchestrator.start_session("session-embedding-trigger")
    state.workflow.stage = WorkflowStage.READY_TO_GENERATE
    embedding = RecordingEmbeddingService()

    version = await orchestrator.request_generation(state)
    assert embedding.calls == []

    approved = await orchestrator.approve(
        state,
        version,
        embedding_service=embedding,
    )

    assert embedding.calls == [(approved.version_id, approved.content)]
