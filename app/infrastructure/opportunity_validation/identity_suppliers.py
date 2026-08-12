"""Production identity suppliers for Candidate promotion facts."""

from __future__ import annotations

from uuid import uuid4


class ProductionOpportunityIdentityGenerator:
    """Supplies one server-owned opaque Opportunity identity per call."""

    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


class ProductionCandidateOpportunityBindingIdentityGenerator:
    """Supplies one server-owned opaque promotion binding identity per call."""

    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


class ProductionCandidatePromotionAdmissionIdentityGenerator:
    """Supplies one server-owned opaque v2 promotion admission identity."""

    __slots__ = ()

    def __call__(self) -> str:
        return uuid4().hex


__all__ = [
    "ProductionCandidateOpportunityBindingIdentityGenerator",
    "ProductionCandidatePromotionAdmissionIdentityGenerator",
    "ProductionOpportunityIdentityGenerator",
]
