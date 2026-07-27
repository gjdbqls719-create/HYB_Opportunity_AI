from __future__ import annotations

from dataclasses import dataclass

from app.domain.change import (
    ChangeDetectedEvent,
    ChangeSet,
)
from market_data.inventory_snapshot import (
    InventorySnapshot,
)
from market_data.price_snapshot import PriceSnapshot
from market_data.seller_snapshot import SellerSnapshot


SupportedSnapshot = (
    PriceSnapshot
    | InventorySnapshot
    | SellerSnapshot
)


@dataclass(frozen=True, slots=True)
class SnapshotPair:
    """
    변화 탐지에 사용할 이전·현재 Snapshot 쌍.

    Application Layer는 Snapshot의 저장 방식이나
    조회 방식에 관여하지 않고, 이미 준비된 두 Snapshot을
    비교 대상으로 전달받는다.
    """

    previous: SupportedSnapshot
    current: SupportedSnapshot

    def __post_init__(self) -> None:
        supported_types = (
            PriceSnapshot,
            InventorySnapshot,
            SellerSnapshot,
        )

        if not isinstance(
            self.previous,
            supported_types,
        ):
            raise TypeError(
                "previous는 지원되는 Snapshot이어야 합니다."
            )

        if not isinstance(
            self.current,
            supported_types,
        ):
            raise TypeError(
                "current는 지원되는 Snapshot이어야 합니다."
            )

        if type(self.previous) is not type(self.current):
            raise TypeError(
                "previous와 current는 동일한 종류의 "
                "Snapshot이어야 합니다."
            )

    @property
    def snapshot_type(self) -> type[SupportedSnapshot]:
        return type(self.current)

    @property
    def canonical_product_id(self) -> str:
        return self.current.canonical_product_id

    @property
    def marketplace(self) -> str:
        return self.current.marketplace


@dataclass(frozen=True, slots=True)
class ChangeDetectionResponse:
    """
    한 번의 Change Detection Application 실행 결과.
    """

    change_sets: tuple[ChangeSet, ...]
    events: tuple[ChangeDetectedEvent, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "change_sets",
            tuple(self.change_sets),
        )
        object.__setattr__(
            self,
            "events",
            tuple(self.events),
        )

        if not all(
            isinstance(change_set, ChangeSet)
            for change_set in self.change_sets
        ):
            raise TypeError(
                "change_sets의 모든 항목은 "
                "ChangeSet이어야 합니다."
            )

        if not all(
            isinstance(event, ChangeDetectedEvent)
            for event in self.events
        ):
            raise TypeError(
                "events의 모든 항목은 "
                "ChangeDetectedEvent이어야 합니다."
            )

    @property
    def compared_pair_count(self) -> int:
        return len(self.change_sets)

    @property
    def changed_pair_count(self) -> int:
        return sum(
            change_set.has_changes
            for change_set in self.change_sets
        )

    @property
    def unchanged_pair_count(self) -> int:
        return (
            self.compared_pair_count
            - self.changed_pair_count
        )

    @property
    def change_count(self) -> int:
        return sum(
            change_set.change_count
            for change_set in self.change_sets
        )

    @property
    def event_count(self) -> int:
        return len(self.events)

    @property
    def has_changes(self) -> bool:
        return self.changed_pair_count > 0

    def events_for_product(
        self,
        canonical_product_id: str,
    ) -> tuple[ChangeDetectedEvent, ...]:
        normalized_id = canonical_product_id.strip()

        if not normalized_id:
            raise ValueError(
                "canonical_product_id는 "
                "비어 있을 수 없습니다."
            )

        return tuple(
            event
            for event in self.events
            if event.canonical_product_id
            == normalized_id
        )