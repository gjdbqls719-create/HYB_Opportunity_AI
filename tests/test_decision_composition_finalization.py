from dataclasses import replace
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.application.assessment_snapshot import CompetitionAssessmentSnapshot, DemandAssessmentSnapshot
from app.application.dashboard_api import ProductionOpportunityDecisionDashboardProvider
from app.application.decision_composition import (
    DecisionCompositionProjectionError,
    DecisionCompositionCommitError,
    DecisionCompositionPersistenceError,
    DecisionCompositionProvenanceError,
    DecisionCompositionVersionConflictError,
    DuplicateDecisionCompositionError,
    FinalizeDecisionComposition,
    GetDecisionCompositionHistory,
    GetLatestDecisionComposition,
    MalformedDecisionCompositionError,
    UnsupportedDecisionCompositionVersionError,
)
from app.domain.decision_engine import DecisionEvidenceAvailability, DecisionFreshness, DecisionOutcome
from app.domain.market_intelligence import CompetitionLevel, DemandLevel, MarketEvidenceStatus, MarketObservationScope, analyze_competition, analyze_demand
from app.domain.opportunity import EvidenceStatus, ProductionSafetyAssessment, ProductionSafetyStatus
from app.infrastructure.market_observation import SQLiteMarketObservationRepository
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from app.web import app, get_opportunity_decision_dashboard_provider
from test_competition_intelligence import NOW, observation as competition_observation
from test_demand_intelligence import observation as demand_observation
from test_production_safety_snapshot_binding import safety_command
from test_opportunity_market_identity_binding import service
from test_market_observation_repository import external


def repositories():
    connection = sqlite3.connect(":memory:", check_same_thread=False)
    validation = SQLiteValidationQueueRepository(connection=connection)
    market = SQLiteMarketObservationRepository(connection=connection)
    return validation, market


def listing_identity():
    base = competition_observation().identity
    return replace(
        base,
        scope=MarketObservationScope.LISTING,
        marketplace_item_id="item-1",
        normalized_query=None,
    )


def seed_required_sources(
    validation, market, *, economics_input=None, safety_assessment=None,
    competition_level=None, demand_level=None,
):
    identity = listing_identity()
    admission = replace(safety_command(), market_observation_identity=identity)
    if economics_input is not None:
        admission = replace(admission, verified_economics=economics_input)
    if safety_assessment is not None:
        admission = replace(admission, production_safety=safety_assessment)
    service(validation).add(
        admission
    )
    competition_observation_value = replace(
        competition_observation(), identity=identity
    )
    competition_assessment = analyze_competition(
        competition_observation_value, generated_at=NOW
    )
    if competition_level is not None:
        competition_assessment = replace(
            competition_assessment, competition_level=competition_level
        )
    competition_snapshot = CompetitionAssessmentSnapshot(
        "competition-snapshot-1", identity,
        competition_observation_value.observation_id, competition_assessment,
        DecisionEvidenceAvailability.COMPLETE, competition_assessment.confidence,
        DecisionFreshness.FRESH, NOW, "assessment-snapshot-v1", "competition-policy-v1",
    )
    market.save_assessment_snapshot(
        competition_observation_value, competition_snapshot
    )
    demand_observation_value = replace(demand_observation(), identity=identity)
    demand_assessment = analyze_demand(demand_observation_value, generated_at=NOW)
    if demand_level is not None:
        demand_assessment = replace(demand_assessment, demand_level=demand_level)
    demand_snapshot = DemandAssessmentSnapshot(
        "demand-snapshot-1", identity, demand_observation_value.observation_id,
        demand_assessment, DecisionEvidenceAvailability.COMPLETE,
        demand_assessment.confidence, DecisionFreshness.STALE, NOW,
        "assessment-snapshot-v1", "demand-policy-v1",
    )
    market.save_assessment_snapshot(demand_observation_value, demand_snapshot)
    return identity


def unavailable_economics():
    value = safety_command().verified_economics
    def money(item):
        return replace(item, amount=None, evidence=replace(item.evidence, status=EvidenceStatus.MISSING))
    def rate(item):
        return replace(item, rate=None, evidence=replace(item.evidence, status=EvidenceStatus.MISSING))
    return replace(
        value,
        purchase_cost=money(value.purchase_cost),
        shipping_cost=money(value.shipping_cost),
        expected_sale_price=money(value.expected_sale_price),
        marketplace_fee_rate=rate(value.marketplace_fee_rate),
        payment_fee_rate=rate(value.payment_fee_rate),
        fixed_fee=money(value.fixed_fee),
    )


