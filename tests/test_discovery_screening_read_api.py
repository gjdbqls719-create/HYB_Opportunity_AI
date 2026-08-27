from __future__ import annotations

from datetime import timedelta
from datetime import datetime, timezone
import sqlite3

from fastapi.testclient import TestClient

from app.domain.discovery_identity import DiscoveryExecutionResult
from app.domain.discovery_identity import (
    CANDIDATE_HANDOFF_POLICY_NAME,
    CANDIDATE_HANDOFF_POLICY_VERSION,
)
from app.domain.market_intelligence import (
    MarketObservationIdentity,
    MarketObservationScope,
)
from app.infrastructure.discovery import (
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
    SQLiteDiscoveryResultRepository,
    SQLiteDiscoveryScreeningCompletionRepository,
)
from app.web import (
    app,
    get_authoritative_discovery_screening_reader,
)
import app.web as web
from tests.discovery_screening_persistence_support import (
    prepare_bundle,
    prepare_completion_lineage,
)
from tests.test_discovery_screening_read_application import (
    close_all,
    reader,
    reverse_ranked_bundle,
)
from collectors.collection_fact import CollectionFact
from engine import orchestrator
from tests.test_discovery_screening_production_integration import (
    COLLECTOR,
    OBSERVED_AT,
    close_all as close_production_repositories,
    open_entry,
    product,
    production_command,
    production_runtime,
)


ROUTE = "/api/v1/discovery/executions/execution-1/screening-ranking"


def use(query) -> TestClient:
    app.dependency_overrides[get_authoritative_discovery_screening_reader] = (
        lambda: query
    )
    return TestClient(app)


def clear() -> None:
    app.dependency_overrides.clear()


