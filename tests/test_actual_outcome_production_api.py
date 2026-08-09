from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import sqlite3

from fastapi.testclient import TestClient
import pytest

import app.web as web_module
from app.infrastructure.actual_outcome import ActualOutcomeHistoryError, SQLiteActualOutcomeRepository
from app.infrastructure.actual_acquisition_settlement import ActualAcquisitionSettlementHistoryError
from app.web import app
from test_actual_acquisition_settlement_production_api import _settlement_payload
from test_actual_sale_settlement_production_api import _sale_payload, _setup
from test_o2_economics_production_chain_api import economics_chain_client


def _journey(economics_chain_client, *, quantity=10, sale_changes=None, sale_mutator=None):
    result = _setup(economics_chain_client, quantity=quantity)
    result["acquisition_route"] = f"/api/v1/opportunities/{result['opportunity_id']}/actual-acquisition-settlements"
    acquisition = result["client"].post(result["acquisition_route"], json=_settlement_payload(result["purchase"]))
    assert acquisition.status_code == 201, acquisition.text
    result["acquisition"] = acquisition.json()
    payload = _sale_payload(result, **(sale_changes or {}))
    if sale_mutator is not None:
        sale_mutator(payload)
    sale = result["client"].post(result["sale_route"], json=payload)
    assert sale.status_code == 201, sale.text
    result["sale"] = sale.json()
    result["sale_payload"] = payload
    result["outcome_route"] = f"/api/v1/opportunities/{result['opportunity_id']}/actual-outcomes"
    result["outcome_payload"] = {
        "command_id": "actual-outcome-command-1",
        "actual_acquisition_settlement_id": result["acquisition"]["settlement_id"],
        "actual_sale_settlement_ids": [result["sale"]["settlement_id"]],
        "requested_at": (datetime.fromisoformat(result["sale"]["period_end"]) + timedelta(minutes=10)).isoformat(),
    }
    return result


def _legacy_counts(database):
    with sqlite3.connect(database) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        selected = ("opportunity_actual_economics", "opportunity_actual_economics_events", "economics_variance_history")
        return {name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in selected if name in tables}


