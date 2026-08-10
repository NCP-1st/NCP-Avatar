from dataclasses import dataclass, field

from backend.agents.diary_chatbot.models import ChatbotTurnResult, WorkflowStage

@dataclass
class DiaryWorkflowState:
    """Provider-free state transitions for clarification, approval, and rendering gates."""

    session_id: str
    stage: WorkflowStage = WorkflowStage.COLLECTING
    question_count: int = 0
    asked_fields: set[str] = field(default_factory=set)
    skipped_fields: set[str] = field(default_factory=set)
    last_question_field: str | None = None
    turns: list[ChatbotTurnResult] = field(default_factory=list)

    def apply_turn(self, result: ChatbotTurnResult) -> WorkflowStage:
        self.turns.append(result)
        effective_missing = [
            field_name for field_name in result.coverage.missing_fields
            if field_name not in self.skipped_fields
        ]
        if result.coverage.sufficient or not effective_missing:
            self.stage = WorkflowStage.AWAITING_SUMMARY_CONFIRMATION
            self.last_question_field = None
            return self.stage
        top_field = effective_missing[0]
        will_ask = bool(result.response.question)
        if will_ask:
            self.question_count += 1
            self.asked_fields.add(top_field)
            self.last_question_field = top_field
        self.stage = (
            WorkflowStage.NEEDS_CLARIFICATION
            if will_ask
            else WorkflowStage.AWAITING_SUMMARY_CONFIRMATION
        )
        return self.stage

    def skip_current_question(self, missing_fields: list[str]) -> str | None:
        if self.stage is not WorkflowStage.NEEDS_CLARIFICATION or not self.last_question_field:
            raise ValueError("skippable clarification question is not expected")
        self.skipped_fields.add(self.last_question_field)
        next_field = next(
            (field_name for field_name in missing_fields
             if field_name not in self.skipped_fields),
            None,
        )
        if next_field is None:
            self.last_question_field = None
            self.stage = WorkflowStage.AWAITING_SUMMARY_CONFIRMATION
            return None
        self.question_count += 1
        self.asked_fields.add(next_field)
        self.last_question_field = next_field
        self.stage = WorkflowStage.NEEDS_CLARIFICATION
        return next_field

    def confirm_summary(self, *, correct: bool) -> WorkflowStage:
        if self.stage is not WorkflowStage.AWAITING_SUMMARY_CONFIRMATION:
            raise ValueError("summary confirmation is not expected")
        self.stage = (
            WorkflowStage.AWAITING_MORE_CONTENT if correct
            else WorkflowStage.AWAITING_CORRECTION
        )
        return self.stage

    def choose_more_content(self, *, wants_more: bool) -> WorkflowStage:
        if self.stage is not WorkflowStage.AWAITING_MORE_CONTENT:
            raise ValueError("more-content choice is not expected")
        self.stage = (
            WorkflowStage.ADDING_MORE_CONTENT if wants_more
            else WorkflowStage.READY_TO_GENERATE
        )
        return self.stage

    def finish_review_input(self, *, correction: bool) -> WorkflowStage:
        expected = WorkflowStage.AWAITING_CORRECTION if correction else WorkflowStage.ADDING_MORE_CONTENT
        if self.stage is not expected:
            raise ValueError("review input is not expected")
        self.stage = (
            WorkflowStage.AWAITING_SUMMARY_CONFIRMATION
            if correction else WorkflowStage.READY_TO_GENERATE
        )
        return self.stage

    def mark_drafted(self) -> None:
        if self.stage is not WorkflowStage.READY_TO_GENERATE:
            raise ValueError("diary generation requires sufficient information")
        self.stage = WorkflowStage.DRAFTED

    def approve(self) -> None:
        if self.stage is not WorkflowStage.DRAFTED:
            raise ValueError("only a drafted diary can be approved")
        self.stage = WorkflowStage.APPROVED

    def begin_render(self) -> None:
        if self.stage is not WorkflowStage.APPROVED:
            raise PermissionError("rendering requires an approved diary version")
        self.stage = WorkflowStage.RENDERING
