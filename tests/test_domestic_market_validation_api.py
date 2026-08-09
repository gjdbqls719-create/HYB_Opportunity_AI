from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import sqlite3

from fastapi.testclient import TestClient
import pytest

import app.web as web_module
from app.infrastructure.domestic_market_validation import (
    SQLiteDomesticMarketValidationRepository,
)
from app.web import app
from test_competition_operational_admission import body as competition_payload
from test_demand_operational_admission import body as demand_payload
from test_domestic_selling_opportunity_api import domestic_payload
from test_domestic_selling_opportunity_sqlite import seed
from test_domestic_market_validation_sqlite import seed as seed_legacy_validation


@pytest.fixture
def market_validation_client(tmp_path, monkeypatch):
    database = tmp_path / "domestic-market-validation-api.db"
    seed(database)
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)
    app.dependency_overrides.clear()
    with TestClient(app) as client:
        journey = _create_o2_market_sources(client)
        yield (client, database, *journey)
    app.dependency_overrides.clear()


def _create_o2_market_sources(client, *, competition=None, demand=None):
    domestic = client.post(
        "/api/v1/opportunities/source-opportunity-1/domestic-selling-admissions",
        json=domestic_payload(),
    )
    assert domestic.status_code == 201
    domestic_body = domestic.json()
    opportunity_id = domestic_body["domestic_opportunity_identity"]["opportunity_id"]
    market_identity = domestic_body["market_binding"]["market_observation_identity"]

    competition = competition or competition_payload()
    competition["identity"] = deepcopy(market_identity)
    competition_response = client.post(
        f"/api/v1/opportunities/{opportunity_id}/competition-observations",
        json=competition,
    )
    assert competition_response.status_code == 201

    demand = demand or demand_payload()
    demand["identity"] = deepcopy(market_identity)
    demand_response = client.post(
        f"/api/v1/opportunities/{opportunity_id}/demand-observations",
        json=demand,
    )
    assert demand_response.status_code == 201

    return (
        domestic_body,
        competition_response.json(),
        demand_response.json(),
    )


def validation_payload(competition, demand, **changes):
    competition_observation_id = competition["observation"]["observation_id"]
    competition_assessment_id = competition["assessment"]["snapshot_id"]
    demand_observation_id = demand["observation"]["observation_id"]
    demand_assessment_id = demand["assessment"]["snapshot_id"]
    verified_at = datetime.now(timezone.utc).replace(microsecond=0)
    value = {
        "command_id": "domestic-market-validation-command-1",
        "competition_observation_id": competition_observation_id,
        "competition_assessment_id": competition_assessment_id,
        "demand_observation_id": demand_observation_id,
        "demand_assessment_id": demand_assessment_id,
        "accepted_external_signal_ids": [],
        "operator_id": "founder-1",
        "reviewed_source_ids": [
            competition_observation_id,
            competition_assessment_id,
            demand_observation_id,
            demand_assessment_id,
        ],
        "current_use_confirmed": True,
        "verified_at": verified_at.isoformat(),
        "requested_at": verified_at.isoformat(),
        "policy_name": "domestic-market-validation",
        "policy_version": "1.0.0",
    }
    value.update(changes)
    return value


