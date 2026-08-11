from dataclasses import dataclass, field
from uuid import uuid4

from backend.agents.diary_chatbot import DiaryGenerationAgent, MultimodalChatAgent
from backend.agents.diary_chatbot.models import (
    ChatbotTurnResult,
    DiaryVersion,
    MultimodalContext,
    RenderResult,
    TurnResponse,
    WorkflowStage,
)
from backend.agents.diary_chatbot.sanitize import FALLBACK_QUESTIONS
from backend.orchestration.diary_workflow import DiaryWorkflowState
from backend.services.avatar import AvatarAdapter
from backend.services.storage import StorageAdapter
from backend.services.voice import VoiceAdapter

MAX_DIARY_VERSIONS = 3


@dataclass
class DiaryOrchestrationState:
    workflow: DiaryWorkflowState
    text_inputs: dict[str, str] = field(default_factory=dict)
    latest_turn: ChatbotTurnResult | None = None
    versions: list[DiaryVersion] = field(default_factory=list)
    review_summary: str | None = None
    correction_notes: list[str] = field(default_factory=list)

    @property
    def session_id(self) -> str:
        return self.workflow.session_id

    @property
    def stage(self) -> WorkflowStage:
        return self.workflow.stage

    @property
    def questions_asked_count(self) -> int:
        return self.workflow.question_count