def add_competition_snapshot(market, identity, suffix, generated_at):
    observation = replace(
        competition_observation(), identity=identity,
        observation_id=f"competition-observation-{suffix}", observed_at=generated_at,
    )
    assessment = analyze_competition(observation, generated_at=generated_at)
    snapshot = CompetitionAssessmentSnapshot(
        f"competition-snapshot-{suffix}", identity, observation.observation_id,
        assessment, DecisionEvidenceAvailability.COMPLETE, assessment.confidence,
        DecisionFreshness.FRESH, generated_at, "assessment-snapshot-v1",
        "competition-policy-v1",
    )
    market.save_assessment_snapshot(observation, snapshot)
    return snapshot


def add_demand_snapshot(market, identity, suffix, generated_at):
    observation = replace(
        demand_observation(), identity=identity,
        observation_id=f"demand-observation-{suffix}", observed_at=generated_at,
    )
    assessment = analyze_demand(observation, generated_at=generated_at)
    snapshot = DemandAssessmentSnapshot(
        f"demand-snapshot-{suffix}", identity, observation.observation_id,
        assessment, DecisionEvidenceAvailability.COMPLETE, assessment.confidence,
        DecisionFreshness.FRESH, generated_at, "assessment-snapshot-v1",
        "demand-policy-v1",
    )
    market.save_assessment_snapshot(observation, snapshot)
    return snapshot


def finalizer(validation, market):
    return FinalizeDecisionComposition(
        source_repository=validation,
        assessment_repository=market,
        composition_repository=validation,
    )


def persisted_state(connection):
    tables = tuple(
        row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    )
    return {
        table: tuple(tuple(row) for row in connection.execute(f'SELECT * FROM "{table}"').fetchall())
        for table in tables
    }


def test_finalize_all_required_sources_without_external_signal() -> None:
    validation, market = repositories()
    seed_required_sources(validation, market)

    result = finalizer(validation, market).execute(
        "opp-bound", generated_at=NOW, schema_version="decision-input-v1",
        policy_version="decision-policy-v1",
    )

    assert result.composition_version == 1
    assert result.external_signal_ids == ()
    external = result.evidence_metadata[-1]
    assert external.availability is DecisionEvidenceAvailability.UNAVAILABLE
    assert external.confidence is None
    assert external.freshness is DecisionFreshness.UNKNOWN
    assert GetLatestDecisionComposition(validation).execute("opp-bound") == result
    validation.close(); market.close()


def test_identical_provenance_is_rejected_and_history_is_immutable() -> None:
    validation, market = repositories(); seed_required_sources(validation, market)
    finalize = finalizer(validation, market)
    first = finalize.execute("opp-bound", generated_at=NOW, schema_version="decision-input-v1", policy_version="decision-policy-v1")

    with pytest.raises(DuplicateDecisionCompositionError):
        finalize.execute("opp-bound", generated_at=NOW + timedelta(minutes=1), schema_version="decision-input-v1", policy_version="decision-policy-v1")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        validation._connection.execute("UPDATE decision_composition_history SET payload_json='{}'")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        validation._connection.execute("DELETE FROM decision_composition_history")
    assert GetDecisionCompositionHistory(validation).execute("opp-bound") == (first,)
    validation.close(); market.close()


def test_finalization_failure_rolls_back_only_composition() -> None:
    validation, market = repositories(); seed_required_sources(validation, market)
    admission_before = validation._connection.execute("SELECT COUNT(*) FROM opportunity_lifecycles").fetchone()[0]
    assessment_before = validation._connection.execute("SELECT COUNT(*) FROM market_assessment_snapshot_history").fetchone()[0]
    validation._connection.execute("""CREATE TRIGGER fail_composition BEFORE INSERT ON decision_composition_history
    BEGIN SELECT RAISE(ABORT, 'composition failure'); END""")

    with pytest.raises(DecisionCompositionPersistenceError):
        finalizer(validation, market).execute("opp-bound", generated_at=NOW, schema_version="decision-input-v1", policy_version="decision-policy-v1")

    assert validation._connection.execute("SELECT COUNT(*) FROM decision_composition_history").fetchone()[0] == 0
    assert validation._connection.execute("SELECT COUNT(*) FROM decision_composition_current").fetchone()[0] == 0
    assert validation._connection.execute("SELECT COUNT(*) FROM opportunity_lifecycles").fetchone()[0] == admission_before
    assert validation._connection.execute("SELECT COUNT(*) FROM market_assessment_snapshot_history").fetchone()[0] == assessment_before
    validation.close(); market.close()


