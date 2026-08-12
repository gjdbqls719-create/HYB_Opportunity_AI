"""Immutable new-to-market KR selling target authority facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from app.domain.market_intelligence import MarketObservationIdentity
from app.domain.opportunity.lifecycle import OpportunityLifecycleStatus

if TYPE_CHECKING:
    from app.domain.decision_engine import OpportunityIdentity


NEW_TO_MARKET_TARGET_IDENTITY_SCHEMA_VERSION = (
    "new-to-market-domestic-selling-target-identity-v1"
)
OPPORTUNITY_DOMESTIC_SELLING_TARGET_BINDING_SCHEMA_VERSION = (
    "opportunity-domestic-selling-target-binding-v1"
)
BOUNDED_KR_SEARCH_MANIFEST_SCHEMA_VERSION = "bounded-kr-search-manifest-v1"
NEW_TO_MARKET_SOURCE_MANIFEST_SCHEMA_VERSION = (
    "new-to-market-domestic-selling-source-manifest-v1"
)
NEW_TO_MARKET_ADMISSION_SCHEMA_VERSION = (
    "new-to-market-domestic-selling-opportunity-admission-v1"
)


class NewToMarketDomesticSellingTargetKind(StrEnum):
    NEW_TO_MARKET_DOMESTIC_SELLING_TARGET = (
        "new_to_market_domestic_selling_target"
    )


class BoundedKRSearchScopeKind(StrEnum):
    QUERY = "query"
    CATEGORY = "category"


class BoundedKRSearchConclusion(StrEnum):
    EXACT_KR_IDENTITY_NOT_ESTABLISHED = "exact_kr_identity_not_established"


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


def _text_tuple(value: tuple[str, ...], name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple) or not value:
        raise ValueError(f"{name} must be a non-empty tuple")
    normalized = tuple(_text(item, name) for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must contain unique values")
    return normalized


@dataclass(frozen=True, slots=True)
class BoundedKRSearchManifest:
    searched_channels: tuple[str, ...]
    scope_kind: BoundedKRSearchScopeKind
    scope_value: str
    performed_at: datetime
    operator_id: str
    evidence_references: tuple[str, ...]
    conclusion: BoundedKRSearchConclusion = (
        BoundedKRSearchConclusion.EXACT_KR_IDENTITY_NOT_ESTABLISHED
    )
    market: str = "KR"
    schema_version: str = BOUNDED_KR_SEARCH_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "searched_channels",
            _text_tuple(self.searched_channels, "searched_channels"),
        )
        object.__setattr__(
            self,
            "evidence_references",
            _text_tuple(self.evidence_references, "evidence_references"),
        )
        try:
            object.__setattr__(
                self, "scope_kind", BoundedKRSearchScopeKind(self.scope_kind)
            )
        except ValueError as error:
            raise ValueError("unsupported bounded search scope kind") from error
        object.__setattr__(self, "scope_value", _text(self.scope_value, "scope_value"))
        object.__setattr__(
            self, "performed_at", _aware(self.performed_at, "performed_at")
        )
        object.__setattr__(self, "operator_id", _text(self.operator_id, "operator_id"))
        try:
            conclusion = BoundedKRSearchConclusion(self.conclusion)
        except ValueError as error:
            raise ValueError("unsupported bounded search conclusion") from error
        if conclusion is not BoundedKRSearchConclusion.EXACT_KR_IDENTITY_NOT_ESTABLISHED:
            raise ValueError("bounded search must not assert universal absence")
        object.__setattr__(self, "conclusion", conclusion)
        if _text(self.market, "market").upper() != "KR":
            raise ValueError("bounded search market must be KR")
        object.__setattr__(self, "market", "KR")
        if self.schema_version != BOUNDED_KR_SEARCH_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported bounded KR search manifest schema")


@dataclass(frozen=True, slots=True)
class NewToMarketDomesticSellingTargetIdentity:
    domestic_selling_target_id: str
    market: str = "KR"
    kind: NewToMarketDomesticSellingTargetKind = (
        NewToMarketDomesticSellingTargetKind.NEW_TO_MARKET_DOMESTIC_SELLING_TARGET
    )
    schema_version: str = NEW_TO_MARKET_TARGET_IDENTITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "domestic_selling_target_id",
            _text(self.domestic_selling_target_id, "domestic_selling_target_id"),
        )
        if _text(self.market, "market").upper() != "KR":
            raise ValueError("new-to-market selling target market must be KR")
        object.__setattr__(self, "market", "KR")
        try:
            kind = NewToMarketDomesticSellingTargetKind(self.kind)
        except ValueError as error:
            raise ValueError("unsupported new-to-market target kind") from error
        if kind is not (
            NewToMarketDomesticSellingTargetKind.NEW_TO_MARKET_DOMESTIC_SELLING_TARGET
        ):
            raise ValueError("unsupported new-to-market target kind")
        object.__setattr__(self, "kind", kind)
        if self.schema_version != NEW_TO_MARKET_TARGET_IDENTITY_SCHEMA_VERSION:
            raise ValueError("unsupported new-to-market target identity schema")


@dataclass(frozen=True, slots=True)
class OpportunityDomesticSellingTargetBinding:
    opportunity_id: str
    discovery_reference: str
    target_identity: NewToMarketDomesticSellingTargetIdentity
    bound_at: datetime
    schema_version: str = (
        OPPORTUNITY_DOMESTIC_SELLING_TARGET_BINDING_SCHEMA_VERSION
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "opportunity_id", _text(self.opportunity_id, "opportunity_id"))
        object.__setattr__(
            self,
            "discovery_reference",
            _text(self.discovery_reference, "discovery_reference"),
        )
        if not isinstance(
            self.target_identity, NewToMarketDomesticSellingTargetIdentity
        ):
            raise TypeError("target_identity must be NewToMarketDomesticSellingTargetIdentity")
        object.__setattr__(self, "bound_at", _aware(self.bound_at, "bound_at"))
        if self.schema_version != (
            OPPORTUNITY_DOMESTIC_SELLING_TARGET_BINDING_SCHEMA_VERSION
        ):
            raise ValueError("unsupported Opportunity target binding schema")


@dataclass(frozen=True, slots=True)
class NewToMarketDomesticSellingSourceManifest:
    source_opportunity_identity: OpportunityIdentity
    source_lifecycle_status: OpportunityLifecycleStatus
    source_lifecycle_version: int
    source_market_identity: MarketObservationIdentity
    candidate_id: str
    candidate_opportunity_binding_id: str
    promotion_command_id: str
    promotion_admission_id: str
    finalized_group_id: str
    product_snapshot_capture_command_id: str
    product_snapshot_ids: tuple[str, ...]
    representative_product_snapshot_id: str
    selected_product_snapshot_id: str
    selected_source_observation_id: str
    schema_version: str = NEW_TO_MARKET_SOURCE_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        from app.domain.decision_engine import OpportunityIdentity

        if not isinstance(self.source_opportunity_identity, OpportunityIdentity):
            raise TypeError("source_opportunity_identity must be OpportunityIdentity")
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
        if not isinstance(self.source_market_identity, MarketObservationIdentity):
            raise TypeError("source_market_identity must be MarketObservationIdentity")
        for name in (
            "candidate_id",
            "candidate_opportunity_binding_id",
            "promotion_command_id",
            "promotion_admission_id",
            "finalized_group_id",
            "product_snapshot_capture_command_id",
            "representative_product_snapshot_id",
            "selected_product_snapshot_id",
            "selected_source_observation_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(
            self,
            "product_snapshot_ids",
            _text_tuple(self.product_snapshot_ids, "product_snapshot_ids"),
        )
        if self.representative_product_snapshot_id not in self.product_snapshot_ids:
            raise ValueError("representative Product Snapshot must belong to source cohort")
        if self.selected_product_snapshot_id not in self.product_snapshot_ids:
            raise ValueError("selected Product Snapshot must belong to source cohort")
        if self.schema_version != NEW_TO_MARKET_SOURCE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported new-to-market source manifest schema")


@dataclass(frozen=True, slots=True)
class NewToMarketDomesticSellingOpportunityAdmission:
    admission_id: str
    source_manifest: NewToMarketDomesticSellingSourceManifest
    domestic_opportunity_identity: OpportunityIdentity
    target_identity: NewToMarketDomesticSellingTargetIdentity
    search_manifest: BoundedKRSearchManifest
    operator_id: str
    decision_reason: str
    verified_at: datetime
    requested_at: datetime
    admitted_at: datetime
    policy_name: str
    policy_version: str
    schema_version: str = NEW_TO_MARKET_ADMISSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        from app.domain.decision_engine import OpportunityIdentity

        object.__setattr__(self, "admission_id", _text(self.admission_id, "admission_id"))
        if not isinstance(
            self.source_manifest, NewToMarketDomesticSellingSourceManifest
        ):
            raise TypeError("source_manifest must be NewToMarketDomesticSellingSourceManifest")
        if not isinstance(self.domestic_opportunity_identity, OpportunityIdentity):
            raise TypeError("domestic_opportunity_identity must be OpportunityIdentity")
        if (
            self.domestic_opportunity_identity.opportunity_id
            == self.source_manifest.source_opportunity_identity.opportunity_id
        ):
            raise ValueError("source and domestic Opportunity identities must differ")
        if not isinstance(
            self.target_identity, NewToMarketDomesticSellingTargetIdentity
        ):
            raise TypeError("target_identity must be NewToMarketDomesticSellingTargetIdentity")
        if not isinstance(self.search_manifest, BoundedKRSearchManifest):
            raise TypeError("search_manifest must be BoundedKRSearchManifest")
        object.__setattr__(self, "operator_id", _text(self.operator_id, "operator_id"))
        object.__setattr__(
            self, "decision_reason", _text(self.decision_reason, "decision_reason")
        )
        if self.search_manifest.operator_id != self.operator_id:
            raise ValueError("search operator must equal admission operator")
        for name in ("verified_at", "requested_at", "admitted_at"):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if self.search_manifest.performed_at > self.verified_at:
            raise ValueError("bounded search cannot follow verification")
        if self.verified_at > self.requested_at:
            raise ValueError("verified_at cannot follow requested_at")
        if self.admitted_at < self.requested_at:
            raise ValueError("admitted_at cannot precede requested_at")
        for name in ("policy_name", "policy_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.schema_version != NEW_TO_MARKET_ADMISSION_SCHEMA_VERSION:
            raise ValueError("unsupported new-to-market admission schema")


__all__ = [
    "BOUNDED_KR_SEARCH_MANIFEST_SCHEMA_VERSION",
    "NEW_TO_MARKET_ADMISSION_SCHEMA_VERSION",
    "NEW_TO_MARKET_SOURCE_MANIFEST_SCHEMA_VERSION",
    "NEW_TO_MARKET_TARGET_IDENTITY_SCHEMA_VERSION",
    "OPPORTUNITY_DOMESTIC_SELLING_TARGET_BINDING_SCHEMA_VERSION",
    "BoundedKRSearchConclusion",
    "BoundedKRSearchManifest",
    "BoundedKRSearchScopeKind",
    "NewToMarketDomesticSellingOpportunityAdmission",
    "NewToMarketDomesticSellingSourceManifest",
    "NewToMarketDomesticSellingTargetIdentity",
    "NewToMarketDomesticSellingTargetKind",
    "OpportunityDomesticSellingTargetBinding",
]
