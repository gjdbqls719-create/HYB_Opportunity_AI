from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.opportunity_market_identity import (
    OpportunityMarketIdentityBinding,
)
from app.domain.opportunity import OpportunityLifecycle
from app.domain.opportunity import OpportunityDomesticSellingTargetBinding


class OperationalOpportunityBindingConflictError(ValueError):
    pass


class OperationalOpportunityBindingUnavailableError(RuntimeError):
    pass


class OperationalOpportunityEligibilityRepository(Protocol):
    def get(self, opportunity_id: str) -> OpportunityLifecycle | None: ...

    def get_market_identity_binding(
        self,
        opportunity_id: str,
    ) -> OpportunityMarketIdentityBinding | None: ...

    def get_target_binding(
        self,
        opportunity_id: str,
    ) -> OpportunityDomesticSellingTargetBinding | None: ...


@dataclass(frozen=True, slots=True)
class OperationalMarketIdentitySubject:
    binding: OpportunityMarketIdentityBinding


@dataclass(frozen=True, slots=True)
class OperationalDomesticSellingTargetSubject:
    binding: OpportunityDomesticSellingTargetBinding


OperationalOpportunitySubject = (
    OperationalMarketIdentitySubject | OperationalDomesticSellingTargetSubject
)


@dataclass(frozen=True, slots=True)
class OperationalOpportunityEligibility:
    lifecycle: OpportunityLifecycle
    subject: OperationalOpportunitySubject | None

    @property
    def market_binding(self) -> OpportunityMarketIdentityBinding | None:
        if isinstance(self.subject, OperationalMarketIdentitySubject):
            return self.subject.binding
        return None

    @property
    def target_binding(self) -> OpportunityDomesticSellingTargetBinding | None:
        if isinstance(self.subject, OperationalDomesticSellingTargetSubject):
            return self.subject.binding
        return None


def get_operational_opportunity_eligibility(
    repository: OperationalOpportunityEligibilityRepository,
    opportunity_id: str,
) -> OperationalOpportunityEligibility | None:
    lifecycle = repository.get(opportunity_id)
    if lifecycle is None or lifecycle.is_archived:
        return None
    market_binding = repository.get_market_identity_binding(opportunity_id)
    target_binding = repository.get_target_binding(opportunity_id)
    if market_binding is not None and target_binding is not None:
        raise OperationalOpportunityBindingConflictError(
            "Opportunity has conflicting operational binding variants"
        )
    subject = None
    if market_binding is not None:
        subject = OperationalMarketIdentitySubject(market_binding)
    elif target_binding is not None:
        subject = OperationalDomesticSellingTargetSubject(target_binding)
    return OperationalOpportunityEligibility(lifecycle=lifecycle, subject=subject)
