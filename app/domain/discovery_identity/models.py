"""Identity language for pre-admission discovery candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.decision_engine import OpportunityIdentity
from app.domain.market_intelligence import (
    MarketObservationIdentity,
    MarketObservationScope,
)


DISCOVERY_IDENTITY_SCHEMA_VERSION = "discovery-identity-v1"
ADMISSION_SNAPSHOT_HANDOFF_SCHEMA_VERSION = "admission-snapshot-handoff-v2"


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _market_identity(value: MarketObservationIdentity) -> MarketObservationIdentity:
    if not isinstance(value, MarketObservationIdentity):
        raise TypeError("market_observation_identity must be MarketObservationIdentity")
    if value.scope not in {
        MarketObservationScope.LISTING,
        MarketObservationScope.CANONICAL_PRODUCT,
    }:
        raise ValueError(
            "discovery candidate market scope must be listing or canonical_product"
        )
    return value


@dataclass(frozen=True, slots=True)
class OpportunityCandidateIdentity:
    """Identity of one ProductGroup candidate before lifecycle admission."""

    candidate_id: str
    discovery_reference: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "candidate_id", _required_text(self.candidate_id, "candidate_id")
        )
        object.__setattr__(
            self,
            "discovery_reference",
            _required_text(self.discovery_reference, "discovery_reference"),
        )


@dataclass(frozen=True, slots=True)
class DiscoveryOpportunityContext:
    """Explicit context propagated through every pre-admission owner boundary."""

    candidate_identity: OpportunityCandidateIdentity
    market_observation_identity: MarketObservationIdentity
    discovery_execution_id: str
    command_id: str
    requested_at: datetime
    schema_version: str = DISCOVERY_IDENTITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_identity, OpportunityCandidateIdentity):
            raise TypeError(
                "candidate_identity must be OpportunityCandidateIdentity"
            )
        _market_identity(self.market_observation_identity)
        for name in ("discovery_execution_id", "command_id", "schema_version"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        _aware(self.requested_at, "requested_at")


@dataclass(frozen=True, slots=True)
class AdmissionSnapshotChainHandoff:
    """Explicit candidate-to-Opportunity promotion and source-chain handoff."""

    discovery_context: DiscoveryOpportunityContext
    opportunity_identity: OpportunityIdentity
    product_observation_snapshot_ids: tuple[str, ...]
    price_intelligence_snapshot_id: str
    economics_calculation_snapshot_id: str
    candidate_opportunity_binding_id: str
    admission_command_id: str
    handed_off_at: datetime
    schema_version: str = ADMISSION_SNAPSHOT_HANDOFF_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.discovery_context, DiscoveryOpportunityContext):
            raise TypeError("discovery_context must be DiscoveryOpportunityContext")
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if (
            self.candidate_identity.discovery_reference
            != self.opportunity_identity.discovery_reference
        ):
            raise ValueError(
                "candidate and Opportunity discovery references must match"
            )
        source_ids = self.product_observation_snapshot_ids
        if not isinstance(source_ids, tuple):
            raise TypeError("product_observation_snapshot_ids must be a tuple")
        if not source_ids:
            raise ValueError("product_observation_snapshot_ids must not be empty")
        normalized_ids = tuple(
            _required_text(value, "product_observation_snapshot_id")
            for value in source_ids
        )
        if len(set(normalized_ids)) != len(normalized_ids):
            raise ValueError("product_observation_snapshot_ids must be unique")
        object.__setattr__(self, "product_observation_snapshot_ids", normalized_ids)
        for name in (
            "price_intelligence_snapshot_id",
            "economics_calculation_snapshot_id",
            "candidate_opportunity_binding_id",
            "admission_command_id",
            "schema_version",
        ):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        _aware(self.handed_off_at, "handed_off_at")

    @property
    def candidate_identity(self) -> OpportunityCandidateIdentity:
        return self.discovery_context.candidate_identity

    @property
    def market_observation_identity(self) -> MarketObservationIdentity:
        return self.discovery_context.market_observation_identity


__all__ = [
    "ADMISSION_SNAPSHOT_HANDOFF_SCHEMA_VERSION",
    "DISCOVERY_IDENTITY_SCHEMA_VERSION",
    "AdmissionSnapshotChainHandoff",
    "DiscoveryOpportunityContext",
    "OpportunityCandidateIdentity",
]
