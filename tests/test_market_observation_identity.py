from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from app.domain.market_intelligence import (
    MarketObservationIdentity,
    MarketObservationScope,
)


STARTED_AT = datetime(2026, 8, 5, 9, tzinfo=timezone.utc)
ENDED_AT = STARTED_AT + timedelta(minutes=5)


def identity(**overrides) -> MarketObservationIdentity:
    values = dict(
        scope=MarketObservationScope.LISTING,
        market="KR",
        marketplace="Coupang",
        canonical_product_id=None,
        marketplace_item_id="item-1",
        normalized_query=None,
        category=None,
        variant_identity="black-128gb",
        condition="new",
        window_started_at=STARTED_AT,
        window_ended_at=ENDED_AT,
    )
    values.update(overrides)
    return MarketObservationIdentity(**values)


def test_listing_identity_requires_item_id_and_normalizes_marketplace() -> None:
    item = identity(scope="listing", marketplace_item_id=" item-1 ")

    assert item.scope is MarketObservationScope.LISTING
    assert item.marketplace == "coupang"
    assert item.marketplace_item_id == "item-1"


def test_search_query_identity_requires_normalized_query() -> None:
    item = identity(
        scope=MarketObservationScope.SEARCH_QUERY,
        marketplace_item_id=None,
        normalized_query=" wireless mouse ",
    )
    assert item.normalized_query == "wireless mouse"


def test_category_identity_requires_category() -> None:
    item = identity(
        scope=MarketObservationScope.CATEGORY,
        marketplace_item_id=None,
        category=" electronics ",
    )
    assert item.category == "electronics"


def test_canonical_product_identity_requires_canonical_id() -> None:
    item = identity(
        scope=MarketObservationScope.CANONICAL_PRODUCT,
        marketplace_item_id=None,
        canonical_product_id="CP-000001",
    )
    assert item.canonical_product_id == "CP-000001"


@pytest.mark.parametrize(
    ("scope", "required_name"),
    (
        (MarketObservationScope.LISTING, "marketplace_item_id"),
        (MarketObservationScope.CANONICAL_PRODUCT, "canonical_product_id"),
        (MarketObservationScope.SEARCH_QUERY, "normalized_query"),
        (MarketObservationScope.CATEGORY, "category"),
    ),
)
def test_scope_validation_rejects_missing_required_identity(scope, required_name) -> None:
    values = {
        "scope": scope,
        "marketplace_item_id": None,
        "canonical_product_id": None,
        "normalized_query": None,
        "category": None,
    }
    with pytest.raises(ValueError, match=required_name):
        identity(**values)


@pytest.mark.parametrize("timestamp_name", ("window_started_at", "window_ended_at"))
def test_window_timestamps_must_be_timezone_aware(timestamp_name: str) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        identity(**{timestamp_name: datetime(2026, 8, 5)})


def test_window_end_cannot_precede_start() -> None:
    with pytest.raises(ValueError, match="cannot precede"):
        identity(window_ended_at=STARTED_AT - timedelta(seconds=1))


def test_identity_is_immutable_and_has_value_equality() -> None:
    left = identity()
    right = identity()

    assert left == right
    with pytest.raises(FrozenInstanceError):
        left.marketplace_item_id = "changed"  # type: ignore[misc]
