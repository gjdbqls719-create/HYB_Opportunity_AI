from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol
from uuid import uuid4
import sqlite3

from app.application.assessment_snapshot import AssessmentSnapshotRepository
from app.application.opportunity_market_identity import (
    GetOpportunityMarketIdentity,
    OpportunityMarketIdentityBindingNotFoundError,
    OpportunityMarketIdentityConflictError,
)
from app.domain.decision_engine import (
    DecisionDimension,
    DecisionEvidenceAvailability,
    DecisionEvidenceMetadata,
    DecisionFreshness,
    OpportunityIdentity,
)
from app.domain.market_intelligence import MarketObservationIdentity
from app.application.production_safety_evaluation import (
    MalformedProductionSafetyEvaluationPersistenceError,
    ProductionSafetyEvaluationPersistenceError,
    UnsupportedProductionSafetyEvaluationVersionError,
)


COMPOSITION_SCHEMA_VERSION = "decision-composition-v1"
METADATA_POLICY_VERSION = "decision-composition-metadata-v1"
DECISION_SCHEMA_VERSION = "decision-input-v1"
DECISION_POLICY_VERSION = "decision-policy-v1"
ASSESSMENT_SCHEMA_VERSION = "assessment-snapshot-v1"
COMPETITION_POLICY_VERSION = "competition-policy-v1"
DEMAND_POLICY_VERSION = "demand-policy-v1"
EXTERNAL_SIGNAL_SCHEMA_VERSION = "external-signal-v1"
FRESHNESS_WINDOW = timedelta(days=30)


class DecisionCompositionNotFoundError(LookupError): pass
class DuplicateDecisionCompositionError(ValueError): pass
class DecisionCompositionVersionConflictError(ValueError): pass
class DecisionCompositionError(RuntimeError): pass
class DecisionCompositionProvenanceError(DecisionCompositionError): pass
class DecisionCompositionPersistenceError(DecisionCompositionError): pass
class DecisionCompositionProjectionError(DecisionCompositionPersistenceError): pass
class DecisionCompositionCommitError(DecisionCompositionPersistenceError): pass
class MalformedDecisionCompositionError(DecisionCompositionError): pass
class UnsupportedDecisionCompositionVersionError(DecisionCompositionError): pass
class MissingDecisionCompositionSourceError(DecisionCompositionProvenanceError): pass
class DecisionCompositionIdentityConflictError(DecisionCompositionProvenanceError): pass
class DecisionCompositionOpportunityNotFoundError(DecisionCompositionNotFoundError): pass
class SelectedExternalSignalNotFoundError(DecisionCompositionNotFoundError): pass


