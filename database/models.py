from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True)
class Product:
    name: str
    marketplace: str
    price: float
    currency: str

    brand: str = ""
    model_number: str = ""
    category: str = ""
    shipping_cost: float = 0.0
    seller: str = ""
    product_url: str = ""
    image_url: str = ""
    rating: float | None = None
    review_count: int | None = None
    in_stock: bool = True

    def __post_init__(self) -> None:
        self.name = self.name.strip()
        self.marketplace = self.marketplace.strip()
        self.currency = self.currency.strip().upper()

        if not self.name:
            raise ValueError("상품명은 비어 있을 수 없습니다.")

        if not self.marketplace:
            raise ValueError("마켓 이름은 비어 있을 수 없습니다.")

        if self.price < 0:
            raise ValueError("상품 가격은 0보다 작을 수 없습니다.")

        if self.shipping_cost < 0:
            raise ValueError("배송비는 0보다 작을 수 없습니다.")

        if self.rating is not None and not 0 <= self.rating <= 5:
            raise ValueError("평점은 0에서 5 사이여야 합니다.")

        if self.review_count is not None and self.review_count < 0:
            raise ValueError("리뷰 수는 0보다 작을 수 없습니다.")

    @property
    def total_cost(self) -> float:
        return round(self.price + self.shipping_cost, 2)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["total_cost"] = self.total_cost
        return data