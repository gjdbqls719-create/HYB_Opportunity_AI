from __future__ import annotations

from abc import ABC, abstractmethod
from math import isfinite
from typing import Any

from app.models import Product


class MarketplaceValidationError(ValueError):
    """마켓 원본 또는 정규화된 상품이 공통 계약을 위반했을 때 발생한다."""


class MarketplaceAdapter(ABC):
    """마켓별 원본 데이터를 검증된 공통 Product 모델로 변환한다."""

    marketplace_name: str

    @abstractmethod
    def normalize(self, raw_product: dict[str, Any]) -> Product:
        """마켓 원본 상품 하나를 Product 객체로 변환한다."""
        raise NotImplementedError

    def normalize_and_validate(self, raw_product: dict[str, Any]) -> Product:
        """원본 데이터를 정규화한 뒤 Marketplace 공통 계약을 검증한다."""

        if not isinstance(raw_product, dict):
            raise MarketplaceValidationError(
                "마켓 원본 상품은 dict 형식이어야 합니다."
            )

        product = self.normalize(raw_product)
        return self.validate_product(product)

    def validate_product(self, product: Product) -> Product:
        """정규화된 Product가 Marketplace 공통 계약을 지키는지 검증한다."""

        if not isinstance(product, Product):
            raise MarketplaceValidationError(
                "normalize()는 Product 객체를 반환해야 합니다."
            )

        expected_marketplace = self.marketplace_name.strip().lower()
        actual_marketplace = product.marketplace.strip().lower()

        if not expected_marketplace:
            raise MarketplaceValidationError(
                "Adapter의 marketplace_name은 비어 있을 수 없습니다."
            )

        if actual_marketplace != expected_marketplace:
            raise MarketplaceValidationError(
                "정규화된 상품의 marketplace가 Adapter와 일치하지 않습니다."
            )

        if not product.item_id.strip():
            raise MarketplaceValidationError(
                "마켓 상품 ID는 비어 있을 수 없습니다."
            )

        if not product.title.strip():
            raise MarketplaceValidationError(
                "상품명은 비어 있을 수 없습니다."
            )

        if not product.currency.strip():
            raise MarketplaceValidationError(
                "통화는 비어 있을 수 없습니다."
            )

        if not isfinite(product.price):
            raise MarketplaceValidationError(
                "상품 가격은 유한한 숫자여야 합니다."
            )

        if product.price < 0:
            raise MarketplaceValidationError(
                "상품 가격은 0보다 작을 수 없습니다."
            )

        return product


def parse_price(value: Any) -> float:
    """문자열 또는 숫자 가격을 안전하게 유한한 float로 바꾼다."""

    if isinstance(value, bool):
        raise ValueError("가격에 True 또는 False를 사용할 수 없습니다.")

    if isinstance(value, int | float):
        price = float(value)
    elif isinstance(value, str):
        cleaned = (
            value.strip()
            .replace(",", "")
            .replace("$", "")
            .replace("£", "")
            .replace("€", "")
            .replace("₩", "")
        )

        if not cleaned:
            raise ValueError("가격이 비어 있습니다.")

        price = float(cleaned)
    else:
        raise TypeError("지원하지 않는 가격 형식입니다.")

    if not isfinite(price):
        raise ValueError("가격은 유한한 숫자여야 합니다.")

    if price < 0:
        raise ValueError("가격은 0보다 작을 수 없습니다.")

    return round(price, 2)


def parse_rating(value: Any) -> float | None:
    """평점을 0~5 범위의 값으로 변환한다."""

    if value is None or value == "":
        return None

    rating = float(value)

    if not isfinite(rating):
        raise ValueError("평점은 유한한 숫자여야 합니다.")

    if not 0 <= rating <= 5:
        raise ValueError("평점은 0에서 5 사이여야 합니다.")

    return round(rating, 1)


def parse_review_count(value: Any) -> int | None:
    """리뷰 수를 정수로 변환한다."""

    if value is None or value == "":
        return None

    if isinstance(value, bool):
        raise ValueError("리뷰 수에 True 또는 False를 사용할 수 없습니다.")

    if isinstance(value, str):
        value = value.strip().replace(",", "")

    count = int(value)

    if count < 0:
        raise ValueError("리뷰 수는 0보다 작을 수 없습니다.")

    return count
