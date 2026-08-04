from __future__ import annotations

from uuid import uuid4

from app.application.economics_variance import (
    CaptureEstimatedEconomicsBaseline,
    EconomicsVarianceService,
)
from app.application.opportunity_lifecycle import (
    Approve,
    OpportunityLifecycleRepository,
    OpportunityLifecycleService,
    Reject,
    ReturnToReview,
    StartReview,
)
from app.application.opportunity_validation.models import (
    AddToValidationQueueCommand,
    ValidationActionCommand,
    ValidationAdmissionSnapshot,
    ValidationQueueItem,
    ValidationQueueQuery,
)
from app.application.opportunity_validation.ports import ValidationQueueRepository
from app.application.opportunity_validation.reference import canonicalize_discovery_reference
from app.domain.opportunity import EconomicsCalculation, OpportunityLifecycle
from app.application.opportunity_market_identity import OpportunityMarketIdentityBinding
from app.application.verified_economics_snapshot import VerifiedEconomicsSnapshot
from app.application.production_safety_snapshot import ProductionSafetySnapshot


class OpportunityValidationService:
    def __init__(
        self,
        *,
        queue_repository: ValidationQueueRepository,
        lifecycle_repository: OpportunityLifecycleRepository,
    ) -> None:
        self._queue_repository = queue_repository
        self._lifecycle_service = OpportunityLifecycleService(lifecycle_repository)

    def add(self, command: AddToValidationQueueCommand) -> ValidationQueueItem:
        lifecycle, transition, snapshot = self._build_admission(command)
        if command.market_observation_identity is None:
            self._queue_repository.admit(lifecycle, transition, snapshot)
        elif command.verified_economics is not None:
            self._queue_repository.admit_with_decision_sources(
                lifecycle,
                transition,
                snapshot,
                self._binding(command, lifecycle),
                self._verified_economics(command, lifecycle),
                self._production_safety(command, lifecycle),
            )
        else:
            self._queue_repository.admit_with_market_identity(
                lifecycle,
                transition,
                snapshot,
                self._binding(command, lifecycle),
            )
        return self._load_admitted(lifecycle.opportunity_id)

    def add_with_economics(
        self,
        command: AddToValidationQueueCommand,
        economics: EconomicsCalculation,
    ) -> ValidationQueueItem:
        """Variance-ready admission without changing the existing add/API contract."""
        lifecycle, transition, snapshot = self._build_admission(command)
        baseline = EconomicsVarianceService.build_snapshot(
            CaptureEstimatedEconomicsBaseline(
                opportunity_id=lifecycle.opportunity_id,
                economics=economics,
                captured_at=command.captured_at,
            )
        )
        if command.market_observation_identity is None:
            self._queue_repository.admit_with_economics(
                lifecycle, transition, snapshot, baseline
            )
        elif command.verified_economics is not None:
            self._queue_repository.admit_with_economics_and_decision_sources(
                lifecycle,
                transition,
                snapshot,
                baseline,
                self._binding(command, lifecycle),
                self._verified_economics(command, lifecycle),
                self._production_safety(command, lifecycle),
            )
        else:
            self._queue_repository.admit_with_economics_and_market_identity(
                lifecycle,
                transition,
                snapshot,
                baseline,
                self._binding(command, lifecycle),
            )
        return self._load_admitted(lifecycle.opportunity_id)

    def _build_admission(self, command: AddToValidationQueueCommand):
        opportunity_id = command.opportunity_id or uuid4().hex
        discovery_reference = canonicalize_discovery_reference(command.discovery_reference)
        lifecycle = OpportunityLifecycle(
            opportunity_id,
            discovery_reference,
            created_at=command.captured_at,
            updated_at=command.captured_at,
        )
        transition = lifecycle.creation_transition(
            operator_id=command.operator_id,
            reason=command.reason,
            note=command.note,
        )
        snapshot = ValidationAdmissionSnapshot(
            opportunity_id=opportunity_id,
            discovery_reference=discovery_reference,
            marketplace=command.marketplace,
            title=command.title,
            admission_recommendation=command.admission_recommendation,
            admission_score=command.admission_score,
            admission_roi=command.admission_roi,
            currency=command.currency,
            admission_safety_status=command.admission_safety_status,
            captured_at=command.captured_at,
        )
        return lifecycle, transition, snapshot

    def prepare_admission(self, command: AddToValidationQueueCommand):
        """Build the existing admission facts without persisting them."""
        return self._build_admission(command)

    def prepare_market_binding(self, command, lifecycle):
        """Build the existing market binding for a shared atomic boundary."""
        return self._binding(command, lifecycle)

    @staticmethod
    def _binding(command, lifecycle) -> OpportunityMarketIdentityBinding:
        return OpportunityMarketIdentityBinding(
            opportunity_id=lifecycle.opportunity_id,
            discovery_reference=lifecycle.discovery_reference,
            market_observation_identity=command.market_observation_identity,
            bound_at=command.captured_at,
        )

    @staticmethod
    def _verified_economics(command, lifecycle) -> VerifiedEconomicsSnapshot:
        return VerifiedEconomicsSnapshot(
            opportunity_id=lifecycle.opportunity_id,
            inputs=command.verified_economics,
            snapshot_at=command.captured_at,
        )

    @staticmethod
    def _production_safety(command, lifecycle) -> ProductionSafetySnapshot | None:
        if command.production_safety is None:
            return None
        return ProductionSafetySnapshot(
            opportunity_id=lifecycle.opportunity_id,
            assessment=command.production_safety,
            snapshot_at=command.captured_at,
            rule_version=command.production_safety_rule_version,
        )

    def _load_admitted(self, opportunity_id: str) -> ValidationQueueItem:
        item = self._queue_repository.get_queue_item(opportunity_id)
        if item is None:
            raise RuntimeError("admitted validation queue item could not be loaded")
        return item

    def list(self, query: ValidationQueueQuery) -> tuple[ValidationQueueItem, ...]:
        if query.limit < 1:
            raise ValueError("limit must be at least 1")
        return self._queue_repository.list_queue(statuses=query.statuses, limit=query.limit)

    def get(self, opportunity_id: str) -> ValidationQueueItem | None:
        return self._queue_repository.get_queue_item(opportunity_id)

    def start_review(self, command: ValidationActionCommand):
        return self._lifecycle_service.start_review(self._lifecycle_command(StartReview, command))

    def approve(self, command: ValidationActionCommand):
        return self._lifecycle_service.approve(self._lifecycle_command(Approve, command))

    def reject(self, command: ValidationActionCommand):
        return self._lifecycle_service.reject(self._lifecycle_command(Reject, command))

    def return_to_review(self, command: ValidationActionCommand):
        return self._lifecycle_service.return_to_review(self._lifecycle_command(ReturnToReview, command))

    @staticmethod
    def _lifecycle_command(command_type, command: ValidationActionCommand):
        return command_type(
            command.opportunity_id,
            command.expected_version,
            command.operator_id,
            command.reason,
            command.occurred_at,
            command.note,
        )
