from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3

from fastapi.testclient import TestClient
import pytest

import app.web as web_module
from app.infrastructure.capital_readiness import SQLiteCapitalReadinessRepository
from app.infrastructure.sourcing import SQLiteCriticalCostCompletenessRepository
from app.web import app
from test_competition_operational_admission import body as competition_payload
from test_demand_operational_admission import body as demand_payload
from test_domestic_market_validation_api import validation_payload
from test_o2_economics_production_chain_api import (
    _chain_payloads,
    _execute_chain,
    economics_chain_client,
)


def _market_validation(client, opportunity_id, sourcing, **changes):
    identity = deepcopy(
        sourcing["selling_product_lineage"]["market_observation_identity"]
    )
    competition = competition_payload()
    competition["identity"] = deepcopy(identity)
    competition_response = client.post(
        f"/api/v1/opportunities/{opportunity_id}/competition-observations",
        json=competition,
    )
    assert competition_response.status_code == 201, competition_response.text
    demand = demand_payload()
    demand["identity"] = deepcopy(identity)
    demand_response = client.post(
        f"/api/v1/opportunities/{opportunity_id}/demand-observations",
        json=demand,
    )
    assert demand_response.status_code == 201, demand_response.text
    payload = validation_payload(
        competition_response.json(), demand_response.json(), **changes
    )
    response = client.post(
        f"/api/v1/opportunities/{opportunity_id}/domestic-market-validations",
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response, payload


def _critical_payload(opportunity_id, verified, chain, **changes):
    value = {
        "command_id": "critical-cost-api-command-1",
        "composition_id": chain["landed"].json()["composition_id"],
        "acquisition_normalization_id": chain["normalization"].json()[
            "normalization_id"
        ],
        "verified_economics_opportunity_id": opportunity_id,
        "verified_economics_snapshot_at": verified["snapshot_at"],
        "verified_economics_schema_version": verified["schema_version"],
        "requested_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    value.update(changes)
    return value


def _readiness_payload(market, critical, chain, **changes):
    value = {
        "command_id": "capital-readiness-api-command-1",
        "conservative_economics_result_id": chain["conservative"].json()[
            "result_id"
        ],
        "domestic_market_validation_assessment_id": market.json()["assessment_id"],
        "critical_cost_assessment_id": critical.json()["assessment_id"],
        "requested_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    value.update(changes)
    return value


def _ready_journey(economics_chain_client):
    client, database, opportunity_id, sourcing, verified = economics_chain_client
    market, market_payload = _market_validation(
        client, opportunity_id, sourcing
    )
    chain = _execute_chain(
        client,
        opportunity_id,
        _chain_payloads(opportunity_id, sourcing, verified),
    )
    critical_payload = _critical_payload(opportunity_id, verified, chain)
    critical = client.post(
        f"/api/v1/opportunities/{opportunity_id}/critical-cost-assessments",
        json=critical_payload,
    )
    assert critical.status_code == 201, critical.text
    readiness_payload = _readiness_payload(market, critical, chain)
    readiness = client.post(
        f"/api/v1/opportunities/{opportunity_id}/capital-readiness-assessments",
        json=readiness_payload,
    )
    assert readiness.status_code == 201, readiness.text
    return (
        client,
        database,
        opportunity_id,
        verified,
        market,
        market_payload,
        chain,
        critical,
        critical_payload,
        readiness,
        readiness_payload,
    )


def test_api_only_o2_reaches_ready_with_exact_v2_manifests(
    economics_chain_client,
):
    (
        _, _, opportunity_id, _, market, _, chain, critical, _, readiness, _
    ) = _ready_journey(economics_chain_client)

    critical_body = critical.json()
    assert critical_body["opportunity_id"] == opportunity_id
    assert critical_body["state"] == "complete"
    assert critical_body["policy_version"] == "2.0.0"
    assert critical_body["assessment_schema_version"] == (
        "critical-cost-completeness-v2"
    )
    assert critical_body["acquisition_normalization_id"] == (
        chain["normalization"].json()["normalization_id"]
    )
    assert critical_body["allocation_authority_ids"] == [
        chain["supplier"].json()["authority_id"],
        chain["freight"].json()["authority_id"],
    ]
    assert critical_body["fx_observation_ids"] == [
        chain["fx"].json()["observation_id"]
    ]

    body = readiness.json()
    assert body["opportunity_id"] == opportunity_id
    assert body["state"] == "ready_for_capital_review"
    assert body["blocking_reasons"] == []
    manifest = body["source_manifest"]
    assert manifest["conservative_economics_result_id"] == (
        chain["conservative"].json()["result_id"]
    )
    assert manifest["domestic_market_validation_assessment_id"] == (
        market.json()["assessment_id"]
    )
    assert manifest["critical_cost_assessment_id"] == critical_body["assessment_id"]
    assert body["critical_cost_normalization_id"] == (
        manifest["acquisition_normalization_id"]
    )


def test_both_routes_replay_after_restart_and_changed_commands_conflict(
    economics_chain_client,
):
    (
        client, database, opportunity_id, _, _, _, _, critical,
        critical_payload, readiness, readiness_payload,
    ) = _ready_journey(economics_chain_client)
    critical_route = (
        f"/api/v1/opportunities/{opportunity_id}/critical-cost-assessments"
    )
    readiness_route = (
        f"/api/v1/opportunities/{opportunity_id}/capital-readiness-assessments"
    )

    critical_replay = client.post(critical_route, json=critical_payload)
    readiness_replay = client.post(readiness_route, json=readiness_payload)
    assert critical_replay.status_code == 200
    assert readiness_replay.status_code == 200
    assert critical_replay.json() == {**critical.json(), "replayed": True}
    assert readiness_replay.json() == {**readiness.json(), "replayed": True}

    changed_critical = deepcopy(critical_payload)
    changed_critical["acquisition_normalization_id"] = "changed-normalization"
    assert client.post(critical_route, json=changed_critical).status_code == 409
    changed_readiness = deepcopy(readiness_payload)
    changed_readiness["critical_cost_assessment_id"] = "changed-assessment"
    assert client.post(readiness_route, json=changed_readiness).status_code == 409

    with TestClient(app) as restarted:
        assert restarted.post(critical_route, json=critical_payload).json() == (
            critical_replay.json()
        )
        assert restarted.post(readiness_route, json=readiness_payload).json() == (
            readiness_replay.json()
        )
    with sqlite3.connect(database) as connection:
        for table in (
            "critical_cost_completeness_history",
            "critical_cost_completeness_receipts",
            "capital_readiness_history",
            "capital_readiness_receipts",
        ):
            assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1


def test_readiness_blocks_exact_normalization_mismatch(
    economics_chain_client,
):
    (
        client, _, opportunity_id, verified, market, _, chain, _, _, _, _
    ) = _ready_journey(economics_chain_client)
    payloads = _chain_payloads(
        opportunity_id,
        economics_chain_client[3],
        verified,
    )
    normalization = deepcopy(payloads["normalization"])
    normalization.update(
        command_id="normalization-command-b",
        composition_id=chain["landed"].json()["composition_id"],
        allocation_authority_ids=[
            chain["supplier"].json()["authority_id"],
            chain["freight"].json()["authority_id"],
        ],
        fx_observation_ids=[chain["fx"].json()["observation_id"]],
    )
    normalization_b = client.post(
        f"/api/v1/opportunities/{opportunity_id}/acquisition-cost-normalizations",
        json=normalization,
    )
    assert normalization_b.status_code == 201
    critical_payload = _critical_payload(
        opportunity_id,
        verified,
        chain,
        command_id="critical-cost-command-b",
        acquisition_normalization_id=normalization_b.json()["normalization_id"],
    )
    critical_b = client.post(
        f"/api/v1/opportunities/{opportunity_id}/critical-cost-assessments",
        json=critical_payload,
    )
    assert critical_b.status_code == 201
    assert critical_b.json()["state"] == "complete"
    readiness = client.post(
        f"/api/v1/opportunities/{opportunity_id}/capital-readiness-assessments",
        json=_readiness_payload(
            market,
            critical_b,
            chain,
            command_id="readiness-normalization-mismatch",
        ),
    )
    assert readiness.status_code == 201
    assert readiness.json()["state"] == "blocked"
    assert "sourcing_lineage_mismatch" in readiness.json()["blocking_reasons"]
    assert readiness.json()["critical_cost_normalization_id"] != (
        readiness.json()["source_manifest"]["acquisition_normalization_id"]
    )


def test_valid_market_blocked_and_critical_incomplete_results_remain_2xx(
    economics_chain_client,
):
    (
        client, _, opportunity_id, verified, _, market_payload, chain,
        critical, _, _, _,
    ) = _ready_journey(economics_chain_client)
    blocked_market_payload = deepcopy(market_payload)
    blocked_market_payload.update(
        command_id="blocked-market-command",
        current_use_confirmed=False,
    )
    blocked_market = client.post(
        f"/api/v1/opportunities/{opportunity_id}/domestic-market-validations",
        json=blocked_market_payload,
    )
    assert blocked_market.status_code == 201
    readiness = client.post(
        f"/api/v1/opportunities/{opportunity_id}/capital-readiness-assessments",
        json=_readiness_payload(
            blocked_market,
            critical,
            chain,
            command_id="blocked-market-readiness-command",
        ),
    )
    assert readiness.status_code == 201
    assert "domestic_market_not_validated" in readiness.json()["blocking_reasons"]

    same_currency = {
        "command_id": "cny-normalization-command",
        "composition_id": chain["landed"].json()["composition_id"],
        "allocation_authority_ids": [
            chain["supplier"].json()["authority_id"],
            chain["freight"].json()["authority_id"],
        ],
        "fx_observation_ids": [],
        "target_currency": "CNY",
        "requested_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    normalization = client.post(
        f"/api/v1/opportunities/{opportunity_id}/acquisition-cost-normalizations",
        json=same_currency,
    )
    assert normalization.status_code == 201
    incomplete = client.post(
        f"/api/v1/opportunities/{opportunity_id}/critical-cost-assessments",
        json=_critical_payload(
            opportunity_id,
            verified,
            chain,
            command_id="incomplete-critical-command",
            acquisition_normalization_id=normalization.json()["normalization_id"],
        ),
    )
    assert incomplete.status_code == 201
    assert incomplete.json()["state"] == "incomplete"
    assert "cross_currency_fx_missing" in {
        value["code"] for value in incomplete.json()["blocking_reasons"]
    }
    blocked = client.post(
        f"/api/v1/opportunities/{opportunity_id}/capital-readiness-assessments",
        json=_readiness_payload(
            blocked_market,
            incomplete,
            chain,
            command_id="incomplete-critical-readiness-command",
        ),
    )
    assert blocked.status_code == 201
    assert "critical_cost_incomplete" in blocked.json()["blocking_reasons"]


def test_conservative_economics_blocked_is_a_valid_readiness_result(
    economics_chain_client,
):
    (
        client, _, opportunity_id, verified, market, _, chain,
        critical, _, _, _,
    ) = _ready_journey(economics_chain_client)
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    normalization = client.post(
        f"/api/v1/opportunities/{opportunity_id}/acquisition-cost-normalizations",
        json={
            "command_id": "blocked-economics-normalization",
            "composition_id": chain["landed"].json()["composition_id"],
            "allocation_authority_ids": [
                chain["supplier"].json()["authority_id"],
                chain["freight"].json()["authority_id"],
            ],
            "fx_observation_ids": [],
            "target_currency": "CNY",
            "requested_at": now,
        },
    )
    assert normalization.status_code == 201
    source = client.post(
        f"/api/v1/opportunities/{opportunity_id}/economics-source-compositions",
        json={
            "command_id": "blocked-economics-source",
            "acquisition_normalization_id": normalization.json()["normalization_id"],
            "verified_economics_snapshot_at": verified["snapshot_at"],
            "verified_economics_schema_version": verified["schema_version"],
            "requested_at": now,
        },
    )
    assert source.status_code == 201
    assert source.json()["state"] == "blocked"
    conservative = client.post(
        f"/api/v1/opportunities/{opportunity_id}/conservative-economics",
        json={
            "command_id": "blocked-conservative-result",
            "source_composition_id": source.json()["composition_id"],
            "scenario": {
                "scenario_name": "blocked-source-scenario",
                "scenario_version": "1.0.0",
                "sale_price_factor": "0.90",
                "assumption_owner": "founder",
            },
            "requested_at": now,
        },
    )
    assert conservative.status_code == 201
    assert conservative.json()["status"] == "blocked"
    readiness = client.post(
        f"/api/v1/opportunities/{opportunity_id}/capital-readiness-assessments",
        json=_readiness_payload(
            market,
            critical,
            chain,
            command_id="blocked-economics-readiness",
            conservative_economics_result_id=conservative.json()["result_id"],
        ),
    )
    assert readiness.status_code == 201
    assert readiness.json()["state"] == "blocked"
    assert "conservative_economics_blocked" in readiness.json()["blocking_reasons"]


def test_expired_quote_is_preserved_as_critical_and_readiness_blocker(
    economics_chain_client,
):
    (
        client, _, opportunity_id, verified, market, _, _, _, _, _, _
    ) = _ready_journey(economics_chain_client)
    sourcing = economics_chain_client[3]
    now = datetime.now(timezone.utc).replace(microsecond=0)
    evidence = deepcopy(sourcing["quote"]["evidence"])
    evidence.pop("schema_version", None)
    revision = client.post(
        f"/api/v1/sourcing/admissions/{sourcing['admission_id']}/quote-revisions",
        json={
            "command_id": "expired-quote-revision-command",
            "expected_revision": sourcing["revision"],
            "requested_at": now.isoformat(),
            "operator_id": "founder-1",
            "quoted_unit_price": sourcing["quote"]["unit_price"],
            "minimum_order_quantity": sourcing["quote"]["minimum_order_quantity"],
            "quoted_quantity": sourcing["quote"]["quoted_quantity"],
            "shipping_terms": sourcing["quote"]["shipping_terms"],
            "lead_time_availability": sourcing["quote"]["lead_time_availability"],
            "lead_time_days": sourcing["quote"]["lead_time_days"],
            "quote_observed_at": (now - timedelta(days=2)).isoformat(),
            "quote_valid_until": (now - timedelta(days=1)).isoformat(),
            "quote_evidence": evidence,
        },
    )
    assert revision.status_code == 201, revision.text
    payloads = _chain_payloads(opportunity_id, revision.json(), verified)
    for value in payloads.values():
        value["command_id"] = f"expired-{value['command_id']}"
    chain = _execute_chain(client, opportunity_id, payloads)
    critical = client.post(
        f"/api/v1/opportunities/{opportunity_id}/critical-cost-assessments",
        json=_critical_payload(
            opportunity_id,
            verified,
            chain,
            command_id="expired-critical-command",
        ),
    )
    assert critical.status_code == 201
    assert critical.json()["state"] == "incomplete"
    assert "quote_expired" in {
        value["code"] for value in critical.json()["blocking_reasons"]
    }
    readiness = client.post(
        f"/api/v1/opportunities/{opportunity_id}/capital-readiness-assessments",
        json=_readiness_payload(
            market,
            critical,
            chain,
            command_id="expired-readiness-command",
        ),
    )
    assert readiness.status_code == 201
    assert "quote_expired" in readiness.json()["blocking_reasons"]


@pytest.mark.parametrize(
    ("route_name", "missing_field"),
    (("critical", "acquisition_normalization_id"), ("readiness", "critical_cost_assessment_id")),
)
def test_missing_exact_sources_are_404_and_caller_owned_fields_are_422(
    economics_chain_client,
    route_name,
    missing_field,
):
    (
        client, _, opportunity_id, _, _, _, _, _, critical_payload, _, readiness_payload,
    ) = _ready_journey(economics_chain_client)
    if route_name == "critical":
        route = f"/api/v1/opportunities/{opportunity_id}/critical-cost-assessments"
        payload = deepcopy(critical_payload)
    else:
        route = f"/api/v1/opportunities/{opportunity_id}/capital-readiness-assessments"
        payload = deepcopy(readiness_payload)
    payload["command_id"] = f"missing-{route_name}-command"
    payload[missing_field] = "missing-exact-source"
    assert client.post(route, json=payload).status_code == 404
    payload = deepcopy(critical_payload if route_name == "critical" else readiness_payload)
    payload["assessment_id"] = "caller-owned"
    assert client.post(route, json=payload).status_code == 422


def test_route_opportunity_cannot_mix_o1_and_o2_terminal_sources(
    economics_chain_client,
):
    (
        client, _, _, _, _, _, _, _, critical_payload, _, readiness_payload,
    ) = _ready_journey(economics_chain_client)
    assert client.post(
        "/api/v1/opportunities/source-opportunity-1/critical-cost-assessments",
        json=critical_payload,
    ).status_code == 409
    assert client.post(
        "/api/v1/opportunities/source-opportunity-1/capital-readiness-assessments",
        json=readiness_payload,
    ).status_code == 409


def test_route_dependencies_own_one_connection_and_close(tmp_path, monkeypatch):
    database = tmp_path / "capital-production-cleanup.db"
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)
    for factory in (
        web_module.get_critical_cost_assessment_entry,
        web_module.get_capital_readiness_entry,
    ):
        dependency = factory()
        entry = next(dependency)
        repository = entry._repository
        assert repository._connection is repository._connection
        dependency.close()
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            repository._connection.execute("SELECT 1")


@pytest.mark.parametrize(
    ("factory_name", "repository_name", "identity_name"),
    (
        (
            "get_critical_cost_assessment_entry",
            "SQLiteCriticalCostCompletenessRepository",
            "ProductionCriticalCostCompletenessIdentityGenerator",
        ),
        (
            "get_capital_readiness_entry",
            "SQLiteCapitalReadinessRepository",
            "ProductionCapitalReadinessIdentityGenerator",
        ),
    ),
)
def test_partial_composition_failure_closes_owned_connection(
    tmp_path, monkeypatch, factory_name, repository_name, identity_name
):
    database = tmp_path / f"partial-{factory_name}.db"
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)
    captured = []
    real_repository = getattr(web_module, repository_name)

    class CapturingRepository(real_repository):
        def __init__(self, value):
            super().__init__(value)
            captured.append(self)

    monkeypatch.setattr(web_module, repository_name, CapturingRepository)
    monkeypatch.setattr(
        web_module,
        identity_name,
        lambda: (_ for _ in ()).throw(RuntimeError("broken production composition")),
    )
    with pytest.raises(RuntimeError, match="broken production composition"):
        next(getattr(web_module, factory_name)())
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0]._connection.execute("SELECT 1")


