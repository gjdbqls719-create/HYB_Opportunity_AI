from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from app.application.watchlist import (
    MonitorStatus,
    WatchListMonitorUseCase,
)
from app.domain.watchlist import WatchItem, WatchItemStatus
from app.models import Product
from market_data.price_snapshot import PriceSnapshot


BASE_TIME = datetime(2026, 7, 29, tzinfo=timezone.utc)
ANALYZED_AT = BASE_TIME + timedelta(days=1)


@dataclass(frozen=True)
class FakeChangeResponse:
    has_changes: bool
    change_count: int


class FakeRepository:
    def __init__(self, items: tuple[WatchItem, ...]) -> None:
        self.items = items
        self.saved: list[WatchItem] = []

    def list_watching(self) -> tuple[WatchItem, ...]:
        return tuple(
            item
            for item in self.items
            if item.status is WatchItemStatus.WATCHING
        )

    def save(self, item: WatchItem) -> None:
        self.saved.append(item)


class FakeLookup:
    def __init__(self, results: dict[str, Product | None | Exception]) -> None:
        self.results = results
        self.calls: list[dict[str, str]] = []

    def get_listing(
        self,
        *,
        marketplace: str,
        item_id: str,
        url: str = "",
    ) -> Product | None:
        self.calls.append(
            {
                "marketplace": marketplace,
                "item_id": item_id,
                "url": url,
            }
        )
        result = self.results[item_id]
        if isinstance(result, Exception):
            raise result
        return result


class FakeDetector:
    def __init__(
        self,
        responses: dict[str, FakeChangeResponse | Exception],
    ) -> None:
        self.responses = responses
        self.snapshots: list[PriceSnapshot] = []

    def execute(
        self,
        *,
        current_snapshot: PriceSnapshot,
    ) -> FakeChangeResponse:
        self.snapshots.append(current_snapshot)
        result = self.responses[current_snapshot.item_id]
        if isinstance(result, Exception):
            raise result
        return result


def make_item(
    item_id: str = "item-1",
    *,
    watch_id: str = "watch-1",
    price: float = 500.0,
    canonical_product_id: str | None = None,
    url: str | None = None,
) -> WatchItem:
    return WatchItem(
        marketplace="ebay",
        item_id=item_id,
        title=f"Product {item_id}",
        current_price=price,
        currency="USD",
        url=url if url is not None else f"https://example.com/{item_id}",
        canonical_product_id=canonical_product_id,
        watch_id=watch_id,
        created_at=BASE_TIME,
        updated_at=BASE_TIME,
    )


def make_product(
    item_id: str = "item-1",
    *,
    price: float = 450.0,
    marketplace: str = "ebay",
    currency: str = "USD",
    url: str | None = None,
) -> Product:
    return Product(
        marketplace=marketplace,
        item_id=item_id,
        title=f"Product {item_id}",
        price=price,
        currency=currency,
        condition="New",
        url=url if url is not None else f"https://example.com/{item_id}",
        seller="seller-1",
    )


def make_use_case(
    *,
    items: tuple[WatchItem, ...],
    lookup_results: dict[str, Product | None | Exception],
    detector_responses: dict[str, FakeChangeResponse | Exception],
) -> tuple[
    WatchListMonitorUseCase,
    FakeRepository,
    FakeLookup,
    FakeDetector,
]:
    repository = FakeRepository(items)
    lookup = FakeLookup(lookup_results)
    detector = FakeDetector(detector_responses)
    use_case = WatchListMonitorUseCase(
        repository=repository,
        listing_lookup=lookup,
        change_detector=detector,
        clock=lambda: ANALYZED_AT,
        snapshot_id_factory=lambda: "snapshot-1",
    )
    return use_case, repository, lookup, detector


def test_monitor_returns_empty_result_when_watch_list_is_empty() -> None:
    use_case, repository, lookup, detector = make_use_case(
        items=(),
        lookup_results={},
        detector_responses={},
    )

    result = use_case.execute()

    assert result.total_count == 0
    assert repository.saved == []
    assert lookup.calls == []
    assert detector.snapshots == []


