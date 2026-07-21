from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True, init=False)
class Product:
    """
    HYB Opportunity AI 전체에서 사용하는 단일 상품 모델.

    마켓플레이스 수집/분석 코드에서 사용하던 ``title``·``url``과
    초기 데이터베이스 모델에서 사용하던 ``name``·``product_url``을
    모두 지원한다. 내부 저장 필드는 ``title``과 ``url``로 통일한다.
    """

    marketplace: str
    item_id: str
    title: str
    price: float
    currency: str
    condition: str
    url: str

    brand: str
    model_number: str
    category: str
    shipping_cost: float
    seller: str
    image_url: str
    rating: float | None
    review_count: int | None
    in_stock: bool

    def __init__(
        self,
        *,
        marketplace: str,
        price: float,
        currency: str,
        item_id: str = "",
        title: str | None = None,
        name: str | None = None,
        condition: str = "",
        url: str | None = None,
        product_url: str | None = None,
        brand: str = "",
        model_number: str = "",
        category: str = "",
        shipping_cost: float = 0.0,
        seller: str = "",
        image_url: str = "",
        rating: float | None = None,
        review_count: int | None = None,
        in_stock: bool = True,
    ) -> None:
        resolved_title = title if title is not None else name
        resolved_url = url if url is not None else product_url

        if resolved_title is None:
            raise ValueError("상품명(title 또는 name)을 입력해야 합니다.")

        self.marketplace = marketplace.strip()
        self.item_id = item_id.strip()
        self.title = resolved_title.strip()
        self.price = float(price)
        self.currency = currency.strip().upper()
        self.condition = condition.strip()
        self.url = (resolved_url or "").strip()

        self.brand = brand.strip()
        self.model_number = model_number.strip()
        self.category = category.strip()
        self.shipping_cost = float(shipping_cost)
        self.seller = seller.strip()
        self.image_url = image_url.strip()
        self.rating = float(rating) if rating is not None else None
        self.review_count = (
            int(review_count) if review_count is not None else None
        )
        self.in_stock = bool(in_stock)

        self._validate()

    def _validate(self) -> None:
        if not self.title:
            raise ValueError("상품명은 비어 있을 수 없습니다.")

        if not self.marketplace:
            raise ValueError("마켓 이름은 비어 있을 수 없습니다.")

        if not self.currency:
            raise ValueError("통화는 비어 있을 수 없습니다.")

        if self.price < 0:
            raise ValueError("상품 가격은 0보다 작을 수 없습니다.")

        if self.shipping_cost < 0:
            raise ValueError("배송비는 0보다 작을 수 없습니다.")

        if self.rating is not None and not 0 <= self.rating <= 5:
            raise ValueError("평점은 0에서 5 사이여야 합니다.")

        if self.review_count is not None and self.review_count < 0:
            raise ValueError("리뷰 수는 0보다 작을 수 없습니다.")

    @property
    def name(self) -> str:
        """이전 데이터베이스 모델과의 호환용 상품명 별칭."""
        return self.title

    @name.setter
    def name(self, value: str) -> None:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("상품명은 비어 있을 수 없습니다.")
        self.title = cleaned

    @property
    def product_url(self) -> str:
        """이전 데이터베이스 모델과의 호환용 URL 별칭."""
        return self.url

    @product_url.setter
    def product_url(self, value: str) -> None:
        self.url = value.strip()

    @property
    def total_cost(self) -> float:
        return round(self.price + self.shipping_cost, 2)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["name"] = self.name
        data["product_url"] = self.product_url
        data["total_cost"] = self.total_cost
        return data