def test_missing_required_source_rejected_without_history() -> None:
    validation, market = repositories()
    service(validation).add(safety_command())
    with pytest.raises(DecisionCompositionProvenanceError, match="competition"):
        finalizer(validation, market).execute("opp-bound", generated_at=NOW, schema_version="decision-input-v1", policy_version="decision-policy-v1")
    assert validation.get_decision_composition_history("opp-bound") == ()
    validation.close(); market.close()


def test_dashboard_uses_finalized_composition_and_does_not_write() -> None:
    validation, market = repositories(); seed_required_sources(validation, market)
    finalizer(validation, market).execute("opp-bound", generated_at=NOW, schema_version="decision-input-v1", policy_version="decision-policy-v1")
    before = persisted_state(validation._connection)
    provider = ProductionOpportunityDecisionDashboardProvider(validation, assessment_repository=market)
    app.dependency_overrides[get_opportunity_decision_dashboard_provider] = lambda: provider
    try:
        client = TestClient(app)
        response = client.get("/api/v1/opportunities/opp-bound/decision-dashboard")
        repeated = client.get("/api/v1/opportunities/opp-bound/decision-dashboard")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert repeated.status_code == 200
    assert repeated.json() == response.json()
    assert set(response.json()) == {"summary", "action", "warnings", "evidence", "metadata"}
    assert persisted_state(validation._connection) == before
    validation.close(); market.close()


def test_metadata_uses_unknown_confidence_and_source_age() -> None:
    validation, market = repositories(); seed_required_sources(validation, market)
    result = finalizer(validation, market).execute(
        "opp-bound", generated_at=NOW + timedelta(days=31),
        schema_version="decision-input-v1", policy_version="decision-policy-v1",
    )
    economics, safety = result.evidence_metadata[:2]
    assert economics.confidence is None
    assert economics.freshness in {DecisionFreshness.STALE, DecisionFreshness.UNKNOWN}
    assert safety.confidence is None
    assert safety.freshness is DecisionFreshness.STALE
    validation.close(); market.close()


def test_external_selection_changes_create_new_version_and_can_omit_prior_signal() -> None:
    validation, market = repositories(); identity = seed_required_sources(validation, market)
    first_signal = replace(
        external(), identity=identity, signal_id="signal-selected-1",
        candidate_id="candidate-selected-1", verification_id="verification-selected-1",
        signal_name="RATING", captured_at=NOW, verified_at=NOW,
        operator_id="operator-1",
        evidence=replace(external().evidence, status=MarketEvidenceStatus.HUMAN_VERIFIED),
    )
    second_signal = replace(
        external(), identity=identity, signal_id="signal-selected-2",
        candidate_id="candidate-selected-2", verification_id="verification-selected-2",
        signal_name="REVIEW_COUNT", captured_at=NOW - timedelta(days=31),
        verified_at=NOW - timedelta(days=31),
        operator_id="operator-1",
        evidence=replace(external().evidence, confidence=external().evidence.confidence / 2,
                         status=MarketEvidenceStatus.HUMAN_VERIFIED),
    )
    market.save(first_signal); market.save(second_signal)
    finalize = finalizer(validation, market)
    first = finalize.execute(
        "opp-bound", generated_at=NOW, schema_version="decision-input-v1",
        policy_version="decision-policy-v1", external_signal_ids=(first_signal.signal_id,),
    )
    second = finalize.execute(
        "opp-bound", generated_at=NOW + timedelta(minutes=1),
        schema_version="decision-input-v1", policy_version="decision-policy-v1",
        external_signal_ids=(first_signal.signal_id, second_signal.signal_id),
    )
    third = finalize.execute(
        "opp-bound", generated_at=NOW + timedelta(minutes=2),
        schema_version="decision-input-v1", policy_version="decision-policy-v1",
        external_signal_ids=(second_signal.signal_id,),
    )
    external_metadata = second.evidence_metadata[-1]
    assert first.composition_version == 1
    assert second.composition_version == 2
    assert third.composition_version == 3
    assert first.evidence_metadata[-1].freshness is DecisionFreshness.FRESH
    assert second.external_signal_ids == (first_signal.signal_id, second_signal.signal_id)
    assert third.external_signal_ids == (second_signal.signal_id,)
    assert first_signal.signal_id not in third.external_signal_ids
    assert external_metadata.confidence == second_signal.evidence.confidence
    assert external_metadata.freshness is DecisionFreshness.STALE
    assert GetDecisionCompositionHistory(validation).execute("opp-bound") == (third, second, first)
    validation.close(); market.close()