def test_monitor_only_processes_watching_items() -> None:
    watching = make_item("watching", watch_id="watch-1")
    archived = make_item("archived", watch_id="watch-2")
    archived.archive(changed_at=BASE_TIME + timedelta(hours=1))
    use_case, _, lookup, _ = make_use_case(
        items=(watching, archived),
        lookup_results={"watching": make_product("watching")},
        detector_responses={
            "watching": FakeChangeResponse(False, 0),
        },
    )

    result = use_case.execute()

    assert result.total_count == 1
    assert [call["item_id"] for call in lookup.calls] == ["watching"]


def test_monitor_passes_watch_identity_to_listing_lookup() -> None:
    item = make_item()
    use_case, _, lookup, _ = make_use_case(
        items=(item,),
        lookup_results={"item-1": make_product()},
        detector_responses={"item-1": FakeChangeResponse(False, 0)},
    )

    use_case.execute()

    assert lookup.calls == [
        {
            "marketplace": "ebay",
            "item_id": "item-1",
            "url": "https://example.com/item-1",
        }
    ]


def test_monitor_returns_updated_and_records_latest_analysis() -> None:
    item = make_item(price=500.0)
    use_case, repository, _, _ = make_use_case(
        items=(item,),
        lookup_results={"item-1": make_product(price=450.0)},
        detector_responses={"item-1": FakeChangeResponse(True, 1)},
    )

    result = use_case.execute()
    monitored = result.items[0]

    assert monitored.status is MonitorStatus.UPDATED
    assert monitored.previous_price == 500.0
    assert monitored.current_price == 450.0
    assert monitored.change_count == 1
    assert item.current_price == 450.0
    assert item.last_analyzed_at == ANALYZED_AT
    assert item.updated_at == ANALYZED_AT
    assert repository.saved == [item]


def test_monitor_returns_unchanged_when_detector_has_no_changes() -> None:
    item = make_item(price=500.0)
    use_case, repository, _, _ = make_use_case(
        items=(item,),
        lookup_results={"item-1": make_product(price=500.0)},
        detector_responses={"item-1": FakeChangeResponse(False, 0)},
    )

    result = use_case.execute()

    assert result.items[0].status is MonitorStatus.UNCHANGED
    assert result.successful_count == 1
    assert repository.saved == [item]


def test_monitor_creates_price_snapshot_for_existing_change_use_case() -> None:
    item = make_item(canonical_product_id="canonical-1")
    use_case, _, _, detector = make_use_case(
        items=(item,),
        lookup_results={"item-1": make_product(price=450.0)},
        detector_responses={"item-1": FakeChangeResponse(True, 2)},
    )

    use_case.execute()

    snapshot = detector.snapshots[0]
    assert snapshot.snapshot_id == "snapshot-1"
    assert snapshot.canonical_product_id == "canonical-1"
    assert snapshot.marketplace == "ebay"
    assert snapshot.item_id == "item-1"
    assert str(snapshot.price) == "450.0"
    assert snapshot.currency == "USD"
    assert snapshot.condition == "New"
    assert snapshot.seller_id == "seller-1"
    assert snapshot.observed_at == ANALYZED_AT


def test_monitor_uses_listing_identity_when_canonical_id_is_absent() -> None:
    item = make_item(canonical_product_id=None)
    use_case, _, _, detector = make_use_case(
        items=(item,),
        lookup_results={"item-1": make_product()},
        detector_responses={"item-1": FakeChangeResponse(False, 0)},
    )

    use_case.execute()

    assert detector.snapshots[0].canonical_product_id == (
        "listing:ebay:item-1"
    )


def test_monitor_returns_not_found_without_saving_or_detecting() -> None:
    item = make_item()
    use_case, repository, _, detector = make_use_case(
        items=(item,),
        lookup_results={"item-1": None},
        detector_responses={},
    )

    result = use_case.execute()

    assert result.items[0].status is MonitorStatus.NOT_FOUND
    assert repository.saved == []
    assert detector.snapshots == []
    assert item.last_analyzed_at is None


