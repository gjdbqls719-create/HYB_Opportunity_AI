from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import sqlite3

from fastapi.testclient import TestClient
import pytest

import app.web as web_module
from app.infrastructure.purchase_execution import (
    PurchaseExecutionHistoryError,
    SQLitePurchaseExecutionRepository,
)
from app.web import app
from test_capital_execution_production_api import _execute_capital_journey
from test_o2_economics_production_chain_api import economics_chain_client


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _payload(result, **changes):
    execution = result["execution"].json()
    values = {
        "contract_version": "2.0.0",
        "command_id": "purchase-execution-command-1",
        "real_money_execution_intent_id": execution["intent_id"],
        "quote_id": execution["quote_id"],
        "quote_revision": execution["quote_revision"],
        "actual_quantity": execution["execution_quantity"],
        "actual_quantity_unit": execution["execution_quantity_unit"],
        "supplier_order_committed_amount": execution[
            "proposed_supplier_order_committed_amount"
        ],
        "supplier_order_currency": execution["supplier_order_currency"],
        "external_order_reference": "supplier-order-opaque-001",
        "founder_id": execution["founder_id"],
        "executed_at": execution["evaluated_at"],
        "evidence_references": [
            {
                "reference": "artifact://supplier-order-confirmation/001",
                "observed_at": execution["evaluated_at"],
            }
        ],
        "requested_at": _now(),
    }
    values.update(changes)
    return values


def _commercial_side_effect_counts(database):
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        selected = tuple(
            sorted(
                name
                for name in tables
                if name in {
                    "opportunity_actual_economics",
                    "opportunity_actual_economics_events",
                }
                or "inventory" in name.lower()
            )
        )
        return {
            name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            for name in selected
        }


def test_api_only_ready_intent_records_exact_external_purchase_and_replays(
    economics_chain_client,
):
    result = _execute_capital_journey(economics_chain_client)
    client = result["client"]
    route = (
        f"/api/v1/opportunities/{result['opportunity_id']}"
        "/purchase-execution-records"
    )
    payload = _payload(result)
    before_side_effects = _commercial_side_effect_counts(result["database"])

    fresh = client.post(route, json=payload)
    assert fresh.status_code == 201, fresh.text
    body = fresh.json()
    execution = result["execution"].json()
    assert body["opportunity_id"] == result["opportunity_id"]
    assert body["real_money_execution_intent_id"] == execution["intent_id"]
    assert body["actual_quantity"] == execution["execution_quantity"]
    assert body["actual_quantity_unit"] == execution["execution_quantity_unit"]
    assert body["supplier_order_committed_amount"] == execution[
        "proposed_supplier_order_committed_amount"
    ]
    assert body["supplier_order_currency"] == execution["supplier_order_currency"]
    assert body["quote_id"] == execution["quote_id"]
    assert body["quote_revision"] == execution["quote_revision"]
    assert body["founder_id"] == execution["founder_id"]
    assert body["external_order_reference"] == "supplier-order-opaque-001"
    assert body["evidence_references"][0]["reference"] == (
        "artifact://supplier-order-confirmation/001"
    )
    assert body["policy_name"] == "exact-ready-intent-purchase-execution"
    assert body["record_id"] != execution["intent_id"]
    assert datetime.fromisoformat(body["executed_at"]).utcoffset() is not None
    assert datetime.fromisoformat(body["admitted_at"]).utcoffset() is not None
    assert datetime.fromisoformat(body["committed_at"]).utcoffset() is not None

    with sqlite3.connect(result["database"]) as connection:
        row = connection.execute(
            "SELECT execution_intent_id, COUNT(*) "
            "FROM purchase_execution_record_history GROUP BY execution_intent_id"
        ).fetchone()
        assert row == (execution["intent_id"], 1)
    assert _commercial_side_effect_counts(result["database"]) == before_side_effects

    replay = TestClient(app).post(route, json=payload)
    assert replay.status_code == 200, replay.text
    assert replay.json()["record_id"] == body["record_id"]
    assert replay.json()["admitted_at"] == body["admitted_at"]
    assert replay.json()["committed_at"] == body["committed_at"]
    assert replay.json()["replayed"] is True

    alias_payload = deepcopy(payload)
    alias_payload.update(
        command_id="purchase-execution-alias-command",
        requested_at=_now(),
    )
    alias = TestClient(app).post(route, json=alias_payload)
    assert alias.status_code == 200, alias.text
    assert alias.json()["record_id"] == body["record_id"]

    changed_same_command = deepcopy(payload)
    changed_same_command["external_order_reference"] = "changed-order"
    changed = client.post(route, json=changed_same_command)
    assert changed.status_code == 409

    competing = deepcopy(payload)
    competing.update(
        command_id="purchase-execution-competing-command",
        external_order_reference="different-actual-order",
    )
    conflict = client.post(route, json=competing)
    assert conflict.status_code == 409


