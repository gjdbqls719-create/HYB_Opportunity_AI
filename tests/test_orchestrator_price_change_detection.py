from __future__ import annotations

from datetime import datetime, timezone

from app.models import Product
from engine.orchestrator import find_best_opportunities
from storage.price_history import PriceHistoryRepository


def make_product(
    *,
    price: float,
) -> Product:
    return Product(
        marketplace="ebay",
        item_id="price-change-001",
        title="Price Change Product",
        price=price,
        currency="USD",
        condition="New",
        url="https://example.com/price-change-001",
        seller="seller-001",
    )


def test_find_best_opportunities_detects_latest_price_change(
    monkeypatch,
    tmp_path,
) -> None:
    previous_product = make_product(price=100.0)
    current_product = make_product(price=80.0)

    repository = PriceHistoryRepository(
        tmp_path / "price_history.db"
    )
    repository.save_product_price(
        previous_product,
        observed_at=datetime(
            2025,
            1,
            1,
            tzinfo=timezone.utc,
        ),
        canonical_product_id=(
            previous_product.item_id
        ),
    )

    monkeypatch.setattr(
        "engine.orchestrator.search_products",
        lambda query, limit: [current_product],
    )

    result = find_best_opportunities(
        query="price change",
        price_history_repository=repository,
    )[0]

    assert result.price_snapshot is not None
    assert result.price_change_detection is not None
    assert (
        result.price_change_detection.compared_pair_count
        == 1
    )
    assert (
        result.price_change_detection.changed_pair_count
        == 1
    )
    assert result.price_change_detection.has_changes is True
    assert result.price_change_detection.change_count >= 1


def test_find_best_opportunities_treats_missing_history_as_first_observation(
    monkeypatch,
    tmp_path,
) -> None:
    current_product = make_product(price=80.0)

    repository = PriceHistoryRepository(
        tmp_path / "price_history.db"
    )

    monkeypatch.setattr(
        "engine.orchestrator.search_products",
        lambda query, limit: [current_product],
    )

    result = find_best_opportunities(
        query="first observation",
        price_history_repository=repository,
    )[0]

    assert result.price_snapshot is not None
    assert result.price_change_detection is not None
    assert (
        result.price_change_detection.compared_pair_count
        == 0
    )
    assert result.price_change_detection.has_changes is False


def test_find_best_opportunities_skips_change_detection_without_repository(
    monkeypatch,
) -> None:
    current_product = make_product(price=80.0)

    monkeypatch.setattr(
        "engine.orchestrator.search_products",
        lambda query, limit: [current_product],
    )

    result = find_best_opportunities(
        query="without repository",
    )[0]

    assert result.price_snapshot is not None
    assert result.price_change_detection is None
