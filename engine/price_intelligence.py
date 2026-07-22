from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from statistics import mean, median

from app.models import Product


TWOPLACES = Decimal("0.01")


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
    recommended_selling_price: Decimal
    sample_size: int


def _to_decimal(
    value: Decimal | int | float | str,
) -> Decimal:
    if isinstance(value, Decimal):
        return value

    return Decimal(str(value))


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(
        TWOPLACES,
        rounding=ROUND_HALF_UP,
    )


def analyze_product_prices(
    products: list[Product],
    *,
    fallback_multiplier: Decimal | int | float = Decimal("1.5"),
) -> PriceIntelligence:
    """
    같은 상품으로 판단된 Product 목록의 가격을 분석한다.

    상품이 2개 이상이면 중앙값을 권장 판매가로 사용한다.
    상품이 1개뿐이면 가격 정보가 부족하므로
    기존 방식인 매입가 × fallback_multiplier를 사용한다.
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
    average_price = Decimal(
        str(mean(prices))
    )
    median_price = Decimal(
        str(median(prices))
    )
    highest_price = max(prices)

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
        recommended_selling_price=_round_money(
            recommended_selling_price
        ),
        sample_size=len(prices),
    )