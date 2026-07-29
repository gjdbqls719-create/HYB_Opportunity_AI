from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.domain.watchlist import (
    DuplicateWatchItemError,
    WatchIdentityStrength,
    WatchItem,
    WatchItemNotFoundError,
    WatchItemStatus,
    WatchList,
    WeakWatchIdentityError,
)
from app.models import Product


BASE_TIME = datetime(
    2026,
    7,
    29,
    0,
    0,
    tzinfo=timezone.utc,
)


def make_product(
    *,
    marketplace: str = "ebay",
    item_id: str = "item-1",
    title: str = "Apple iPhone 17 128GB",
    price: float = 500.0,
    url: str = "https://example.com/item-1",
) -> Product:
    return Product(
        marketplace=marketplace,
        item_id=item_id,
        title=title,
        price=price,
        currency="USD",
        condition="New",
        url=url,
        brand="Apple",
        model_number="A0001",
    )


def make_watch_item(
    *,
    item_id: str = "item-1",
    canonical_product_id: str | None = None,
    watch_id: str = "watch-1",
) -> WatchItem:
    return WatchItem.from_product(
        make_product(item_id=item_id),
        canonical_product_id=canonical_product_id,
        created_at=BASE_TIME,
        note="초기 관찰 상품",
    ) if watch_id == "generated" else WatchItem(
        marketplace="ebay",
        item_id=item_id,
        title="Apple iPhone 17 128GB",
        current_price=500.0,
        currency="USD",
        url=f"https://example.com/{item_id}",
        canonical_product_id=canonical_product_id,
        brand="Apple",
        model_number="A0001",
        note="초기 관찰 상품",
        watch_id=watch_id,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def test_watch_item_can_be_created_from_product() -> None:
    item = WatchItem.from_product(
        make_product(),
        canonical_product_id="canonical-iphone-17-128",
        target_roi=30.0,
        target_net_profit=100.0,
        note="  가격 하락 감시  ",
        created_at=BASE_TIME,
    )

    assert item.marketplace == "ebay"
    assert item.item_id == "item-1"
    assert item.current_price == 500.0
    assert item.currency == "USD"
    assert item.note == "가격 하락 감시"
    assert item.target_roi == 30.0
    assert item.target_net_profit == 100.0
    assert item.status is WatchItemStatus.WATCHING


def test_canonical_product_id_is_strong_identity() -> None:
    item = make_watch_item(
        canonical_product_id="canonical-iphone-17-128"
    )

    assert (
        item.identity_strength
        is WatchIdentityStrength.STRONG
    )
    assert item.identity_key == (
        "canonical:canonical-iphone-17-128"
    )


def test_marketplace_item_id_is_listing_identity() -> None:
    item = make_watch_item()

    assert (
        item.identity_strength
        is WatchIdentityStrength.LISTING
    )
    assert item.identity_key == "listing:ebay:item-1"


def test_title_only_identity_is_weak() -> None:
    item = WatchItem(
        marketplace="ebay",
        item_id="",
        title="Apple iPhone 17 128GB",
        current_price=500.0,
        currency="USD",
        url="",
        watch_id="weak-1",
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )

    assert (
        item.identity_strength
        is WatchIdentityStrength.WEAK
    )
    assert item.identity_key == (
        "weak-title:ebay:apple iphone 17 128gb"
    )


def test_watch_list_rejects_weak_identity_by_default() -> None:
    item = WatchItem(
        marketplace="ebay",
        item_id="",
        title="Apple iPhone 17 128GB",
        current_price=500.0,
        currency="USD",
        url="",
        watch_id="weak-1",
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )

    with pytest.raises(WeakWatchIdentityError):
        WatchList().add(item)


def test_watch_list_can_explicitly_allow_weak_identity() -> None:
    item = WatchItem(
        marketplace="ebay",
        item_id="",
        title="Apple iPhone 17 128GB",
        current_price=500.0,
        currency="USD",
        url="",
        watch_id="weak-1",
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )

    watch_list = WatchList(
        allow_weak_identity=True
    )
    watch_list.add(item)

    assert len(watch_list) == 1


def test_watch_list_adds_and_gets_item() -> None:
    item = make_watch_item()
    watch_list = WatchList()

    watch_list.add(item)

    assert len(watch_list) == 1
    assert watch_list.get("watch-1") is item
    assert (
        watch_list.find_by_identity(item.identity_key)
        is item
    )


def test_watch_list_rejects_duplicate_listing_identity() -> None:
    first = make_watch_item(
        watch_id="watch-1",
    )
    duplicate = make_watch_item(
        watch_id="watch-2",
    )
    watch_list = WatchList([first])

    with pytest.raises(
        DuplicateWatchItemError,
        match="동일한 상품",
    ):
        watch_list.add(duplicate)


def test_watch_list_rejects_duplicate_canonical_identity() -> None:
    first = make_watch_item(
        item_id="listing-a",
        canonical_product_id="canonical-product-1",
        watch_id="watch-1",
    )
    duplicate = make_watch_item(
        item_id="listing-b",
        canonical_product_id="canonical-product-1",
        watch_id="watch-2",
    )
    watch_list = WatchList([first])

    with pytest.raises(DuplicateWatchItemError):
        watch_list.add(duplicate)


def test_different_marketplace_listings_are_not_merged() -> None:
    ebay_item = WatchItem(
        marketplace="ebay",
        item_id="shared-id",
        title="Sample Product",
        current_price=100.0,
        currency="USD",
        watch_id="watch-ebay",
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )
    amazon_item = WatchItem(
        marketplace="amazon",
        item_id="shared-id",
        title="Sample Product",
        current_price=100.0,
        currency="USD",
        watch_id="watch-amazon",
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )

    watch_list = WatchList(
        [ebay_item, amazon_item]
    )

    assert len(watch_list) == 2


def test_watch_item_can_be_archived_and_restored() -> None:
    changed_at = BASE_TIME + timedelta(hours=1)
    restored_at = BASE_TIME + timedelta(hours=2)
    item = make_watch_item()

    item.archive(changed_at=changed_at)

    assert item.status is WatchItemStatus.ARCHIVED
    assert item.updated_at == changed_at
    assert item.is_active is False

    item.restore(changed_at=restored_at)

    assert item.status is WatchItemStatus.WATCHING
    assert item.updated_at == restored_at
    assert item.is_active is True


def test_watch_list_filters_watching_and_archived_items() -> None:
    watching = make_watch_item(
        item_id="watching",
        watch_id="watch-1",
    )
    archived = make_watch_item(
        item_id="archived",
        watch_id="watch-2",
    )
    archived.archive(
        changed_at=BASE_TIME + timedelta(hours=1)
    )

    watch_list = WatchList(
        [watching, archived]
    )

    assert watch_list.list_watching() == (watching,)
    assert watch_list.list_archived() == (archived,)
    assert watch_list.list_all() == (
        watching,
        archived,
    )


def test_watch_list_removes_item_and_releases_identity() -> None:
    first = make_watch_item()
    watch_list = WatchList([first])

    removed = watch_list.remove("watch-1")

    assert removed is first
    assert len(watch_list) == 0
    assert (
        watch_list.find_by_identity(first.identity_key)
        is None
    )

    replacement = make_watch_item(
        watch_id="watch-2"
    )
    watch_list.add(replacement)

    assert len(watch_list) == 1


def test_watch_list_raises_for_missing_item() -> None:
    watch_list = WatchList()

    with pytest.raises(WatchItemNotFoundError):
        watch_list.get("missing-watch-id")


def test_watch_item_updates_targets_and_note() -> None:
    changed_at = BASE_TIME + timedelta(hours=1)
    note_changed_at = BASE_TIME + timedelta(hours=2)
    item = make_watch_item()

    item.update_targets(
        target_roi=35.0,
        target_net_profit=120.0,
        changed_at=changed_at,
    )
    item.update_note(
        "  공급처 확인 필요  ",
        changed_at=note_changed_at,
    )

    assert item.target_roi == 35.0
    assert item.target_net_profit == 120.0
    assert item.note == "공급처 확인 필요"
    assert item.updated_at == note_changed_at


def test_watch_item_records_latest_analysis() -> None:
    analyzed_at = BASE_TIME + timedelta(days=1)
    item = make_watch_item()

    item.record_analysis(
        observed_price=450.0,
        analyzed_at=analyzed_at,
    )

    assert item.current_price == 450.0
    assert item.last_analyzed_at == analyzed_at
    assert item.updated_at == analyzed_at


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("current_price", -1.0),
        ("target_roi", -0.1),
        ("target_net_profit", -10.0),
    ],
)
def test_watch_item_rejects_negative_numbers(
    field_name: str,
    value: float,
) -> None:
    arguments = {
        "marketplace": "ebay",
        "item_id": "item-1",
        "title": "Sample Product",
        "current_price": 100.0,
        "currency": "USD",
        "watch_id": "watch-1",
        "created_at": BASE_TIME,
        "updated_at": BASE_TIME,
    }
    arguments[field_name] = value

    with pytest.raises(ValueError):
        WatchItem(**arguments)


def test_watch_item_requires_timezone_aware_datetime() -> None:
    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        WatchItem(
            marketplace="ebay",
            item_id="item-1",
            title="Sample Product",
            current_price=100.0,
            currency="USD",
            watch_id="watch-1",
            created_at=datetime(2026, 7, 29),
            updated_at=datetime(2026, 7, 29),
        )