def test_o2_domestic_market_validation_route_returns_validated_assessment(
    market_validation_client,
):
    client, _, domestic, competition, demand = market_validation_client
    opportunity_id = domestic["domestic_opportunity_identity"]["opportunity_id"]

    response = client.post(
        f"/api/v1/opportunities/{opportunity_id}/domestic-market-validations",
        json=validation_payload(competition, demand),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["state"] == "validated_for_capital"
    assert body["blocking_reasons"] == []
    assert body["source_manifest"]["opportunity_id"] == opportunity_id
    assert body["source_manifest"]["market_identity"]["market"] == "KR"
    assert body["source_manifest"]["competition"]["observation_id"] == (
        competition["observation"]["observation_id"]
    )
    assert body["source_manifest"]["demand"]["assessment_id"] == (
        demand["assessment"]["snapshot_id"]
    )
    assert body["verification"]["operator_id"] == "founder-1"
    assert body["verification"]["current_use_confirmed"] is True


@pytest.mark.parametrize(
    "forbidden",
    ("assessment_id", "state", "blocking_reasons", "evaluated_at", "committed_at"),
)
def test_caller_cannot_declare_server_validation_fields(
    market_validation_client,
    forbidden,
):
    client, _, domestic, competition, demand = market_validation_client
    opportunity_id = domestic["domestic_opportunity_identity"]["opportunity_id"]
    payload = validation_payload(competition, demand)
    payload[forbidden] = "caller-value"

    assert client.post(
        f"/api/v1/opportunities/{opportunity_id}/domestic-market-validations",
        json=payload,
    ).status_code == 422


@pytest.mark.parametrize(
    ("change", "expected"),
    (
        ({"opportunity": "missing-opportunity"}, 404),
        ({"competition_observation_id": "missing-competition"}, 404),
        ({"competition_assessment_id": "missing-competition-assessment"}, 404),
        ({"demand_observation_id": "missing-demand"}, 404),
        ({"demand_assessment_id": "missing-demand-assessment"}, 404),
        ({"opportunity": "source-opportunity-1"}, 409),
    ),
)
def test_exact_source_and_lineage_http_errors(
    market_validation_client,
    change,
    expected,
):
    client, _, domestic, competition, demand = market_validation_client
    opportunity_id = change.get(
        "opportunity",
        domestic["domestic_opportunity_identity"]["opportunity_id"],
    )
    payload_changes = {key: value for key, value in change.items() if key != "opportunity"}
    payload = validation_payload(competition, demand, **payload_changes)

    assert client.post(
        f"/api/v1/opportunities/{opportunity_id}/domestic-market-validations",
        json=payload,
    ).status_code == expected


def test_blocked_current_use_is_committed_business_result(market_validation_client):
    client, _, domestic, competition, demand = market_validation_client
    opportunity_id = domestic["domestic_opportunity_identity"]["opportunity_id"]
    response = client.post(
        f"/api/v1/opportunities/{opportunity_id}/domestic-market-validations",
        json=validation_payload(
            competition,
            demand,
            current_use_confirmed=False,
        ),
    )

    assert response.status_code == 201
    assert response.json()["state"] == "blocked"
    assert response.json()["blocking_reasons"] == [
        "current_use_verification_missing"
    ]


@pytest.mark.parametrize(
    "blocked_source",
    ("partial_demand", "unsupported_evidence"),
)
def test_source_policy_blockers_remain_authoritative_2xx(
    tmp_path,
    monkeypatch,
    blocked_source,
):
    database = tmp_path / f"blocked-{blocked_source}.db"
    seed(database)
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)
    demand = demand_payload()
    competition = competition_payload()
    if blocked_source == "partial_demand":
        demand["evidence"].pop("rating")
        expected = "demand_assessment_partial"
    else:
        competition["evidence"]["median_price"]["status"] = "estimated"
        expected = "required_evidence_status_unsupported"
    with TestClient(app) as client:
        domestic, competition_result, demand_result = _create_o2_market_sources(
            client,
            competition=competition,
            demand=demand,
        )
        opportunity_id = domestic["domestic_opportunity_identity"]["opportunity_id"]
        response = client.post(
            f"/api/v1/opportunities/{opportunity_id}/domestic-market-validations",
            json=validation_payload(competition_result, demand_result),
        )
    assert response.status_code == 201
    assert response.json()["state"] == "blocked"
    assert expected in response.json()["blocking_reasons"]


def test_exact_replay_restart_and_changed_payload_conflicts(market_validation_client):
    client, database, domestic, competition, demand = market_validation_client
    opportunity_id = domestic["domestic_opportunity_identity"]["opportunity_id"]
    route = f"/api/v1/opportunities/{opportunity_id}/domestic-market-validations"
    payload = validation_payload(competition, demand)

    first = client.post(route, json=payload)
    replay = client.post(route, json=payload)
    changed_source = deepcopy(payload)
    changed_source["competition_assessment_id"] = "changed-assessment"
    changed_verification = deepcopy(payload)
    changed_verification["operator_id"] = "other-founder"

    assert first.status_code == 201
    assert replay.status_code == 200
    assert replay.json() == {**first.json(), "replayed": True}
    assert client.post(route, json=changed_source).status_code == 409
    assert client.post(route, json=changed_verification).status_code == 409

    with TestClient(app) as restarted:
        restart_replay = restarted.post(route, json=payload)
    assert restart_replay.status_code == 200
    assert restart_replay.json() == replay.json()

    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM domestic_market_validation_history"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM domestic_market_validation_receipts"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM validation_queue_admission_snapshots WHERE opportunity_id=?",
            (opportunity_id,),
        ).fetchone()[0] == 0


def test_validation_uses_no_verified_economics_or_capital_state(market_validation_client):
    client, database, domestic, competition, demand = market_validation_client
    opportunity_id = domestic["domestic_opportunity_identity"]["opportunity_id"]
    response = client.post(
        f"/api/v1/opportunities/{opportunity_id}/domestic-market-validations",
        json=validation_payload(competition, demand),
    )
    assert response.status_code == 201
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM verified_economics_snapshots WHERE opportunity_id=?",
            (opportunity_id,),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name LIKE 'capital_%'"
        ).fetchone()[0] == 0


def test_legacy_kr_opportunity_remains_supported(tmp_path, monkeypatch):
    database = tmp_path / "legacy-kr-market-validation.db"
    seed_legacy_validation(database)
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)
    competition = {
        "observation": {"observation_id": "competition-observation-1"},
        "assessment": {"snapshot_id": "competition-assessment-1"},
    }
    demand = {
        "observation": {"observation_id": "demand-observation-1"},
        "assessment": {"snapshot_id": "demand-assessment-1"},
    }
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/opportunities/opportunity-1/domestic-market-validations",
            json=validation_payload(competition, demand),
        )
    assert response.status_code == 201
    assert response.json()["source_manifest"]["opportunity_id"] == "opportunity-1"
    assert response.json()["state"] in {"validated_for_capital", "blocked"}


