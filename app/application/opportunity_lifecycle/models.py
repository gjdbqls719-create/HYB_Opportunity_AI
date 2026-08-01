from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.opportunity import FounderDecision, OpportunityLifecycle, OpportunityLifecycleTransition


@dataclass(frozen=True, slots=True)
class CreateOpportunityLifecycle:
    opportunity_id: str
    discovery_reference: str
    operator_id: str
    reason: str
    occurred_at: datetime
    note: str | None = None


@dataclass(frozen=True, slots=True)
class LifecycleCommand:
    opportunity_id: str
    expected_version: int
    operator_id: str
    reason: str
    occurred_at: datetime
    note: str | None = None


class StartReview(LifecycleCommand):
    pass


class Approve(LifecycleCommand):
    pass


class Reject(LifecycleCommand):
    pass


class Purchase(LifecycleCommand):
    pass


class List(LifecycleCommand):
    pass


class Sell(LifecycleCommand):
    pass


class Archive(LifecycleCommand):
    pass


class Restore(LifecycleCommand):
    pass


@dataclass(frozen=True, slots=True)
class LifecycleOperationResult:
    lifecycle: OpportunityLifecycle
    transition: OpportunityLifecycleTransition
    founder_decision: FounderDecision | None = None
