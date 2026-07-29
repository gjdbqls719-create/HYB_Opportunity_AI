from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite


class MonitorStatus(StrEnum):
    """개별 Watch Item 감시 실행 결과 상태."""

    UPDATED = "updated"
    UNCHANGED = "unchanged"
    NOT_FOUND = "not_found"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class MonitorItemResult:
    """
    하나의 Watch Item을 다시 조회하고 분석한 결과.

    UPDATED와 UNCHANGED는 Marketplace Listing을 정상적으로 조회하고
    분석까지 완료한 상태다. NOT_FOUND는 Listing을 찾지 못한 상태이며,
    FAILED는 조회 또는 분석 과정에서 실행 오류가 발생한 상태다.
    """

    watch_id: str
    marketplace: str
    item_id: str
    status: MonitorStatus

    previous_price: float | None = None
    current_price: float | None = None
    currency: str = ""
    change_count: int = 0
    error_message: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "watch_id", self.watch_id.strip())
        object.__setattr__(
            self,
            "marketplace",
            self.marketplace.strip().lower(),
        )
        object.__setattr__(self, "item_id", self.item_id.strip())
        object.__setattr__(
            self,
            "currency",
            self.currency.strip().upper(),
        )
        object.__setattr__(
            self,
            "error_message",
            self.error_message.strip(),
        )

        if not self.watch_id:
            raise ValueError("watch_id는 비어 있을 수 없습니다.")

        if not self.marketplace:
            raise ValueError("marketplace는 비어 있을 수 없습니다.")

        if not isinstance(self.status, MonitorStatus):
            raise TypeError("status는 MonitorStatus여야 합니다.")

        self._validate_optional_price(
            self.previous_price,
            field_name="previous_price",
        )
        self._validate_optional_price(
            self.current_price,
            field_name="current_price",
        )

        if not isinstance(self.change_count, int):
            raise TypeError("change_count는 정수여야 합니다.")

        if self.change_count < 0:
            raise ValueError("change_count는 음수일 수 없습니다.")

        completed_statuses = {
            MonitorStatus.UPDATED,
            MonitorStatus.UNCHANGED,
        }

        if self.status in completed_statuses:
            if self.current_price is None:
                raise ValueError(
                    "정상 완료 결과에는 current_price가 필요합니다."
                )

            if not self.currency:
                raise ValueError(
                    "정상 완료 결과에는 currency가 필요합니다."
                )

        if self.status is MonitorStatus.UPDATED:
            if self.change_count < 1:
                raise ValueError(
                    "UPDATED 결과의 change_count는 1 이상이어야 합니다."
                )
        elif self.change_count != 0:
            raise ValueError(
                "UPDATED가 아닌 결과의 change_count는 0이어야 합니다."
            )

        if self.status is MonitorStatus.FAILED:
            if not self.error_message:
                raise ValueError(
                    "FAILED 결과에는 error_message가 필요합니다."
                )
        elif self.error_message:
            raise ValueError(
                "FAILED가 아닌 결과에는 error_message를 기록할 수 없습니다."
            )

    @property
    def is_successful(self) -> bool:
        return self.status in {
            MonitorStatus.UPDATED,
            MonitorStatus.UNCHANGED,
        }

    @property
    def has_changes(self) -> bool:
        return self.status is MonitorStatus.UPDATED

    @staticmethod
    def _validate_optional_price(
        value: float | None,
        *,
        field_name: str,
    ) -> None:
        if value is None:
            return

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TypeError(f"{field_name}는 숫자여야 합니다.")

        if not isfinite(float(value)):
            raise ValueError(f"{field_name}는 유한한 숫자여야 합니다.")

        if value < 0:
            raise ValueError(f"{field_name}는 음수일 수 없습니다.")


@dataclass(frozen=True, slots=True)
class WatchListMonitorResult:
    """한 번의 Watch List 감시 실행에서 생성된 전체 결과."""

    items: tuple[MonitorItemResult, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "items", tuple(self.items))

        if not all(
            isinstance(item, MonitorItemResult)
            for item in self.items
        ):
            raise TypeError(
                "items의 모든 항목은 MonitorItemResult여야 합니다."
            )

    @property
    def total_count(self) -> int:
        return len(self.items)

    @property
    def successful_count(self) -> int:
        return sum(item.is_successful for item in self.items)

    @property
    def updated_count(self) -> int:
        return sum(item.has_changes for item in self.items)

    @property
    def unchanged_count(self) -> int:
        return sum(
            item.status is MonitorStatus.UNCHANGED
            for item in self.items
        )

    @property
    def not_found_count(self) -> int:
        return sum(
            item.status is MonitorStatus.NOT_FOUND
            for item in self.items
        )

    @property
    def failed_count(self) -> int:
        return sum(
            item.status is MonitorStatus.FAILED
            for item in self.items
        )

    @property
    def change_count(self) -> int:
        return sum(item.change_count for item in self.items)

    @property
    def has_failures(self) -> bool:
        return self.failed_count > 0

    @property
    def has_changes(self) -> bool:
        return self.updated_count > 0
