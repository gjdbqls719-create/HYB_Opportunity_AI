from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import isfinite

from app.domain.market_intelligence import (
    CompetitionAssessment,
    DemandAssessment,
    ExternalMarketSignal,
    MarketEvidenceStatus,
    MarketObservationIdentity,
    MarketObservationScope,
)
from app.domain.opportunity import ProductionSafetyAssessment, VerifiedEconomicsInput


class DecisionOutcome(StrEnum):
    INVEST = "invest"
    REVIEW = "review"
    REJECT = "reject"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class DecisionDimension(StrEnum):
    ECONOMICS = "economics"
    SAFETY = "safety"
    COMPETITION = "competition"
    DEMAND = "demand"
    EXTERNAL_REFERENCE = "external_reference"


class DecisionReasonCode(StrEnum):
    ECONOMICS_READY = "economics_ready"
    ECONOMICS_UNAVAILABLE = "economics_unavailable"
    SAFETY_READY = "safety_ready"
    SAFETY_BLOCKED = "safety_blocked"
    LOW_COMPETITION = "low_competition"
    HIGH_COMPETITION = "high_competition"
    HIGH_DEMAND = "high_demand"
    LOW_DEMAND = "low_demand"
    DEMAND_PARTIAL = "demand_partial"
    COMPETITION_UNAVAILABLE = "competition_unavailable"
    DEMAND_UNAVAILABLE = "demand_unavailable"
    MARKET_STALE = "market_stale"
    EXTERNAL_SIGNAL_AGREES = "external_signal_agrees"
    EXTERNAL_SIGNAL_DISAGREES = "external_signal_disagrees"
    EXTERNAL_SIGNAL_UNAVAILABLE = "external_signal_unavailable"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class DecisionEvidenceAvailability(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class DecisionFreshness(StrEnum):
    FRESH = "fresh"
    STALE = "stale"
    UNKNOWN = "unknown"


CORE_DECISION_DIMENSIONS = frozenset({
    DecisionDimension.ECONOMICS,
    DecisionDimension.SAFETY,
    DecisionDimension.COMPETITION,
    DecisionDimension.DEMAND,
})


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _confidence(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal")
    if not value.is_finite() or not Decimal("0") <= value <= Decimal("1"):
        raise ValueError(f"{name} must be between 0 and 1")
    return value


def _dimensions(
    values: tuple[DecisionDimension, ...],
    name: str,
) -> tuple[DecisionDimension, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{name} must be a tuple")
    if any(not isinstance(value, DecisionDimension) for value in values):
        raise TypeError(f"{name} must contain DecisionDimension values")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} cannot contain duplicates")
    return values


def _reasons(
    values: tuple[DecisionReasonCode, ...],
    name: str,
) -> tuple[DecisionReasonCode, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{name} must be a tuple")
    if any(not isinstance(value, DecisionReasonCode) for value in values):
        raise TypeError(f"{name} must contain DecisionReasonCode values")
    if len(set(values)) != len(values):
        raise ValueError(f"{name} cannot contain duplicates")
    return values


def _immutable_external_value(value: object) -> bool:
    if isinstance(value, Decimal):
        return value.is_finite()
    if isinstance(value, float):
        return isfinite(value)
    if isinstance(value, (str, int, bool)):
        return True
    if isinstance(value, tuple):
        return all(_immutable_external_value(item) for item in value)
    return False


@dataclass(frozen=True, slots=True)
class OpportunityIdentity:
    opportunity_id: str
    discovery_reference: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "opportunity_id",
            _required_text(self.opportunity_id, "opportunity_id"),
        )
        object.__setattr__(
            self,
            "discovery_reference",
            _required_text(self.discovery_reference, "discovery_reference"),
        )


@dataclass(frozen=True, slots=True)
class DecisionConfidence:
    confidence: Decimal
    availability: DecisionEvidenceAvailability
    missing_dimensions: tuple[DecisionDimension, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.availability, DecisionEvidenceAvailability):
            raise TypeError("availability must be DecisionEvidenceAvailability")
        object.__setattr__(self, "confidence", _confidence(self.confidence, "confidence"))
        object.__setattr__(
            self,
            "missing_dimensions",
            _dimensions(self.missing_dimensions, "missing_dimensions"),
        )
        missing = set(self.missing_dimensions)
        if self.availability is DecisionEvidenceAvailability.COMPLETE and missing:
            raise ValueError("complete confidence cannot have missing dimensions")
        if self.availability is DecisionEvidenceAvailability.PARTIAL:
            if not missing:
                raise ValueError("partial confidence requires missing dimensions")
            if CORE_DECISION_DIMENSIONS.issubset(missing):
                raise ValueError("partial confidence cannot miss every core dimension")
        if (
            self.availability is DecisionEvidenceAvailability.UNAVAILABLE
            and not CORE_DECISION_DIMENSIONS.issubset(missing)
        ):
            raise ValueError(
                "unavailable confidence requires every core dimension to be missing"
            )


@dataclass(frozen=True, slots=True)
class DecisionEvidenceMetadata:
    dimension: DecisionDimension
    availability: DecisionEvidenceAvailability
    freshness: DecisionFreshness

    def __post_init__(self) -> None:
        if not isinstance(self.dimension, DecisionDimension):
            raise TypeError("dimension must be DecisionDimension")
        if not isinstance(self.availability, DecisionEvidenceAvailability):
            raise TypeError("availability must be DecisionEvidenceAvailability")
        if not isinstance(self.freshness, DecisionFreshness):
            raise TypeError("freshness must be DecisionFreshness")


@dataclass(frozen=True, slots=True)
class DecisionDimensionResult:
    dimension: DecisionDimension
    availability: DecisionEvidenceAvailability
    confidence: Decimal | None
    freshness: DecisionFreshness
    assessment_reference: str | None
    reason_codes: tuple[DecisionReasonCode, ...]
    generated_at: datetime
    schema_version: str
    policy_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.dimension, DecisionDimension):
            raise TypeError("dimension must be DecisionDimension")
        if not isinstance(self.availability, DecisionEvidenceAvailability):
            raise TypeError("availability must be DecisionEvidenceAvailability")
        if not isinstance(self.freshness, DecisionFreshness):
            raise TypeError("freshness must be DecisionFreshness")
        if self.assessment_reference is not None:
            object.__setattr__(
                self,
                "assessment_reference",
                _required_text(self.assessment_reference, "assessment_reference"),
            )
        if self.availability is DecisionEvidenceAvailability.UNAVAILABLE:
            if self.confidence is not None:
                raise ValueError("unavailable dimension confidence must be None")
        elif self.confidence is None:
            raise ValueError("available dimension requires confidence")
        else:
            object.__setattr__(self, "confidence", _confidence(self.confidence, "confidence"))
        object.__setattr__(self, "reason_codes", _reasons(self.reason_codes, "reason_codes"))
        object.__setattr__(self, "generated_at", _aware(self.generated_at, "generated_at"))
        object.__setattr__(self, "schema_version", _required_text(self.schema_version, "schema_version"))
        object.__setattr__(self, "policy_version", _required_text(self.policy_version, "policy_version"))


@dataclass(frozen=True, slots=True)
class DecisionInput:
    opportunity_identity: OpportunityIdentity
    market_observation_identity: MarketObservationIdentity
    verified_economics: VerifiedEconomicsInput
    production_safety: ProductionSafetyAssessment
    competition_assessment: CompetitionAssessment | None
    demand_assessment: DemandAssessment | None
    external_signals: tuple[ExternalMarketSignal, ...]
    evidence_metadata: tuple[DecisionEvidenceMetadata, ...]
    generated_at: datetime
    schema_version: str
    policy_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.market_observation_identity, MarketObservationIdentity):
            raise TypeError(
                "market_observation_identity must be MarketObservationIdentity"
            )
        if self.market_observation_identity.scope not in {
            MarketObservationScope.LISTING,
            MarketObservationScope.CANONICAL_PRODUCT,
        }:
            raise ValueError(
                "market_observation_identity scope must be listing or canonical_product"
            )
        if not isinstance(self.verified_economics, VerifiedEconomicsInput):
            raise TypeError("verified_economics must be VerifiedEconomicsInput")
        if not isinstance(self.production_safety, ProductionSafetyAssessment):
            raise TypeError("production_safety must be ProductionSafetyAssessment")
        if self.competition_assessment is not None and not isinstance(
            self.competition_assessment, CompetitionAssessment
        ):
            raise TypeError("competition_assessment must be CompetitionAssessment or None")
        if self.demand_assessment is not None and not isinstance(
            self.demand_assessment, DemandAssessment
        ):
            raise TypeError("demand_assessment must be DemandAssessment or None")
        if not isinstance(self.external_signals, tuple):
            raise TypeError("external_signals must be a tuple")
        if any(not isinstance(value, ExternalMarketSignal) for value in self.external_signals):
            raise TypeError("external_signals must contain ExternalMarketSignal values")
        if any(
            value.evidence.status is not MarketEvidenceStatus.HUMAN_VERIFIED
            for value in self.external_signals
        ):
            raise ValueError("external_signals must be human verified")
        if any(
            not _immutable_external_value(value.evidence.value)
            for value in self.external_signals
        ):
            raise ValueError("external signal values must be immutable scalars or tuples")
        if not isinstance(self.evidence_metadata, tuple):
            raise TypeError("evidence_metadata must be a tuple")
        if any(not isinstance(value, DecisionEvidenceMetadata) for value in self.evidence_metadata):
            raise TypeError("evidence_metadata must contain DecisionEvidenceMetadata values")
        metadata_dimensions = tuple(value.dimension for value in self.evidence_metadata)
        if len(set(metadata_dimensions)) != len(metadata_dimensions):
            raise ValueError("evidence_metadata cannot contain duplicate dimensions")
        if set(metadata_dimensions) != set(DecisionDimension):
            raise ValueError("evidence_metadata must cover every decision dimension")
        metadata_by_dimension = {
            value.dimension: value for value in self.evidence_metadata
        }
        for dimension, assessment in (
            (DecisionDimension.COMPETITION, self.competition_assessment),
            (DecisionDimension.DEMAND, self.demand_assessment),
        ):
            unavailable = (
                metadata_by_dimension[dimension].availability
                is DecisionEvidenceAvailability.UNAVAILABLE
            )
            if (assessment is None) != unavailable:
                raise ValueError(
                    f"{dimension.value} availability must match its assessment"
                )
        external_unavailable = (
            metadata_by_dimension[DecisionDimension.EXTERNAL_REFERENCE].availability
            is DecisionEvidenceAvailability.UNAVAILABLE
        )
        if (not self.external_signals) != external_unavailable:
            raise ValueError(
                "external reference availability must match external_signals"
            )
        if any(
            value.identity != self.market_observation_identity
            for value in self.external_signals
        ):
            raise ValueError(
                "external signal identity must match market_observation_identity"
            )
        object.__setattr__(self, "generated_at", _aware(self.generated_at, "generated_at"))
        object.__setattr__(self, "schema_version", _required_text(self.schema_version, "schema_version"))
        object.__setattr__(self, "policy_version", _required_text(self.policy_version, "policy_version"))


