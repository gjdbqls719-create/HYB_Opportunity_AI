from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from app.infrastructure.change import (
    PriceHistorySnapshotProvider,
)
from app.models import Product
from market_data.price_snapshot import PriceSnapshot
from market_data.snapshot_mapper import (
    price_history_to_price_snapshot,
)
from storage.price_history import (
    PriceHistoryRecord,
    PriceHistoryRepository,
)


OBSERVED_AT = datetime(
    2026,
    7,
    27,
    12,
    0,
    tzinfo=timezone.utc,
)


def make_product(
    *,
    item_id: str = "item_001",
    price: float = 100.0,
) -> Product:
    return Product(
        marketplace="ebay",
        item_id=item_id,
        title=f"Product {item_id}",
        price=price,
        currency="USD",
        condition="new",
        url=f"https://example.com/{item_id}",
        seller="seller_001",
    )


def make_record(
    *,
    record_id: int = 1,
    canonical_product_id: str | None = "canonical_001",
    observed_at: str = "2026-07-27T12:00:00+00:00",
) -> PriceHistoryRecord:
    return PriceHistoryRecord(
        id=record_id,
        canonical_product_id=canonical_product_id,
        marketplace="ebay",
        item_id="item_001",
        seller_id="seller_001",
        title="Product item_001",
        price=100.25,
        currency="usd",
        condition="new",
        url="https://example.com/item_001",
        observed_at=observed_at,
    )


def make_repository(
    database_path: Path,
) -> PriceHistoryRepository:
    return PriceHistoryRepository(
        database_path=database_path,
    )


def test_mapper_converts_storage_record_to_snapshot() -> None:
    snapshot = price_history_to_price_snapshot(
        make_record()
    )

    assert isinstance(snapshot, PriceSnapshot)
    assert snapshot.snapshot_id == "price_history_1"
    assert snapshot.canonical_product_id == "canonical_001"
    assert snapshot.marketplace == "ebay"
    assert snapshot.item_id == "item_001"
    assert snapshot.price == Decimal("100.25")
    assert snapshot.currency == "USD"
    assert snapshot.seller_id == "seller_001"
    assert snapshot.observed_at == OBSERVED_AT


def test_mapper_accepts_utc_z_suffix() -> None:
    snapshot = price_history_to_price_snapshot(
        make_record(
            observed_at="2026-07-27T12:00:00Z",
        )
    )

    assert snapshot.observed_at == OBSERVED_AT


def test_mapper_normalizes_naive_time_to_utc() -> None:
    snapshot = price_history_to_price_snapshot(
        make_record(
            observed_at="2026-07-27T12:00:00",
        )
    )

    assert snapshot.observed_at == OBSERVED_AT
    assert snapshot.observed_at.tzinfo is timezone.utc


def test_mapper_rejects_invalid_observed_at() -> None:
    with pytest.raises(
        ValueError,
        match="ISO 8601",
    ):
        price_history_to_price_snapshot(
            make_record(
                observed_at="not-a-datetime",
            )
        )


def test_mapper_requires_canonical_product_id() -> None:
    with pytest.raises(
        ValueError,
        match="canonical_product_id",
    ):
        price_history_to_price_snapshot(
            make_record(
                canonical_product_id=None,
            )
        )


def test_mapper_rejects_wrong_record_type() -> None:
    with pytest.raises(
        TypeError,
        match="PriceHistoryRecord",
    ):
        price_history_to_price_snapshot(
            "invalid",  # type: ignore[arg-type]
        )


def test_provider_exposes_required_port_methods(
    tmp_path: Path,
) -> None:
    provider = PriceHistorySnapshotProvider(
        repository=make_repository(
            tmp_path / "history.db"
        )
    )

    assert callable(
        provider.get_latest_for_listing
    )
    assert callable(
        provider.get_latest_for_canonical_product
    )


def test_provider_returns_none_when_listing_is_missing(
    tmp_path: Path,
) -> None:
    provider = PriceHistorySnapshotProvider(
        repository=make_repository(
            tmp_path / "history.db"
        )
    )

    snapshot = provider.get_latest_for_listing(
        marketplace="ebay",
        item_id="missing",
    )

    assert snapshot is None


