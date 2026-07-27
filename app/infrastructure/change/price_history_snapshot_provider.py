from __future__ import annotations

from collections.abc import Callable

from market_data.price_snapshot import PriceSnapshot
from market_data.snapshot_mapper import (
    price_history_to_price_snapshot,
)
from storage.price_history import (
    PriceHistoryRecord,
    PriceHistoryRepository,
)


PriceSnapshotMapper = Callable[
    [PriceHistoryRecord],
    PriceSnapshot,
]


class PriceHistorySnapshotProvider:
    """
    기존 SQLite PriceHistoryRepository를
    PriceSnapshotProvider Application Port에 연결한다.

    Application Layer에는 PriceHistoryRecord나 SQLite를
    노출하지 않고 Domain PriceSnapshot만 반환한다.
    """

    def __init__(
        self,
        *,
        repository: PriceHistoryRepository,
        mapper: PriceSnapshotMapper = (
            price_history_to_price_snapshot
        ),
    ) -> None:
        if not isinstance(
            repository,
            PriceHistoryRepository,
        ):
            raise TypeError(
                "repository는 "
                "PriceHistoryRepository여야 합니다."
            )

        if not callable(mapper):
            raise TypeError(
                "mapper는 호출 가능한 객체여야 합니다."
            )

        self._repository = repository
        self._mapper = mapper

    def get_latest_for_listing(
        self,
        *,
        marketplace: str,
        item_id: str,
    ) -> PriceSnapshot | None:
        cleaned_marketplace = self._require_text(
            marketplace,
            field_name="marketplace",
        )
        cleaned_item_id = self._require_text(
            item_id,
            field_name="item_id",
        )

        record = self._repository.get_latest_record(
            marketplace=cleaned_marketplace,
            item_id=cleaned_item_id,
        )

        return self._map_optional_record(record)

    def get_latest_for_canonical_product(
        self,
        *,
        canonical_product_id: str,
    ) -> PriceSnapshot | None:
        cleaned_id = self._require_text(
            canonical_product_id,
            field_name="canonical_product_id",
        )

        record = (
            self._repository
            .get_latest_canonical_record(
                canonical_product_id=cleaned_id,
            )
        )

        return self._map_optional_record(record)

    def _map_optional_record(
        self,
        record: PriceHistoryRecord | None,
    ) -> PriceSnapshot | None:
        if record is None:
            return None

        snapshot = self._mapper(record)

        if not isinstance(snapshot, PriceSnapshot):
            raise TypeError(
                "mapper는 PriceSnapshot을 반환해야 합니다."
            )

        return snapshot

    @staticmethod
    def _require_text(
        value: str,
        *,
        field_name: str,
    ) -> str:
        if not isinstance(value, str):
            raise TypeError(
                f"{field_name}는 문자열이어야 합니다."
            )

        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError(
                f"{field_name}는 비어 있을 수 없습니다."
            )

        return cleaned_value