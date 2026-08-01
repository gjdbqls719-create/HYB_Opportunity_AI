from datetime import datetime, timedelta, timezone

from app.application.opportunity_lifecycle import (
    Approve, CreateOpportunityLifecycle, List, OpportunityLifecycleService,
    Purchase, Reject, Sell, StartReview,
)


NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)


class MemoryRepository:
    def __init__(self):
        self.item = None
        self.events = []

    def create(self, lifecycle, transition):
        self.item = lifecycle
        self.events.append(transition)

    def get(self, opportunity_id):
        return self.item if self.item and self.item.opportunity_id == opportunity_id else None

    def save_transition(self, lifecycle, transition, *, expected_version):
        assert expected_version + 1 == lifecycle.version
        self.item = lifecycle
        self.events.append(transition)

    def list_transitions(self, opportunity_id):
        return tuple(self.events)


def command(cls, version, minute):
    return cls("opp-1", version, "founder", "manual validation", NOW + timedelta(minutes=minute))


def test_application_creates_only_when_explicitly_called_and_runs_sale_path() -> None:
    repository = MemoryRepository()
    service = OpportunityLifecycleService(repository)
    created = service.create(CreateOpportunityLifecycle("opp-1", "validation-queue:row-1", "founder", "saved to queue", NOW))
    assert created.lifecycle.version == 1
    service.start_review(command(StartReview, 1, 1))
    approved = service.approve(command(Approve, 2, 2))
    assert approved.founder_decision is not None
    assert approved.transition.founder_decision_id == approved.founder_decision.decision_id
    service.purchase(command(Purchase, 3, 3))
    service.list(command(List, 4, 4))
    sold = service.sell(command(Sell, 5, 5))
    assert sold.lifecycle.status.value == "sold"
    assert len(repository.events) == 6


def test_application_reject_creates_independent_founder_decision() -> None:
    repository = MemoryRepository()
    service = OpportunityLifecycleService(repository)
    service.create(CreateOpportunityLifecycle("opp-1", "validation-queue:row-1", "founder", "saved", NOW))
    result = service.reject(command(Reject, 1, 1))
    assert result.lifecycle.status.value == "rejected"
    assert result.founder_decision is not None
    assert result.founder_decision.decision.value == "reject"
