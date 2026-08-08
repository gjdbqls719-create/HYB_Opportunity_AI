"""Immutable Capital-facing domestic market validation facts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.domain.market_intelligence.evidence import MarketEvidenceStatus
from app.domain.market_intelligence.identity import MarketObservationIdentity


DOMESTIC_MARKET_VALIDATION_SCHEMA_VERSION = "domestic-market-validation-v1"
DOMESTIC_MARKET_SOURCE_MANIFEST_SCHEMA_VERSION = "domestic-market-source-manifest-v1"
DOMESTIC_MARKET_VERIFICATION_SCHEMA_VERSION = "domestic-market-current-use-verification-v1"
DOMESTIC_MARKET_VALIDATION_POLICY_NAME = "domestic-market-validation"
DOMESTIC_MARKET_VALIDATION_POLICY_VERSION = "1.0.0"


class DomesticMarketValidationState(StrEnum):
    VALIDATED_FOR_CAPITAL = "validated_for_capital"
    BLOCKED = "blocked"


class DomesticMarketValidationReasonCode(StrEnum):
    NON_DOMESTIC_MARKET = "non_domestic_market"
    OPPORTUNITY_MARKET_LINEAGE_MISMATCH = "opportunity_market_lineage_mismatch"
    COMPETITION_SOURCE_MISSING = "competition_source_missing"
    COMPETITION_ASSESSMENT_NOT_COMPLETE = "competition_assessment_not_complete"
    COMPETITION_REQUIRED_METRIC_MISSING = "competition_required_metric_missing"
    COMPETITION_PROVENANCE_INSUFFICIENT = "competition_provenance_insufficient"
    DEMAND_SOURCE_MISSING = "demand_source_missing"
    DEMAND_ASSESSMENT_PARTIAL = "demand_assessment_partial"
    DEMAND_REQUIRED_METRIC_MISSING = "demand_required_metric_missing"
    DEMAND_PROVENANCE_INSUFFICIENT = "demand_provenance_insufficient"
    REQUIRED_EVIDENCE_STATUS_UNSUPPORTED = "required_evidence_status_unsupported"
    SOURCE_TIME_UNKNOWN = "source_time_unknown"
    SOURCE_TIME_IN_FUTURE = "source_time_in_future"
    CURRENT_USE_VERIFICATION_MISSING = "current_use_verification_missing"

    @property
    def order(self) -> int:
        return _REASON_ORDER.index(self)


_REASON_ORDER = tuple(DomesticMarketValidationReasonCode)


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _optional_text(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text or None")
    return value.strip() or None


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _optional_aware(value: datetime | None, name: str) -> datetime | None:
    return None if value is None else _aware(value, name)


def _text_tuple(value: tuple[str, ...], name: str) -> tuple[str, ...]:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple")
    normalized = tuple(_text(item, name) for item in value)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must not contain duplicates")
    return normalized


@dataclass(frozen=True, slots=True)
class DomesticMarketMetricEvidence:
    metric: str
    value: int | Decimal
    source: str | None
    reference: str | None
    observed_at: datetime | None
    collection_method: str
    status: MarketEvidenceStatus
    confidence: Decimal
    unit: str | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric", _text(self.metric, "metric"))
        if isinstance(self.value, bool) or not isinstance(self.value, (int, Decimal)):
            raise TypeError("metric value must be int or Decimal")
        if isinstance(self.value, Decimal) and not self.value.is_finite():
            raise ValueError("metric value must be finite")
        object.__setattr__(self, "source", _optional_text(self.source, "source"))
        object.__setattr__(self, "reference", _optional_text(self.reference, "reference"))
        object.__setattr__(self, "observed_at", _optional_aware(self.observed_at, "observed_at"))
        object.__setattr__(self, "collection_method", _text(self.collection_method, "collection_method"))
        object.__setattr__(self, "status", MarketEvidenceStatus(self.status))
        if not isinstance(self.confidence, Decimal):
            raise TypeError("confidence must be Decimal")
        if not self.confidence.is_finite() or not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("confidence must be between zero and one")
        object.__setattr__(self, "unit", _optional_text(self.unit, "unit"))


@dataclass(frozen=True, slots=True)
class DomesticMarketAnalysisSourceManifest:
    observation_id: str
    assessment_id: str
    observation_schema_version: str | None
    assessment_schema_version: str | None
    assessment_policy_version: str | None
    availability: str | None
    evidence: tuple[DomesticMarketMetricEvidence, ...]

    def __post_init__(self) -> None:
        for name in ("observation_id", "assessment_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in (
            "observation_schema_version",
            "assessment_schema_version",
            "assessment_policy_version",
            "availability",
        ):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))
        if not isinstance(self.evidence, tuple) or any(
            not isinstance(item, DomesticMarketMetricEvidence) for item in self.evidence
        ):
            raise TypeError("evidence must be a DomesticMarketMetricEvidence tuple")
        metrics = tuple(item.metric for item in self.evidence)
        if len(set(metrics)) != len(metrics):
            raise ValueError("source evidence metrics must be unique")


@dataclass(frozen=True, slots=True)
class DomesticMarketValidationSourceManifest:
    opportunity_id: str
    discovery_reference: str
    market_identity: MarketObservationIdentity
    competition: DomesticMarketAnalysisSourceManifest
    demand: DomesticMarketAnalysisSourceManifest
    accepted_external_signal_ids: tuple[str, ...]
    schema_version: str = DOMESTIC_MARKET_SOURCE_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("opportunity_id", "discovery_reference"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.market_identity, MarketObservationIdentity):
            raise TypeError("market_identity must be MarketObservationIdentity")
        if not isinstance(self.competition, DomesticMarketAnalysisSourceManifest):
            raise TypeError("competition must be a source manifest")
        if not isinstance(self.demand, DomesticMarketAnalysisSourceManifest):
            raise TypeError("demand must be a source manifest")
        object.__setattr__(
            self,
            "accepted_external_signal_ids",
            _text_tuple(self.accepted_external_signal_ids, "accepted_external_signal_ids"),
        )
        if self.schema_version != DOMESTIC_MARKET_SOURCE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported domestic market source manifest schema")


@dataclass(frozen=True, slots=True)
class DomesticMarketVerification:
    operator_id: str
    verified_at: datetime
    current_use_confirmed: bool
    reviewed_source_ids: tuple[str, ...]
    schema_version: str = DOMESTIC_MARKET_VERIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "operator_id", _text(self.operator_id, "operator_id"))
        object.__setattr__(self, "verified_at", _aware(self.verified_at, "verified_at"))
        if not isinstance(self.current_use_confirmed, bool):
            raise TypeError("current_use_confirmed must be bool")
        object.__setattr__(
            self,
            "reviewed_source_ids",
            _text_tuple(self.reviewed_source_ids, "reviewed_source_ids"),
        )
        if self.schema_version != DOMESTIC_MARKET_VERIFICATION_SCHEMA_VERSION:
            raise ValueError("unsupported domestic market verification schema")


@dataclass(frozen=True, slots=True)
class DomesticMarketValidationReason:
    code: DomesticMarketValidationReasonCode

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", DomesticMarketValidationReasonCode(self.code))


@dataclass(frozen=True, slots=True)
class DomesticMarketValidationAssessment:
    assessment_id: str
    source_manifest: DomesticMarketValidationSourceManifest
    verification: DomesticMarketVerification
    state: DomesticMarketValidationState
    blocking_reasons: tuple[DomesticMarketValidationReason, ...]
    policy_name: str
    policy_version: str
    requested_at: datetime
    evaluated_at: datetime
    schema_version: str = DOMESTIC_MARKET_VALIDATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "assessment_id", _text(self.assessment_id, "assessment_id"))
        if not isinstance(self.source_manifest, DomesticMarketValidationSourceManifest):
            raise TypeError("source_manifest must be DomesticMarketValidationSourceManifest")
        if not isinstance(self.verification, DomesticMarketVerification):
            raise TypeError("verification must be DomesticMarketVerification")
        state = DomesticMarketValidationState(self.state)
        object.__setattr__(self, "state", state)
        if not isinstance(self.blocking_reasons, tuple) or any(
            not isinstance(item, DomesticMarketValidationReason) for item in self.blocking_reasons
        ):
            raise TypeError("blocking_reasons must be a reason tuple")
        codes = tuple(item.code for item in self.blocking_reasons)
        if len(set(codes)) != len(codes):
            raise ValueError("blocking reasons must be unique")
        if codes != tuple(sorted(codes, key=lambda value: value.order)):
            raise ValueError("blocking reasons must use deterministic order")
        if state is DomesticMarketValidationState.VALIDATED_FOR_CAPITAL and codes:
            raise ValueError("VALIDATED_FOR_CAPITAL cannot carry blockers")
        if state is DomesticMarketValidationState.BLOCKED and not codes:
            raise ValueError("BLOCKED assessment requires blockers")
        if state is DomesticMarketValidationState.VALIDATED_FOR_CAPITAL:
            expected_reviewed_sources = (
                self.source_manifest.competition.observation_id,
                self.source_manifest.competition.assessment_id,
                self.source_manifest.demand.observation_id,
                self.source_manifest.demand.assessment_id,
                *self.source_manifest.accepted_external_signal_ids,
            )
            if self.source_manifest.market_identity.market.upper() != "KR":
                raise ValueError("VALIDATED_FOR_CAPITAL requires a KR Market identity")
            if not self.verification.current_use_confirmed:
                raise ValueError("VALIDATED_FOR_CAPITAL requires current-use verification")
            if self.verification.reviewed_source_ids != expected_reviewed_sources:
                raise ValueError("VALIDATED_FOR_CAPITAL requires exact reviewed source identities")
        object.__setattr__(self, "policy_name", _text(self.policy_name, "policy_name"))
        object.__setattr__(self, "policy_version", _text(self.policy_version, "policy_version"))
        if (
            self.policy_name != DOMESTIC_MARKET_VALIDATION_POLICY_NAME
            or self.policy_version != DOMESTIC_MARKET_VALIDATION_POLICY_VERSION
        ):
            raise ValueError("unsupported domestic market validation policy")
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        object.__setattr__(self, "evaluated_at", _aware(self.evaluated_at, "evaluated_at"))
        if self.schema_version != DOMESTIC_MARKET_VALIDATION_SCHEMA_VERSION:
            raise ValueError("unsupported domestic market validation schema")

    @property
    def reason_codes(self) -> tuple[DomesticMarketValidationReasonCode, ...]:
        return tuple(item.code for item in self.blocking_reasons)


__all__ = [
    name for name in globals()
    if name.startswith("DomesticMarket") or name.startswith("DOMESTIC_MARKET")
]
