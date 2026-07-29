from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.application.watchlist import (
    WatchListRepository,
)
from app.domain.watchlist import (
    DuplicateWatchItemError,
    WatchItem,
    WatchItemStatus,
)
from app.infrastructure.watchlist import (
    SQLiteWatchListRepository,
)


BASE_TIME = datetime(
    2026,
    7,
    29,
    1,
    0,
    tzinfo=timezone.utc,
)


def make_watch_item(
    *,
    watch_id: str = "watch-1",
    marketplace: str = "ebay",
    item_id: str = "item-1",
    canonical_product_id: str | None = None,
    created_offset_minutes: int = 0,
) -> WatchItem:
    created_at = BASE_TIME + timedelta(
        minutes=created_offset_minutes
    )

    return WatchItem(
        watch_id=watch_id,
        marketplace=marketplace,
        item_id=item_id,
        canonical_product_id=(
            canonical_product_id
        ),
        title="Apple iPhone 17 128GB",
        current_price=500.0,
        currency="USD",
        url=f"https://example.com/{item_id}",
        brand="Apple",
        model_number="A0001",
        target_roi=30.0,
        target_net_profit=100.0,
        note="가격 하락 감시",
        created_at=created_at,
        updated_at=created_at,
    )


@pytest.fixture
def repository(
    tmp_path: Path,
) -> SQLiteWatchListRepository:
    repository = SQLiteWatchListRepository(
        tmp_path / "watchlist.db"
    )

    yield repository

    repository.close()


def test_repository_implements_application_port(
    repository: SQLiteWatchListRepository,
) -> None:
    assert isinstance(
        repository,
        WatchListRepository,
    )


