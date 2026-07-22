from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from statistics import mean, median

from app.models import Product


TWOPLACES = Decimal("0.01")
ONE_HUNDRED = Decimal("100")


@dataclass(slots=True, frozen=True)
class PriceIntelligence:
    """
    같은 상품 그룹의 시장 가격 분석 결과.
    """

    currency: str
    lowest_price: Decimal
    average_price: Decimal
    median_price: Decimal
    highest_price: Decimal
    price_range: Decimal
    price_variation_rate: Decimal
    price_stability_level: str
    recommended_selling_price: Decimal
    sample_size: int


def _to_decimal(
    value: Decimal | int | float | str,
) -> Decimal:
    """
    지원되는 숫자 입력값을 안전하게 Decimal로 변환한다.

    float는 Decimal(value)가 아니라 Decimal(str(value))를 사용해
    이진 부동소수점 오차가 그대로 유입되는 것을 방지한다.
    """

    if isinstance(value, Decimal):
        return value

    return Decimal(str(value))


def _round_money(value: Decimal) -> Decimal:
    """
    금액을 소수점 둘째 자리까지 ROUND_HALF_UP 방식으로 반올림한다.
    """

    return value.quantize(
        TWOPLACES,
        rounding=ROUND_HALF_UP,
    )


def _calculate_price_stability_level(
    price_variation_rate: Decimal,
    sample_size: int,
) -> str:
    """
    가격 변동률과 표본 수를 기준으로 가격 안정성 등급을 계산한다.

    표본이 하나뿐이면 가격 비교가 불가능하므로 unknown을 반환한다.
    """

    if sample_size == 1:
        return "unknown"

    if price_variation_rate <= Decimal("10"):
        return "very_high"

    if price_variation_rate <= Decimal("20"):
        return "high"

    if price_variation_rate <= Decimal("40"):
        return "medium"

    if price_variation_rate <= Decimal("60"):
        return "low"

    return "very_low"


def analyze_product_prices(
    products: list[Product],
    *,
    fallback_multiplier: Decimal | int | float = Decimal("1.5"),
) -> PriceIntelligence:
    """
    같은 상품으로 판단된 Product 목록의 가격을 분석한다.

    상품이 2개 이상이면 중앙값을 권장 판매가로 사용한다.

    상품이 1개뿐이면 비교 가능한 시장 가격 정보가 부족하므로
    매입가에 fallback_multiplier를 곱한 값을 권장 판매가로 사용한다.

    가격 변동률은 가격 범위를 평균 가격으로 나눈 백분율이다.
    표본이 하나뿐이면 변동률은 0이지만 안정성은 unknown으로 처리한다.
    """

    if not products:
        raise ValueError(
            "가격을 분석할 상품이 하나 이상 필요합니다."
        )

    multiplier = _to_decimal(fallback_multiplier)

    if multiplier <= 0:
        raise ValueError(
            "fallback_multiplier는 0보다 커야 합니다."
        )

    currencies = {
        product.currency.upper().strip()
        for product in products
    }

    if len(currencies) != 1:
        raise ValueError(
            "서로 다른 통화의 상품 가격은 함께 분석할 수 없습니다."
        )

    prices = [
        _to_decimal(product.price)
        for product in products
    ]

    if any(price <= 0 for price in prices):
        raise ValueError(
            "상품 가격은 0보다 커야 합니다."
        )

    lowest_price = min(prices)
    average_price = Decimal(str(mean(prices)))
    median_price = Decimal(str(median(prices)))
    highest_price = max(prices)
    price_range = highest_price - lowest_price

    price_variation_rate = (
        price_range
        / average_price
        * ONE_HUNDRED
    )

    price_stability_level = (
        _calculate_price_stability_level(
            price_variation_rate,
            len(prices),
        )
    )

    if len(prices) == 1:
        recommended_selling_price = (
            lowest_price * multiplier
        )
    else:
        recommended_selling_price = median_price

    return PriceIntelligence(
        currency=next(iter(currencies)),
        lowest_price=_round_money(lowest_price),
        average_price=_round_money(average_price),
        median_price=_round_money(median_price),
        highest_price=_round_money(highest_price),
        price_range=_round_money(price_range),
        price_variation_rate=_round_money(
            price_variation_rate
        ),
        price_stability_level=price_stability_level,
        recommended_selling_price=_round_money(
            recommended_selling_price
        ),
        sample_size=len(prices),
    )