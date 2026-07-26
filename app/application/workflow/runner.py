from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime

from app.application.workflow.models import (
    WorkflowContext,
    WorkflowEvent,
    WorkflowEventType,
    WorkflowRun,
    WorkflowStatus,
    utc_now,
)
from app.application.workflow.ports import WorkflowObserver, WorkflowStep


class WorkflowExecutionError(RuntimeError):
    """Workflow step 실패와 해당 실행 기록을 함께 전달한다."""

    def __init__(self, message: str, *, run: WorkflowRun) -> None:
        super().__init__(message)
        self.run = run


class WorkflowRunner:
    """동기식, fail-fast Application Workflow 실행기."""

    def __init__(
        self,
        *,
        workflow_name: str,
        steps: Iterable[WorkflowStep],
        observers: Iterable[WorkflowObserver] = (),
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        normalized_name = workflow_name.strip()
        if not normalized_name:
            raise ValueError("workflow_name은 비어 있을 수 없습니다.")

        materialized_steps = tuple(steps)
        if not materialized_steps:
            raise ValueError("Workflow에는 하나 이상의 step이 필요합니다.")

        step_names = tuple(step.name.strip() for step in materialized_steps)
        if any(not name for name in step_names):
            raise ValueError("Workflow step name은 비어 있을 수 없습니다.")
        if len(set(step_names)) != len(step_names):
            raise ValueError("Workflow step name은 서로 달라야 합니다.")

        self._workflow_name = normalized_name
        self._steps = materialized_steps
        self._observers = tuple(observers)
        self._clock = clock

    def run(self, context: WorkflowContext | None = None) -> WorkflowRun:
        execution_context = context or WorkflowContext()
        started_at = self._clock()
        completed_steps: list[str] = []
        observer_errors: list[str] = []

        self._emit(
            event_type=WorkflowEventType.WORKFLOW_STARTED,
            occurred_at=started_at,
            observer_errors=observer_errors,
        )

        for step in self._steps:
            step_name = step.name.strip()
            self._emit(
                event_type=WorkflowEventType.STEP_STARTED,
                occurred_at=self._clock(),
                step_name=step_name,
                observer_errors=observer_errors,
            )

            try:
                step.execute(execution_context)
            except Exception as error:
                finished_at = self._clock()
                error_message = str(error) or error.__class__.__name__
                self._emit(
                    event_type=WorkflowEventType.STEP_FAILED,
                    occurred_at=finished_at,
                    step_name=step_name,
                    error_message=error_message,
                    observer_errors=observer_errors,
                )
                self._emit(
                    event_type=WorkflowEventType.WORKFLOW_FAILED,
                    occurred_at=finished_at,
                    step_name=step_name,
                    error_message=error_message,
                    observer_errors=observer_errors,
                )
                run = WorkflowRun(
                    workflow_name=self._workflow_name,
                    status=WorkflowStatus.FAILED,
                    started_at=started_at,
                    finished_at=finished_at,
                    completed_steps=tuple(completed_steps),
                    failed_step=step_name,
                    error_message=error_message,
                    observer_errors=tuple(observer_errors),
                )
                raise WorkflowExecutionError(
                    f"Workflow '{self._workflow_name}'의 '{step_name}' 단계가 실패했습니다.",
                    run=run,
                ) from error

            completed_steps.append(step_name)
            self._emit(
                event_type=WorkflowEventType.STEP_COMPLETED,
                occurred_at=self._clock(),
                step_name=step_name,
                observer_errors=observer_errors,
            )

        finished_at = self._clock()
        self._emit(
            event_type=WorkflowEventType.WORKFLOW_COMPLETED,
            occurred_at=finished_at,
            observer_errors=observer_errors,
        )

        return WorkflowRun(
            workflow_name=self._workflow_name,
            status=WorkflowStatus.COMPLETED,
            started_at=started_at,
            finished_at=finished_at,
            completed_steps=tuple(completed_steps),
            observer_errors=tuple(observer_errors),
        )

    def _emit(
        self,
        *,
        event_type: WorkflowEventType,
        occurred_at: datetime,
        observer_errors: list[str],
        step_name: str | None = None,
        error_message: str | None = None,
    ) -> None:
        event = WorkflowEvent(
            workflow_name=self._workflow_name,
            event_type=event_type,
            occurred_at=occurred_at,
            step_name=step_name,
            error_message=error_message,
        )

        for observer in self._observers:
            try:
                observer.on_event(event)
            except Exception as error:
                observer_errors.append(
                    f"{observer.__class__.__name__}: "
                    f"{str(error) or error.__class__.__name__}"
                )
