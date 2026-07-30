from __future__ import annotations

from datetime import datetime, timezone

from app.application.watchlist import MonitorStatus
from app.domain.watchlist import WatchItem
from app.infrastructure.watchlist import (
    SQLiteWatchListRepository,
    create_watchlist_monitor,
)
from app.models import Product
from storage.price_history import PriceHistoryRepository


RC_START = datetime(2026, 6, 30, tzinfo=timezone.utc)


class ControlledDateTime(datetime):
    current = datetime(2026, 7, 31, tzinfo=timezone.utc)

    @classmethod
    def now(cls, tz=None):
        current = cls.current
        if tz is not None:
            current = current.astimezone(tz)
        return cls(
            current.year,
            current.month,
            current.day,
            current.hour,
            current.minute,
            current.second,
            current.microsecond,
            tzinfo=current.tzinfo,
        )


class FailOnceSQLiteWatchListRepository(SQLiteWatchListRepository):
    fail_next_save = False

    def save(self, item: WatchItem) -> None:
        if self.fail_next_save:
            self.fail_next_save = False
            raise RuntimeError("watch item save failed")
        super().save(item)


def make_item(
    *,
    marketplace: str,
    item_id: str,
    canonical_product_id: str,
    price: float,
) -> WatchItem:
    return WatchItem(
        marketplace=marketplace,
        item_id=item_id,
        canonical_product_id=canonical_product_id,
        title=f"{marketplace} {item_id}",
        current_price=price,
        currency="USD",
        url=f"https://example.com/{marketplace}/{item_id}",
        created_at=RC_START,
        updated_at=RC_START,
    )


def make_product(
    *,
    marketplace: str,
    item_id: str,
    price: float,
) -> Product:
    return Product(
        marketplace=marketplace,
        item_id=item_id,
        title=f"{marketplace} {item_id}",
        price=price,
        currency="USD",
        condition="New",
        url=f"https://example.com/{marketplace}/{item_id}",
        seller=f"{marketplace}-seller",
    )


def set_time(day: int, hour: int = 0) -> datetime:
    current = ControlledDateTime(
        2026,
        7,
        day,
        hour,
        tzinfo=timezone.utc,
    )
    ControlledDateTime.current = current
    return current


def test_production_monitor_end_to_end_release_candidate(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "sprint11-rc.db"
    current_products = {
        "ebay": make_product(
            marketplace="ebay",
            item_id="ebay-1",
            price=100.0,
        ),
        "amazon": make_product(
            marketplace="amazon",
            item_id="amazon-1",
            price=90.0,
        ),
    }
    monkeypatch.setattr(
        "app.application.watchlist.monitor.datetime",
        ControlledDateTime,
    )
    monkeypatch.setattr(
        "app.infrastructure.watchlist.marketplace_readers."
        "ebay.get_product_by_id",
        lambda item_id: current_products["ebay"],
    )
    monkeypatch.setattr(
        "app.infrastructure.watchlist.marketplace_readers."
        "amazon.get_product_by_id",
        lambda item_id: current_products["amazon"],
    )

    repository = FailOnceSQLiteWatchListRepository(database_path)
    ebay_item = make_item(
        marketplace="ebay",
        item_id="ebay-1",
        canonical_product_id="canonical-ebay",
        price=100.0,
    )
    repository.save(ebay_item)
    monitor = create_watchlist_monitor(
        database_path,
        repository=repository,
    )
    price_history = PriceHistoryRepository(database_path)

    set_time(1)
    first = monitor.execute()
    assert first.items[0].status is MonitorStatus.UNCHANGED
    assert first.items[0].change_count == 0
    assert price_history.count_records() == 1
    assert repository.get(ebay_item.watch_id).current_price == 100.0

    current_products["ebay"] = make_product(
        marketplace="ebay",
        item_id="ebay-1",
        price=80.0,
    )
    set_time(2)
    changed = monitor.execute()
    assert changed.items[0].status is MonitorStatus.UPDATED
    assert changed.items[0].change_count == 1
    assert price_history.count_records() == 2
    assert repository.get(ebay_item.watch_id).current_price == 80.0

    set_time(3)
    unchanged = monitor.execute()
    assert unchanged.items[0].status is MonitorStatus.UNCHANGED
    assert unchanged.items[0].change_count == 0
    assert price_history.count_records() == 3

    retry = monitor.execute()
    assert retry.items[0].status is MonitorStatus.UNCHANGED
    assert price_history.count_records() == 3

    current_products["ebay"] = make_product(
        marketplace="ebay",
        item_id="ebay-1",
        price=70.0,
    )
    retry_time = set_time(4)
    repository.fail_next_save = True
    failed_save = monitor.execute()
    assert failed_save.items[0].status is MonitorStatus.FAILED
    assert price_history.count_records() == 4
    assert repository.get(ebay_item.watch_id).current_price == 80.0

    save_retry = monitor.execute()
    assert save_retry.items[0].status is MonitorStatus.UNCHANGED
    assert save_retry.items[0].change_count == 0
    assert price_history.count_records() == 4
    saved_item = repository.get(ebay_item.watch_id)
    assert saved_item.current_price == 70.0
    assert saved_item.last_analyzed_at == retry_time

    conflict_time = set_time(5)
    price_history.save_product_price(
        make_product(
            marketplace="ebay",
            item_id="ebay-1",
            price=60.0,
        ),
        observed_at=conflict_time,
        canonical_product_id="canonical-ebay",
        seller_id="ebay-seller",
    )
    current_products["ebay"] = make_product(
        marketplace="ebay",
        item_id="ebay-1",
        price=50.0,
    )
    conflict = monitor.execute()
    assert conflict.items[0].status is MonitorStatus.FAILED
    assert "different data" in conflict.items[0].error_message
    assert price_history.count_records() == 5
    assert repository.get(ebay_item.watch_id).current_price == 70.0

    set_time(6)
    recovered = monitor.execute()
    assert recovered.items[0].status is MonitorStatus.UPDATED
    assert recovered.items[0].change_count == 1
    assert price_history.count_records() == 6
    assert repository.get(ebay_item.watch_id).current_price == 50.0

    amazon_item = make_item(
        marketplace="amazon",
        item_id="amazon-1",
        canonical_product_id="canonical-amazon",
        price=100.0,
    )
    repository.save(amazon_item)
    set_time(7)
    batch = monitor.execute()

    assert batch.total_count == 2
    assert [entry.status for entry in batch.items] == [
        MonitorStatus.UNCHANGED,
        MonitorStatus.UNCHANGED,
    ]
    assert price_history.count_records() == 8
    assert repository.get(ebay_item.watch_id).current_price == 50.0
    assert repository.get(amazon_item.watch_id).current_price == 90.0
    assert len(
        price_history.get_product_history(
            marketplace="ebay",
            item_id="ebay-1",
        )
    ) == 7
    assert len(
        price_history.get_product_history(
            marketplace="amazon",
            item_id="amazon-1",
        )
    ) == 1

    repository.close()
