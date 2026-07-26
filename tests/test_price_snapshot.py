from datetime import datetime, timezone
from decimal import Decimal

import pytest

from market_data.price_snapshot import PriceSnapshot


def create_price_snapshot() -> PriceSnapshot:
    return PriceSnapshot(
        snapshot_id="snap_price_001",
        canonical_product_id="product_001",
        marketplace=" ebay ",
        observed_at=datetime.now(timezone.utc),
        source_url=" https://example.com/item/001 ",
        item_id="item_001",
        price=Decimal("99.99"),
        currency=" usd ",
        condition=" new ",
        seller_id=" seller001 ",
    )


def test_price_snapshot_creation():
    snapshot = create_price_snapshot()

    assert snapshot.snapshot_id == "snap_price_001"
    assert snapshot.item_id == "item_001"
    assert snapshot.price == Decimal("99.99")
    assert snapshot.currency == "USD"
    assert snapshot.condition == "new"


def test_price_snapshot_normalizes_fields():
    snapshot = create_price_snapshot()

    assert snapshot.marketplace == "ebay"
    assert snapshot.currency == "USD"
    assert snapshot.seller_id == "seller001"


def test_price_snapshot_is_immutable():
    snapshot = create_price_snapshot()

    with pytest.raises(AttributeError):
        snapshot.price = Decimal("120.00")


@pytest.mark.parametrize(
    "field",
    [
        "item_id",
        "currency",
        "condition",
    ],
)
def test_price_snapshot_required_fields(field):
    values = {
        "snapshot_id": "snap_price_001",
        "canonical_product_id": "product_001",
        "marketplace": "ebay",
        "observed_at": datetime.now(timezone.utc),
        "source_url": "https://example.com/item/001",
        "item_id": "item_001",
        "price": Decimal("99.99"),
        "currency": "USD",
        "condition": "new",
    }

    values[field] = ""

    with pytest.raises(ValueError):
        PriceSnapshot(**values)


def test_price_snapshot_rejects_negative_price():
    with pytest.raises(ValueError):
        PriceSnapshot(
            snapshot_id="snap_price_001",
            canonical_product_id="product_001",
            marketplace="ebay",
            observed_at=datetime.now(timezone.utc),
            source_url="https://example.com/item/001",
            item_id="item_001",
            price=Decimal("-1"),
            currency="USD",
            condition="new",
        )