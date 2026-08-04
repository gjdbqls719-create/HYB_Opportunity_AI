from dataclasses import replace
from datetime import timedelta
from contextlib import closing

import pytest

from app.application.dashboard_api import ProductionOpportunityDecisionDashboardProvider
from app.application.assessment_snapshot import CompetitionAssessmentSnapshot, DemandAssessmentSnapshot
from app.application.decision_composition import (
    DecisionCompositionVersionConflictError,
    FinalizeDecisionComposition,
    MissingDecisionCompositionSourceError,
)
from app.infrastructure.market_observation import SQLiteMarketObservationRepository
from app.infrastructure.production_safety_evaluation import SQLiteProductionSafetyEvaluationRepository
from app.infrastructure.snapshot_chain import SQLiteSnapshotChainBindingRepository
from app.domain.decision_engine import DecisionEvidenceAvailability, DecisionFreshness
from app.domain.market_intelligence import analyze_competition, analyze_demand
from test_competition_intelligence import observation as competition_observation
from test_demand_intelligence import observation as demand_observation
from test_production_safety_evaluation_persistence import command as safety_command, service as safety_service
from test_snapshot_chain_binding_persistence import BOUND, boundary as chain_boundary, command as chain_command, prepare


def seed(path):
    prepare(path)
    with SQLiteSnapshotChainBindingRepository(path) as chains:
        chain_boundary(chains).execute(chain_command())
    with SQLiteProductionSafetyEvaluationRepository(path) as safety:
        safety_service(safety).execute(safety_command())
        identity = safety._chains.get_binding("chain-binding-1").market_observation_identity
    with closing(SQLiteMarketObservationRepository(path)) as market:
        add_assessments(market, identity, "operational")


def _observation(value, identity, observation_id):
    evidence = {
        name: replace(item, market=identity.market, marketplace=identity.marketplace)
        for name, item in value.evidence.items()
    }
    return replace(value, identity=identity, observation_id=observation_id, observed_at=BOUND, evidence=evidence)


def add_assessments(market, identity, suffix):
    competition_observed = _observation(competition_observation(), identity, f"competition-observation-{suffix}")
    competition = analyze_competition(competition_observed, generated_at=BOUND)
    market.save_assessment_snapshot(competition_observed, CompetitionAssessmentSnapshot(
        f"competition-snapshot-{suffix}", identity, competition_observed.observation_id,
        competition, DecisionEvidenceAvailability.COMPLETE, competition.confidence,
        DecisionFreshness.FRESH, BOUND, "assessment-snapshot-v1", "competition-policy-v1",
    ))
    demand_observed = _observation(demand_observation(), identity, f"demand-observation-{suffix}")
    demand = analyze_demand(demand_observed, generated_at=BOUND)
    market.save_assessment_snapshot(demand_observed, DemandAssessmentSnapshot(
        f"demand-snapshot-{suffix}", identity, demand_observed.observation_id,
        demand, DecisionEvidenceAvailability.COMPLETE, demand.confidence,
        DecisionFreshness.FRESH, BOUND, "assessment-snapshot-v1", "demand-policy-v1",
    ))


def finalizer(safety, market, compositions=None):
    sources = safety._chains._owners._sources
    return FinalizeDecisionComposition(
        source_repository=sources,
        assessment_repository=market,
        composition_repository=compositions or sources,
        production_safety_repository=safety,
    )


def test_operational_current_is_exact_finalization_and_dashboard_source(tmp_path):
    path = tmp_path / "decision.db"
    seed(path)
    with SQLiteProductionSafetyEvaluationRepository(path) as safety, closing(SQLiteMarketObservationRepository(path)) as market:
        sources = safety._chains._owners._sources
        result = finalizer(safety, market).execute(
            "opportunity-1", generated_at=BOUND + timedelta(minutes=3),
            schema_version="decision-input-v1", policy_version="decision-policy-v1",
        )
        assert result.production_safety_snapshot_id == "safety-evaluation-1"
        assert safety.get_decision_source(result.production_safety_snapshot_id).assessment == safety.get_current_production_safety_evaluation("opportunity-1").assessment
        dashboard = ProductionOpportunityDecisionDashboardProvider(
            sources,
            production_safety_repository=safety,
            assessment_repository=market,
            composition_repository=sources,
        ).get("opportunity-1")
        assert dashboard.opportunity_identity.opportunity_id == "opportunity-1"


def test_missing_operational_current_does_not_fall_back_to_legacy(tmp_path):
    path = tmp_path / "missing.db"
    prepare(path)
    with SQLiteSnapshotChainBindingRepository(path) as chains:
        chain_boundary(chains).execute(chain_command())
    with SQLiteProductionSafetyEvaluationRepository(path) as safety, closing(SQLiteMarketObservationRepository(path)) as market:
        identity = safety._chains.get_binding("chain-binding-1").market_observation_identity
        add_assessments(market, identity, "missing")
        with pytest.raises(MissingDecisionCompositionSourceError, match="operational"):
            finalizer(safety, market).execute(
                "opportunity-1", generated_at=BOUND + timedelta(minutes=3),
                schema_version="decision-input-v1", policy_version="decision-policy-v1",
            )


def test_safety_current_change_changes_composition_provenance(tmp_path):
    path = tmp_path / "versions.db"
    seed(path)
    with SQLiteProductionSafetyEvaluationRepository(path) as safety, closing(SQLiteMarketObservationRepository(path)) as market:
        sources = safety._chains._owners._sources
        first = finalizer(safety, market).execute(
            "opportunity-1", generated_at=BOUND + timedelta(minutes=3),
            schema_version="decision-input-v1", policy_version="decision-policy-v1",
        )
        safety_service(safety, evaluation_id="safety-evaluation-2").execute(
            replace(safety_command(), command_id="safety-command-2", selected_product_snapshot_id="product-2")
        )
        second = finalizer(safety, market).execute(
            "opportunity-1", generated_at=BOUND + timedelta(minutes=4),
            schema_version="decision-input-v1", policy_version="decision-policy-v1",
        )
        assert first.production_safety_snapshot_id == "safety-evaluation-1"
        assert second.production_safety_snapshot_id == "safety-evaluation-2"
        assert second.composition_version == 2
        assert len(sources.get_decision_composition_history("opportunity-1")) == 2


def test_finalization_rejects_stale_safety_current_inside_transaction(tmp_path):
    path = tmp_path / "stale.db"
    seed(path)
    with SQLiteProductionSafetyEvaluationRepository(path) as safety, closing(SQLiteMarketObservationRepository(path)) as market:
        sources = safety._chains._owners._sources
        class ChangeCurrentBeforeCommit:
            def get_latest_decision_composition(self, opportunity_id):
                return sources.get_latest_decision_composition(opportunity_id)
            def finalize_decision_composition(self, snapshot):
                safety_service(safety, evaluation_id="safety-evaluation-2").execute(
                    replace(safety_command(), command_id="safety-command-2", selected_product_snapshot_id="product-2")
                )
                return sources.finalize_decision_composition(snapshot)
        with pytest.raises(DecisionCompositionVersionConflictError, match="stale"):
            finalizer(safety, market, ChangeCurrentBeforeCommit()).execute(
                "opportunity-1", generated_at=BOUND + timedelta(minutes=3),
                schema_version="decision-input-v1", policy_version="decision-policy-v1",
            )
        assert sources.get_decision_composition_history("opportunity-1") == ()