def test_v2_http_separates_cross_currency_capital_and_supplier_commitment(
    economics_chain_client,
):
    result = _execute_capital_journey(
        economics_chain_client,
        execution_contract_version="2.0.0",
        supplier_order_amount="500",
    )
    execution = result["execution"].json()
    assert execution["authorized_acquisition_capital_currency"] == "KRW"
    assert execution["proposed_supplier_order_committed_amount"] == "500"
    assert execution["supplier_order_currency"] == result["sourcing"]["quote"]["unit_price"]["currency"]
    assert execution["planned_execution_amount"] is None

    route = f"/api/v1/opportunities/{result['opportunity_id']}/purchase-execution-records"
    payload = {
        "contract_version": "2.0.0",
        "command_id": "purchase-execution-v2-command-1",
        "real_money_execution_intent_id": execution["intent_id"],
        "quote_id": execution["quote_id"],
        "quote_revision": execution["quote_revision"],
        "actual_quantity": execution["execution_quantity"],
        "actual_quantity_unit": execution["execution_quantity_unit"],
        "supplier_order_committed_amount": "500",
        "supplier_order_currency": execution["supplier_order_currency"],
        "external_order_reference": "supplier-order-v2-001",
        "founder_id": execution["founder_id"],
        "executed_at": execution["evaluated_at"],
        "evidence_references": [{
            "reference": "artifact://supplier-checkout/actual-001",
            "observed_at": execution["evaluated_at"],
        }],
        "requested_at": _now(),
    }
    fresh = result["client"].post(route, json=payload)
    assert fresh.status_code == 201, fresh.text
    body = fresh.json()
    assert body["authorized_acquisition_capital_currency"] == "KRW"
    assert body["supplier_order_committed_amount"] == "500"
    assert body["supplier_order_currency"] == execution["supplier_order_currency"]
    assert body["actual_total_committed_amount"] is None

    drift = deepcopy(payload)
    drift.update(command_id="purchase-execution-v2-drift", supplier_order_committed_amount="510")
    assert result["client"].post(route, json=drift).status_code == 409


def test_new_production_v1_writes_are_disabled(economics_chain_client):
    result = _execute_capital_journey(economics_chain_client)
    execution_v1 = deepcopy(result["execution_payload"])
    execution_v1.pop("proposed_supplier_order_committed_amount")
    execution_v1.pop("supplier_order_currency")
    execution_v1.pop("supplier_order_checkout_evidence_reference")
    execution_v1.update(
        contract_version="1.0.0",
        command_id="new-v1-intent-is-disabled",
        planned_execution_amount=result["approval"].json()["approved_capital"],
        currency=result["approval"].json()["currency"],
    )
    response = result["client"].post(
        f"/api/v1/opportunities/{result['opportunity_id']}/real-money-execution-intents",
        json=execution_v1,
    )
    assert response.status_code == 422
    assert "new v1" in response.json()["detail"]


