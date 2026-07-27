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
        item_id="price-save-001",
        title="Price Save Product",
        price=price,
        currency="USD",
        condition="New",
        url="https://example.com/price-save-001",
        seller="seller-001",
    )


def patch_search(
    monkeypatch,
    *,
    product: Product,
) -> None:
    monkeypatch.setattr(
        "engine.orchestrator.search_products",
        lambda query, limit: [product],
    )


def test_first_observation_is_saved_after_empty_detection(
    monkeypatch,
    tmp_path,
) -> None:
    current_product = make_product(price=80.0)
    repository = PriceHistoryRepository(
        tmp_path / "price_history.db"
    )
    patch_search(
        monkeypatch,
        product=current_product,
    )

    result = find_best_opportunities(
        query="first observation",
        price_history_repository=repository,
    )[0]

    assert result.price_change_detection is not None
    assert (
        result.price_change_detection.compared_pair_count
        == 0
    )
    assert result.price_history_record_id is not None
    assert repository.count_records() == 1

    saved = repository.get_latest_record(
        marketplace=current_product.marketplace,
        item_id=current_product.item_id,
    )

    assert saved is not None
    assert saved.id == result.price_history_record_id
    assert saved.price == 80.0
    assert (
        saved.canonical_product_id
        == current_product.item_id
    )
    assert saved.seller_id == "seller-001"


def test_change_detection_runs_before_current_snapshot_save(
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
    patch_search(
        monkeypatch,
        product=current_product,
    )

    result = find_best_opportunities(
        query="changed price",
        price_history_repository=repository,
    )[0]

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
    assert repository.count_records() == 2

    history = repository.get_product_history(
        marketplace=current_product.marketplace,
        item_id=current_product.item_id,
    )

    assert history[0].price == 80.0
    assert history[1].price == 100.0


def test_saved_snapshot_becomes_previous_on_next_run(
    monkeypatch,
    tmp_path,
) -> None:
    repository = PriceHistoryRepository(
        tmp_path / "price_history.db"
    )

    first_product = make_product(price=100.0)
    patch_search(
        monkeypatch,
        product=first_product,
    )
    first_result = find_best_opportunities(
        query="first run",
        price_history_repository=repository,
    )[0]

    assert first_result.price_change_detection is not None
    assert (
        first_result.price_change_detection.compared_pair_count
        == 0
    )

    second_product = make_product(price=90.0)
    patch_search(
        monkeypatch,
        product=second_product,
    )
    second_result = find_best_opportunities(
        query="second run",
        price_history_repository=repository,
    )[0]

    assert second_result.price_change_detection is not None
    assert (
        second_result.price_change_detection.compared_pair_count
        == 1
    )
    assert (
        second_result.price_change_detection.changed_pair_count
        == 1
    )
    assert repository.count_records() == 2


def test_no_repository_means_no_detection_and_no_save(
    monkeypatch,
) -> None:
    current_product = make_product(price=80.0)
    patch_search(
        monkeypatch,
        product=current_product,
    )

    result = find_best_opportunities(
        query="no repository",
    )[0]

    assert result.price_change_detection is None
    assert result.price_history_record_id is None