@dataclass(frozen=True, slots=True)
class DecisionResult:
    opportunity_identity: OpportunityIdentity
    outcome: DecisionOutcome
    confidence: DecisionConfidence
    dimension_results: tuple[DecisionDimensionResult, ...]
    blocking_reasons: tuple[DecisionReasonCode, ...]
    supporting_reasons: tuple[DecisionReasonCode, ...]
    uncertainty_reasons: tuple[DecisionReasonCode, ...]
    generated_at: datetime
    schema_version: str
    policy_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.outcome, DecisionOutcome):
            raise TypeError("outcome must be DecisionOutcome")
        if not isinstance(self.confidence, DecisionConfidence):
            raise TypeError("confidence must be DecisionConfidence")
        if not isinstance(self.dimension_results, tuple):
            raise TypeError("dimension_results must be a tuple")
        if any(not isinstance(value, DecisionDimensionResult) for value in self.dimension_results):
            raise TypeError("dimension_results must contain DecisionDimensionResult values")
        dimensions = tuple(value.dimension for value in self.dimension_results)
        if len(set(dimensions)) != len(dimensions):
            raise ValueError("dimension_results cannot contain duplicate dimensions")
        if set(dimensions) != set(DecisionDimension):
            raise ValueError("dimension_results must cover every decision dimension")
        object.__setattr__(self, "blocking_reasons", _reasons(self.blocking_reasons, "blocking_reasons"))
        object.__setattr__(self, "supporting_reasons", _reasons(self.supporting_reasons, "supporting_reasons"))
        object.__setattr__(self, "uncertainty_reasons", _reasons(self.uncertainty_reasons, "uncertainty_reasons"))
        all_reasons = (
            self.blocking_reasons
            + self.supporting_reasons
            + self.uncertainty_reasons
        )
        if len(set(all_reasons)) != len(all_reasons):
            raise ValueError("a reason cannot belong to multiple result categories")
        object.__setattr__(self, "generated_at", _aware(self.generated_at, "generated_at"))
        object.__setattr__(self, "schema_version", _required_text(self.schema_version, "schema_version"))
        object.__setattr__(self, "policy_version", _required_text(self.policy_version, "policy_version"))