class DiaryOrchestrator:
    """Coordinates agents and adapters; agents never invoke each other directly."""

    def __init__(
        self,
        *,
        chat_agent: MultimodalChatAgent,
        generation_agent: DiaryGenerationAgent | None = None,
        voice_adapter: VoiceAdapter | None = None,
        avatar_adapter: AvatarAdapter | None = None,
        storage_adapter: StorageAdapter | None = None,
    ) -> None:
        self._chat = chat_agent
        self._generation = generation_agent
        self._voice = voice_adapter
        self._avatar = avatar_adapter
        self._storage = storage_adapter

    def start_session(self, session_id: str) -> DiaryOrchestrationState:
        return DiaryOrchestrationState(workflow=DiaryWorkflowState(session_id=session_id))

    def start_new_version_chat(self, state: DiaryOrchestrationState) -> None:
        if any(version.approved for version in state.versions):
            raise ValueError("이미 오늘의 일기로 확정된 버전이 있습니다.")
        if len(state.versions) >= MAX_DIARY_VERSIONS:
            raise ValueError("일기 후보는 최대 3개까지 만들 수 있습니다.")
        state.workflow = DiaryWorkflowState(session_id=state.session_id)
        state.text_inputs = {}
        state.latest_turn = None
        state.review_summary = None
        state.correction_notes = []

    async def handle_turn(
        self,
        state: DiaryOrchestrationState,
        message: str,
        *,
        image_urls: dict[str, str] | None = None,
        audio_transcripts: dict[str, str] | None = None,
        text_input_id: str | None = None,
    ) -> DiaryOrchestrationState:
        if state.stage in {
            WorkflowStage.READY_TO_GENERATE,
            WorkflowStage.AWAITING_SUMMARY_CONFIRMATION,
            WorkflowStage.AWAITING_MORE_CONTENT,
        }:
            return state

        review_input_stage = state.stage
        if message.strip():
            input_id = text_input_id or f"turn-{len(state.text_inputs) + 1}"
            state.text_inputs[input_id] = message.strip()
            if review_input_stage is WorkflowStage.AWAITING_CORRECTION:
                state.correction_notes.append(message.strip())
        state.text_inputs.update(audio_transcripts or {})
        result = await self._chat.interpret(
            MultimodalContext(
                session_id=state.session_id,
                user_message=message.strip() or None,
                text_inputs=dict(state.text_inputs),
                image_urls=image_urls or {},
                audio_transcripts=audio_transcripts or {},
                prior_events=[
                    event
                    for turn in state.workflow.turns
                    for event in turn.events
                ],
                prior_reactions=[turn.response.reaction for turn in state.workflow.turns],
                skipped_fields=sorted(state.workflow.skipped_fields),
            )
        )
        state.latest_turn = result
        if review_input_stage is WorkflowStage.AWAITING_CORRECTION:
            state.workflow.turns.append(result)
            state.workflow.finish_review_input(correction=True)
        elif review_input_stage is WorkflowStage.ADDING_MORE_CONTENT:
            state.workflow.turns.append(result)
            state.workflow.finish_review_input(correction=False)
        else:
            state.workflow.apply_turn(result)
        if state.stage is WorkflowStage.AWAITING_SUMMARY_CONFIRMATION:
            state.review_summary = self.build_review_summary(state)
        return state

    def skip_current_question(self, state: DiaryOrchestrationState) -> None:
        if state.latest_turn is None:
            raise ValueError("clarification question is not available")
        next_field = state.workflow.skip_current_question(
            state.latest_turn.coverage.missing_fields
        )
        if next_field is None:
            state.review_summary = self.build_review_summary(state)
            return
        state.latest_turn = state.latest_turn.model_copy(
            update={
                "response": TurnResponse(
                    reaction="알겠어요. 해당 정보는 건너뛸게요.",
                    question=FALLBACK_QUESTIONS[next_field],
                )
            }
        )

    def review_summary(self, state: DiaryOrchestrationState, *, correct: bool) -> None:
        state.workflow.confirm_summary(correct=correct)

    def choose_more_content(self, state: DiaryOrchestrationState, *, wants_more: bool) -> None:
        state.workflow.choose_more_content(wants_more=wants_more)

    @staticmethod
    def build_review_summary(state: DiaryOrchestrationState) -> str:
        """Build one natural sentence from verified people, places, events, and emotions."""
        people: list[str] = []
        locations: list[str] = []
        activities: list[str] = []
        emotions: list[str] = []
        image_descriptions: list[str] = []
        for turn in state.workflow.turns:
            for observation in turn.image_observations:
                if observation.description not in image_descriptions:
                    image_descriptions.append(observation.description)
            for event in turn.events:
                for person in event.people:
                    if person not in people:
                        people.append(person)
                if event.location and event.location not in locations:
                    locations.append(event.location)
                detail = event.event.strip()
                if detail and detail not in activities:
                    activities.append(detail)
                for emotion in event.emotions:
                    display_emotion = emotion.excerpt or emotion.label
                    if display_emotion not in emotions:
                        emotions.append(display_emotion)

        activity_text = ", ".join(activities) or "오늘의 일을 기록했어요"
        prefix_parts = []
        if people and not any(person in activity_text for person in people):
            prefix_parts.append(f"{_with_and_particle(', '.join(people))} 함께")
        if locations and not any(location in activity_text for location in locations):
            prefix_parts.append(f"{', '.join(locations)}에서")
        summary = " ".join([*prefix_parts, activity_text]).strip().rstrip(".")
        if emotions:
            summary += f", 이때 느낀 감정은 {', '.join(emotions)}였어요."
        else:
            summary += "."
        if image_descriptions:
            summary = _append_summary_sentence(
                summary,
                f"사진에서 확인한 내용은 {', '.join(image_descriptions)}",
            )
        if state.correction_notes:
            summary += " 정정해 주신 내용은 " + ", ".join(state.correction_notes) + "예요."
        return summary

    async def request_generation(self, state: DiaryOrchestrationState) -> DiaryVersion:
        if not self._generation:
            raise NotImplementedError("diary generation adapter is not configured")
        if state.stage is not WorkflowStage.READY_TO_GENERATE:
            raise ValueError("diary is not ready for generation")
        draft = await self._generation.generate(
            state.workflow.turns,
            source_texts=dict(state.text_inputs),
        )
        version = DiaryVersion(
            **draft.model_dump(),
            version_id=str(uuid4()),
            session_id=state.session_id,
            approved=False,
        )
        state.versions.append(version)
        state.workflow.mark_drafted()
        return version

    def approve(self, state: DiaryOrchestrationState, version: DiaryVersion) -> DiaryVersion:
        if version.session_id != state.session_id:
            raise ValueError("version does not belong to this session")
        approved = version.model_copy(update={"approved": True})
        state.versions = [
            approved
            if item.version_id == version.version_id
            else item.model_copy(update={"approved": False})
            for item in state.versions
        ]
        state.workflow.approve()
        return approved

    async def render(self, version: DiaryVersion, *, voice_id: str = "default") -> RenderResult:
        if not version.approved:
            raise PermissionError("rendering requires an approved diary version")
        if not self._voice or not self._avatar or not self._storage:
            raise NotImplementedError("render adapters are not fully configured")
        audio = await self._voice.synthesize(version.content, voice_id=voice_id)
        video = await self._avatar.render(audio, version_id=version.version_id)
        audio_object = await self._storage.upload(
            audio, object_name=f"{version.version_id}.mp3", mime_type="audio/mpeg"
        )
        video_object = await self._storage.upload(
            video, object_name=f"{version.version_id}.mp4", mime_type="video/mp4"
        )
        return RenderResult(
            version_id=version.version_id,
            audio_url=audio_object.url,
            video_url=video_object.url,
        )


def _with_and_particle(text: str) -> str:
    """Attach 과/와 without relying on generated grammar."""
    if not text:
        return text
    last = text[-1]
    if "가" <= last <= "힣":
        has_batchim = (ord(last) - ord("가")) % 28 != 0
        return text + ("과" if has_batchim else "와")
    return text + "와"


def _append_summary_sentence(base: str, addition: str) -> str:
    """Append a phrase without producing endings such as '보입니다예요'."""
    addition = addition.strip()
    if not addition:
        return base
    if addition.endswith((".", "!", "?", "다", "요")):
        return f"{base} {addition}"
    return f"{base} {addition}예요."
