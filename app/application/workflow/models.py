from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class WorkflowStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowEventType(str, Enum):
    WORKFLOW_STARTED = "workflow_started"
    STEP_STARTED = "step_started"
    STEP_COMPLETED = "step_completed"
    STEP_FAILED = "step_failed"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"


@dataclass(slots=True, frozen=True)
class WorkflowEvent:
    workflow_name: str
    event_type: WorkflowEventType
    occurred_at: datetime
    step_name: str | None = None
    error_message: str | None = None


@dataclass(slots=True, frozen=True)
class WorkflowRun:
    workflow_name: str
    status: WorkflowStatus
    started_at: datetime
    finished_at: datetime
    completed_steps: tuple[str, ...]
    failed_step: str | None = None
    error_message: str | None = None
    observer_errors: tuple[str, ...] = ()

    @property
    def duration_seconds(self) -> float:
        return max(
            0.0,
            (self.finished_at - self.started_at).total_seconds(),
        )


@dataclass(slots=True)
class WorkflowContext:
    """Workflow step 사이에서 명시적으로 공유하는 실행 데이터."""

    _values: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        normalized_key = key.strip()
        if not normalized_key:
            raise ValueError("WorkflowContext key는 비어 있을 수 없습니다.")
        self._values[normalized_key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._values.get(key, default)

    def require(self, key: str) -> Any:
        if key not in self._values:
            raise KeyError(f"WorkflowContext에 '{key}' 값이 없습니다.")
        return self._values[key]

    def snapshot(self) -> Mapping[str, Any]:
        return MappingProxyType(dict(self._values))


def utc_now() -> datetime:
    return datetime.now(timezone.utc)
