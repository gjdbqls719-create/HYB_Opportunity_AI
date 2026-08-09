from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.opportunity_market_identity import (
    OpportunityMarketIdentityBinding,
)
from app.domain.opportunity import OpportunityLifecycle


class OperationalOpportunityEligibilityRepository(Protocol):
    def get(self, opportunity_id: str) -> OpportunityLifecycle | None: ...

    def get_market_identity_binding(
        self,
        opportunity_id: str,
    ) -> OpportunityMarketIdentityBinding | None: ...


@dataclass(frozen=True, slots=True)
class OperationalOpportunityEligibility:
    lifecycle: OpportunityLifecycle
    market_binding: OpportunityMarketIdentityBinding | None


def get_operational_opportunity_eligibility(
    repository: OperationalOpportunityEligibilityRepository,
    opportunity_id: str,
) -> OperationalOpportunityEligibility | None:
    lifecycle = repository.get(opportunity_id)
    if lifecycle is None or lifecycle.is_archived:
        return None
    return OperationalOpportunityEligibility(
        lifecycle=lifecycle,
        market_binding=repository.get_market_identity_binding(opportunity_id),
    )