def test_api_rejects_missing_wrong_route_deviations_and_blocked_intent(
    economics_chain_client,
):
    result = _execute_capital_journey(economics_chain_client)
    client = result["client"]
    route = (
        f"/api/v1/opportunities/{result['opportunity_id']}"
        "/purchase-execution-records"
    )
    base = _payload(result)

    missing = deepcopy(base)
    missing.update(
        command_id="purchase-missing-command",
        real_money_execution_intent_id="missing-intent",
    )
    assert client.post(route, json=missing).status_code == 404
    assert client.post(
        "/api/v1/opportunities/different-o2/purchase-execution-records",
        json=base,
    ).status_code == 409

    deviations = (
        {"quote_id": "different-quote"},
        {"quote_revision": 999},
        {"actual_quantity": 999},
        {"actual_quantity_unit": "case"},
        {"supplier_order_committed_amount": "1"},
        {"supplier_order_currency": "USD"},
        {"founder_id": "different-founder"},
    )
    for index, changes in enumerate(deviations):
        payload = deepcopy(base)
        payload.update(command_id=f"purchase-deviation-{index}", **changes)
        assert client.post(route, json=payload).status_code == 409

    invalid_time = deepcopy(base)
    invalid_time.update(
        command_id="purchase-naive-time",
        executed_at="2026-01-01T00:00:00",
    )
    assert client.post(route, json=invalid_time).status_code == 422
    malformed_reference = deepcopy(base)
    malformed_reference.update(
        command_id="purchase-empty-reference", external_order_reference=" "
    )
    assert client.post(route, json=malformed_reference).status_code == 422

    blocked_execution_payload = deepcopy(result["execution_payload"])
    blocked_execution_payload.update(
        command_id="blocked-intent-for-purchase-command",
        execution_quantity=11,
    )
    blocked = client.post(
        f"/api/v1/opportunities/{result['opportunity_id']}/real-money-execution-intents",
        json=blocked_execution_payload,
    )
    assert blocked.status_code == 201
    assert blocked.json()["state"] == "blocked"
    blocked_payload = deepcopy(base)
    blocked_payload.update(
        command_id="purchase-against-blocked-command",
        real_money_execution_intent_id=blocked.json()["intent_id"],
        actual_quantity=blocked.json()["execution_quantity"],
    )
    blocked_response = client.post(route, json=blocked_payload)
    assert blocked_response.status_code == 409


def test_http_same_command_concurrency_creates_one_purchase_record(
    economics_chain_client,
):
    result = _execute_capital_journey(economics_chain_client)
    route = (
        f"/api/v1/opportunities/{result['opportunity_id']}"
        "/purchase-execution-records"
    )
    payload = _payload(result)

    def execute(_):
        return TestClient(app).post(route, json=payload)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = tuple(pool.map(execute, range(2)))
    assert sorted(value.status_code for value in responses) == [200, 201]
    assert responses[0].json()["record_id"] == responses[1].json()["record_id"]
    with sqlite3.connect(result["database"]) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM purchase_execution_record_history"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT COUNT(*) FROM purchase_execution_record_receipts"
        ).fetchone()[0] == 1


def test_persistence_failure_is_503_atomic_closed_and_retryable(
    economics_chain_client, monkeypatch
):
    result = _execute_capital_journey(economics_chain_client)
    route = (
        f"/api/v1/opportunities/{result['opportunity_id']}"
        "/purchase-execution-records"
    )
    payload = _payload(result)
    captured = []
    real_repository = SQLitePurchaseExecutionRepository

    class FailingRepository(real_repository):
        def __init__(self, value):
            super().__init__(value)
            captured.append(self)

        def save_record(self, *_args, **_kwargs):
            raise PurchaseExecutionHistoryError("private sqlite detail")

    monkeypatch.setattr(web_module, "SQLitePurchaseExecutionRepository", FailingRepository)
    failed = result["client"].post(route, json=payload)
    assert failed.status_code == 503
    assert "private sqlite" not in failed.text
    with sqlite3.connect(result["database"]) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM purchase_execution_record_history"
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM purchase_execution_record_receipts"
        ).fetchone()[0] == 0
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0]._connection.execute("SELECT 1")

    monkeypatch.setattr(web_module, "SQLitePurchaseExecutionRepository", real_repository)
    retry = result["client"].post(route, json=payload)
    assert retry.status_code == 201, retry.text


def test_purchase_execution_dependency_owns_one_connection_and_closes(
    economics_chain_client,
):
    result = _execute_capital_journey(economics_chain_client)
    dependency = web_module.get_purchase_execution_entry()
    entry = next(dependency)
    repository = entry._repository
    assert repository._execution._connection is repository._connection
    assert repository._execution._sourcing._connection is repository._connection
    dependency.close()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        repository._connection.execute("SELECT 1")
