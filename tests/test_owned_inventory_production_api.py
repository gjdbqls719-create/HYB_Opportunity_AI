from copy import deepcopy
from datetime import timedelta
import sqlite3

from fastapi.testclient import TestClient
import pytest

import app.web as web_module
from app.application.owned_inventory import (
    GetOwnedInventoryPositions,
    OwnedInventoryOpportunityNotFoundError,
)
from app.infrastructure.goods_receipt import (
    GoodsReceiptHistoryError,
    SQLiteGoodsReceiptRepository,
)
from app.web import app
from test_goods_receipt_production_api import _payload, _prepare
from test_o2_economics_production_chain_api import economics_chain_client
from test_owned_inventory import MemoryOwnedInventoryRepository, O2, NOW, _receipt


def _route(opportunity_id: str) -> str:
    return f"/api/v1/opportunities/{opportunity_id}/owned-inventory"


def test_get_empty_then_partial_damaged_projection_and_restart_rebuild(
    economics_chain_client,
):
    result = _prepare(economics_chain_client, quantity=100)
    route = _route(result["opportunity_id"])
    empty = result["client"].get(route)
    assert empty.status_code == 200, empty.text
    assert empty.json() == {
        "opportunity_id": result["opportunity_id"],
        "positions": [],
        "position_count": 0,
    }

    first_payload = _payload(
        result["purchase"],
        received_quantity=60,
        sellable_quantity=58,
        damaged_quantity=2,
    )
    first = result["client"].post(result["receipt_route"], json=first_payload)
    assert first.status_code == 201, first.text
    second_payload = _payload(
        result["purchase"],
        command_id="goods-receipt-command-2",
        received_quantity=40,
        sellable_quantity=40,
        damaged_quantity=0,
    )
    second_payload["evidence_references"][0]["reference"] = "artifact://receipt/2"
    second = result["client"].post(result["receipt_route"], json=second_payload)
    assert second.status_code == 201, second.text

    populated = result["client"].get(route)
    assert populated.status_code == 200, populated.text
    body = populated.json()
    assert body["opportunity_id"] == result["opportunity_id"]
    assert body["position_count"] == 1
    position = body["positions"][0]
    assert position["total_received"] == 100
    assert position["total_sellable_received"] == 98
    assert position["total_damaged_received"] == 2
    assert position["total_outbound_quantity"] == 0
    assert position["sellable_on_hand"] == 98
    assert position["quantity_unit"] == result["purchase"]["actual_quantity_unit"]
    assert position["contributing_purchase_execution_ids"] == [
        result["purchase"]["record_id"]
    ]
    assert position["contributing_goods_receipt_ids"] == sorted(
        [first.json()["record_id"], second.json()["record_id"]]
    )
    assert position["source_event_count"] == 2
    assert position["policy_name"] == "receipt-derived-owned-inventory"
    assert position["policy_version"] == "1.0.0"
    assert position["schema_version"] == "owned-inventory-position-v1"
    assert isinstance(position["sellable_on_hand"], int)
    assert "available" not in position
    assert not any("amount" in key for key in position)

    restarted = TestClient(app).get(route)
    assert restarted.status_code == 200, restarted.text
    assert restarted.json() == body
    with sqlite3.connect(result["database"]) as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert not {
        name
        for name in names
        if "owned_inventory" in name or "inventory_balance" in name
    }


def test_get_missing_opportunity_is_404(economics_chain_client):
    result = _prepare(economics_chain_client)

    response = result["client"].get(_route("missing-o2"))

    assert response.status_code == 404
    assert response.json() == {"detail": "opportunity not found"}