def test_lookup_failure_is_isolated_from_next_item() -> None:
    failed = make_item("failed", watch_id="watch-1")
    successful = make_item("successful", watch_id="watch-2")
    use_case, repository, _, _ = make_use_case(
        items=(failed, successful),
        lookup_results={
            "failed": RuntimeError("network unavailable"),
            "successful": make_product("successful"),
        },
        detector_responses={
            "successful": FakeChangeResponse(False, 0),
        },
    )

    result = use_case.execute()

    assert [item.status for item in result.items] == [
        MonitorStatus.FAILED,
        MonitorStatus.UNCHANGED,
    ]
    assert result.items[0].error_message == "network unavailable"
    assert repository.saved == [successful]


def test_change_detection_failure_is_isolated_and_item_is_not_saved() -> None:
    item = make_item()
    use_case, repository, _, _ = make_use_case(
        items=(item,),
        lookup_results={"item-1": make_product()},
        detector_responses={"item-1": RuntimeError("detect failed")},
    )

    result = use_case.execute()

    assert result.items[0].status is MonitorStatus.FAILED
    assert result.items[0].error_message == "detect failed"
    assert repository.saved == []
    assert item.current_price == 500.0
    assert item.last_analyzed_at is None


def test_monitor_rejects_mismatched_marketplace_result() -> None:
    item = make_item()
    use_case, repository, _, detector = make_use_case(
        items=(item,),
        lookup_results={
            "item-1": make_product(marketplace="amazon"),
        },
        detector_responses={},
    )

    result = use_case.execute()

    assert result.items[0].status is MonitorStatus.FAILED
    assert "marketplace" in result.items[0].error_message
    assert repository.saved == []
    assert detector.snapshots == []


def test_monitor_rejects_mismatched_item_id_result() -> None:
    item = make_item()
    use_case, repository, _, detector = make_use_case(
        items=(item,),
        lookup_results={"item-1": make_product("different")},
        detector_responses={},
    )

    result = use_case.execute()

    assert result.items[0].status is MonitorStatus.FAILED
    assert "item_id" in result.items[0].error_message
    assert repository.saved == []
    assert detector.snapshots == []


def test_monitor_rejects_currency_change_until_domain_supports_it() -> None:
    item = make_item()
    use_case, repository, _, detector = make_use_case(
        items=(item,),
        lookup_results={"item-1": make_product(currency="KRW")},
        detector_responses={},
    )

    result = use_case.execute()

    assert result.items[0].status is MonitorStatus.FAILED
    assert "currency" in result.items[0].error_message
    assert repository.saved == []
    assert detector.snapshots == []


def test_monitor_builds_fallback_source_locator_when_urls_are_empty() -> None:
    item = make_item(url="")
    use_case, _, _, detector = make_use_case(
        items=(item,),
        lookup_results={"item-1": make_product(url="")},
        detector_responses={"item-1": FakeChangeResponse(False, 0)},
    )

    use_case.execute()

    assert detector.snapshots[0].source_url == (
        "ebay://listing/item-1"
    )


def test_naive_clock_failure_is_reported_per_item() -> None:
    item = make_item()
    repository = FakeRepository((item,))
    use_case = WatchListMonitorUseCase(
        repository=repository,
        listing_lookup=FakeLookup({"item-1": make_product()}),
        change_detector=FakeDetector({}),
        clock=lambda: datetime(2026, 7, 30),
    )

    result = use_case.execute()

    assert result.items[0].status is MonitorStatus.FAILED
    assert "timezone-aware" in result.items[0].error_message
    assert repository.saved == []


@pytest.mark.parametrize(
    ("argument_name", "value"),
    [
        ("repository", None),
        ("listing_lookup", None),
        ("change_detector", None),
    ],
)
def test_monitor_requires_dependencies(
    argument_name: str,
    value: Any,
) -> None:
    arguments: dict[str, Any] = {
        "repository": FakeRepository(()),
        "listing_lookup": FakeLookup({}),
        "change_detector": FakeDetector({}),
    }
    arguments[argument_name] = value

    with pytest.raises(TypeError):
        WatchListMonitorUseCase(**arguments)
