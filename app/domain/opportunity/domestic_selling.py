"""Immutable authority for foreign-source to KR domestic-selling admission."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.domain.opportunity.lifecycle import OpportunityLifecycleStatus

if TYPE_CHECKING:
    from app.domain.decision_engine import OpportunityIdentity


DOMESTIC_SELLING_OPPORTUNITY_ADMISSION_SCHEMA_VERSION = (
    "domestic-selling-opportunity-admission-v1"
)
DOMESTIC_PRODUCT_EQUIVALENCE_SCHEMA_VERSION = (
    "domestic-product-equivalence-verification-v1"
)


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _positive(value: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class DomesticProductEquivalenceVerification:
    operator_id: str
    verified_at: datetime
    evidence_reference: str
    confirmed: bool
    schema_version: str = DOMESTIC_PRODUCT_EQUIVALENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "operator_id", _text(self.operator_id, "operator_id"))
        object.__setattr__(self, "verified_at", _aware(self.verified_at, "verified_at"))
        object.__setattr__(
            self,
            "evidence_reference",
            _text(self.evidence_reference, "evidence_reference"),
        )
        if self.confirmed is not True:
            raise ValueError("product equivalence must be explicitly confirmed")
        if self.schema_version != DOMESTIC_PRODUCT_EQUIVALENCE_SCHEMA_VERSION:
            raise ValueError("unsupported product equivalence verification schema")


@dataclass(frozen=True, slots=True)
class DomesticSellingOpportunityAdmission:
    admission_id: str
    source_opportunity_identity: OpportunityIdentity
    source_lifecycle_status: OpportunityLifecycleStatus
    source_lifecycle_version: int
    domestic_opportunity_identity: OpportunityIdentity
    source_candidate_id: str
    source_candidate_opportunity_binding_id: str
    source_promotion_command_id: str
    source_product_snapshot_id: str
    source_market_identity: MarketObservationIdentity
    domestic_market_identity: MarketObservationIdentity
    product_equivalence: DomesticProductEquivalenceVerification
    policy_name: str
    policy_version: str
    requested_at: datetime
    admitted_at: datetime
    schema_version: str = DOMESTIC_SELLING_OPPORTUNITY_ADMISSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "admission_id", _text(self.admission_id, "admission_id"))
        # decision_engine imports the opportunity package while defining this type.
        from app.domain.decision_engine import OpportunityIdentity

        for name in ("source_opportunity_identity", "domestic_opportunity_identity"):
            if not isinstance(getattr(self, name), OpportunityIdentity):
                raise TypeError(f"{name} must be OpportunityIdentity")
        if (
            self.source_opportunity_identity.opportunity_id
            == self.domestic_opportunity_identity.opportunity_id
        ):
            raise ValueError("source and domestic Opportunity identities must differ")
        try:
            object.__setattr__(
                self,
                "source_lifecycle_status",
                OpportunityLifecycleStatus(self.source_lifecycle_status),
            )
        except ValueError as error:
            raise ValueError("unsupported source lifecycle status") from error
        object.__setattr__(
            self,
            "source_lifecycle_version",
            _positive(self.source_lifecycle_version, "source_lifecycle_version"),
        )
        for name in (
            "source_candidate_id",
            "source_candidate_opportunity_binding_id",
            "source_promotion_command_id",
            "source_product_snapshot_id",
            "policy_name",
            "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("source_market_identity", "domestic_market_identity"):
            if not isinstance(getattr(self, name), MarketObservationIdentity):
                raise TypeError(f"{name} must be MarketObservationIdentity")
        if self.domestic_market_identity.market.upper() != "KR":
            raise ValueError("domestic Market identity must be KR")
        if self.domestic_market_identity.scope not in {
            MarketObservationScope.LISTING,
            MarketObservationScope.CANONICAL_PRODUCT,
        }:
            raise ValueError("domestic Market identity must identify a listing or canonical product")
        if not isinstance(
            self.product_equivalence, DomesticProductEquivalenceVerification
        ):
            raise TypeError(
                "product_equivalence must be DomesticProductEquivalenceVerification"
            )
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        object.__setattr__(self, "admitted_at", _aware(self.admitted_at, "admitted_at"))
        if self.product_equivalence.verified_at > self.requested_at:
            raise ValueError("verified_at cannot follow requested_at")
        if self.admitted_at < self.requested_at:
            raise ValueError("admitted_at cannot precede requested_at")
        if self.schema_version != DOMESTIC_SELLING_OPPORTUNITY_ADMISSION_SCHEMA_VERSION:
            raise ValueError("unsupported domestic selling admission schema")


__all__ = [
    "DOMESTIC_PRODUCT_EQUIVALENCE_SCHEMA_VERSION",
    "DOMESTIC_SELLING_OPPORTUNITY_ADMISSION_SCHEMA_VERSION",
    "DomesticProductEquivalenceVerification",
    "DomesticSellingOpportunityAdmission",
]
