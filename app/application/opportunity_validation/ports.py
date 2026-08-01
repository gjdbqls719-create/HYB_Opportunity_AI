from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.application.opportunity_validation.models import ValidationAdmissionSnapshot, ValidationQueueItem
from app.domain.opportunity import OpportunityLifecycle, OpportunityLifecycleStatus, OpportunityLifecycleTransition


class DuplicateActiveValidationError(ValueError):
    pass


class DuplicateValidationConflictError(DuplicateActiveValidationError):
    """A canonical reference already belongs to another non-archived lifecycle."""

    pass


@runtime_checkable
class ValidationQueueRepository(Protocol):
    def admit(
        self,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        snapshot: ValidationAdmissionSnapshot,
    ) -> None: ...

    def list_queue(
        self,
        *,
        statuses: tuple[OpportunityLifecycleStatus, ...],
        limit: int,
    ) -> tuple[ValidationQueueItem, ...]: ...

    def get_queue_item(self, opportunity_id: str) -> ValidationQueueItem | None: ...