@dataclass(frozen=True, slots=True)
class DecisionCompositionSnapshot:
    composition_id: str
    composition_version: int
    opportunity_identity: OpportunityIdentity
    market_observation_identity: MarketObservationIdentity
    verified_economics_snapshot_id: str
    production_safety_snapshot_id: str
    competition_assessment_snapshot_id: str
    demand_assessment_snapshot_id: str
    external_signal_ids: tuple[str, ...]
    evidence_metadata: tuple[DecisionEvidenceMetadata, ...]
    generated_at: datetime
    schema_version: str
    policy_version: str
    composition_schema_version: str = COMPOSITION_SCHEMA_VERSION
    metadata_policy_version: str = METADATA_POLICY_VERSION

    def __post_init__(self):
        if not isinstance(self.composition_id, str) or not self.composition_id.strip(): raise ValueError("composition_id must be non-empty")
        if isinstance(self.composition_version, bool) or self.composition_version < 1: raise ValueError("composition_version must be positive")
        if not isinstance(self.opportunity_identity, OpportunityIdentity): raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.market_observation_identity, MarketObservationIdentity): raise TypeError("market_observation_identity must be MarketObservationIdentity")
        for name in ("verified_economics_snapshot_id", "production_safety_snapshot_id", "competition_assessment_snapshot_id", "demand_assessment_snapshot_id", "schema_version", "policy_version", "composition_schema_version", "metadata_policy_version"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip(): raise ValueError(f"{name} must be non-empty")
        if not isinstance(self.external_signal_ids, tuple): raise TypeError("external_signal_ids must be tuple")
        if len(set(self.external_signal_ids)) != len(self.external_signal_ids): raise ValueError("external_signal_ids cannot duplicate")
        if not isinstance(self.evidence_metadata, tuple): raise TypeError("evidence_metadata must be tuple")
        if tuple(value.dimension for value in self.evidence_metadata) != tuple(DecisionDimension): raise ValueError("evidence_metadata must preserve dimension order")
        if not isinstance(self.generated_at, datetime) or self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None: raise ValueError("generated_at must be timezone-aware")


class DecisionCompositionRepository(Protocol):
    def finalize_decision_composition(self, snapshot: DecisionCompositionSnapshot) -> DecisionCompositionSnapshot: ...
    def get_latest_decision_composition(self, opportunity_id: str) -> DecisionCompositionSnapshot | None: ...
    def get_decision_composition(self, composition_id: str) -> DecisionCompositionSnapshot | None: ...
    def get_decision_composition_history(self, opportunity_id: str) -> tuple[DecisionCompositionSnapshot, ...]: ...


class FinalizeDecisionComposition:
    def __init__(self, *, source_repository, assessment_repository: AssessmentSnapshotRepository, composition_repository: DecisionCompositionRepository, production_safety_repository=None):
        self._sources = source_repository
        self._assessments = assessment_repository
        self._compositions = composition_repository
        self._production_safety = production_safety_repository

    def execute(self, opportunity_id: str, *, generated_at: datetime, schema_version: str, policy_version: str, external_signal_ids: tuple[str, ...] | None = None):
        self._validate_requested_versions(schema_version, policy_version)
        item = self._sources.get_queue_item(opportunity_id)
        if item is None: raise DecisionCompositionOpportunityNotFoundError("opportunity subject not found")
        opportunity = OpportunityIdentity(item.opportunity_id, item.discovery_reference)
        try:
            market_identity = GetOpportunityMarketIdentity(self._sources).execute(opportunity_id)
        except OpportunityMarketIdentityBindingNotFoundError as error:
            raise MissingDecisionCompositionSourceError("market identity binding not found") from error
        except OpportunityMarketIdentityConflictError as error:
            raise DecisionCompositionIdentityConflictError(str(error)) from error
        try:
            economics = self._sources.get_verified_economics_snapshot(opportunity_id)
            safety = (
                self._production_safety.get_current_decision_source(opportunity_id)
                if self._production_safety is not None
                else self._sources.get_production_safety_snapshot(opportunity_id)
            )
            competition = self._assessments.get_latest_competition_assessment_snapshot(market_identity)
            demand = self._assessments.get_latest_demand_assessment_snapshot(market_identity)
        except UnsupportedProductionSafetyEvaluationVersionError as error:
            raise UnsupportedDecisionCompositionVersionError(str(error)) from error
        except MalformedProductionSafetyEvaluationPersistenceError as error:
            raise MalformedDecisionCompositionError(str(error)) from error
        except ProductionSafetyEvaluationPersistenceError as error:
            raise DecisionCompositionPersistenceError(
                "operational Production Safety persistence is unavailable"
            ) from error
        except sqlite3.Error as error:
            raise DecisionCompositionPersistenceError(
                "authoritative composition persistence is unavailable"
            ) from error
        except (KeyError, TypeError, ValueError) as error:
            raise MalformedDecisionCompositionError(
                "authoritative composition source is malformed"
            ) from error
        if economics is None: raise MissingDecisionCompositionSourceError("verified economics snapshot not found")
        if safety is None: raise MissingDecisionCompositionSourceError("operational production safety evaluation not found" if self._production_safety is not None else "production safety snapshot not found")
        if competition is None: raise MissingDecisionCompositionSourceError("competition assessment snapshot not found")
        if demand is None: raise MissingDecisionCompositionSourceError("demand assessment snapshot not found")
        self._validate_source_versions(economics, safety, competition, demand)
        latest_signals = self._assessments.get_latest_human_verified_external_signals(market_identity)
        bound_signal_ids = None
        get_bound_ids = getattr(self._sources, "get_bound_review_external_signal_ids", None)
        if get_bound_ids is not None:
            bound_signal_ids = get_bound_ids(opportunity_id)
        if external_signal_ids is None:
            signals = latest_signals if bound_signal_ids is None else self._assessments.get_human_verified_external_signals_by_ids(market_identity, bound_signal_ids)
        else:
            if not isinstance(external_signal_ids, tuple):
                raise TypeError("external_signal_ids must be tuple")
            if bound_signal_ids is not None and any(value not in bound_signal_ids for value in external_signal_ids):
                raise DecisionCompositionIdentityConflictError("external signal is not bound to opportunity review")
            signals = self._assessments.get_human_verified_external_signals_by_ids(
                market_identity, external_signal_ids
            )
            if tuple(signal.signal_id for signal in signals) != external_signal_ids:
                raise SelectedExternalSignalNotFoundError("selected external signal not found")
        for signal in signals:
            if signal.schema_version != EXTERNAL_SIGNAL_SCHEMA_VERSION:
                raise UnsupportedDecisionCompositionVersionError("unsupported external signal schema version")
        metadata = self._metadata(economics, safety, competition, demand, signals, generated_at)
        latest = self._compositions.get_latest_decision_composition(opportunity_id)
        snapshot = DecisionCompositionSnapshot(
            composition_id=uuid4().hex,
            composition_version=1 if latest is None else latest.composition_version + 1,
            opportunity_identity=opportunity,
            market_observation_identity=market_identity,
            verified_economics_snapshot_id=economics.opportunity_id,
            production_safety_snapshot_id=(safety.evaluation_id if self._production_safety is not None else safety.opportunity_id),
            competition_assessment_snapshot_id=competition.snapshot_id,
            demand_assessment_snapshot_id=demand.snapshot_id,
            external_signal_ids=tuple(signal.signal_id for signal in signals),
            evidence_metadata=metadata,
            generated_at=generated_at,
            schema_version=schema_version,
            policy_version=policy_version,
        )
        return self._compositions.finalize_decision_composition(snapshot)

    @staticmethod
    def _metadata(economics, safety, competition, demand, signals, as_of):
        economics_missing = economics.inputs.readiness_missing_fields
        economics_availability = (
            DecisionEvidenceAvailability.COMPLETE
            if not economics_missing
            else DecisionEvidenceAvailability.UNAVAILABLE
            if len(economics_missing) == 6
            else DecisionEvidenceAvailability.PARTIAL
        )
        economics_times = FinalizeDecisionComposition._economics_timestamps(economics)
        external_confidence = min((signal.evidence.confidence for signal in signals), default=None)
        return (
            DecisionEvidenceMetadata(DecisionDimension.ECONOMICS, economics_availability, None, FinalizeDecisionComposition._freshness(economics_times, as_of)),
            DecisionEvidenceMetadata(DecisionDimension.SAFETY, DecisionEvidenceAvailability.COMPLETE, None, FinalizeDecisionComposition._freshness(((safety.evaluated_at if hasattr(safety, "evaluated_at") else safety.snapshot_at),), as_of)),
            DecisionEvidenceMetadata(DecisionDimension.COMPETITION, competition.availability, competition.confidence, competition.freshness),
            DecisionEvidenceMetadata(DecisionDimension.DEMAND, demand.availability, demand.confidence, demand.freshness),
            DecisionEvidenceMetadata(DecisionDimension.EXTERNAL_REFERENCE, DecisionEvidenceAvailability.COMPLETE if signals else DecisionEvidenceAvailability.UNAVAILABLE, external_confidence, FinalizeDecisionComposition._freshness(tuple(min(signal.captured_at, signal.verified_at) for signal in signals), as_of)),
        )

    @staticmethod
    def _economics_timestamps(snapshot):
        inputs = snapshot.inputs
        required = (inputs.purchase_cost, inputs.shipping_cost, inputs.expected_sale_price,
                    inputs.marketplace_fee_rate, inputs.payment_fee_rate, inputs.fixed_fee)
        return tuple(value.evidence.observed_at for value in required)

    @staticmethod
    def _freshness(timestamps, as_of):
        if not timestamps:
            return DecisionFreshness.UNKNOWN
        if any(value is None for value in timestamps):
            return DecisionFreshness.UNKNOWN
        return (DecisionFreshness.FRESH if all(as_of - value <= FRESHNESS_WINDOW for value in timestamps)
                else DecisionFreshness.STALE)

    @staticmethod
    def _validate_requested_versions(schema_version, policy_version):
        if schema_version != DECISION_SCHEMA_VERSION:
            raise UnsupportedDecisionCompositionVersionError("unsupported decision schema version")
        if policy_version != DECISION_POLICY_VERSION:
            raise UnsupportedDecisionCompositionVersionError("unsupported decision policy version")

    @staticmethod
    def _validate_source_versions(economics, safety, competition, demand):
        from app.application.verified_economics_snapshot import VERIFIED_ECONOMICS_SNAPSHOT_SCHEMA_VERSION
        from app.application.production_safety_snapshot import PRODUCTION_SAFETY_SNAPSHOT_SCHEMA_VERSION
        from app.application.production_safety_evaluation import PRODUCTION_SAFETY_EVALUATION_SCHEMA_VERSION
        safety_schema = (
            safety.evaluation_schema_version
            if hasattr(safety, "evaluation_schema_version")
            else safety.schema_version
        )
        expected_safety_schema = (
            PRODUCTION_SAFETY_EVALUATION_SCHEMA_VERSION
            if hasattr(safety, "evaluation_id")
            else PRODUCTION_SAFETY_SNAPSHOT_SCHEMA_VERSION
        )
        supported = (
            (economics.schema_version, VERIFIED_ECONOMICS_SNAPSHOT_SCHEMA_VERSION, "economics schema"),
            (safety_schema, expected_safety_schema, "safety schema"),
            (safety.rule_version, "production-safety-v1", "safety rule"),
            (competition.schema_version, ASSESSMENT_SCHEMA_VERSION, "competition schema"),
            (competition.policy_version, COMPETITION_POLICY_VERSION, "competition policy"),
            (demand.schema_version, ASSESSMENT_SCHEMA_VERSION, "demand schema"),
            (demand.policy_version, DEMAND_POLICY_VERSION, "demand policy"),
        )
        for actual, expected, name in supported:
            if actual != expected:
                raise UnsupportedDecisionCompositionVersionError(f"unsupported {name} version")


class GetLatestDecisionComposition:
    def __init__(self, repository): self._repository = repository
    def execute(self, opportunity_id):
        value = self._repository.get_latest_decision_composition(opportunity_id)
        if value is None: raise DecisionCompositionNotFoundError("finalized decision composition not found")
        return value

class GetDecisionComposition:
    def __init__(self, repository): self._repository = repository
    def execute(self, composition_id):
        value = self._repository.get_decision_composition(composition_id)
        if value is None: raise DecisionCompositionNotFoundError("decision composition not found")
        return value

class GetDecisionCompositionHistory:
    def __init__(self, repository): self._repository = repository
    def execute(self, opportunity_id): return self._repository.get_decision_composition_history(opportunity_id)