def test_provider_returns_latest_listing_snapshot(
    tmp_path: Path,
) -> None:
    repository = make_repository(
        tmp_path / "history.db"
    )
    product = make_product()

    repository.save_product_price(
        product,
        observed_at=datetime(
            2026,
            7,
            27,
            10,
            0,
            tzinfo=timezone.utc,
        ),
        canonical_product_id="canonical_001",
    )

    repository.save_product_price(
        Product(
            marketplace=product.marketplace,
            item_id=product.item_id,
            title=product.title,
            price=80.0,
            currency=product.currency,
            condition=product.condition,
            url=product.url,
            seller=product.seller,
        ),
        observed_at=OBSERVED_AT,
        canonical_product_id="canonical_001",
    )

    provider = PriceHistorySnapshotProvider(
        repository=repository
    )

    snapshot = provider.get_latest_for_listing(
        marketplace=" ebay ",
        item_id=" item_001 ",
    )

    assert snapshot is not None
    assert snapshot.price == Decimal("80.0")
    assert snapshot.observed_at == OBSERVED_AT
    assert snapshot.canonical_product_id == "canonical_001"


def test_provider_returns_latest_canonical_snapshot(
    tmp_path: Path,
) -> None:
    repository = make_repository(
        tmp_path / "history.db"
    )

    repository.save_product_price(
        make_product(
            item_id="item_001",
            price=100.0,
        ),
        observed_at=datetime(
            2026,
            7,
            27,
            10,
            0,
            tzinfo=timezone.utc,
        ),
        canonical_product_id="canonical_001",
    )

    repository.save_product_price(
        make_product(
            item_id="item_002",
            price=90.0,
        ),
        observed_at=OBSERVED_AT,
        canonical_product_id="canonical_001",
    )

    provider = PriceHistorySnapshotProvider(
        repository=repository
    )

    snapshot = (
        provider.get_latest_for_canonical_product(
            canonical_product_id=" canonical_001 "
        )
    )

    assert snapshot is not None
    assert snapshot.item_id == "item_002"
    assert snapshot.price == Decimal("90.0")
    assert snapshot.observed_at == OBSERVED_AT


@pytest.mark.parametrize(
    ("method_name", "arguments"),
    [
        (
            "get_latest_for_listing",
            {
                "marketplace": " ",
                "item_id": "item_001",
            },
        ),
        (
            "get_latest_for_listing",
            {
                "marketplace": "ebay",
                "item_id": " ",
            },
        ),
        (
            "get_latest_for_canonical_product",
            {
                "canonical_product_id": " ",
            },
        ),
    ],
)
def test_provider_rejects_blank_identifiers(
    tmp_path: Path,
    method_name: str,
    arguments: dict[str, str],
) -> None:
    provider = PriceHistorySnapshotProvider(
        repository=make_repository(
            tmp_path / "history.db"
        )
    )

    method = getattr(provider, method_name)

    with pytest.raises(ValueError):
        method(**arguments)


def test_provider_rejects_invalid_repository() -> None:
    with pytest.raises(
        TypeError,
        match="PriceHistoryRepository",
    ):
        PriceHistorySnapshotProvider(
            repository=object(),  # type: ignore[arg-type]
        )


def test_provider_rejects_invalid_mapper(
    tmp_path: Path,
) -> None:
    with pytest.raises(
        TypeError,
        match="mapper",
    ):
        PriceHistorySnapshotProvider(
            repository=make_repository(
                tmp_path / "history.db"
            ),
            mapper=None,  # type: ignore[arg-type]
        )


def test_provider_rejects_mapper_wrong_return_type(
    tmp_path: Path,
) -> None:
    repository = make_repository(
        tmp_path / "history.db"
    )

    repository.save_product_price(
        make_product(),
        observed_at=OBSERVED_AT,
        canonical_product_id="canonical_001",
    )

    provider = PriceHistorySnapshotProvider(
        repository=repository,
        mapper=lambda _: "invalid",  # type: ignore[arg-type]
    )

    with pytest.raises(
        TypeError,
        match="PriceSnapshot",
    ):
        provider.get_latest_for_listing(
            marketplace="ebay",
            item_id="item_001",
        )