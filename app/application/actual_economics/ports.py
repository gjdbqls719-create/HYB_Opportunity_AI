from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.opportunity import ActualEconomics, ActualEconomicsEvent, OpportunityLifecycle


class ActualEconomicsNotFoundError(LookupError):
    pass


class DuplicateActualEconomicsError(ValueError):
    pass


class ActualEconomicsVersionConflictError(RuntimeError):
    pass


class ActualEconomicsSemanticError(ValueError):
    pass


class ActualEconomicsLifecyclePreconditionError(ValueError):
    pass


@runtime_checkable
class ActualEconomicsRepository(Protocol):
    def create(self, economics: ActualEconomics, event: ActualEconomicsEvent) -> None: ...
    def get(self, opportunity_id: str) -> ActualEconomics | None: ...
    def save_event(self, economics: ActualEconomics, event: ActualEconomicsEvent, *, expected_version: int) -> None: ...
    def list_events(self, opportunity_id: str) -> tuple[ActualEconomicsEvent, ...]: ...


@runtime_checkable
class LifecycleReader(Protocol):
    def get(self, opportunity_id: str) -> OpportunityLifecycle | None: ...
