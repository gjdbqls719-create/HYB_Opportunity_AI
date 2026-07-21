from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import mean

from storage.price_history import PriceHistoryRecord


@dataclass(slots=True, frozen=True)
class PriceTrend:
    """
    특정 상품의 시간에 따른 가격 추세 분석 결과.
    """

    marketplace: str
    item_id: str
    title: str
    currency: str

    sample_size: int
    period_days: float

    oldest_price: float
    current_price: float
    lowest_price: float
    highest_price: float
    average_price: float

    absolute_change: float
    percentage_change: float | None

    trend_direction: str
    price_position: str
    recommendation: str
    reason: str

    has_sufficient_history: bool


def analyze_price_trend(
    records: list[PriceHistoryRecord],
    *,
    meaningful_change_rate: float = 1.0,
    bargain_threshold_rate: float = 5.0,
) -> PriceTrend:
    """
    가격 이력 목록을 이용해 가격 추세를 분석한다.

    Args:
        records:
            같은 상품의 가격 기록 목록.
            최신순 또는 과거순 어느 쪽이어도 된다.

        meaningful_change_rate:
            상승 또는 하락으로 판단할 최소 변동률.
            기본값은 1%.

        bargain_threshold_rate:
            평균 가격보다 얼마나 낮아야
            저렴한 가격으로 판단할지 정하는 비율.
            기본값은 5%.

    Returns:
        PriceTrend 분석 결과.
    """
    if not records:
        raise ValueError(
            "가격 이력이 최소 1개 필요합니다."
        )

    if meaningful_change_rate < 0:
        raise ValueError(
            "meaningful_change_rate는 "
            "0 이상이어야 합니다."
        )

    if bargain_threshold_rate < 0:
        raise ValueError(
            "bargain_threshold_rate는 "
            "0 이상이어야 합니다."
        )

    _validate_records(records)

    sorted_records = sorted(
        records,
        key=lambda record: (
            _parse_observed_at(record.observed_at),
            record.id,
        ),
    )

    oldest_record = sorted_records[0]
    current_record = sorted_records[-1]

    prices = [
        float(record.price)
        for record in sorted_records
    ]

    sample_size = len(prices)

    oldest_price = round(
        float(oldest_record.price),
        2,
    )

    current_price = round(
        float(current_record.price),
        2,
    )

    lowest_price = round(
        min(prices),
        2,
    )

    highest_price = round(
        max(prices),
        2,
    )

    average_price = round(
        mean(prices),
        2,
    )

    absolute_change = round(
        current_price - oldest_price,
        2,
    )

    percentage_change = _calculate_percentage_change(
        oldest_price=oldest_price,
        current_price=current_price,
    )

    oldest_time = _parse_observed_at(
        oldest_record.observed_at
    )

    current_time = _parse_observed_at(
        current_record.observed_at
    )

    period_seconds = max(
        0.0,
        (
            current_time - oldest_time
        ).total_seconds(),
    )

    period_days = round(
        period_seconds / 86_400,
        2,
    )

    has_sufficient_history = sample_size >= 2

    trend_direction = _determine_trend_direction(
        sample_size=sample_size,
        percentage_change=percentage_change,
        meaningful_change_rate=(
            meaningful_change_rate
        ),
    )

    price_position = _determine_price_position(
        current_price=current_price,
        lowest_price=lowest_price,
        highest_price=highest_price,
        average_price=average_price,
        bargain_threshold_rate=(
            bargain_threshold_rate
        ),
    )

    recommendation, reason = (
        _build_recommendation(
            sample_size=sample_size,
            current_price=current_price,
            lowest_price=lowest_price,
            average_price=average_price,
            percentage_change=percentage_change,
            trend_direction=trend_direction,
            bargain_threshold_rate=(
                bargain_threshold_rate
            ),
        )
    )

    return PriceTrend(
        marketplace=current_record.marketplace,
        item_id=current_record.item_id,
        title=current_record.title,
        currency=current_record.currency,
        sample_size=sample_size,
        period_days=period_days,
        oldest_price=oldest_price,
        current_price=current_price,
        lowest_price=lowest_price,
        highest_price=highest_price,
        average_price=average_price,
        absolute_change=absolute_change,
        percentage_change=percentage_change,
        trend_direction=trend_direction,
        price_position=price_position,
        recommendation=recommendation,
        reason=reason,
        has_sufficient_history=(
            has_sufficient_history
        ),
    )


