from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.domain.decision_engine import DecisionEvidenceAvailability, DecisionFreshness
from app.domain.market_intelligence import (
    CompetitionAssessment,
    DemandAssessment,
    DemandAssessmentAvailability,
    ExternalMarketSignal,
    MarketObservationIdentity,
)


class DuplicateAssessmentSnapshotError(ValueError):
    pass


class AssessmentSnapshotProvenanceError(ValueError):
    pass


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _common(snapshot) -> None:
    if not isinstance(snapshot.identity, MarketObservationIdentity):
        raise TypeError("identity must be MarketObservationIdentity")
    for name in ("snapshot_id", "source_observation_id", "schema_version", "policy_version"):
        object.__setattr__(snapshot, name, _required(getattr(snapshot, name), name))
    if not isinstance(snapshot.availability, DecisionEvidenceAvailability):
        raise TypeError("availability must be DecisionEvidenceAvailability")
    if not isinstance(snapshot.freshness, DecisionFreshness):
        raise TypeError("freshness must be DecisionFreshness")
    if not isinstance(snapshot.confidence, Decimal):
        raise TypeError("confidence must be Decimal")
    if not snapshot.confidence.is_finite() or not Decimal("0") <= snapshot.confidence <= Decimal("1"):
        raise ValueError("confidence must be between 0 and 1")
    if not isinstance(snapshot.generated_at, datetime):
        raise TypeError("generated_at must be datetime")
    if snapshot.generated_at.tzinfo is None or snapshot.generated_at.utcoffset() is None:
        raise ValueError("generated_at must be timezone-aware")


@dataclass(frozen=True, slots=True)
class CompetitionAssessmentSnapshot:
    snapshot_id: str
    identity: MarketObservationIdentity
    source_observation_id: str
    assessment: CompetitionAssessment
    availability: DecisionEvidenceAvailability
    confidence: Decimal
    freshness: DecisionFreshness
    generated_at: datetime
    schema_version: str
    policy_version: str

    def __post_init__(self) -> None:
        _common(self)
        if not isinstance(self.assessment, CompetitionAssessment):
            raise TypeError("assessment must be CompetitionAssessment")
        if self.availability is not DecisionEvidenceAvailability.COMPLETE:
            raise ValueError("competition assessment snapshot must be complete")
        if self.confidence != self.assessment.confidence:
            raise ValueError("confidence must match competition assessment")
        if self.generated_at != self.assessment.generated_at:
            raise ValueError("generated_at must match competition assessment")


@dataclass(frozen=True, slots=True)
class DemandAssessmentSnapshot:
    snapshot_id: str
    identity: MarketObservationIdentity
    source_observation_id: str
    assessment: DemandAssessment
    availability: DecisionEvidenceAvailability
    confidence: Decimal
    freshness: DecisionFreshness
    generated_at: datetime
    schema_version: str
    policy_version: str

    def __post_init__(self) -> None:
        _common(self)
        if not isinstance(self.assessment, DemandAssessment):
            raise TypeError("assessment must be DemandAssessment")
        expected = (
            DecisionEvidenceAvailability.COMPLETE
            if self.assessment.availability is DemandAssessmentAvailability.COMPLETE
            else DecisionEvidenceAvailability.PARTIAL
        )
        if self.availability is not expected:
            raise ValueError("availability must match demand assessment")
        if self.confidence != self.assessment.confidence:
            raise ValueError("confidence must match demand assessment")
        if self.generated_at != self.assessment.generated_at:
            raise ValueError("generated_at must match demand assessment")


AssessmentSnapshot = CompetitionAssessmentSnapshot | DemandAssessmentSnapshot


class AssessmentSnapshotRepository(Protocol):
    def save_assessment_snapshot(self, observation, snapshot: AssessmentSnapshot) -> None: ...
    def get_competition_assessment_snapshot(self, snapshot_id: str) -> CompetitionAssessmentSnapshot | None: ...
    def get_demand_assessment_snapshot(self, snapshot_id: str) -> DemandAssessmentSnapshot | None: ...
    def get_latest_competition_assessment_snapshot(self, identity: MarketObservationIdentity) -> CompetitionAssessmentSnapshot | None: ...
    def get_latest_demand_assessment_snapshot(self, identity: MarketObservationIdentity) -> DemandAssessmentSnapshot | None: ...
    def get_latest_human_verified_external_signals(self, identity: MarketObservationIdentity) -> tuple[ExternalMarketSignal, ...]: ...
    def get_human_verified_external_signals_by_ids(self, identity: MarketObservationIdentity, signal_ids: tuple[str, ...]) -> tuple[ExternalMarketSignal, ...]: ...
