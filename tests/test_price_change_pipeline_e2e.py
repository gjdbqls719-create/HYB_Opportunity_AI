from __future__ import annotations

from app.models import Product
from engine.orchestrator import find_best_opportunities
from storage.price_history import PriceHistoryRepository


ITEM_ID = "e2e-price-history-001"


def make_product(
    *,
    price: float,
) -> Product:
    return Product(
        marketplace="ebay",
        item_id=ITEM_ID,
        title="E2E Price History Product",
        price=price,
        currency="USD",
        condition="New",
        url=f"https://example.com/{ITEM_ID}",
        seller="seller-e2e",
    )


def set_search_result(
    monkeypatch,
    *,
    product: Product,
) -> None:
    monkeypatch.setattr(
        "engine.orchestrator.search_products",
        lambda query, limit: [product],
    )


def run_discovery(
    monkeypatch,
    *,
    repository: PriceHistoryRepository,
    price: float,
):
    product = make_product(price=price)
    set_search_result(
        monkeypatch,
        product=product,
    )

    results = find_best_opportunities(
        query="e2e price history",
        price_history_repository=repository,
    )

    assert len(results) == 1
    return results[0]


def test_price_change_pipeline_end_to_end(
    monkeypatch,
    tmp_path,
) -> None:
    """
    Discovery → PriceSnapshot → Change Detection
    → Append-Only Persistence 전체 흐름을 검증한다.

    1차 실행: 최초 관찰
    2차 실행: 가격 하락
    3차 실행: 가격 상승
    """
    repository = PriceHistoryRepository(
        tmp_path / "price_history_e2e.db"
    )

    first = run_discovery(
        monkeypatch,
        repository=repository,
        price=100.0,
    )

    assert first.price_snapshot is not None
    assert first.price_change_detection is not None
    assert (
        first.price_change_detection.compared_pair_count
        == 0
    )
    assert first.price_change_detection.has_changes is False
    assert first.price_history_record_id is not None
    assert repository.count_records() == 1

    second = run_discovery(
        monkeypatch,
        repository=repository,
        price=80.0,
    )

    assert second.price_snapshot is not None
    assert second.price_change_detection is not None
    assert (
        second.price_change_detection.compared_pair_count
        == 1
    )
    assert (
        second.price_change_detection.changed_pair_count
        == 1
    )
    assert second.price_change_detection.has_changes is True
    assert second.price_history_record_id is not None
    assert repository.count_records() == 2

    third = run_discovery(
        monkeypatch,
        repository=repository,
        price=120.0,
    )

    assert third.price_snapshot is not None
    assert third.price_change_detection is not None
    assert (
        third.price_change_detection.compared_pair_count
        == 1
    )
    assert (
        third.price_change_detection.changed_pair_count
        == 1
    )
    assert third.price_change_detection.has_changes is True
    assert third.price_history_record_id is not None
    assert repository.count_records() == 3

    latest = repository.get_latest_record(
        marketplace="ebay",
        item_id=ITEM_ID,
    )

    assert latest is not None
    assert latest.price == 120.0
    assert (
        latest.id
        == third.price_history_record_id
    )

    history = repository.get_product_history(
        marketplace="ebay",
        item_id=ITEM_ID,
    )

    assert len(history) == 3
    assert [record.price for record in history] == [
        120.0,
        80.0,
        100.0,
    ]

    assert len({
        first.price_history_record_id,
        second.price_history_record_id,
        third.price_history_record_id,
    }) == 3
