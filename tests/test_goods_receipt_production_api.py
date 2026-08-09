from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
import sqlite3

from fastapi.testclient import TestClient
import pytest

import app.web as web_module
from app.infrastructure.goods_receipt import (
    GoodsReceiptHistoryError,
    SQLiteGoodsReceiptRepository,
)
from app.web import app
from test_capital_execution_production_api import _execute_capital_journey
from test_o2_economics_production_chain_api import economics_chain_client
from test_purchase_execution_production_api import _payload as purchase_payload


def _now():
    return datetime.now(timezone.utc).isoformat()


def _receipt_times(purchase):
    received = datetime.fromisoformat(purchase["executed_at"])
    inspected = received
    return received.isoformat(), inspected.isoformat()


def _payload(purchase, **changes):
    received_quantity = changes.pop("received_quantity", purchase["actual_quantity"])
    received_at, inspected_at = _receipt_times(purchase)
    values = {
        "command_id": "goods-receipt-command-1",
        "purchase_execution_record_id": purchase["record_id"],
        "received_quantity": received_quantity,
        "quantity_unit": purchase["actual_quantity_unit"],
        "sellable_quantity": received_quantity,
        "damaged_quantity": 0,
        "evidence_references": [
            {
                "reference": "artifact://goods-receipt/photo-1",
                "observed_at": inspected_at,
                "operator_id": "founder-1",
                "collection_method": "founder_inspection",
            }
        ],
        "delivery_reference": "carrier-tracking-001",
        "operator_id": "founder-1",
        "received_at": received_at,
        "inspected_at": inspected_at,
        "requested_at": _now(),
    }
    values.update(changes)
    return values


def _prepare(economics_chain_client, *, quantity=10):
    result = _execute_capital_journey(economics_chain_client, quantity=quantity)
    purchase_route = (
        f"/api/v1/opportunities/{result['opportunity_id']}"
        "/purchase-execution-records"
    )
    response = result["client"].post(purchase_route, json=purchase_payload(result))
    assert response.status_code == 201, response.text
    result["purchase"] = response.json()
    result["receipt_route"] = (
        f"/api/v1/opportunities/{result['opportunity_id']}/goods-receipts"
    )
    return result


def _isolated_side_effect_counts(database):
    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        selected = sorted(
            name
            for name in tables
            if name
            in {
                "opportunity_actual_economics",
                "opportunity_actual_economics_events",
                "actual_acquisition_settlement_history",
                "actual_acquisition_settlement_receipts",
            }
            or ("inventory" in name.lower() and not name.startswith("goods_receipt"))
        )
        return {
            name: connection.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0]
            for name in selected
        }


def test_api_quantity_100_partial_60_40_journey_restart_replay_and_over_receipt(
    economics_chain_client,
):
    result = _prepare(economics_chain_client, quantity=100)
    purchase = result["purchase"]
    assert purchase["actual_quantity"] == 100
    before = _isolated_side_effect_counts(result["database"])
    first_payload = _payload(
        purchase,
        received_quantity=60,
        sellable_quantity=58,
        damaged_quantity=2,
    )
    first = result["client"].post(result["receipt_route"], json=first_payload)
    assert first.status_code == 201, first.text
    first_body = first.json()
    assert first_body["received_quantity"] == 60
    assert first_body["sellable_quantity"] == 58
    assert first_body["damaged_quantity"] == 2
    assert first_body["purchase_execution_record_id"] == purchase["record_id"]
    assert first_body["supplier_id"] == purchase["supplier_id"]
    assert first_body["sourcing_product_id"] == purchase["sourcing_product_id"]
    assert first_body["quote_id"] == purchase["quote_id"]
    assert first_body["delivery_reference"] == "carrier-tracking-001"
    assert datetime.fromisoformat(first_body["received_at"]).utcoffset() is not None
    assert datetime.fromisoformat(first_body["committed_at"]).utcoffset() is not None

    second_payload = _payload(
        purchase,
        command_id="goods-receipt-command-2",
        received_quantity=40,
        sellable_quantity=40,
        damaged_quantity=0,
        delivery_reference=None,
    )
    second_payload["evidence_references"][0]["reference"] = (
        "artifact://goods-receipt/photo-2"
    )
    second = result["client"].post(result["receipt_route"], json=second_payload)
    assert second.status_code == 201, second.text
    assert second.json()["record_id"] != first_body["record_id"]

    with SQLiteGoodsReceiptRepository(result["database"]) as repository:
        assert repository.get_cumulative_received_quantity(purchase["record_id"]) == 100
    assert _isolated_side_effect_counts(result["database"]) == before

    replay = TestClient(app).post(result["receipt_route"], json=first_payload)
    assert replay.status_code == 200, replay.text
    assert replay.json()["record_id"] == first_body["record_id"]
    assert replay.json()["admitted_at"] == first_body["admitted_at"]
    assert replay.json()["committed_at"] == first_body["committed_at"]
    assert replay.json()["replayed"] is True

    over = _payload(
        purchase,
        command_id="goods-receipt-command-3",
        received_quantity=1,
        sellable_quantity=1,
        damaged_quantity=0,
    )
    assert result["client"].post(result["receipt_route"], json=over).status_code == 409
    with sqlite3.connect(result["database"]) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM goods_receipt_record_history"
        ).fetchone()[0] == 2


