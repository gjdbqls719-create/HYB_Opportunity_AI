from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class MarketSnapshot:
    product_name: str
    marketplace: str
    currency: str

    current_price: float
    average_price: float
    lowest_price: float
    highest_price: float

    estimated_monthly_sales: int = 0
    competitor_count: int = 0
    rating: float | None = None
    review_count: int | None = None
    price_change_rate: float = 0.0
    in_stock: bool = True

    def __post_init__(self) -> None:
        self.product_name = self.product_name.strip()
        self.marketplace = self.marketplace.strip()
        self.currency = self.currency.strip().upper()

        if not self.product_name:
            raise ValueError("상품명은 비어 있을 수 없습니다.")

        if not self.marketplace:
            raise ValueError("마켓 이름은 비어 있을 수 없습니다.")

        prices = {
            "현재가": self.current_price,
            "평균가": self.average_price,
            "최저가": self.lowest_price,
            "최고가": self.highest_price,
        }

        for label, price in prices.items():
            if price < 0:
                raise ValueError(f"{label}는 0보다 작을 수 없습니다.")

        if self.lowest_price > self.highest_price:
            raise ValueError("최저가는 최고가보다 클 수 없습니다.")

        if not self.lowest_price <= self.average_price <= self.highest_price:
            raise ValueError(
                "평균가는 최저가와 최고가 사이여야 합니다."
            )

        if self.estimated_monthly_sales < 0:
            raise ValueError("예상 판매량은 0보다 작을 수 없습니다.")

        if self.competitor_count < 0:
            raise ValueError("경쟁 판매자 수는 0보다 작을 수 없습니다.")

        if self.rating is not None and not 0 <= self.rating <= 5:
            raise ValueError("평점은 0에서 5 사이여야 합니다.")

        if self.review_count is not None and self.review_count < 0:
            raise ValueError("리뷰 수는 0보다 작을 수 없습니다.")

    @property
    def price_position_rate(self) -> float:
        """
        현재 가격이 최저가와 최고가 사이에서 어느 위치인지 계산한다.

        0%에 가까우면 시장 최저가에 가깝고,
        100%에 가까우면 시장 최고가에 가깝다.
        """

        price_range = self.highest_price - self.lowest_price

        if price_range == 0:
            return 0.0

        position = (
            (self.current_price - self.lowest_price)
            / price_range
            * 100
        )

        return round(position, 1)

    @property
    def discount_from_average_rate(self) -> float:
        """
        현재가가 시장 평균가보다 얼마나 저렴한지 계산한다.
        양수면 평균가보다 저렴하고, 음수면 더 비싸다.
        """

        if self.average_price == 0:
            return 0.0

        discount = (
            (self.average_price - self.current_price)
            / self.average_price
            * 100
        )

        return round(discount, 1)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["price_position_rate"] = self.price_position_rate
        data["discount_from_average_rate"] = (
            self.discount_from_average_rate
        )
        return data