def test_repository_creates_database_schema(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "nested" / "watch.db"

    repository = SQLiteWatchListRepository(
        database_path
    )

    try:
        assert database_path.exists()
        assert repository.count() == 0
    finally:
        repository.close()


def test_repository_saves_and_gets_item(
    repository: SQLiteWatchListRepository,
) -> None:
    item = make_watch_item()

    repository.save(item)

    restored = repository.get("watch-1")

    assert restored is not None
    assert restored.watch_id == "watch-1"
    assert restored.identity_key == (
        "listing:ebay:item-1"
    )
    assert restored.title == item.title
    assert restored.current_price == 500.0
    assert restored.target_roi == 30.0
    assert restored.target_net_profit == 100.0
    assert (
        restored.status
        is WatchItemStatus.WATCHING
    )


def test_repository_returns_none_for_missing_item(
    repository: SQLiteWatchListRepository,
) -> None:
    assert repository.get("missing") is None


def test_repository_updates_existing_watch_id(
    repository: SQLiteWatchListRepository,
) -> None:
    item = make_watch_item()
    repository.save(item)

    changed_at = BASE_TIME + timedelta(hours=1)

    item.update_targets(
        target_roi=40.0,
        target_net_profit=150.0,
        changed_at=changed_at,
    )
    item.update_note(
        "공급처 재확인",
        changed_at=changed_at,
    )

    repository.save(item)

    restored = repository.get(item.watch_id)

    assert restored is not None
    assert restored.target_roi == 40.0
    assert restored.target_net_profit == 150.0
    assert restored.note == "공급처 재확인"
    assert restored.updated_at == changed_at
    assert repository.count() == 1


def test_repository_finds_item_by_identity(
    repository: SQLiteWatchListRepository,
) -> None:
    item = make_watch_item(
        canonical_product_id=(
            "canonical-iphone-17-128"
        )
    )
    repository.save(item)

    restored = repository.find_by_identity(
        item.identity_key
    )

    assert restored is not None
    assert restored.watch_id == item.watch_id
    assert (
        restored.canonical_product_id
        == "canonical-iphone-17-128"
    )


def test_repository_rejects_duplicate_listing_identity(
    repository: SQLiteWatchListRepository,
) -> None:
    first = make_watch_item(
        watch_id="watch-1",
        item_id="same-item",
    )
    duplicate = make_watch_item(
        watch_id="watch-2",
        item_id="same-item",
    )

    repository.save(first)

    with pytest.raises(
        DuplicateWatchItemError,
        match="동일한 상품 Identity",
    ):
        repository.save(duplicate)

    assert repository.count() == 1


def test_repository_rejects_duplicate_canonical_identity(
    repository: SQLiteWatchListRepository,
) -> None:
    first = make_watch_item(
        watch_id="watch-1",
        item_id="listing-a",
        canonical_product_id="canonical-1",
    )
    duplicate = make_watch_item(
        watch_id="watch-2",
        item_id="listing-b",
        canonical_product_id="canonical-1",
    )

    repository.save(first)

    with pytest.raises(
        DuplicateWatchItemError
    ):
        repository.save(duplicate)

    assert repository.count() == 1


def test_repository_allows_same_item_id_across_marketplaces(
    repository: SQLiteWatchListRepository,
) -> None:
    ebay_item = make_watch_item(
        watch_id="watch-ebay",
        marketplace="ebay",
        item_id="shared-item",
    )
    amazon_item = make_watch_item(
        watch_id="watch-amazon",
        marketplace="amazon",
        item_id="shared-item",
    )

    repository.save(ebay_item)
    repository.save(amazon_item)

    assert repository.count() == 2


def test_repository_lists_items_in_created_order(
    repository: SQLiteWatchListRepository,
) -> None:
    second = make_watch_item(
        watch_id="watch-2",
        item_id="item-2",
        created_offset_minutes=2,
    )
    first = make_watch_item(
        watch_id="watch-1",
        item_id="item-1",
        created_offset_minutes=1,
    )

    repository.save(second)
    repository.save(first)

    items = repository.list_all()

    assert tuple(
        item.watch_id
        for item in items
    ) == (
        "watch-1",
        "watch-2",
    )


def test_repository_lists_watching_and_archived_items(
    repository: SQLiteWatchListRepository,
) -> None:
    watching = make_watch_item(
        watch_id="watch-active",
        item_id="active-item",
    )
    archived = make_watch_item(
        watch_id="watch-archived",
        item_id="archived-item",
    )

    archived.archive(
        changed_at=BASE_TIME + timedelta(hours=1)
    )

    repository.save(watching)
    repository.save(archived)

    assert tuple(
        item.watch_id
        for item in repository.list_watching()
    ) == (
        "watch-active",
    )

    assert tuple(
        item.watch_id
        for item in repository.list_archived()
    ) == (
        "watch-archived",
    )


def test_archive_state_is_persisted_after_domain_change(
    repository: SQLiteWatchListRepository,
) -> None:
    item = make_watch_item()
    repository.save(item)

    archived_at = BASE_TIME + timedelta(hours=1)

    loaded = repository.get(item.watch_id)

    assert loaded is not None

    loaded.archive(
        changed_at=archived_at
    )
    repository.save(loaded)

    restored = repository.get(item.watch_id)

    assert restored is not None
    assert (
        restored.status
        is WatchItemStatus.ARCHIVED
    )
    assert restored.updated_at == archived_at


def test_repository_exists_checks(
    repository: SQLiteWatchListRepository,
) -> None:
    item = make_watch_item()
    repository.save(item)

    assert repository.exists(
        item.watch_id
    )
    assert repository.exists_identity(
        item.identity_key
    )

    assert not repository.exists(
        "missing-watch"
    )
    assert not repository.exists_identity(
        "listing:ebay:missing-item"
    )


def test_repository_deletes_item(
    repository: SQLiteWatchListRepository,
) -> None:
    item = make_watch_item()
    repository.save(item)

    assert repository.delete(
        item.watch_id
    )
    assert repository.count() == 0
    assert repository.get(
        item.watch_id
    ) is None

    assert not repository.delete(
        item.watch_id
    )


def test_repository_persists_data_across_instances(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "persistent.db"

    first_repository = SQLiteWatchListRepository(
        database_path
    )
    first_repository.save(
        make_watch_item()
    )
    first_repository.close()

    second_repository = SQLiteWatchListRepository(
        database_path
    )

    try:
        restored = second_repository.get(
            "watch-1"
        )

        assert restored is not None
        assert restored.title == (
            "Apple iPhone 17 128GB"
        )
        assert second_repository.count() == 1
    finally:
        second_repository.close()


def test_repository_supports_in_memory_database() -> None:
    repository = SQLiteWatchListRepository(
        ":memory:"
    )

    try:
        repository.save(
            make_watch_item()
        )

        assert repository.count() == 1
        assert repository.get(
            "watch-1"
        ) is not None
    finally:
        repository.close()


def test_closed_repository_rejects_operations(
    tmp_path: Path,
) -> None:
    repository = SQLiteWatchListRepository(
        tmp_path / "closed.db"
    )
    repository.close()

    with pytest.raises(
        RuntimeError,
        match="종료된",
    ):
        repository.count()