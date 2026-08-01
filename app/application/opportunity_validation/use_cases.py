from __future__ import annotations

from app.application.opportunity_validation.models import AddToValidationQueueCommand, ValidationActionCommand, ValidationQueueQuery
from app.application.opportunity_validation.service import OpportunityValidationService


class AddToValidationQueue:
    def __init__(self, service: OpportunityValidationService) -> None: self._service = service
    def execute(self, command: AddToValidationQueueCommand): return self._service.add(command)


class GetValidationQueue:
    def __init__(self, service: OpportunityValidationService) -> None: self._service = service
    def execute(self, query: ValidationQueueQuery = ValidationQueueQuery()): return self._service.list(query)


class GetValidationQueueItem:
    def __init__(self, service: OpportunityValidationService) -> None: self._service = service
    def execute(self, opportunity_id: str): return self._service.get(opportunity_id)


class StartOpportunityReview:
    def __init__(self, service: OpportunityValidationService) -> None: self._service = service
    def execute(self, command: ValidationActionCommand): return self._service.start_review(command)


class ApproveOpportunity:
    def __init__(self, service: OpportunityValidationService) -> None: self._service = service
    def execute(self, command: ValidationActionCommand): return self._service.approve(command)


class RejectOpportunity:
    def __init__(self, service: OpportunityValidationService) -> None: self._service = service
    def execute(self, command: ValidationActionCommand): return self._service.reject(command)


class ReturnToReview:
    def __init__(self, service: OpportunityValidationService) -> None: self._service = service
    def execute(self, command: ValidationActionCommand): return self._service.return_to_review(command)