def test_changed_assessment_provenance_advances_versions_and_round_trips_exact_ids() -> None:
    validation, market = repositories(); identity = seed_required_sources(validation, market)
    finalize = finalizer(validation, market)
    first = finalize.execute(
        "opp-bound", generated_at=NOW, schema_version="decision-input-v1",
        policy_version="decision-policy-v1",
    )
    competition = add_competition_snapshot(
        market, identity, "2", NOW + timedelta(hours=1)
    )
    second = finalize.execute(
        "opp-bound", generated_at=NOW + timedelta(hours=1),
        schema_version="decision-input-v1", policy_version="decision-policy-v1",
    )
    demand = add_demand_snapshot(market, identity, "2", NOW + timedelta(hours=2))
    third = finalize.execute(
        "opp-bound", generated_at=NOW + timedelta(hours=2),
        schema_version="decision-input-v1", policy_version="decision-policy-v1",
    )
    assert (first.composition_version, second.composition_version, third.composition_version) == (1, 2, 3)
    assert second.competition_assessment_snapshot_id == competition.snapshot_id
    assert third.demand_assessment_snapshot_id == demand.snapshot_id
    assert GetLatestDecisionComposition(validation).execute("opp-bound") == third
    assert GetDecisionCompositionHistory(validation).execute("opp-bound") == (third, second, first)
    validation.close(); market.close()


def test_unsupported_decision_versions_are_rejected() -> None:
    validation, market = repositories(); seed_required_sources(validation, market)
    with pytest.raises(UnsupportedDecisionCompositionVersionError):
        finalizer(validation, market).execute(
            "opp-bound", generated_at=NOW, schema_version="unsupported",
            policy_version="decision-policy-v1",
        )
    with pytest.raises(UnsupportedDecisionCompositionVersionError):
        finalizer(validation, market).execute(
            "opp-bound", generated_at=NOW, schema_version="decision-input-v1",
            policy_version="unsupported",
        )
    validation.close(); market.close()


def test_malformed_composition_payload_is_deterministic() -> None:
    validation, market = repositories(); seed_required_sources(validation, market)
    finalizer(validation, market).execute(
        "opp-bound", generated_at=NOW, schema_version="decision-input-v1",
        policy_version="decision-policy-v1",
    )
    validation._connection.execute(
        "UPDATE decision_composition_current SET payload_json='not-json'"
    )
    validation._connection.commit()
    with pytest.raises(MalformedDecisionCompositionError):
        GetLatestDecisionComposition(validation).execute("opp-bound")
    validation.close(); market.close()


def test_projection_failure_rolls_back_new_history_and_keeps_prior_current() -> None:
    validation, market = repositories(); identity = seed_required_sources(validation, market)
    finalize = finalizer(validation, market)
    first = finalize.execute(
        "opp-bound", generated_at=NOW, schema_version="decision-input-v1",
        policy_version="decision-policy-v1",
    )
    signal = replace(
        external(), identity=identity, signal_id="signal-projection-failure",
        candidate_id="candidate-projection-failure",
        verification_id="verification-projection-failure", signal_name="RATING",
        operator_id="operator-1", verified_at=NOW,
        evidence=replace(external().evidence, status=MarketEvidenceStatus.HUMAN_VERIFIED),
    )
    market.save(signal)
    validation._connection.execute(
        """CREATE TRIGGER fail_composition_projection BEFORE UPDATE ON decision_composition_current
        BEGIN SELECT RAISE(ABORT, 'projection failure'); END"""
    )
    with pytest.raises(DecisionCompositionProjectionError):
        finalize.execute(
            "opp-bound", generated_at=NOW + timedelta(minutes=1),
            schema_version="decision-input-v1", policy_version="decision-policy-v1",
        )
    assert GetLatestDecisionComposition(validation).execute("opp-bound") == first
    assert GetDecisionCompositionHistory(validation).execute("opp-bound") == (first,)
    validation.close(); market.close()


