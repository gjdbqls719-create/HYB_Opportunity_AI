from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.models import Product
from storage.price_history import (
    PriceHistoryRepository,
)


def make_product(
    *,
    item_id: str = "TEST-001",
    title: str = "Test Product",
    price: float = 100.0,
    marketplace: str = "test-market",
) -> Product:
    return Product(
        marketplace=marketplace,
        item_id=item_id,
        title=title,
        price=price,
        currency="USD",
        condition="New",
        url=(
            "https://example.com/products/"
            f"{item_id}"
        ),
    )


def make_repository(
    tmp_path: Path,
) -> PriceHistoryRepository:
    database_path = (
        tmp_path
        / "test_price_history.db"
    )

    return PriceHistoryRepository(
        database_path=database_path,
    )


def test_database_is_created(
    tmp_path: Path,
) -> None:
    database_path = (
        tmp_path
        / "nested"
        / "price_history.db"
    )

    PriceHistoryRepository(
        database_path=database_path,
    )

    assert database_path.exists()


def test_save_and_read_product_price(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)

    product = make_product(
        price=129.99,
    )

    observed_at = datetime(
        2026,
        7,
        21,
        10,
        30,
        tzinfo=timezone.utc,
    )

    record_id = repository.save_product_price(
        product,
        observed_at=observed_at,
    )

    history = repository.get_product_history(
        marketplace=product.marketplace,
        item_id=product.item_id,
    )

    assert record_id > 0
    assert len(history) == 1

    record = history[0]

    assert record.item_id == "TEST-001"
    assert record.title == "Test Product"
    assert record.price == 129.99
    assert record.currency == "USD"
    assert record.observed_at == (
        observed_at.isoformat()
    )


def test_history_is_returned_in_latest_order(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)

    product_old = make_product(
        price=120.0,
    )

    product_new = make_product(
        price=99.0,
    )

    repository.save_product_price(
        product_old,
        observed_at=datetime(
            2026,
            7,
            20,
            tzinfo=timezone.utc,
        ),
    )

    repository.save_product_price(
        product_new,
        observed_at=datetime(
            2026,
            7,
            21,
            tzinfo=timezone.utc,
        ),
    )

    history = repository.get_product_history(
        marketplace="test-market",
        item_id="TEST-001",
    )

    assert len(history) == 2
    assert history[0].price == 99.0
    assert history[1].price == 120.0


def test_save_multiple_products(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)

    products = [
        make_product(
            item_id="ITEM-001",
            price=10.0,
        ),
        make_product(
            item_id="ITEM-002",
            price=20.0,
        ),
        make_product(
            item_id="ITEM-003",
            price=30.0,
        ),
    ]

    saved_count = repository.save_products(
        products,
    )

    assert saved_count == 3
    assert repository.count_records() == 3


def test_get_latest_record(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)

    product = make_product()

    repository.save_product_price(
        product,
        observed_at=datetime(
            2026,
            7,
            20,
            tzinfo=timezone.utc,
        ),
    )

    newer_product = make_product(
        price=88.0,
    )

    repository.save_product_price(
        newer_product,
        observed_at=datetime(
            2026,
            7,
            21,
            tzinfo=timezone.utc,
        ),
    )

    latest = repository.get_latest_record(
        marketplace=product.marketplace,
        item_id=product.item_id,
    )

    assert latest is not None
    assert latest.price == 88.0


def test_get_latest_record_returns_none(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)

    latest = repository.get_latest_record(
        marketplace="ebay",
        item_id="NOT-FOUND",
    )

    assert latest is None


def test_delete_all_records(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)

    repository.save_products(
        [
            make_product(
                item_id="ITEM-001",
            ),
            make_product(
                item_id="ITEM-002",
            ),
        ]
    )

    deleted_count = (
        repository.delete_all_records()
    )

    assert deleted_count == 2
    assert repository.count_records() == 0


def test_rejects_invalid_limit(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)

    with pytest.raises(ValueError):
        repository.get_product_history(
            marketplace="ebay",
            item_id="TEST-001",
            limit=0,
        )