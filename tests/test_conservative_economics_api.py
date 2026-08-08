from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import sqlite3

from fastapi.testclient import TestClient
import pytest

from app.application.conservative_economics import (
    ConservativeEconomicsProductionEntry,
    ConservativeEconomicsProductionRequest,
    ConservativeEconomicsScenario,
    EvaluateConservativeEconomics,
)
from app.infrastructure.conservative_economics import (
    ConservativeEconomicsHistoryError,
    ProductionConservativeEconomicsIdentityGenerator,
    SQLiteConservativeEconomicsRepository,
)
from app.web import app, get_conservative_economics_entry
import app.web as web
from test_conservative_economics import rate, verified_input
from test_conservative_economics_sqlite import counts, seed_source
from test_economics_source_composition import Calls
from test_sourcing_authority_contract import NOW


CALCULATED_AT = NOW + timedelta(minutes=30)
COMMITTED_AT = NOW + timedelta(minutes=31)


def payload(**changes):
    value = {
        "command_id": "conservative-economics-command-1",
        "source_composition_id": "economics-source-composition-1",
        "scenario": {
            "scenario_name": "founder-explicit-unit-scenario",
            "scenario_version": "1.0.0",
            "sale_price_factor": "0.90",
            "assumption_owner": "founder",
        },
        "requested_at": NOW.isoformat(),
    }
    value.update(changes)
    return value


def production_entry(repository, *, identity=None, calculated=None, committed=None):
    return ConservativeEconomicsProductionEntry(
        repository=repository,
        result_id_generator=identity or Calls("conservative-result-1"),
        calculated_clock=calculated or Calls(CALCULATED_AT),
        committed_clock=committed or Calls(COMMITTED_AT),
    )


def use(entry):
    app.dependency_overrides[get_conservative_economics_entry] = lambda: entry
    return TestClient(app)


def clear_overrides():
    app.dependency_overrides.clear()


def test_production_entry_resolves_exact_source_and_delegates_to_owner(tmp_path):
    path = tmp_path / "conservative-entry.sqlite3"
    source = seed_source(path)
    repository = SQLiteConservativeEconomicsRepository(path)
    identity = Calls("conservative-result-1")
    calculated = Calls(CALCULATED_AT)
    committed = Calls(COMMITTED_AT)
    entry = production_entry(
        repository,
        identity=identity,
        calculated=calculated,
        committed=committed,
    )
    try:
        result = entry.execute(
            ConservativeEconomicsProductionRequest(
                command_id="conservative-economics-command-1",
                opportunity_id=source.opportunity_identity.opportunity_id,
                source_composition_id=source.composition_id,
                scenario=ConservativeEconomicsScenario(
                    "founder-explicit-unit-scenario",
                    "1.0.0",
                    Decimal("0.90"),
                    "founder",
                ),
                requested_at=NOW,
            )
        )

        assert isinstance(entry._evaluate, EvaluateConservativeEconomics)
        assert result.result.source_composition_id == source.composition_id
        assert result.result.opportunity_identity == source.opportunity_identity
        assert identity.count == calculated.count == committed.count == 1
    finally:
        repository.close()


def test_production_composition_uses_authoritative_dependencies_and_closes_scope(
    tmp_path, monkeypatch
):
    path = tmp_path / "conservative-composition.sqlite3"
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    dependency = get_conservative_economics_entry()
    entry = next(dependency)
    repository = entry._repository

    assert isinstance(entry, ConservativeEconomicsProductionEntry)
    assert isinstance(repository, SQLiteConservativeEconomicsRepository)
    assert isinstance(
        entry._evaluate._identity,
        ProductionConservativeEconomicsIdentityGenerator,
    )
    assert entry._evaluate._calculated is not entry._evaluate._committed
    assert entry._evaluate._calculated().tzinfo is not None
    assert entry._evaluate._committed().tzinfo is not None
    assert repository._connection.execute("PRAGMA database_list").fetchone()[2] == str(path)

    dependency.close()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        repository._connection.execute("SELECT 1")


def test_partial_composition_failure_closes_constructed_repository(monkeypatch):
    closed = []

    class Repository:
        def __init__(self, path):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            closed.append(True)

    monkeypatch.setattr(web, "SQLiteConservativeEconomicsRepository", Repository)
    monkeypatch.setattr(
        web,
        "ProductionConservativeEconomicsIdentityGenerator",
        lambda: (_ for _ in ()).throw(RuntimeError("construction failed")),
    )

    with pytest.raises(RuntimeError, match="construction failed"):
        next(get_conservative_economics_entry())
    assert closed == [True]


