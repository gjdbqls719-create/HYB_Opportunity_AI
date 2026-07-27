from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.trend.direction import TrendDirection
from app.domain.trend.volatility import PriceVolatility


@dataclass(frozen=True, slots=True)
class PriceTrendAnalysis:
    """
    가격 이력 분석 결과를 표현하는 불변 Domain Model.

    이 객체는 계산 방법이나 저장 방식에 관여하지 않는다.
    Trend Analysis Engine이 계산한 결과를 검증하고 전달하는
    역할만 담당한다.
    """

    current_price: Decimal
    highest_price: Decimal
    lowest_price: Decimal
    average_price: Decimal
    median_price: Decimal
    price_range: Decimal
    change_rate: Decimal
    direction: TrendDirection
    volatility: PriceVolatility
    near_lowest: bool
    near_highest: bool
    sample_count: int

    def __post_init__(self) -> None:
        decimal_fields = (
            "current_price",
            "highest_price",
            "lowest_price",
            "average_price",
            "median_price",
            "price_range",
            "change_rate",
        )

        for field_name in decimal_fields:
            value = getattr(self, field_name)

            if not isinstance(value, Decimal):
                raise TypeError(
                    f"{field_name}는 Decimal이어야 합니다."
                )

        non_negative_fields = (
            "current_price",
            "highest_price",
            "lowest_price",
            "average_price",
            "median_price",
            "price_range",
        )

        for field_name in non_negative_fields:
            value = getattr(self, field_name)

            if value < Decimal("0"):
                raise ValueError(
                    f"{field_name}는 0보다 작을 수 없습니다."
                )

        if not isinstance(
            self.direction,
            TrendDirection,
        ):
            raise TypeError(
                "direction은 TrendDirection이어야 합니다."
            )

        if not isinstance(
            self.volatility,
            PriceVolatility,
        ):
            raise TypeError(
                "volatility는 PriceVolatility이어야 합니다."
            )

        if not isinstance(self.near_lowest, bool):
            raise TypeError(
                "near_lowest는 bool이어야 합니다."
            )

        if not isinstance(self.near_highest, bool):
            raise TypeError(
                "near_highest는 bool이어야 합니다."
            )

        if not isinstance(self.sample_count, int):
            raise TypeError(
                "sample_count는 int여야 합니다."
            )

        if self.sample_count < 1:
            raise ValueError(
                "sample_count는 1 이상이어야 합니다."
            )

        if self.lowest_price > self.highest_price:
            raise ValueError(
                "lowest_price는 highest_price보다 "
                "클 수 없습니다."
            )

        if not (
            self.lowest_price
            <= self.current_price
            <= self.highest_price
        ):
            raise ValueError(
                "current_price는 lowest_price와 "
                "highest_price 사이여야 합니다."
            )

        if not (
            self.lowest_price
            <= self.average_price
            <= self.highest_price
        ):
            raise ValueError(
                "average_price는 lowest_price와 "
                "highest_price 사이여야 합니다."
            )

        if not (
            self.lowest_price
            <= self.median_price
            <= self.highest_price
        ):
            raise ValueError(
                "median_price는 lowest_price와 "
                "highest_price 사이여야 합니다."
            )

        expected_range = (
            self.highest_price
            - self.lowest_price
        )

        if self.price_range != expected_range:
            raise ValueError(
                "price_range는 highest_price에서 "
                "lowest_price를 뺀 값이어야 합니다."
            )

        if self.sample_count == 1:
            self._validate_single_sample()

    def _validate_single_sample(self) -> None:
        if not (
            self.current_price
            == self.highest_price
            == self.lowest_price
            == self.average_price
            == self.median_price
        ):
            raise ValueError(
                "sample_count가 1이면 모든 대표 가격은 "
                "current_price와 같아야 합니다."
            )

        if self.price_range != Decimal("0"):
            raise ValueError(
                "sample_count가 1이면 price_range는 "
                "0이어야 합니다."
            )

        if self.change_rate != Decimal("0"):
            raise ValueError(
                "sample_count가 1이면 change_rate는 "
                "0이어야 합니다."
            )

        if self.direction is not TrendDirection.STABLE:
            raise ValueError(
                "sample_count가 1이면 direction은 "
                "STABLE이어야 합니다."
            )
