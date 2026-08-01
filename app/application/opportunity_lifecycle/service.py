from __future__ import annotations

from app.application.opportunity_lifecycle.models import (
    Approve,
    Archive,
    CreateOpportunityLifecycle,
    LifecycleCommand,
    LifecycleOperationResult,
    List,
    Purchase,
    Reject,
    Restore,
    ReturnToReview,
    Sell,
    StartReview,
)
from app.application.opportunity_lifecycle.ports import (
    LifecycleNotFoundError,
    LifecycleVersionConflictError,
    OpportunityLifecycleRepository,
)
from app.domain.opportunity import FounderDecision, FounderDecisionType, OpportunityLifecycle


class OpportunityLifecycleService:
    def __init__(self, repository: OpportunityLifecycleRepository) -> None:
        self._repository = repository

    def create(self, command: CreateOpportunityLifecycle) -> LifecycleOperationResult:
        lifecycle = OpportunityLifecycle(
            opportunity_id=command.opportunity_id,
            discovery_reference=command.discovery_reference,
            created_at=command.occurred_at,
            updated_at=command.occurred_at,
        )
        transition = lifecycle.creation_transition(
            operator_id=command.operator_id,
            reason=command.reason,
            note=command.note,
        )
        self._repository.create(lifecycle, transition)
        return LifecycleOperationResult(lifecycle, transition)

    def start_review(self, command: StartReview) -> LifecycleOperationResult:
        return self._change(command, "start_review")

    def approve(self, command: Approve) -> LifecycleOperationResult:
        decision = self._decision(command, FounderDecisionType.APPROVE)
        return self._change(command, "approve", decision)

    def reject(self, command: Reject) -> LifecycleOperationResult:
        decision = self._decision(command, FounderDecisionType.REJECT)
        return self._change(command, "reject", decision)

    def purchase(self, command: Purchase) -> LifecycleOperationResult:
        return self._change(command, "purchase")

    def list(self, command: List) -> LifecycleOperationResult:
        return self._change(command, "list_for_sale")

    def sell(self, command: Sell) -> LifecycleOperationResult:
        return self._change(command, "sell")

    def archive(self, command: Archive) -> LifecycleOperationResult:
        return self._change(command, "archive")

    def restore(self, command: Restore) -> LifecycleOperationResult:
        return self._change(command, "restore")

    def return_to_review(self, command: ReturnToReview) -> LifecycleOperationResult:
        return self._change(command, "return_to_review")

    def _load(self, command: LifecycleCommand) -> OpportunityLifecycle:
        lifecycle = self._repository.get(command.opportunity_id)
        if lifecycle is None:
            raise LifecycleNotFoundError(command.opportunity_id)
        if lifecycle.version != command.expected_version:
            raise LifecycleVersionConflictError(
                f"expected version {command.expected_version}, found {lifecycle.version}"
            )
        return lifecycle

    def _change(
        self,
        command: LifecycleCommand,
        method_name: str,
        decision: FounderDecision | None = None,
    ) -> LifecycleOperationResult:
        lifecycle = self._load(command)
        method = getattr(lifecycle, method_name)
        kwargs = dict(
            occurred_at=command.occurred_at,
            operator_id=command.operator_id,
            reason=command.reason,
            note=command.note,
        )
        if decision is not None:
            kwargs["founder_decision_id"] = decision.decision_id
        transition = method(**kwargs)
        self._repository.save_transition(
            lifecycle,
            transition,
            expected_version=command.expected_version,
        )
        return LifecycleOperationResult(lifecycle, transition, decision)

    @staticmethod
    def _decision(command: LifecycleCommand, decision: FounderDecisionType) -> FounderDecision:
        return FounderDecision(
            opportunity_id=command.opportunity_id,
            decision=decision,
            reason=command.reason,
            note=command.note,
            decided_at=command.occurred_at,
            operator_id=command.operator_id,
        )