def test_get_multiple_product_positions_are_not_merged_and_are_deterministic():
    records = (
        _receipt("receipt-sku-b", sku_reference="sku-b", received=7, sellable=7),
        _receipt("receipt-sku-a", sku_reference="sku-a", received=3, sellable=3),
    )
    query = GetOwnedInventoryPositions(MemoryOwnedInventoryRepository(records))
    app.dependency_overrides[web_module.get_owned_inventory_query] = lambda: query
    try:
        first = TestClient(app).get(_route(O2.opportunity_id))
        second = TestClient(app).get(_route(O2.opportunity_id))
    finally:
        app.dependency_overrides.pop(web_module.get_owned_inventory_query, None)

    assert first.status_code == 200, first.text
    assert second.json() == first.json()
    positions = first.json()["positions"]
    assert len(positions) == 2
    assert [value["product_key"]["sku_reference"] for value in positions] == [
        "sku-a",
        "sku-b",
    ]
    assert [value["sellable_on_hand"] for value in positions] == [3, 7]


def test_get_source_order_uses_received_time_then_record_id():
    same_time_b = _receipt("receipt-b", received=2, sellable=2)
    same_time_a = _receipt("receipt-a", received=3, sellable=3)
    later = _receipt(
        "receipt-c", received=4, sellable=4, received_at=NOW + timedelta(minutes=1)
    )
    query = GetOwnedInventoryPositions(
        MemoryOwnedInventoryRepository((later, same_time_b, same_time_a))
    )
    app.dependency_overrides[web_module.get_owned_inventory_query] = lambda: query
    try:
        response = TestClient(app).get(_route(O2.opportunity_id))
    finally:
        app.dependency_overrides.pop(web_module.get_owned_inventory_query, None)

    assert response.status_code == 200, response.text
    assert response.json()["positions"][0]["contributing_goods_receipt_ids"] == [
        "receipt-a",
        "receipt-b",
        "receipt-c",
    ]


def test_get_infrastructure_failure_is_bounded_503_and_closes_connection(
    economics_chain_client, monkeypatch
):
    result = _prepare(economics_chain_client)
    captured = []
    real_repository = SQLiteGoodsReceiptRepository

    class FailingRepository(real_repository):
        def __init__(self, value):
            super().__init__(value)
            captured.append(self)

        def list_goods_receipts_for_opportunity(self, _opportunity_id):
            raise GoodsReceiptHistoryError("private sqlite detail")

    monkeypatch.setattr(web_module, "SQLiteGoodsReceiptRepository", FailingRepository)
    response = result["client"].get(_route(result["opportunity_id"]))

    assert response.status_code == 503
    assert "private sqlite" not in response.text
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0]._connection.execute("SELECT 1")


def test_get_partial_composition_conflict_is_409_and_closes_connection(
    economics_chain_client, monkeypatch
):
    result = _prepare(economics_chain_client)
    captured = []
    real_repository = SQLiteGoodsReceiptRepository

    class ConflictingRepository(real_repository):
        def __init__(self, value):
            super().__init__(value)
            captured.append(self)

        def list_goods_receipts_for_opportunity(self, _opportunity_id):
            return (_receipt("conflicting-receipt", identity=O2),)

    monkeypatch.setattr(web_module, "SQLiteGoodsReceiptRepository", ConflictingRepository)
    response = result["client"].get(_route(result["opportunity_id"]))

    assert response.status_code == 409
    assert response.json() == {"detail": "Owned Inventory source conflict"}
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        captured[0]._connection.execute("SELECT 1")


@pytest.mark.parametrize("mode", ("success", "empty", "missing"))
def test_get_dependency_owned_connection_closes(economics_chain_client, mode):
    result = _prepare(economics_chain_client)
    if mode == "success":
        payload = deepcopy(_payload(result["purchase"]))
        assert result["client"].post(result["receipt_route"], json=payload).status_code == 201
    dependency = web_module.get_owned_inventory_query()
    query = next(dependency)
    repository = query._repository
    if mode == "missing":
        with pytest.raises(OwnedInventoryOpportunityNotFoundError):
            query.execute("missing-o2")
    else:
        query.execute(result["opportunity_id"])
    dependency.close()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        repository._connection.execute("SELECT 1")