def test_api_partial_sale_calculable_decimal_strings_replay_restart_and_legacy_isolation(economics_chain_client):
    result = _journey(economics_chain_client, quantity=10)
    before = _legacy_counts(result["database"])
    response = result["client"].post(result["outcome_route"], json=result["outcome_payload"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["state"] == "calculable"
    assert body["inventory_resolution"] == "partial"
    assert body["executed_quantity"] == 10
    assert body["sold_quantity"] == 4
    assert body["remaining_sellable_quantity"] == 6
    assert body["unreceived_quantity"] == 0
    assert body["acquisition_batch_total"] == "10000"
    assert body["actual_cogs"] == "4000"
    assert body["remaining_sellable_inventory_cost_basis"] == "6000"
    assert body["actual_realized_profit"] == "36000"
    assert body["actual_margin"]["available"] is True
    assert isinstance(body["actual_margin"]["value"], str)
    assert len(body["acquisition_allocations"]) == 6
    assert len(body["sale_components"]) == 15
    assert _legacy_counts(result["database"]) == before

    replay = TestClient(app).post(result["outcome_route"], json=result["outcome_payload"])
    assert replay.status_code == 200
    assert replay.json()["outcome_id"] == body["outcome_id"]
    assert replay.json()["calculated_at"] == body["calculated_at"]
    assert replay.json()["replayed"] is True


def test_api_full_resolution(economics_chain_client):
    full = _journey(economics_chain_client, quantity=10, sale_changes={"fulfilled_outbound_quantity": 10})
    full_response = full["client"].post(full["outcome_route"], json=full["outcome_payload"])
    assert full_response.status_code == 201
    assert full_response.json()["inventory_resolution"] == "fully_resolved"
    assert full_response.json()["remaining_sellable_inventory_cost_basis"] == "0"


def test_api_zero_sales_is_calculable_with_unavailable_ratios(economics_chain_client):
    def zero_gross(payload):
        for fact in payload["fixed_monetary_facts"]:
            if fact["category"] == "gross_completed_merchandise":
                fact["amount"] = "0"

    zero = _journey(
        economics_chain_client, quantity=10,
        sale_changes={"fulfilled_outbound_quantity": 0, "transaction_references": []},
        sale_mutator=zero_gross,
    )
    response = zero["client"].post(zero["outcome_route"], json=zero["outcome_payload"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["state"] == "calculable"
    assert body["sold_quantity"] == 0
    assert body["actual_cogs"] == "0"
    assert body["actual_margin"] == {"available": False, "value": None}
    assert body["actual_acquisition_roi"] == {"available": False, "value": None}


def test_api_negative_profit_remains_calculable(economics_chain_client):
    def low_gross(payload):
        for fact in payload["fixed_monetary_facts"]:
            if fact["category"] == "gross_completed_merchandise":
                fact["amount"] = "1"

    negative = _journey(economics_chain_client, quantity=10, sale_mutator=low_gross)
    response = negative["client"].post(negative["outcome_route"], json=negative["outcome_payload"])
    assert response.status_code == 201
    assert response.json()["state"] == "calculable"
    assert Decimal(response.json()["actual_realized_profit"]) < 0


def test_api_missing_wrong_route_changed_command_structural_422_and_alias(economics_chain_client):
    result = _journey(economics_chain_client)
    payload = result["outcome_payload"]
    missing = deepcopy(payload)
    missing.update(command_id="missing", actual_acquisition_settlement_id="missing")
    assert result["client"].post(result["outcome_route"], json=missing).status_code == 404
    assert result["client"].post("/api/v1/opportunities/wrong-o2/actual-outcomes", json=payload).status_code == 409
    first = result["client"].post(result["outcome_route"], json=payload)
    assert first.status_code == 201
    changed = deepcopy(payload)
    changed["actual_sale_settlement_ids"] = []
    assert result["client"].post(result["outcome_route"], json=changed).status_code == 422
    changed = deepcopy(payload)
    changed["requested_at"] = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    assert result["client"].post(result["outcome_route"], json=changed).status_code == 409
    extra = deepcopy(payload)
    extra["command_id"] = "actual-outcome-command-alias"
    alias = result["client"].post(result["outcome_route"], json=extra)
    assert alias.status_code == 201
    assert alias.json()["aliased"] is True
    assert alias.json()["outcome_id"] == first.json()["outcome_id"]


def test_api_persistence_failure_is_503_and_dependency_closes(economics_chain_client, monkeypatch):
    result = _journey(economics_chain_client)
    captured = []
    real_repository = SQLiteActualOutcomeRepository

    class FailingRepository(real_repository):
        def __init__(self, value):
            super().__init__(value)
            captured.append(self)

        def save(self, *_args, **_kwargs):
            raise ActualOutcomeHistoryError("private sqlite detail")

    monkeypatch.setattr(web_module, "SQLiteActualOutcomeRepository", FailingRepository)
    failed = result["client"].post(result["outcome_route"], json=result["outcome_payload"])
    assert failed.status_code == 503
    assert "private sqlite" not in failed.text
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0]._connection.execute("SELECT 1")

    monkeypatch.setattr(web_module, "SQLiteActualOutcomeRepository", real_repository)
    retry = result["client"].post(result["outcome_route"], json=result["outcome_payload"])
    assert retry.status_code == 201

    class SourceFailingRepository(real_repository):
        def get_actual_acquisition_settlement(self, _settlement_id):
            raise ActualAcquisitionSettlementHistoryError("private upstream detail")

    monkeypatch.setattr(web_module, "SQLiteActualOutcomeRepository", SourceFailingRepository)
    upstream_payload = deepcopy(result["outcome_payload"])
    upstream_payload["command_id"] = "actual-outcome-upstream-unavailable"
    upstream = result["client"].post(result["outcome_route"], json=upstream_payload)
    assert upstream.status_code == 503
    assert "private upstream" not in upstream.text
    monkeypatch.setattr(web_module, "SQLiteActualOutcomeRepository", real_repository)

    dependency = web_module.get_actual_outcome_entry()
    entry = next(dependency)
    repository = entry._owner._repository
    assert repository._acquisition._connection is repository._connection
    assert repository._sale._connection is repository._connection
    dependency.close()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        repository._connection.execute("SELECT 1")