def test_api_complete_undamaged_mvp_path_requires_no_actual_settlement(
    economics_chain_client,
):
    result = _prepare(economics_chain_client, quantity=10)
    before = _isolated_side_effect_counts(result["database"])
    response = result["client"].post(
        result["receipt_route"], json=_payload(result["purchase"])
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["received_quantity"] == 10
    assert body["sellable_quantity"] == 10
    assert body["damaged_quantity"] == 0
    assert body["policy_name"] == "exact-purchase-execution-goods-receipt"
    assert "state" not in body
    assert "fulfilled" not in body
    assert "inventory" not in body
    assert _isolated_side_effect_counts(result["database"]) == before
    with sqlite3.connect(result["database"]) as connection:
        settlement_table = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' "
            "AND name='actual_acquisition_settlement_history'"
        ).fetchone()
        assert settlement_table is None


def test_api_errors_are_bounded_and_structural_inputs_are_422(
    economics_chain_client,
):
    result = _prepare(economics_chain_client)
    purchase = result["purchase"]
    base = _payload(purchase)
    missing = deepcopy(base)
    missing.update(
        command_id="goods-receipt-missing",
        purchase_execution_record_id="missing-purchase",
    )
    assert result["client"].post(result["receipt_route"], json=missing).status_code == 404
    assert result["client"].post(
        "/api/v1/opportunities/wrong-o2/goods-receipts", json=base
    ).status_code == 409
    wrong_unit = deepcopy(base)
    wrong_unit.update(command_id="goods-receipt-wrong-unit", quantity_unit="case")
    assert result["client"].post(result["receipt_route"], json=wrong_unit).status_code == 409
    invalid_values = (
        {"received_quantity": 0, "sellable_quantity": 0},
        {"received_quantity": True, "sellable_quantity": 1},
        {"received_quantity": 10, "sellable_quantity": 9, "damaged_quantity": 0},
        {"received_at": "2026-01-01T00:00:00"},
        {"delivery_reference": " "},
        {"extra_field": "forbidden"},
    )
    for index, changes in enumerate(invalid_values):
        payload = deepcopy(base)
        payload.update(command_id=f"goods-receipt-invalid-{index}", **changes)
        assert result["client"].post(result["receipt_route"], json=payload).status_code == 422
    changed = deepcopy(base)
    changed["delivery_reference"] = "changed-delivery"
    first = result["client"].post(result["receipt_route"], json=base)
    assert first.status_code == 201
    assert result["client"].post(result["receipt_route"], json=changed).status_code == 409


def test_api_concurrent_over_receipt_after_60_allows_only_one_30(
    economics_chain_client,
):
    result = _prepare(economics_chain_client, quantity=100)
    purchase = result["purchase"]
    existing = _payload(
        purchase,
        received_quantity=60,
        sellable_quantity=60,
        damaged_quantity=0,
    )
    assert result["client"].post(result["receipt_route"], json=existing).status_code == 201
    payloads = []
    for index in range(2):
        payload = _payload(
            purchase,
            command_id=f"concurrent-30-{index}",
            received_quantity=30,
            sellable_quantity=30,
            damaged_quantity=0,
        )
        payload["evidence_references"][0]["reference"] = f"artifact://receipt/{index}"
        payloads.append(payload)

    def execute(index):
        return TestClient(app).post(result["receipt_route"], json=payloads[index])

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = tuple(pool.map(execute, range(2)))
    assert sorted(value.status_code for value in responses) == [201, 409], [
        value.text for value in responses
    ]
    with SQLiteGoodsReceiptRepository(result["database"]) as repository:
        cumulative = repository.get_cumulative_received_quantity(purchase["record_id"])
        assert cumulative == 90
        assert cumulative <= purchase["actual_quantity"]


def test_api_persistence_failure_is_503_closed_and_retryable(
    economics_chain_client, monkeypatch
):
    result = _prepare(economics_chain_client)
    payload = _payload(result["purchase"])
    captured = []
    real_repository = SQLiteGoodsReceiptRepository

    class FailingRepository(real_repository):
        def __init__(self, value):
            super().__init__(value)
            captured.append(self)

        def save(self, *_args, **_kwargs):
            raise GoodsReceiptHistoryError("private sqlite detail")

    monkeypatch.setattr(web_module, "SQLiteGoodsReceiptRepository", FailingRepository)
    failed = result["client"].post(result["receipt_route"], json=payload)
    assert failed.status_code == 503
    assert "private sqlite" not in failed.text
    with sqlite3.connect(result["database"]) as connection:
        assert connection.execute(
            "SELECT COUNT(*) FROM goods_receipt_record_history"
        ).fetchone()[0] == 0
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0]._connection.execute("SELECT 1")

    monkeypatch.setattr(web_module, "SQLiteGoodsReceiptRepository", real_repository)
    retry = result["client"].post(result["receipt_route"], json=payload)
    assert retry.status_code == 201, retry.text


def test_dependency_owns_one_connection_and_closes(economics_chain_client):
    result = _prepare(economics_chain_client)
    dependency = web_module.get_goods_receipt_entry()
    entry = next(dependency)
    repository = entry._owner._repository
    assert repository._purchase._connection is repository._connection
    assert repository._purchase._execution._connection is repository._connection
    dependency.close()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        repository._connection.execute("SELECT 1")
