from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, median

from app.models import Product


@dataclass(slots=True, frozen=True)
class PriceIntelligence:
    """
    같은 상품 그룹의 시장 가격 분석 결과.
    """

    currency: str
    lowest_price: float
    average_price: float
    median_price: float
    highest_price: float
    recommended_selling_price: float
    sample_size: int


def analyze_product_prices(
    products: list[Product],
    *,
    fallback_multiplier: float = 1.5,
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

    if fallback_multiplier <= 0:
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
        float(product.price)
        for product in products
    ]

    if any(price <= 0 for price in prices):
        raise ValueError(
            "상품 가격은 0보다 커야 합니다."
        )

    lowest_price = min(prices)
    average_price = mean(prices)
    median_price = median(prices)
    highest_price = max(prices)

    if len(prices) == 1:
        recommended_selling_price = (
            lowest_price * fallback_multiplier
        )
    else:
        recommended_selling_price = median_price

    return PriceIntelligence(
        currency=next(iter(currencies)),
        lowest_price=round(lowest_price, 2),
        average_price=round(average_price, 2),
        median_price=round(median_price, 2),
        highest_price=round(highest_price, 2),
        recommended_selling_price=round(
            recommended_selling_price,
            2,
        ),
        sample_size=len(prices),
    )