from __future__ import annotations

from uuid import uuid4

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
from app.domain.opportunity import OpportunityLifecycle


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
        self._queue_repository.admit(lifecycle, transition, snapshot)
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
