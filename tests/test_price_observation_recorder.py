from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.infrastructure.watchlist.price_observation_recorder import (
    PriceHistoryObservationRecorder,
)
from app.models import Product
from market_data.price_snapshot import PriceSnapshot
from storage.price_history import PriceHistoryRepository


OBSERVED_AT = datetime(2026, 7, 31, tzinfo=timezone.utc)


def make_product() -> Product:
    return Product(
        marketplace="ebay",
        item_id="item-1",
        title="Observed Product",
        price=80.0,
        currency="USD",
        condition="New",
        url="https://example.com/item-1",
        seller="product-seller",
    )


def make_snapshot() -> PriceSnapshot:
    return PriceSnapshot(
        snapshot_id="snapshot-1",
        canonical_product_id="canonical-1",
        marketplace="ebay",
        observed_at=OBSERVED_AT,
        source_url="https://example.com/item-1",
        item_id="item-1",
        price=Decimal("80.0"),
        currency="USD",
        condition="New",
        seller_id="snapshot-seller",
    )


def test_recorder_appends_observation_with_snapshot_metadata(
    tmp_path,
) -> None:
    repository = PriceHistoryRepository(tmp_path / "recorder.db")
    recorder = PriceHistoryObservationRecorder(repository=repository)
    product = make_product()
    snapshot = make_snapshot()

    record_id = recorder.record_observation(
        product=product,
        snapshot=snapshot,
    )

    record = repository.get_latest_record(
        marketplace="ebay",
        item_id="item-1",
    )
    assert record is not None
    assert record_id == record.id
    assert record.title == product.title
    assert record.price == product.price
    assert record.observed_at == OBSERVED_AT.isoformat()
    assert record.canonical_product_id == "canonical-1"
    assert record.seller_id == "snapshot-seller"


def test_recorder_returns_existing_id_for_idempotent_retry(
    tmp_path,
) -> None:
    repository = PriceHistoryRepository(tmp_path / "retry.db")
    recorder = PriceHistoryObservationRecorder(repository=repository)
    product = make_product()
    snapshot = make_snapshot()

    first_id = recorder.record_observation(
        product=product,
        snapshot=snapshot,
    )
    second_id = recorder.record_observation(
        product=product,
        snapshot=snapshot,
    )

    assert second_id == first_id
    assert repository.count_records() == 1


def test_recorder_propagates_repository_error(tmp_path) -> None:
    class FailingPriceHistoryRepository(PriceHistoryRepository):
        def save_product_price(self, *args, **kwargs) -> int:
            raise RuntimeError("save failed")

    recorder = PriceHistoryObservationRecorder(
        repository=FailingPriceHistoryRepository(
            tmp_path / "failing.db"
        )
    )

    with pytest.raises(RuntimeError, match="save failed"):
        recorder.record_observation(
            product=make_product(),
            snapshot=make_snapshot(),
        )
