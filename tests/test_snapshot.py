from datetime import datetime, timezone

import pytest

from market_data.snapshot import BaseSnapshot


def create_snapshot() -> BaseSnapshot:
    return BaseSnapshot(
        snapshot_id="snap_001",
        canonical_product_id="product_001",
        marketplace=" ebay ",
        observed_at=datetime.now(timezone.utc),
        source_url=" https://example.com/item/001 ",
    )


def test_base_snapshot_creation():
    snapshot = create_snapshot()

    assert snapshot.snapshot_id == "snap_001"
    assert snapshot.canonical_product_id == "product_001"
    assert snapshot.marketplace == "ebay"
    assert snapshot.source_url == (
        "https://example.com/item/001"
    )


def test_base_snapshot_is_immutable():
    snapshot = create_snapshot()

    with pytest.raises(AttributeError):
        snapshot.marketplace = "amazon"


@pytest.mark.parametrize(
    "field",
    [
        "snapshot_id",
        "canonical_product_id",
        "marketplace",
        "source_url",
    ],
)
def test_base_snapshot_required_fields(field):
    values = {
        "snapshot_id": "snap_001",
        "canonical_product_id": "product_001",
        "marketplace": "ebay",
        "observed_at": datetime.now(timezone.utc),
        "source_url": "https://example.com/item",
    }

    values[field] = ""

    with pytest.raises(ValueError):
        BaseSnapshot(**values)