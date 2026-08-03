from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.application.opportunity_validation.models import ValidationAdmissionSnapshot, ValidationQueueItem
from app.domain.opportunity import (
    EstimatedEconomicsSnapshot,
    OpportunityLifecycle,
    OpportunityLifecycleStatus,
    OpportunityLifecycleTransition,
)
from app.application.opportunity_market_identity import OpportunityMarketIdentityBinding
from app.application.verified_economics_snapshot import VerifiedEconomicsSnapshot
from app.application.production_safety_snapshot import ProductionSafetySnapshot


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

    def admit_with_economics(
        self,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        snapshot: ValidationAdmissionSnapshot,
        economics: EstimatedEconomicsSnapshot,
    ) -> None: ...

    def admit_with_market_identity(
        self,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        snapshot: ValidationAdmissionSnapshot,
        binding: OpportunityMarketIdentityBinding,
    ) -> None: ...

    def admit_with_economics_and_market_identity(
        self,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        snapshot: ValidationAdmissionSnapshot,
        economics: EstimatedEconomicsSnapshot,
        binding: OpportunityMarketIdentityBinding,
    ) -> None: ...

    def admit_with_decision_sources(
        self,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        snapshot: ValidationAdmissionSnapshot,
        binding: OpportunityMarketIdentityBinding,
        verified_economics: VerifiedEconomicsSnapshot,
        production_safety: ProductionSafetySnapshot | None = None,
    ) -> None: ...

    def admit_with_economics_and_decision_sources(
        self,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        snapshot: ValidationAdmissionSnapshot,
        economics: EstimatedEconomicsSnapshot,
        binding: OpportunityMarketIdentityBinding,
        verified_economics: VerifiedEconomicsSnapshot,
        production_safety: ProductionSafetySnapshot | None = None,
    ) -> None: ...

    def list_queue(
        self,
        *,
        statuses: tuple[OpportunityLifecycleStatus, ...],
        limit: int,
    ) -> tuple[ValidationQueueItem, ...]: ...

    def get_queue_item(self, opportunity_id: str) -> ValidationQueueItem | None: ...
