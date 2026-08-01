from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.opportunity import OpportunityLifecycle, OpportunityLifecycleTransition


class LifecycleNotFoundError(LookupError):
    pass


class DuplicateLifecycleError(ValueError):
    pass


class LifecycleVersionConflictError(RuntimeError):
    pass


class LifecycleSemanticError(ValueError):
    pass


@runtime_checkable
class OpportunityLifecycleRepository(Protocol):
    def create(self, lifecycle: OpportunityLifecycle, transition: OpportunityLifecycleTransition) -> None: ...

    def get(self, opportunity_id: str) -> OpportunityLifecycle | None: ...

    def save_transition(
        self,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        *,
        expected_version: int,
    ) -> None: ...

    def list_transitions(self, opportunity_id: str) -> tuple[OpportunityLifecycleTransition, ...]: ...