def test_persistence_failures_are_503_atomic_and_hide_sqlite_details(
    economics_chain_client,
    monkeypatch,
):
    (
        client, database, opportunity_id, _, market, _, chain, critical,
        critical_payload, _, readiness_payload,
    ) = _ready_journey(economics_chain_client)

    class FailingCritical(SQLiteCriticalCostCompletenessRepository):
        def __init__(self, value):
            super().__init__(value)
            self._connection.execute(
                """CREATE TRIGGER fail_critical_receipt BEFORE INSERT ON
                critical_cost_completeness_receipts
                BEGIN SELECT RAISE(ABORT, 'private critical sqlite detail'); END"""
            )

    monkeypatch.setattr(
        web_module, "SQLiteCriticalCostCompletenessRepository", FailingCritical
    )
    failed_critical = deepcopy(critical_payload)
    failed_critical["command_id"] = "failed-critical-command"
    response = client.post(
        f"/api/v1/opportunities/{opportunity_id}/critical-cost-assessments",
        json=failed_critical,
    )
    assert response.status_code == 503
    assert "private critical" not in response.text
    monkeypatch.setattr(
        web_module,
        "SQLiteCriticalCostCompletenessRepository",
        SQLiteCriticalCostCompletenessRepository,
    )

    class FailingReadiness(SQLiteCapitalReadinessRepository):
        def __init__(self, value):
            super().__init__(value)
            self._connection.execute(
                """CREATE TRIGGER fail_readiness_receipt BEFORE INSERT ON
                capital_readiness_receipts
                BEGIN SELECT RAISE(ABORT, 'private readiness sqlite detail'); END"""
            )

    monkeypatch.setattr(web_module, "SQLiteCapitalReadinessRepository", FailingReadiness)
    failed_readiness = deepcopy(readiness_payload)
    failed_readiness["command_id"] = "failed-readiness-command"
    failed_readiness["domestic_market_validation_assessment_id"] = market.json()[
        "assessment_id"
    ]
    failed_readiness["critical_cost_assessment_id"] = critical.json()["assessment_id"]
    failed_readiness["conservative_economics_result_id"] = chain["conservative"].json()[
        "result_id"
    ]
    response = client.post(
        f"/api/v1/opportunities/{opportunity_id}/capital-readiness-assessments",
        json=failed_readiness,
    )
    assert response.status_code == 503
    assert "private readiness" not in response.text
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM critical_cost_completeness_history"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM capital_readiness_history"
        ).fetchone()[0] == 1


