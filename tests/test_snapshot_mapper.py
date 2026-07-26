from datetime import datetime, timezone

from decimal import Decimal

from market_data.snapshot_mapper import (
    price_history_to_price_snapshot,
)
from storage.price_history import (
    PriceHistoryRecord,
)


def create_price_history_record() -> PriceHistoryRecord:
    return PriceHistoryRecord(
        id=1,
        marketplace="ebay",
        item_id="item_001",
        title="Test Product",
        price=99.99,
        currency="USD",
        condition="new",
        url="https://example.com/item/001",
        observed_at=datetime.now(timezone.utc),
        canonical_product_id="product_001",
        seller_id="seller_001",
    )


def test_price_history_to_price_snapshot():
    record = create_price_history_record()

    snapshot = price_history_to_price_snapshot(
        record
    )

    assert snapshot.snapshot_id == (
        "price_history_1"
    )

    assert snapshot.canonical_product_id == (
        "product_001"
    )

    assert snapshot.marketplace == "ebay"

    assert snapshot.item_id == "item_001"

    assert snapshot.price == Decimal("99.99")

    assert snapshot.currency == "USD"

    assert snapshot.condition == "new"

    assert snapshot.seller_id == "seller_001"


def test_price_history_price_converted_to_decimal():
    record = create_price_history_record()

    snapshot = price_history_to_price_snapshot(
        record
    )

    assert isinstance(
        snapshot.price,
        Decimal,
    )