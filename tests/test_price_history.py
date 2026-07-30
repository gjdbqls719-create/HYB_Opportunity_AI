from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier

import pytest

from app.models import Product
from storage.price_history import (
    PriceObservationConflictError,
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

def test_save_and_read_canonical_price_history(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)

    ebay_product = make_product(
        item_id="EBAY-001",
        marketplace="ebay",
        price=100.0,
    )
    amazon_product = make_product(
        item_id="AMAZON-001",
        marketplace="amazon",
        price=95.0,
    )

    repository.save_product_price(
        ebay_product,
        canonical_product_id="CP-000001",
        observed_at=datetime(2026, 7, 20, tzinfo=timezone.utc),
    )
    repository.save_product_price(
        amazon_product,
        canonical_product_id="CP-000001",
        observed_at=datetime(2026, 7, 21, tzinfo=timezone.utc),
    )

    history = repository.get_canonical_history(
        canonical_product_id="CP-000001",
    )

    assert len(history) == 2
    assert history[0].marketplace == "amazon"
    assert history[0].canonical_product_id == "CP-000001"
    assert history[1].marketplace == "ebay"


def test_existing_database_is_migrated_without_data_loss(
    tmp_path: Path,
) -> None:
    import sqlite3

    database_path = tmp_path / "legacy_price_history.db"

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE price_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                marketplace TEXT NOT NULL,
                item_id TEXT NOT NULL,
                title TEXT NOT NULL,
                price REAL NOT NULL,
                currency TEXT NOT NULL,
                condition TEXT NOT NULL,
                url TEXT NOT NULL,
                observed_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO price_history (
                marketplace,
                item_id,
                title,
                price,
                currency,
                condition,
                url,
                observed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "ebay",
                "LEGACY-001",
                "Legacy Product",
                50.0,
                "USD",
                "New",
                "https://example.com/legacy",
                "2026-07-20T00:00:00+00:00",
            ),
        )
        connection.commit()

    repository = PriceHistoryRepository(database_path=database_path)
    records = repository.get_all_records()

    assert len(records) == 1
    assert records[0].item_id == "LEGACY-001"
    assert records[0].canonical_product_id is None
    assert records[0].seller_id is None


def test_seller_is_preserved_in_price_snapshot(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)
    product = Product(
        marketplace="ebay",
        item_id="SELLER-001",
        title="Seller Product",
        price=75.0,
        currency="USD",
        condition="New",
        url="https://example.com/seller-product",
        seller="seller-123",
    )

    repository.save_product_price(
        product,
        canonical_product_id="CP-000002",
    )

    record = repository.get_latest_canonical_record(
        canonical_product_id="CP-000002",
    )

    assert record is not None
    assert record.seller_id == "seller-123"


def test_same_observation_returns_existing_record_id(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)
    product = make_product(price=100.0)
    observed_at = datetime(2026, 7, 31, tzinfo=timezone.utc)

    first_id = repository.save_product_price(
        product,
        observed_at=observed_at,
        canonical_product_id="CP-IDEMPOTENT",
    )
    second_id = repository.save_product_price(
        product,
        observed_at=observed_at,
        canonical_product_id="CP-IDEMPOTENT",
    )

    assert second_id == first_id
    assert repository.count_records() == 1


def test_same_observation_identity_with_different_data_conflicts(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)
    observed_at = datetime(2026, 7, 31, tzinfo=timezone.utc)
    original = make_product(price=100.0)
    conflicting = make_product(price=80.0)

    original_id = repository.save_product_price(
        original,
        observed_at=observed_at,
        canonical_product_id="CP-CONFLICT",
    )

    with pytest.raises(PriceObservationConflictError):
        repository.save_product_price(
            conflicting,
            observed_at=observed_at,
            canonical_product_id="CP-CONFLICT",
        )

    records = repository.get_all_records()
    assert len(records) == 1
    assert records[0].id == original_id
    assert records[0].price == 100.0


def test_same_price_at_different_observation_time_is_appended(
    tmp_path: Path,
) -> None:
    repository = make_repository(tmp_path)
    product = make_product(price=100.0)

    first_id = repository.save_product_price(
        product,
        observed_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
        canonical_product_id="CP-TIMES",
    )
    second_id = repository.save_product_price(
        product,
        observed_at=datetime(2026, 7, 31, tzinfo=timezone.utc),
        canonical_product_id="CP-TIMES",
    )

    assert second_id != first_id
    assert repository.count_records() == 2


@pytest.mark.parametrize(
    ("canonical_product_id", "marketplace", "item_id"),
    [
        ("CP-OTHER", "test-market", "TEST-001"),
        ("CP-IDENTITY", "other-market", "TEST-001"),
        ("CP-IDENTITY", "test-market", "OTHER-ITEM"),
    ],
)
def test_different_observation_identity_is_appended(
    tmp_path: Path,
    canonical_product_id: str,
    marketplace: str,
    item_id: str,
) -> None:
    repository = make_repository(tmp_path)
    observed_at = datetime(2026, 7, 31, tzinfo=timezone.utc)
    repository.save_product_price(
        make_product(),
        observed_at=observed_at,
        canonical_product_id="CP-IDENTITY",
    )

    repository.save_product_price(
        make_product(
            marketplace=marketplace,
            item_id=item_id,
        ),
        observed_at=observed_at,
        canonical_product_id=canonical_product_id,
    )

    assert repository.count_records() == 2


def test_concurrent_same_observation_is_recorded_once(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "concurrent.db"
    first_repository = PriceHistoryRepository(database_path)
    second_repository = PriceHistoryRepository(database_path)
    product = make_product(price=100.0)
    observed_at = datetime(2026, 7, 31, tzinfo=timezone.utc)
    barrier = Barrier(2)

    def save(repository: PriceHistoryRepository) -> int:
        barrier.wait()
        return repository.save_product_price(
            product,
            observed_at=observed_at,
            canonical_product_id="CP-CONCURRENT",
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(save, first_repository)
        second_future = executor.submit(save, second_repository)
        record_ids = {
            first_future.result(),
            second_future.result(),
        }

    assert len(record_ids) == 1
    assert first_repository.count_records() == 1