def _validate_records(
    records: list[PriceHistoryRecord],
) -> None:
    first_record = records[0]

    expected_marketplace = (
        first_record.marketplace
    )

    expected_item_id = first_record.item_id
    expected_currency = first_record.currency

    for record in records:
        if record.price < 0:
            raise ValueError(
                "가격 기록에는 음수 가격을 "
                "사용할 수 없습니다."
            )

        if (
            record.marketplace
            != expected_marketplace
        ):
            raise ValueError(
                "서로 다른 마켓의 기록을 "
                "함께 분석할 수 없습니다."
            )

        if record.item_id != expected_item_id:
            raise ValueError(
                "서로 다른 상품의 기록을 "
                "함께 분석할 수 없습니다."
            )

        if record.currency != expected_currency:
            raise ValueError(
                "서로 다른 통화의 기록을 "
                "함께 분석할 수 없습니다."
            )

        _parse_observed_at(record.observed_at)


def _parse_observed_at(
    observed_at: str,
) -> datetime:
    try:
        return datetime.fromisoformat(
            observed_at
        )
    except ValueError as error:
        raise ValueError(
            "observed_at은 ISO 8601 형식이어야 합니다."
        ) from error


def _calculate_percentage_change(
    *,
    oldest_price: float,
    current_price: float,
) -> float | None:
    if oldest_price == 0:
        return None

    return round(
        (
            (
                current_price
                - oldest_price
            )
            / oldest_price
        )
        * 100,
        2,
    )


def _determine_trend_direction(
    *,
    sample_size: int,
    percentage_change: float | None,
    meaningful_change_rate: float,
) -> str:
    if sample_size < 2:
        return "데이터 부족"

    if percentage_change is None:
        return "판단 불가"

    if percentage_change <= (
        -meaningful_change_rate
    ):
        return "하락"

    if percentage_change >= (
        meaningful_change_rate
    ):
        return "상승"

    return "보합"


def _determine_price_position(
    *,
    current_price: float,
    lowest_price: float,
    highest_price: float,
    average_price: float,
    bargain_threshold_rate: float,
) -> str:
    if current_price == lowest_price:
        return "기간 최저가"

    if current_price == highest_price:
        return "기간 최고가"

    bargain_limit = average_price * (
        1 - bargain_threshold_rate / 100
    )

    expensive_limit = average_price * (
        1 + bargain_threshold_rate / 100
    )

    if current_price <= bargain_limit:
        return "평균보다 저렴"

    if current_price >= expensive_limit:
        return "평균보다 비쌈"

    return "평균 범위"


def _build_recommendation(
    *,
    sample_size: int,
    current_price: float,
    lowest_price: float,
    average_price: float,
    percentage_change: float | None,
    trend_direction: str,
    bargain_threshold_rate: float,
) -> tuple[str, str]:
    if sample_size < 2:
        return (
            "데이터 수집 필요",
            (
                "가격 기록이 1개뿐이어서 "
                "시간에 따른 변화를 판단할 수 없습니다."
            ),
        )

    if current_price == lowest_price:
        return (
            "매입 검토",
            (
                "현재 가격이 저장된 기간의 "
                "최저가입니다."
            ),
        )

    bargain_limit = average_price * (
        1 - bargain_threshold_rate / 100
    )

    if current_price <= bargain_limit:
        return (
            "매입 검토",
            (
                "현재 가격이 기간 평균보다 "
                f"{bargain_threshold_rate:.1f}% 이상 "
                "낮습니다."
            ),
        )

    if trend_direction == "상승":
        return (
            "주의",
            (
                "가격이 상승 추세이며 현재 가격이 "
                "저가 구간이 아닙니다."
            ),
        )

    if trend_direction == "하락":
        change_text = (
            "계산 불가"
            if percentage_change is None
            else f"{abs(percentage_change):.2f}%"
        )

        return (
            "관찰",
            (
                "가격이 "
                f"{change_text} 하락했지만 "
                "기간 최저가에는 도달하지 않았습니다."
            ),
        )

    return (
        "관찰",
        (
            "현재 가격이 기간 평균 범위에 있어 "
            "추가 가격 변화를 확인하는 것이 좋습니다."
        ),
    )