def test_persistence_failure_returns_503_and_preserves_upstream_sources(
    market_validation_client,
    monkeypatch,
):
    client, database, domestic, competition, demand = market_validation_client
    opportunity_id = domestic["domestic_opportunity_identity"]["opportunity_id"]
    captured = []

    class FailingRepository(SQLiteDomesticMarketValidationRepository):
        def __init__(self, value):
            super().__init__(value)
            captured.append(self)
            self._connection.execute(
                """CREATE TRIGGER fail_domestic_market_validation_receipt
                BEFORE INSERT ON domestic_market_validation_receipts
                BEGIN SELECT RAISE(ABORT, 'private sqlite detail'); END"""
            )

    monkeypatch.setattr(
        web_module,
        "SQLiteDomesticMarketValidationRepository",
        FailingRepository,
    )
    response = client.post(
        f"/api/v1/opportunities/{opportunity_id}/domestic-market-validations",
        json=validation_payload(competition, demand),
    )
    assert response.status_code == 503
    assert "private sqlite detail" not in response.text
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM domestic_market_validation_history"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM domestic_market_validation_receipts"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM competition_admission_receipts"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM demand_admission_receipts"
        ).fetchone()[0] == 1
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0]._connection.execute("SELECT 1")


def test_route_closes_request_connection_for_all_completed_outcomes(
    market_validation_client,
    monkeypatch,
):
    client, _, domestic, competition, demand = market_validation_client
    opportunity_id = domestic["domestic_opportunity_identity"]["opportunity_id"]
    route = f"/api/v1/opportunities/{opportunity_id}/domestic-market-validations"
    captured = []

    class CapturingRepository(SQLiteDomesticMarketValidationRepository):
        def __init__(self, value):
            super().__init__(value)
            captured.append(self)

    monkeypatch.setattr(
        web_module,
        "SQLiteDomesticMarketValidationRepository",
        CapturingRepository,
    )
    first_payload = validation_payload(competition, demand)
    assert client.post(route, json=first_payload).status_code == 201
    assert client.post(route, json=first_payload).status_code == 200
    assert client.post(
        route,
        json=validation_payload(
            competition,
            demand,
            command_id="blocked-command",
            current_use_confirmed=False,
        ),
    ).status_code == 201
    assert client.post(
        "/api/v1/opportunities/missing/domestic-market-validations",
        json=validation_payload(
            competition,
            demand,
            command_id="missing-command",
        ),
    ).status_code == 404
    assert client.post(
        "/api/v1/opportunities/source-opportunity-1/domestic-market-validations",
        json=validation_payload(
            competition,
            demand,
            command_id="conflict-command",
        ),
    ).status_code == 409
    invalid = validation_payload(
        competition,
        demand,
        command_id="invalid-command",
    )
    invalid["state"] = "validated_for_capital"
    assert client.post(route, json=invalid).status_code == 422

    assert len(captured) >= 5
    for repository in captured:
        with pytest.raises(sqlite3.ProgrammingError, match="closed"):
            repository._connection.execute("SELECT 1")


def test_dependency_closes_connection_and_partial_composition_failure(
    tmp_path,
    monkeypatch,
):
    database = tmp_path / "domestic-market-validation-cleanup.db"
    seed(database)
    monkeypatch.setattr(web_module, "DEFAULT_DATABASE_PATH", database)

    dependency = web_module.get_domestic_market_validation_entry()
    entry = next(dependency)
    repository = entry._repository
    dependency.close()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        repository._connection.execute("SELECT 1")

    captured = []
    real_repository = SQLiteDomesticMarketValidationRepository

    class CapturingRepository(real_repository):
        def __init__(self, value):
            super().__init__(value)
            captured.append(self)

    monkeypatch.setattr(
        web_module,
        "SQLiteDomesticMarketValidationRepository",
        CapturingRepository,
    )
    monkeypatch.setattr(
        web_module,
        "ProductionDomesticMarketValidationIdentityGenerator",
        lambda: (_ for _ in ()).throw(RuntimeError("broken composition")),
    )
    with pytest.raises(RuntimeError, match="broken composition"):
        next(web_module.get_domestic_market_validation_entry())
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0]._connection.execute("SELECT 1")


def test_api_same_command_converges_without_duplicate_rows(market_validation_client):
    _, database, domestic, competition, demand = market_validation_client
    opportunity_id = domestic["domestic_opportunity_identity"]["opportunity_id"]
    route = f"/api/v1/opportunities/{opportunity_id}/domestic-market-validations"
    payload = validation_payload(competition, demand)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = tuple(
            pool.map(lambda _: TestClient(app).post(route, json=payload), range(2))
        )
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert len({response.json()["assessment_id"] for response in responses}) == 1
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM domestic_market_validation_history"
        ).fetchone()[0] == 1
