from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from statistics import median

from app.domain.trend import (
    PriceTrendAnalysis,
    PriceVolatility,
    TrendDirection,
)
from storage.price_history import PriceHistoryRecord


_PERCENT_QUANTUM = Decimal("0.1")


@dataclass(frozen=True, slots=True)
class TrendAnalysisPolicy:
    """
    가격 추세 판정 임계값을 한곳에서 관리한다.

    모든 값은 백분율 단위다.
    """

    stable_change_rate_threshold: Decimal = Decimal("1.0")
    low_volatility_max_rate: Decimal = Decimal("5.0")
    medium_volatility_max_rate: Decimal = Decimal("15.0")
    proximity_band_rate: Decimal = Decimal("5.0")

    def __post_init__(self) -> None:
        decimal_fields = (
            "stable_change_rate_threshold",
            "low_volatility_max_rate",
            "medium_volatility_max_rate",
            "proximity_band_rate",
        )

        for field_name in decimal_fields:
            value = getattr(self, field_name)

            if not isinstance(value, Decimal):
                raise TypeError(
                    f"{field_name}은 Decimal이어야 합니다."
                )
            if not value.is_finite():
                raise ValueError(
                    f"{field_name}은 유한한 값이어야 합니다."
                )
            if value < 0:
                raise ValueError(
                    f"{field_name}은 0보다 작을 수 없습니다."
                )

        if (
            self.low_volatility_max_rate
            > self.medium_volatility_max_rate
        ):
            raise ValueError(
                "low_volatility_max_rate는 "
                "medium_volatility_max_rate보다 클 수 없습니다."
            )

        if self.proximity_band_rate > Decimal("50.0"):
            raise ValueError(
                "proximity_band_rate는 50.0을 초과할 수 없습니다."
            )


class TrendAnalysisEngine:
    """
    저장된 가격 관측 기록을 가격 추세 도메인 결과로 변환한다.

    PR-3에서는 변동성 및 현재가의 가격 범위 내 위치를 계산한다.
    """

    def __init__(
        self,
        policy: TrendAnalysisPolicy | None = None,
    ) -> None:
        self._policy = policy or TrendAnalysisPolicy()

    def analyze(
        self,
        records: Sequence[PriceHistoryRecord],
    ) -> PriceTrendAnalysis:
        record_list = list(records)

        if not record_list:
            raise ValueError(
                "가격 추세 분석에는 하나 이상의 기록이 필요합니다."
            )

        self._validate_records(record_list)

        ordered_records = sorted(
            record_list,
            key=lambda record: (
                record.observed_at,
                record.id,
            ),
        )
        prices = [
            Decimal(str(record.price))
            for record in ordered_records
        ]

        first_price = prices[0]
        current_price = prices[-1]
        highest_price = max(prices)
        lowest_price = min(prices)
        average_price = (
            sum(prices, start=Decimal("0"))
            / Decimal(len(prices))
        )
        median_price = Decimal(str(median(prices)))
        price_range = highest_price - lowest_price

        change_rate = self._calculate_change_rate(
            first_price=first_price,
            current_price=current_price,
        )
        direction = self._determine_direction(change_rate)
        volatility = self._determine_volatility(
            price_range=price_range,
            average_price=average_price,
        )
        near_lowest, near_highest = self._determine_position_flags(
            current_price=current_price,
            lowest_price=lowest_price,
            highest_price=highest_price,
            price_range=price_range,
        )

        return PriceTrendAnalysis(
            current_price=current_price,
            highest_price=highest_price,
            lowest_price=lowest_price,
            average_price=average_price,
            median_price=median_price,
            price_range=price_range,
            change_rate=change_rate,
            direction=direction,
            volatility=volatility,
            near_lowest=near_lowest,
            near_highest=near_highest,
            sample_count=len(prices),
        )

    @staticmethod
    def _calculate_change_rate(
        *,
        first_price: Decimal,
        current_price: Decimal,
    ) -> Decimal:
        if first_price == 0:
            if current_price == 0:
                return Decimal("0.0")
            return Decimal("100.0")

        change_rate = (
            (current_price - first_price)
            / first_price
            * Decimal("100")
        )
        return change_rate.quantize(
            _PERCENT_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

    def _determine_direction(
        self,
        change_rate: Decimal,
    ) -> TrendDirection:
        threshold = self._policy.stable_change_rate_threshold

        if change_rate > threshold:
            return TrendDirection.UP

        if change_rate < -threshold:
            return TrendDirection.DOWN

        return TrendDirection.STABLE

    def _determine_volatility(
        self,
        *,
        price_range: Decimal,
        average_price: Decimal,
    ) -> PriceVolatility:
        """
        평균가 대비 전체 가격 범위의 비율로 변동성을 판정한다.

        range_rate = (highest - lowest) / average * 100
        """
        if average_price == 0:
            range_rate = Decimal("0.0")
        else:
            range_rate = (
                price_range
                / average_price
                * Decimal("100")
            ).quantize(
                _PERCENT_QUANTUM,
                rounding=ROUND_HALF_UP,
            )

        if range_rate <= self._policy.low_volatility_max_rate:
            return PriceVolatility.LOW

        if range_rate <= self._policy.medium_volatility_max_rate:
            return PriceVolatility.MEDIUM

        return PriceVolatility.HIGH

    def _determine_position_flags(
        self,
        *,
        current_price: Decimal,
        lowest_price: Decimal,
        highest_price: Decimal,
        price_range: Decimal,
    ) -> tuple[bool, bool]:
        """
        현재가가 전체 가격 범위의 양 끝 5% 이내인지 판정한다.

        모든 가격이 같아 범위가 0이면 현재가는 동시에
        최저가이자 최고가이므로 두 플래그 모두 True다.
        """
        if price_range == 0:
            return True, True

        proximity_ratio = (
            self._policy.proximity_band_rate
            / Decimal("100")
        )
        proximity_amount = price_range * proximity_ratio

        near_lowest = (
            current_price - lowest_price
            <= proximity_amount
        )
        near_highest = (
            highest_price - current_price
            <= proximity_amount
        )

        return near_lowest, near_highest

    @staticmethod
    def _validate_records(
        records: list[PriceHistoryRecord],
    ) -> None:
        for record in records:
            if not isinstance(record, PriceHistoryRecord):
                raise TypeError(
                    "records의 모든 항목은 "
                    "PriceHistoryRecord여야 합니다."
                )

            price = Decimal(str(record.price))
            if not price.is_finite():
                raise ValueError(
                    "가격은 유한한 숫자여야 합니다."
                )
            if price < 0:
                raise ValueError(
                    "가격은 0보다 작을 수 없습니다."
                )

            if not record.observed_at.strip():
                raise ValueError(
                    "observed_at은 비어 있을 수 없습니다."
                )


def analyze_price_history(
    records: Sequence[PriceHistoryRecord],
) -> PriceTrendAnalysis:
    """기본 정책의 TrendAnalysisEngine으로 가격 이력을 분석한다."""
    return TrendAnalysisEngine().analyze(records)
