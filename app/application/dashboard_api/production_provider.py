from __future__ import annotations

import sqlite3
from typing import Protocol

from app.application.dashboard_api.query import (
    DashboardCompositionUnavailableError,
    DashboardIdentityConflictError,
    DashboardOpportunityNotFoundError,
    OpportunityDecisionDashboardSource,
)
from app.application.opportunity_validation import ValidationQueueItem
from app.domain.decision_engine import OpportunityIdentity
from app.application.opportunity_market_identity import (
    GetOpportunityMarketIdentity,
    MalformedOpportunityMarketIdentityBindingError,
    OpportunityMarketIdentityBindingNotFoundError,
    OpportunityMarketIdentityConflictError,
    OpportunityMarketIdentityRepository,
)
from app.application.verified_economics_snapshot import (
    GetVerifiedEconomicsSnapshot,
    MalformedVerifiedEconomicsSnapshotError,
    VerifiedEconomicsSnapshotIdentityConflictError,
    VerifiedEconomicsSnapshotNotFoundError,
    VerifiedEconomicsSnapshotRepository,
)
from app.application.production_safety_snapshot import (
    GetProductionSafetySnapshot,
    MalformedProductionSafetySnapshotError,
    ProductionSafetySnapshotIdentityConflictError,
    ProductionSafetySnapshotNotFoundError,
    ProductionSafetySnapshotRepository,
)
from app.application.production_safety_evaluation import ProductionSafetyEvaluationPersistenceError
from app.application.assessment_snapshot import AssessmentSnapshotRepository
from app.application.decision_composition import (
    DecisionCompositionError,
    DecisionCompositionIdentityConflictError,
    DecisionCompositionNotFoundError,
    GetLatestDecisionComposition,
)
from app.application.decision_engine import DecisionExplanationService, DecisionMatrix
from app.application.dashboard import DashboardReadModelAssembler
from app.domain.decision_engine import DecisionInput


MISSING_MARKET_IDENTITY_LINK = (
    "persisted opportunity has no explicit MarketObservationIdentity link"
)
MISSING_VERIFIED_ECONOMICS = (
    "persisted opportunity has no authoritative VerifiedEconomicsInput source"
)
MISSING_PRODUCTION_SAFETY = (
    "persisted opportunity has no authoritative ProductionSafetyAssessment source"
)
MISSING_MARKET_EVIDENCE_COMPOSITION = (
    "production dashboard composition has no connected Competition and Demand evidence sources"
)


class ValidationQueueItemReader(Protocol):
    def get_queue_item(self, opportunity_id: str) -> ValidationQueueItem | None:
        ...


class ProductionOpportunityDecisionDashboardProvider:
    """Resolve authoritative persisted identity before Decision composition.

    The current admission/lifecycle schema does not preserve the explicit
    MarketObservationIdentity required by DecisionInput. Composition stops at
    that boundary instead of deriving an identity from display fields or a
    discovery-reference string.
    """

    def __init__(
        self,
        validation_repository: ValidationQueueItemReader,
        market_identity_repository: OpportunityMarketIdentityRepository | None = None,
        verified_economics_repository: VerifiedEconomicsSnapshotRepository | None = None,
        production_safety_repository: ProductionSafetySnapshotRepository | None = None,
        assessment_repository: AssessmentSnapshotRepository | None = None,
        composition_repository=None,
    ) -> None:
        self._validation_repository = validation_repository
        self._market_identity_repository = (
            market_identity_repository or validation_repository
        )
        self._verified_economics_repository = (
            verified_economics_repository or validation_repository
        )
        self._production_safety_repository = (
            production_safety_repository or validation_repository
        )
        self._assessment_repository = assessment_repository
        self._composition_repository = composition_repository or validation_repository

    def get(self, opportunity_id: str) -> OpportunityDecisionDashboardSource:
        try:
            item = self._validation_repository.get_queue_item(opportunity_id)
        except sqlite3.Error as error:
            raise DashboardCompositionUnavailableError(
                "validation persistence is unavailable"
            ) from error
        if item is None:
            raise DashboardOpportunityNotFoundError(
                "dashboard opportunity not found"
            )
        if item.opportunity_id != opportunity_id:
            raise DashboardIdentityConflictError(
                "persisted opportunity identity does not match request"
            )

        opportunity_identity = OpportunityIdentity(
            opportunity_id=item.opportunity_id,
            discovery_reference=item.discovery_reference,
        )
        try:
            composition = GetLatestDecisionComposition(
                self._composition_repository
            ).execute(opportunity_id)
        except DecisionCompositionNotFoundError as error:
            raise DashboardCompositionUnavailableError(
                "finalized decision composition not found"
            ) from error
        except DecisionCompositionIdentityConflictError as error:
            raise DashboardIdentityConflictError(str(error)) from error
        except DecisionCompositionError as error:
            raise DashboardCompositionUnavailableError(str(error)) from error
        if composition.opportunity_identity != opportunity_identity:
            raise DashboardIdentityConflictError("composition opportunity identity mismatch")
        try:
            economics = self._verified_economics_repository.get_verified_economics_snapshot(
                composition.verified_economics_snapshot_id
            )
            operational_get = getattr(self._production_safety_repository, "get_decision_source", None)
            safety = (
                operational_get(composition.production_safety_snapshot_id)
                if operational_get is not None
                else self._production_safety_repository.get_production_safety_snapshot(
                    composition.production_safety_snapshot_id
                )
            )
        except (MalformedVerifiedEconomicsSnapshotError, MalformedProductionSafetySnapshotError, ProductionSafetyEvaluationPersistenceError) as error:
            raise DashboardCompositionUnavailableError(
                "finalized composition source is malformed"
            ) from error
        if economics is None or safety is None or self._assessment_repository is None:
            raise DashboardCompositionUnavailableError("finalized composition source missing")
        try:
            competition = self._assessment_repository.get_competition_assessment_snapshot(
                composition.competition_assessment_snapshot_id
            )
            demand = self._assessment_repository.get_demand_assessment_snapshot(
                composition.demand_assessment_snapshot_id
            )
            selected = self._assessment_repository.get_human_verified_external_signals_by_ids(
                composition.market_observation_identity,
                composition.external_signal_ids,
            )
        except (KeyError, TypeError, ValueError) as error:
            raise DashboardCompositionUnavailableError(
                "finalized composition source is malformed"
            ) from error
        if competition is None or competition.snapshot_id != composition.competition_assessment_snapshot_id:
            raise DashboardCompositionUnavailableError("competition composition source mismatch")
        if demand is None or demand.snapshot_id != composition.demand_assessment_snapshot_id:
            raise DashboardCompositionUnavailableError("demand composition source mismatch")
        if tuple(signal.signal_id for signal in selected) != composition.external_signal_ids:
            raise DashboardCompositionUnavailableError("external composition source mismatch")
        decision_input = DecisionInput(
            opportunity_identity=opportunity_identity,
            market_observation_identity=composition.market_observation_identity,
            verified_economics=economics.inputs,
            production_safety=safety.assessment,
            competition_assessment=competition.assessment,
            demand_assessment=demand.assessment,
            external_signals=selected,
            evidence_metadata=composition.evidence_metadata,
            generated_at=composition.generated_at,
            schema_version=composition.schema_version,
            policy_version=composition.policy_version,
        )
        result = DecisionMatrix().evaluate(decision_input)
        explanation = DecisionExplanationService().explain(result)
        read_model = DashboardReadModelAssembler().assemble(result, explanation)
        return OpportunityDecisionDashboardSource(opportunity_identity, read_model)
