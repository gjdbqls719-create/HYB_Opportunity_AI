from __future__ import annotations

from typing import Protocol

from app.application.workflow.models import WorkflowContext, WorkflowEvent


class WorkflowStep(Protocol):
    @property
    def name(self) -> str:
        """Workflow 안에서 유일한 단계 이름."""
        ...

    def execute(self, context: WorkflowContext) -> None:
        """공유 context를 읽거나 갱신한다."""
        ...


class WorkflowObserver(Protocol):
    def on_event(self, event: WorkflowEvent) -> None:
        """Workflow 수명주기 이벤트를 관찰한다."""
        ...