def test_screening_read_composition_has_only_persisted_read_dependencies(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "screening-composition.db"
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    dependency = get_authoritative_discovery_screening_reader()
    query = next(dependency)
    result_reader = query._result_reader
    repositories = (
        result_reader._result_repository,
        result_reader._group_repository,
        result_reader._observation_repository,
        query._screening_repository,
    )

    assert isinstance(repositories[0], SQLiteDiscoveryResultRepository)
    assert isinstance(repositories[1], SQLiteDiscoveryGroupRepository)
    assert isinstance(repositories[2], SQLiteDiscoveryObservationRepository)
    assert isinstance(repositories[3], SQLiteDiscoveryScreeningCompletionRepository)
    assert not hasattr(query, "_runtime")
    assert not hasattr(query, "_collector")
    assert not hasattr(query, "_policy_resolver")
    assert {
        repository._connection.execute("PRAGMA database_list").fetchone()[2]
        for repository in repositories
    } == {str(path)}

    dependency.close()
    for repository in repositories:
        try:
            repository._connection.execute("SELECT 1")
        except sqlite3.ProgrammingError as error:
            assert "closed" in str(error)
        else:
            raise AssertionError("screening read repository connection remained open")


def test_exact_get_returns_persisted_order_typed_evaluations_and_authority(
    tmp_path,
) -> None:
    path = tmp_path / "screening-api.db"
    expected = reverse_ranked_bundle(prepare_bundle(path))
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    repository.save_completion_bundle(expected)
    repository.close()
    query, repositories = reader(path)
    client = use(query)
    try:
        response = client.get(ROUTE)
    finally:
        clear()
        close_all(*repositories)

    assert response.status_code == 200
    body = response.json()
    assert body["command_id"] == "command-1"
    assert body["discovery_execution_id"] == "execution-1"
    assert body["screening_status"] == "RECORDED"
    assert body["screening_ranking_publication_id"] == "publication-1"
    assert body["ranking_publication_fingerprint"] == (
        expected.ranking_publication.integrity_fingerprint
    )
    assert body["ranking_policy"]["policy_version"] == "1.0.0"
    assert [item["rank"] for item in body["ranked"]] == [1, 2]
    assert [item["finalized_group"]["finalized_group_id"] for item in body["ranked"]] == [
        "group-1-2",
        "group-1-1",
    ]
    evaluation = body["ranked"][0]["evaluation"]
    assert evaluation["screening_evaluation_id"] == "evaluation-1-2"
    assert evaluation["recommendation"]["review_priority_label"] == (
        "High Review Priority"
    )
    assert evaluation["recommendation"]["raw"] == {
        "label_context": "screening engine label",
        "grade": "BUY",
        "action": "review",
        "summary": "raw summary",
    }
    assert evaluation["recommendation"]["effective"]["grade"] == "WATCH"
    assert evaluation["recommendation"]["safety_intervention_applied"] is True
    assert evaluation["recommendation"]["reasons"][0]["polarity"] == "BLOCKING"
    assert evaluation["screening_policy_manifest"]["ranking"] == body["ranking_policy"]
    assert body["authority_scope"] == "DISCOVERY_SCREENING_ONLY"
    assert body["does_not_authorize"] == [
        "CANDIDATE_ISSUANCE",
        "O1_PROMOTION",
        "CAPITAL_GATE_PASS",
        "FOUNDER_CAPITAL_APPROVAL",
        "REAL_MONEY_EXECUTION_INTENT",
    ]


def test_provenance_and_missing_values_are_not_reinterpreted(tmp_path) -> None:
    path = tmp_path / "screening-provenance-api.db"
    expected = prepare_bundle(path)
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    repository.save_completion_bundle(expected)
    repository.close()
    query, repositories = reader(path)
    client = use(query)
    try:
        body = client.get(ROUTE).json()
    finally:
        clear()
        close_all(*repositories)

    evaluation = body["ranked"][0]["evaluation"]
    economics = {
        item["semantic_role"]: item for item in evaluation["expected_economics"]
    }
    assert economics["purchase_price"]["provenance_kind"] == "OBSERVED"
    assert economics["shipping_cost"]["provenance_kind"] == "UNKNOWN"
    assert economics["shipping_cost"]["value"] is None
    inputs = {
        item["evidence"]["semantic_role"]: item["evidence"]
        for item in evaluation["input_manifest"]["inputs"]
    }
    assert inputs["estimated_monthly_sales"]["provenance_kind"] == (
        "POLICY_ASSUMPTION"
    )
    assert inputs["competitor_count"]["provenance_kind"] == "POLICY_ASSUMPTION"
    assert inputs["shipping_cost_calculation_fallback"]["value"] == {
        "kind": "decimal",
        "value": "0",
    }
    assert inputs["shipping_cost_calculation_fallback"]["provenance_kind"] == (
        "POLICY_ASSUMPTION"
    )


def test_not_ranked_and_legacy_responses_are_explicit(tmp_path) -> None:
    recorded_path = tmp_path / "not-ranked-api.db"
    expected = prepare_bundle(recorded_path)
    repository = SQLiteDiscoveryScreeningCompletionRepository(recorded_path)
    repository.save_completion_bundle(expected)
    repository.close()
    query, repositories = reader(recorded_path)
    client = use(query)
    try:
        body = client.get(ROUTE).json()
    finally:
        clear()
        close_all(*repositories)
    assert body["not_ranked"][0]["rank"] is None
    assert body["not_ranked"][0]["rank_label"] == "Not ranked"
    assert body["not_ranked"][0]["not_ranked_reason_code"] == (
        "UNKNOWN_RANKING_KEY"
    )

    legacy_path = tmp_path / "legacy-api.db"
    command, groups = prepare_completion_lineage(legacy_path)
    results = SQLiteDiscoveryResultRepository(legacy_path)
    results.save_result(
        DiscoveryExecutionResult(
            command_id=command.command_id,
            discovery_execution_id=command.discovery_execution_id,
            finalized_group_ids=tuple(group.finalized_group_id for group in groups),
            completed_at=groups[-1].finalized_at + timedelta(minutes=1),
        )
    )
    results.close()
    query, repositories = reader(legacy_path)
    client = use(query)
    try:
        legacy = client.get(ROUTE)
    finally:
        clear()
        close_all(*repositories)
    assert legacy.status_code == 200
    assert legacy.json()["screening_status"] == (
        "SCREENING_NOT_RECORDED_LEGACY"
    )
    assert legacy.json()["screening_ranking_publication_id"] is None
    assert legacy.json()["ranking_policy"] is None
    assert legacy.json()["ranked"] == legacy.json()["not_ranked"] == []


def test_missing_is_404_and_corrupt_is_409_without_fallback(tmp_path) -> None:
    query, repositories = reader(tmp_path / "missing-api.db")
    client = use(query)
    try:
        missing = client.get(ROUTE)
    finally:
        clear()
        close_all(*repositories)
    assert missing.status_code == 404

    path = tmp_path / "corrupt-api.db"
    expected = prepare_bundle(path)
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    repository.save_completion_bundle(expected)
    repository._connection.execute(
        "DROP TRIGGER trg_discovery_screening_evaluation_history_no_update"
    )
    repository._connection.execute(
        "UPDATE discovery_screening_evaluation_history "
        "SET integrity_fingerprint=?",
        ("a" * 64,),
    )
    repository._connection.commit()
    repository.close()
    query, repositories = reader(path)
    client = use(query)
    try:
        corrupt = client.get(ROUTE)
    finally:
        clear()
        close_all(*repositories)
    assert corrupt.status_code == 409
    assert "malformed" in corrupt.json()["detail"]


def test_get_is_repeatable_read_only_and_openapi_is_explicit(tmp_path) -> None:
    path = tmp_path / "repeat-api.db"
    expected = prepare_bundle(path)
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    repository.save_completion_bundle(expected)
    repository.close()
    query, repositories = reader(path)
    before = tuple(item._connection.total_changes for item in repositories)
    client = use(query)
    try:
        first = client.get(ROUTE)
        second = client.get(ROUTE)
        schema = client.get("/openapi.json").json()
        after = tuple(item._connection.total_changes for item in repositories)
    finally:
        clear()
        close_all(*repositories)

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert before == after
    operation = schema["paths"][
        "/api/v1/discovery/executions/{discovery_execution_id}/screening-ranking"
    ]["get"]
    assert operation["responses"]["200"]["content"]["application/json"][
        "schema"
    ]["$ref"].endswith("DiscoveryScreeningRankingReadResponse")


def test_founder_explicitly_selects_rank_two_through_existing_candidate_api(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "rank-two-candidate.db"
    products = (
        product("camera", "Alpha Camera Model A", 100, 4.8),
        product("drill", "Industrial Drill Model Z", 20, 3.7),
    )

    def search_products(*args, collection_fact_sink=None, **kwargs):
        for value in products:
            if collection_fact_sink is not None:
                collection_fact_sink(
                    CollectionFact(
                        product=value,
                        observed_at=OBSERVED_AT,
                        collector_descriptor=COLLECTOR,
                        source_reference=value.url,
                        candidate_market_identity=MarketObservationIdentity(
                            scope=MarketObservationScope.LISTING,
                            market="US",
                            marketplace="ebay",
                            canonical_product_id=None,
                            marketplace_item_id=value.item_id,
                            normalized_query=None,
                            category=None,
                            variant_identity=None,
                            condition=value.condition,
                            window_started_at=OBSERVED_AT,
                            window_ended_at=OBSERVED_AT,
                        ),
                        candidate_handoff_policy_name=(
                            CANDIDATE_HANDOFF_POLICY_NAME
                        ),
                        candidate_handoff_policy_version=(
                            CANDIDATE_HANDOFF_POLICY_VERSION
                        ),
                    )
                )
        return list(products)

    monkeypatch.setattr(orchestrator, "search_products", search_products)
    entry, repositories = open_entry(path, runtime=production_runtime())

    class References:
        def __init__(self) -> None:
            self.values = iter(("candidate-handoff-1", "candidate-handoff-2"))

        def provide_candidate_discovery_reference(self):
            return next(self.values)

    entry._candidate_discovery_reference_provider = References()
    try:
        entry.execute(production_command())
    finally:
        close_production_repositories(repositories)
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    client = TestClient(app)

    screening = client.get(ROUTE)
    assert screening.status_code == 200
    body = screening.json()
    assert len(body["ranked"]) >= 2
    selected = body["ranked"][1]
    selected_group = selected["finalized_group"]
    handoff = selected_group["candidate_handoff"]
    assert selected["rank"] == 2
    assert handoff is not None

    with sqlite3.connect(path) as connection:
        before_candidates = connection.execute(
            "SELECT COUNT(*) FROM opportunity_candidate_history"
        ).fetchone()[0] if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='opportunity_candidate_history'"
        ).fetchone() else 0
    assert before_candidates == 0

    candidate = client.post(
        "/api/v1/candidates",
        json={
            "issuance_command_id": "founder-selected-rank-two",
            "discovery_command_id": body["command_id"],
            "discovery_execution_id": body["discovery_execution_id"],
            "finalized_group_id": selected_group["finalized_group_id"],
            "discovery_reference": handoff["discovery_reference"],
            "market_observation_identity": handoff["market_observation_identity"],
            "requested_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    assert candidate.status_code == 201
    assert candidate.json()["finalized_group_id"] == selected_group[
        "finalized_group_id"
    ]
    assert candidate.json()["finalized_group_id"] != body["ranked"][0][
        "finalized_group"
    ]["finalized_group_id"]

    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM opportunity_candidate_history"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' "
            "AND (name LIKE '%candidate_promotion%' OR name LIKE 'capital_%')"
        ).fetchone()[0] == 0