def test_request_scope_closes_repository_after_application_failure(tmp_path, monkeypatch):
    path = tmp_path / "conservative-scope-failure.sqlite3"
    repository = SQLiteConservativeEconomicsRepository(path)
    monkeypatch.setattr(
        web,
        "SQLiteConservativeEconomicsRepository",
        lambda database_path: repository,
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/opportunities/opportunity-1/conservative-economics",
            json=payload(source_composition_id="missing-composition"),
        )
    assert response.status_code == 404
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        repository._connection.execute("SELECT 1")


def test_conservative_economics_api_fresh_exact_source_response(tmp_path):
    path = tmp_path / "conservative-api.sqlite3"
    source = seed_source(path)
    repository = SQLiteConservativeEconomicsRepository(path)
    client = use(production_entry(repository))
    try:
        response = client.post(
            f"/api/v1/opportunities/{source.opportunity_identity.opportunity_id}/conservative-economics",
            json=payload(),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["command_id"] == "conservative-economics-command-1"
        assert body["result_id"] == "conservative-result-1"
        assert body["opportunity_id"] == source.opportunity_identity.opportunity_id
        assert body["discovery_reference"] == source.opportunity_identity.discovery_reference
        assert body["source_composition_id"] == source.composition_id
        assert body["status"] == "calculable"
        assert body["economics_currency"] == source.economics_currency
        assert body["scenario_name"] == "founder-explicit-unit-scenario"
        assert body["scenario_version"] == "1.0.0"
        assert body["assumptions"] == [
            {"kind": "sale_price_factor", "value": "0.90", "owner": "founder"}
        ]
        assert body["conservative_acquisition_roi"] is not None
        assert "roi" not in body
        assert "landed_cost_roi" not in body
        assert "capital_ready" not in body
        assert "recommendation" not in body
        assert body["replayed"] is False
        assert counts(repository) == (1, 1)
    finally:
        clear_overrides()
        repository.close()


def test_api_exact_and_restart_replay_skip_identity_and_clocks(tmp_path):
    path = tmp_path / "conservative-replay.sqlite3"
    source = seed_source(path)
    identity = Calls("conservative-result-1")
    calculated = Calls(CALCULATED_AT)
    committed = Calls(COMMITTED_AT)
    repository = SQLiteConservativeEconomicsRepository(path)
    client = use(
        production_entry(
            repository,
            identity=identity,
            calculated=calculated,
            committed=committed,
        )
    )
    route = f"/api/v1/opportunities/{source.opportunity_identity.opportunity_id}/conservative-economics"
    try:
        first = client.post(route, json=payload())
        replay = client.post(route, json=payload())
        assert first.status_code == 201
        assert replay.status_code == 200
        assert replay.json() == {**first.json(), "replayed": True}
        assert identity.count == calculated.count == committed.count == 1
    finally:
        clear_overrides()
        repository.close()

    class Never:
        def __call__(self):
            raise AssertionError("fresh authority called during restart replay")

    repository = SQLiteConservativeEconomicsRepository(path)
    client = use(
        production_entry(
            repository,
            identity=Never(),
            calculated=Never(),
            committed=Never(),
        )
    )
    try:
        restarted = client.post(route, json=payload())
        assert restarted.status_code == 200
        assert restarted.json() == replay.json()
        assert counts(repository) == (1, 1)
    finally:
        clear_overrides()
        repository.close()


def test_api_conflict_missing_source_and_opportunity_mismatch(tmp_path):
    path = tmp_path / "conservative-errors.sqlite3"
    source = seed_source(path)
    repository = SQLiteConservativeEconomicsRepository(path)
    entry = production_entry(repository)
    client = use(entry)
    route = f"/api/v1/opportunities/{source.opportunity_identity.opportunity_id}/conservative-economics"
    try:
        assert client.post(route, json=payload()).status_code == 201
        changed = payload()
        changed["scenario"] = {**changed["scenario"], "sale_price_factor": "0.80"}
        assert client.post(route, json=changed).status_code == 409
        changed_time = payload(requested_at=(NOW + timedelta(seconds=1)).isoformat())
        assert client.post(route, json=changed_time).status_code == 409
        assert client.post(
            route,
            json=payload(
                command_id="missing-command",
                source_composition_id="missing-composition",
            ),
        ).status_code == 404
        assert client.post(
            "/api/v1/opportunities/different-opportunity/conservative-economics",
            json=payload(command_id="mismatch-command"),
        ).status_code == 409
        assert counts(repository) == (1, 1)
    finally:
        clear_overrides()
        repository.close()


@pytest.mark.parametrize("forbidden", ("result_id", "calculated_at", "committed_at"))
def test_request_rejects_server_owned_fields(tmp_path, forbidden):
    path = tmp_path / f"forbidden-{forbidden}.sqlite3"
    source = seed_source(path)
    repository = SQLiteConservativeEconomicsRepository(path)
    client = use(production_entry(repository))
    try:
        response = client.post(
            f"/api/v1/opportunities/{source.opportunity_identity.opportunity_id}/conservative-economics",
            json=payload(**{forbidden: "caller-value"}),
        )
        assert response.status_code == 422
        assert counts(repository) == (0, 0)
    finally:
        clear_overrides()
        repository.close()


def test_blocked_and_negative_results_are_successful_without_fabrication(tmp_path):
    blocked_path = tmp_path / "blocked.sqlite3"
    blocked_source = seed_source(
        blocked_path,
        verified_input(tax_rate=rate("0.01", "tax")),
    )
    blocked_repository = SQLiteConservativeEconomicsRepository(blocked_path)
    client = use(production_entry(blocked_repository))
    try:
        blocked = client.post(
            f"/api/v1/opportunities/{blocked_source.opportunity_identity.opportunity_id}/conservative-economics",
            json=payload(),
        )
        assert blocked.status_code == 201
        body = blocked.json()
        assert body["status"] == "blocked"
        assert body["blocking_reasons"]
        assert body["conservative_profit_per_unit"] is None
        assert body["conservative_margin"] is None
        assert body["conservative_acquisition_roi"] is None
    finally:
        clear_overrides()
        blocked_repository.close()

    negative_path = tmp_path / "negative.sqlite3"
    negative_source = seed_source(
        negative_path,
        verified_input(
            expected_sale_price=replace(
                verified_input().expected_sale_price,
                amount=Decimal("100"),
            )
        ),
    )
    negative_repository = SQLiteConservativeEconomicsRepository(negative_path)
    client = use(production_entry(negative_repository))
    try:
        negative = client.post(
            f"/api/v1/opportunities/{negative_source.opportunity_identity.opportunity_id}/conservative-economics",
            json=payload(),
        )
        assert negative.status_code == 201
        body = negative.json()
        assert body["status"] == "calculable"
        assert Decimal(body["conservative_profit_per_unit"]) < 0
        assert Decimal(body["conservative_margin"]) < 0
        assert Decimal(body["conservative_acquisition_roi"]) < 0
    finally:
        clear_overrides()
        negative_repository.close()


def test_persistence_failure_is_503_without_raw_sqlite_detail():
    class FailingEntry:
        def execute(self, request):
            raise ConservativeEconomicsHistoryError("sqlite secret table failure")

    client = use(FailingEntry())
    try:
        response = client.post(
            "/api/v1/opportunities/opportunity-1/conservative-economics",
            json=payload(),
        )
        assert response.status_code == 503
        assert response.json() == {
            "detail": "conservative economics persistence unavailable"
        }
    finally:
        clear_overrides()


def test_request_scoped_concurrency_converges_and_conflicts(tmp_path, monkeypatch):
    path = tmp_path / "conservative-concurrency.sqlite3"
    source = seed_source(path)
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", path)
    route = f"/api/v1/opportunities/{source.opportunity_identity.opportunity_id}/conservative-economics"

    def post(body):
        with TestClient(app) as client:
            response = client.post(route, json=body)
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        same = tuple(pool.map(post, (payload(), payload())))
    assert sorted(status for status, _ in same) == [200, 201]
    assert len({body["result_id"] for _, body in same}) == 1

    conflict_path = tmp_path / "conservative-concurrency-conflict.sqlite3"
    source = seed_source(conflict_path)
    monkeypatch.setattr(web, "DEFAULT_DATABASE_PATH", conflict_path)
    route = f"/api/v1/opportunities/{source.opportunity_identity.opportunity_id}/conservative-economics"
    changed = payload()
    changed["scenario"] = {**changed["scenario"], "sale_price_factor": "0.80"}
    with ThreadPoolExecutor(max_workers=2) as pool:
        different = tuple(pool.map(post, (payload(), changed)))
    assert sorted(status for status, _ in different) == [201, 409]
