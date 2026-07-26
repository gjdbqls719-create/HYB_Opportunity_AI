from __future__ import annotations

from datetime import datetime, timezone

import pytest

from market_data.seller_snapshot import (
    SellerSnapshot,
)


def create_snapshot(
    *,
    seller_id: str | None = "seller_001",
    seller_rating: float | None = 4.8,
    seller_review_count: int | None = 120,
    seller_count: int = 3,
    is_verified: bool = True,
) -> SellerSnapshot:
    return SellerSnapshot(
        snapshot_id="snapshot_001",
        canonical_product_id="product_001",
        marketplace="ebay",
        observed_at=datetime(
            2026,
            7,
            26,
            tzinfo=timezone.utc,
        ),
        source_url="https://example.com/item",
        item_id="ITEM-001",
        seller_id=seller_id,
        seller_rating=seller_rating,
        seller_review_count=seller_review_count,
        seller_count=seller_count,
        is_verified=is_verified,
    )


def test_creates_seller_snapshot():
    snapshot = create_snapshot()

    assert snapshot.item_id == "ITEM-001"
    assert snapshot.seller_id == "seller_001"
    assert snapshot.seller_rating == 4.8
    assert snapshot.seller_review_count == 120
    assert snapshot.seller_count == 3
    assert snapshot.is_verified is True


def test_allows_missing_seller_id():
    snapshot = create_snapshot(
        seller_id=None,
    )

    assert snapshot.seller_id is None


def test_rejects_invalid_rating():
    with pytest.raises(ValueError):
        create_snapshot(
            seller_rating=5.5,
        )


def test_rejects_negative_review_count():
    with pytest.raises(ValueError):
        create_snapshot(
            seller_review_count=-1,
        )


def test_rejects_negative_seller_count():
    with pytest.raises(ValueError):
        create_snapshot(
            seller_count=-1,
        )


def test_rejects_invalid_verified_type():
    with pytest.raises(TypeError):
        create_snapshot(
            is_verified="yes",
        )


def test_snapshot_is_immutable():
    snapshot = create_snapshot()

    with pytest.raises(
        AttributeError
    ):
        snapshot.seller_count = 10