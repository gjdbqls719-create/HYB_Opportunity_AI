from __future__ import annotations

from app.application.change.models import (
    ChangeDetectionResponse,
    SnapshotPair,
)
from app.domain.change import (
    ChangeEventBatchPublisher,
    ChangeSet,
    create_change_events,
    detect_inventory_changes,
    detect_price_changes,
    detect_seller_changes,
)
from market_data.inventory_snapshot import (
    InventorySnapshot,
)
from market_data.price_snapshot import PriceSnapshot
from market_data.seller_snapshot import SellerSnapshot


class DetectChangesUseCase:
    """
    Snapshot 쌍들을 비교해 ChangeSet과 Domain Event를
    생성하는 Change Application 진입점.

    Snapshot 조회와 저장은 이 Use Case의 책임이 아니다.
    호출자가 준비한 SnapshotPair만 비교한다.

    publisher가 주입되면 생성된 이벤트를 실행 마지막에
    한 번의 batch 호출로 발행한다.
    """

    def __init__(
        self,
        *,
        publisher: ChangeEventBatchPublisher | None = None,
    ) -> None:
        self._publisher = publisher

    def execute(
        self,
        *,
        snapshot_pairs: tuple[SnapshotPair, ...],
    ) -> ChangeDetectionResponse:
        normalized_pairs = tuple(snapshot_pairs)

        if not all(
            isinstance(pair, SnapshotPair)
            for pair in normalized_pairs
        ):
            raise TypeError(
                "snapshot_pairs의 모든 항목은 "
                "SnapshotPair이어야 합니다."
            )

        change_sets = tuple(
            self._detect_pair(pair)
            for pair in normalized_pairs
        )

        events = tuple(
            event
            for change_set in change_sets
            for event in create_change_events(
                change_set
            )
        )

        response = ChangeDetectionResponse(
            change_sets=change_sets,
            events=events,
        )

        if (
            self._publisher is not None
            and response.events
        ):
            self._publisher.publish_many(
                response.events
            )

        return response

    @staticmethod
    def _detect_pair(
        pair: SnapshotPair,
    ) -> ChangeSet:
        previous = pair.previous
        current = pair.current

        if isinstance(previous, PriceSnapshot):
            if not isinstance(current, PriceSnapshot):
                raise TypeError(
                    "PriceSnapshot은 같은 종류끼리 "
                    "비교해야 합니다."
                )

            return detect_price_changes(
                previous,
                current,
            )

        if isinstance(
            previous,
            InventorySnapshot,
        ):
            if not isinstance(
                current,
                InventorySnapshot,
            ):
                raise TypeError(
                    "InventorySnapshot은 같은 종류끼리 "
                    "비교해야 합니다."
                )

            return detect_inventory_changes(
                previous,
                current,
            )

        if isinstance(previous, SellerSnapshot):
            if not isinstance(current, SellerSnapshot):
                raise TypeError(
                    "SellerSnapshot은 같은 종류끼리 "
                    "비교해야 합니다."
                )

            return detect_seller_changes(
                previous,
                current,
            )

        raise TypeError(
            "지원하지 않는 Snapshot 종류입니다."
        )