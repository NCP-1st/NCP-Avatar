from dataclasses import dataclass, field

from backend.agents.diary_chatbot.models import ChatbotTurnResult, WorkflowStage

MAX_FOLLOW_UP_QUESTIONS = 3


@dataclass
class DiaryWorkflowState:
    """Provider-free state transitions for clarification, approval, and rendering gates."""

    session_id: str
    stage: WorkflowStage = WorkflowStage.COLLECTING
    question_count: int = 0
    turns: list[ChatbotTurnResult] = field(default_factory=list)

    def apply_turn(self, result: ChatbotTurnResult) -> WorkflowStage:
        self.turns.append(result)
        if result.coverage.sufficient:
            self.stage = WorkflowStage.READY_TO_GENERATE
            return self.stage
        remaining = max(MAX_FOLLOW_UP_QUESTIONS - self.question_count, 0)
        asked = min(len(result.follow_up_questions), remaining)
        self.question_count += asked
        self.stage = (WorkflowStage.NEEDS_CLARIFICATION
                      if asked and self.question_count < MAX_FOLLOW_UP_QUESTIONS
                      else WorkflowStage.READY_TO_GENERATE)
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
