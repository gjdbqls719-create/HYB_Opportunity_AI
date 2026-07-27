from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.models import Product
from engine.orchestrator import build_price_snapshot
from market_data.price_snapshot import PriceSnapshot


OBSERVED_AT = datetime(
    2026,
    7,
    27,
    13,
    0,
    tzinfo=timezone.utc,
)


def make_product(
    *,
    condition: str = "New",
    seller: str = "seller_001",
    url: str | None = "https://example.com/item_001",
) -> Product:
    return Product(
        marketplace="ebay",
        item_id="item_001",
        title="Test Product",
        price=99.95,
        currency="usd",
        condition=condition,
        url=url,
        seller=seller,
    )


def test_build_price_snapshot_maps_product_fields() -> None:
    snapshot = build_price_snapshot(
        product=make_product(),
        observed_at=OBSERVED_AT,
    )

    assert isinstance(snapshot, PriceSnapshot)
    assert snapshot.snapshot_id.startswith(
        "price_ebay_item_001_"
    )
    assert snapshot.canonical_product_id == "item_001"
    assert snapshot.marketplace == "ebay"
    assert snapshot.observed_at == OBSERVED_AT
    assert snapshot.source_url == (
        "https://example.com/item_001"
    )
    assert snapshot.item_id == "item_001"
    assert snapshot.price == Decimal("99.95")
    assert snapshot.currency == "USD"
    assert snapshot.condition == "New"
    assert snapshot.seller_id == "seller_001"


def test_build_price_snapshot_uses_safe_fallbacks() -> None:
    snapshot = build_price_snapshot(
        product=make_product(
            condition="   ",
            seller="   ",
            url=None,
        ),
        observed_at=OBSERVED_AT,
    )

    assert snapshot.condition == "unknown"
    assert snapshot.seller_id is None
    assert snapshot.source_url == "unknown://source"


def test_build_price_snapshot_generates_unique_ids() -> None:
    product = make_product()

    first = build_price_snapshot(
        product=product,
        observed_at=OBSERVED_AT,
    )
    second = build_price_snapshot(
        product=product,
        observed_at=OBSERVED_AT,
    )

    assert first.snapshot_id != second.snapshot_id