@pytest.mark.parametrize(
    ("expected", "safety", "competition_level", "demand_level", "economics"),
    (
        (DecisionOutcome.INVEST, ProductionSafetyAssessment(ProductionSafetyStatus.READY), CompetitionLevel.LOW, DemandLevel.HIGH, None),
        (DecisionOutcome.REVIEW, ProductionSafetyAssessment(ProductionSafetyStatus.READY), CompetitionLevel.HIGH, DemandLevel.LOW, None),
        (DecisionOutcome.REJECT, ProductionSafetyAssessment(ProductionSafetyStatus.PROFITABILITY_FAILED, failed_checks=("margin",)), CompetitionLevel.LOW, DemandLevel.HIGH, None),
        (DecisionOutcome.INSUFFICIENT_EVIDENCE, ProductionSafetyAssessment(ProductionSafetyStatus.READY), CompetitionLevel.LOW, DemandLevel.HIGH, unavailable_economics()),
    ),
)
def test_persisted_production_outcome_matrix_returns_http_200(
    expected, safety, competition_level, demand_level, economics,
) -> None:
    validation, market = repositories()
    seed_required_sources(
        validation, market, economics_input=economics,
        safety_assessment=safety, competition_level=competition_level,
        demand_level=demand_level,
    )
    finalizer(validation, market).execute(
        "opp-bound", generated_at=NOW, schema_version="decision-input-v1",
        policy_version="decision-policy-v1",
    )
    provider = ProductionOpportunityDecisionDashboardProvider(
        validation, assessment_repository=market
    )
    app.dependency_overrides[get_opportunity_decision_dashboard_provider] = lambda: provider
    try:
        response = TestClient(app).get(
            "/api/v1/opportunities/opp-bound/decision-dashboard"
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 200
    assert response.json()["summary"]["outcome"] == expected.value
    validation.close(); market.close()


def test_concurrent_finalization_allows_exactly_one_identical_provenance(tmp_path) -> None:
    database = tmp_path / "composition-concurrency.sqlite"
    validation = SQLiteValidationQueueRepository(database)
    market = SQLiteMarketObservationRepository(database)
    seed_required_sources(validation, market)
    validation.close(); market.close()

    def run():
        local_validation = SQLiteValidationQueueRepository(database)
        local_market = SQLiteMarketObservationRepository(database)
        try:
            return finalizer(local_validation, local_market).execute(
                "opp-bound", generated_at=NOW, schema_version="decision-input-v1",
                policy_version="decision-policy-v1",
            )
        except Exception as error:
            return error
        finally:
            local_validation.close(); local_market.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda _: run(), range(2)))
    successes = tuple(value for value in results if not isinstance(value, Exception))
    failures = tuple(value for value in results if isinstance(value, Exception))
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], (DuplicateDecisionCompositionError, DecisionCompositionVersionConflictError))
    check = SQLiteValidationQueueRepository(database)
    assert len(check.get_decision_composition_history("opp-bound")) == 1
    check.close()


class CommitFailingConnection:
    def __init__(self, connection):
        object.__setattr__(self, "connection", connection)
        object.__setattr__(self, "fail_commit", False)

    def __getattr__(self, name):
        return getattr(self.connection, name)

    def __setattr__(self, name, value):
        if name in {"connection", "fail_commit"}:
            object.__setattr__(self, name, value)
        else:
            setattr(self.connection, name, value)

    def __enter__(self):
        self.connection.__enter__()
        return self

    def __exit__(self, *args):
        return self.connection.__exit__(*args)

    def commit(self):
        if self.fail_commit:
            self.fail_commit = False
            raise sqlite3.OperationalError("forced commit failure")
        return self.connection.commit()


def test_commit_failure_rolls_back_composition_only() -> None:
    connection = CommitFailingConnection(
        sqlite3.connect(":memory:", check_same_thread=False)
    )
    validation = SQLiteValidationQueueRepository(connection=connection)
    market = SQLiteMarketObservationRepository(connection=connection)
    seed_required_sources(validation, market)
    source_state = persisted_state(connection)
    connection.fail_commit = True
    with pytest.raises(DecisionCompositionCommitError):
        finalizer(validation, market).execute(
            "opp-bound", generated_at=NOW, schema_version="decision-input-v1",
            policy_version="decision-policy-v1",
        )
    after = persisted_state(connection)
    assert after["decision_composition_history"] == ()
    assert after["decision_composition_current"] == ()
    for table, rows in source_state.items():
        if table not in {"decision_composition_history", "decision_composition_current"}:
            assert after[table] == rows
    connection.close()
