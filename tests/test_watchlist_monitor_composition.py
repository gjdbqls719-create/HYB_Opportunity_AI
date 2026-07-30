from __future__ import annotations

from datetime import datetime, timezone

from app.application.watchlist import (
    MonitorStatus,
    WatchListMonitorUseCase,
)
from app.domain.watchlist import WatchItem
from app.infrastructure.watchlist import (
    SQLiteWatchListRepository,
    create_watchlist_monitor,
)
from app.models import Product
from storage.price_history import PriceHistoryRepository


PREVIOUS_OBSERVATION = datetime(
    2026,
    7,
    30,
    tzinfo=timezone.utc,
)


def make_product(
    *,
    price: float,
) -> Product:
    return Product(
        marketplace="ebay",
        item_id="item-1",
        title="eBay Product",
        price=price,
        currency="USD",
        condition="New",
        url="https://example.com/item-1",
        seller="seller-1",
    )


def make_watch_item() -> WatchItem:
    return WatchItem(
        marketplace="ebay",
        item_id="item-1",
        canonical_product_id="canonical-1",
        title="eBay Product",
        current_price=100.0,
        currency="USD",
        url="https://example.com/item-1",
    )


def test_factory_creates_monitor_without_marketplace_call(
    tmp_path,
    monkeypatch,
) -> None:
    def fail_if_called(item_id: str) -> Product:
        raise AssertionError(
            "Factory creation must not call Marketplace APIs"
        )

    monkeypatch.setattr(
        "app.infrastructure.watchlist.marketplace_readers."
        "ebay.get_product_by_id",
        fail_if_called,
    )
    monkeypatch.setattr(
        "app.infrastructure.watchlist.marketplace_readers."
        "amazon.get_product_by_id",
        fail_if_called,
    )

    monitor = create_watchlist_monitor(
        tmp_path / "factory.db"
    )

    assert isinstance(monitor, WatchListMonitorUseCase)
    assert monitor.execute().total_count == 0


def test_composed_monitor_uses_real_dependencies_without_saving_snapshot(
    tmp_path,
    monkeypatch,
) -> None:
    database_path = tmp_path / "monitor.db"
    price_history = PriceHistoryRepository(database_path)
    price_history.save_product_price(
        make_product(price=100.0),
        observed_at=PREVIOUS_OBSERVATION,
        canonical_product_id="canonical-1",
    )

    lookup_calls: list[str] = []

    def fake_get_product_by_id(item_id: str) -> Product:
        lookup_calls.append(item_id)
        return make_product(price=80.0)

    monkeypatch.setattr(
        "app.infrastructure.watchlist.marketplace_readers."
        "ebay.get_product_by_id",
        fake_get_product_by_id,
    )

    with SQLiteWatchListRepository(database_path) as repository:
        item = make_watch_item()
        repository.save(item)
        monitor = create_watchlist_monitor(
            database_path,
            repository=repository,
        )

        result = monitor.execute()
        persisted = repository.get(item.watch_id)

    assert lookup_calls == ["item-1"]
    assert result.total_count == 1
    assert result.items[0].status is MonitorStatus.UPDATED
    assert result.items[0].previous_price == 100.0
    assert result.items[0].current_price == 80.0
    assert result.items[0].change_count == 1
    assert persisted is not None
    assert persisted.current_price == 80.0
    assert persisted.last_analyzed_at is not None
    assert len(
        price_history.get_product_history(
            marketplace="ebay",
            item_id="item-1",
        )
    ) == 1