def test_same_commands_converge_at_api_boundary(economics_chain_client):
    (
        _, database, opportunity_id, _, _, _, _, _,
        critical_payload, _, readiness_payload,
    ) = _ready_journey(economics_chain_client)
    critical_payload = deepcopy(critical_payload)
    critical_payload["command_id"] = "concurrent-critical-command"
    critical_route = (
        f"/api/v1/opportunities/{opportunity_id}/critical-cost-assessments"
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        critical_responses = tuple(
            pool.map(
                lambda _: TestClient(app).post(
                    critical_route, json=critical_payload
                ),
                range(2),
            )
        )
    assert sorted(value.status_code for value in critical_responses) == [200, 201]
    critical_id = critical_responses[0].json()["assessment_id"]

    readiness_payload = deepcopy(readiness_payload)
    readiness_payload.update(
        command_id="concurrent-readiness-command",
        critical_cost_assessment_id=critical_id,
    )
    readiness_route = (
        f"/api/v1/opportunities/{opportunity_id}/capital-readiness-assessments"
    )
    with ThreadPoolExecutor(max_workers=2) as pool:
        readiness_responses = tuple(
            pool.map(
                lambda _: TestClient(app).post(
                    readiness_route, json=readiness_payload
                ),
                range(2),
            )
        )
    assert sorted(value.status_code for value in readiness_responses) == [200, 201]
    assert len({value.json()["assessment_id"] for value in readiness_responses}) == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM critical_cost_completeness_history"
        ).fetchone()[0] == 2
        assert connection.execute(
            "SELECT COUNT(*) FROM capital_readiness_history"
        ).fetchone()[0] == 2
