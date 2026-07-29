from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

from app.application.watchlist.monitor_models import (
    MonitorItemResult,
    MonitorStatus,
    WatchListMonitorResult,
)
from app.application.watchlist.monitor_ports import (
    LatestPriceChangeDetector,
    ListingLookupPort,
)
from app.application.watchlist.ports import WatchListRepository
from app.domain.watchlist import WatchItem
from app.models import Product
from market_data.price_snapshot import PriceSnapshot


Clock = Callable[[], datetime]
SnapshotIdFactory = Callable[[], str]


class WatchListMonitorUseCase:
    """
    감시 중인 Watch Item의 Marketplace Listing을 다시 조회하고,
    기존 Change Application을 통해 최신 가격 변화를 탐지한다.

    이 Use Case는 흐름만 조율한다. 가격 변화 계산은
    LatestPriceChangeDetector가, Watch Item 상태 변경은 Domain이,
    영속성은 WatchListRepository가 각각 책임진다.
    """

    def __init__(
        self,
        *,
        repository: WatchListRepository,
        listing_lookup: ListingLookupPort,
        change_detector: LatestPriceChangeDetector,
        clock: Clock | None = None,
        snapshot_id_factory: SnapshotIdFactory | None = None,
    ) -> None:
        self._validate_dependency(
            repository,
            method_name="list_watching",
            dependency_name="repository",
        )
        self._validate_dependency(
            repository,
            method_name="save",
            dependency_name="repository",
        )
        self._validate_dependency(
            listing_lookup,
            method_name="get_listing",
            dependency_name="listing_lookup",
        )
        self._validate_dependency(
            change_detector,
            method_name="execute",
            dependency_name="change_detector",
        )

        if clock is not None and not callable(clock):
            raise TypeError("clock은 callable 또는 None이어야 합니다.")

        if (
            snapshot_id_factory is not None
            and not callable(snapshot_id_factory)
        ):
            raise TypeError(
                "snapshot_id_factory는 callable 또는 None이어야 합니다."
            )

        self._repository = repository
        self._listing_lookup = listing_lookup
        self._change_detector = change_detector
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._snapshot_id_factory = (
            snapshot_id_factory or (lambda: uuid4().hex)
        )

    def execute(self) -> WatchListMonitorResult:
        """현재 WATCHING 상태인 모든 항목을 서로 격리해 감시한다."""
        results: list[MonitorItemResult] = []

        for item in self._repository.list_watching():
            results.append(self._monitor_item(item))

        return WatchListMonitorResult(items=tuple(results))

    def _monitor_item(self, item: WatchItem) -> MonitorItemResult:
        previous_price = item.current_price

        try:
            product = self._listing_lookup.get_listing(
                marketplace=item.marketplace,
                item_id=item.item_id,
                url=item.url,
            )

            if product is None:
                return self._not_found_result(item)

            self._validate_listing_result(item, product)
            observed_at = self._resolve_observed_at()
            snapshot = self._create_snapshot(
                item=item,
                product=product,
                observed_at=observed_at,
            )
            response = self._change_detector.execute(
                current_snapshot=snapshot,
            )

            item.record_analysis(
                observed_price=product.price,
                analyzed_at=observed_at,
            )
            self._repository.save(item)

            status = (
                MonitorStatus.UPDATED
                if response.has_changes
                else MonitorStatus.UNCHANGED
            )

            return MonitorItemResult(
                watch_id=item.watch_id,
                marketplace=item.marketplace,
                item_id=item.item_id,
                status=status,
                previous_price=previous_price,
                current_price=product.price,
                currency=product.currency,
                change_count=(
                    response.change_count
                    if response.has_changes
                    else 0
                ),
            )
        except Exception as error:  # 항목별 실패 격리가 Use Case 계약이다.
            return self._failed_result(item, error)

    def _create_snapshot(
        self,
        *,
        item: WatchItem,
        product: Product,
        observed_at: datetime,
    ) -> PriceSnapshot:
        snapshot_id = self._snapshot_id_factory()

        if not isinstance(snapshot_id, str):
            raise TypeError("snapshot_id_factory는 문자열을 반환해야 합니다.")

        source_url = product.url or item.url
        if not source_url:
            source_url = (
                f"{item.marketplace}://listing/{item.item_id}"
            )

        return PriceSnapshot(
            snapshot_id=snapshot_id,
            canonical_product_id=(
                item.canonical_product_id or item.identity_key
            ),
            marketplace=product.marketplace,
            observed_at=observed_at,
            source_url=source_url,
            item_id=product.item_id or item.item_id,
            price=Decimal(str(product.price)),
            currency=product.currency,
            condition=product.condition or "Unknown",
            seller_id=product.seller or None,
        )

    def _resolve_observed_at(self) -> datetime:
        observed_at = self._clock()

        if not isinstance(observed_at, datetime):
            raise TypeError("clock은 datetime을 반환해야 합니다.")

        if observed_at.tzinfo is None:
            raise ValueError(
                "clock은 timezone-aware datetime을 반환해야 합니다."
            )

        return observed_at

    @staticmethod
    def _validate_listing_result(
        item: WatchItem,
        product: Product,
    ) -> None:
        if not isinstance(product, Product):
            raise TypeError(
                "ListingLookupPort는 Product 또는 None을 반환해야 합니다."
            )

        if product.marketplace.casefold() != item.marketplace.casefold():
            raise ValueError(
                "조회된 Product의 marketplace가 Watch Item과 다릅니다."
            )

        if (
            item.item_id
            and product.item_id
            and product.item_id.casefold() != item.item_id.casefold()
        ):
            raise ValueError(
                "조회된 Product의 item_id가 Watch Item과 다릅니다."
            )

        if product.currency.casefold() != item.currency.casefold():
            raise ValueError(
                "조회된 Product의 currency가 Watch Item과 다릅니다."
            )

    @staticmethod
    def _not_found_result(item: WatchItem) -> MonitorItemResult:
        return MonitorItemResult(
            watch_id=item.watch_id,
            marketplace=item.marketplace,
            item_id=item.item_id,
            status=MonitorStatus.NOT_FOUND,
        )

    @staticmethod
    def _failed_result(
        item: WatchItem,
        error: Exception,
    ) -> MonitorItemResult:
        message = str(error).strip() or type(error).__name__

        return MonitorItemResult(
            watch_id=item.watch_id,
            marketplace=item.marketplace,
            item_id=item.item_id,
            status=MonitorStatus.FAILED,
            error_message=message,
        )

    @staticmethod
    def _validate_dependency(
        dependency: object,
        *,
        method_name: str,
        dependency_name: str,
    ) -> None:
        if dependency is None:
            raise TypeError(f"{dependency_name}가 필요합니다.")

        if not callable(getattr(dependency, method_name, None)):
            raise TypeError(
                f"{dependency_name}는 {method_name}()을 제공해야 합니다."
            )
