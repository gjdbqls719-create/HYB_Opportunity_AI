from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from database.models import Product


class MarketplaceAdapter(ABC):
    """마켓별 원본 데이터를 공통 Product 모델로 변환한다."""

    marketplace_name: str

    @abstractmethod
    def normalize(self, raw_product: dict[str, Any]) -> Product:
        """마켓 원본 상품 하나를 Product 객체로 변환한다."""
        raise NotImplementedError


def parse_price(value: Any) -> float:
    """문자열 또는 숫자 가격을 안전하게 float로 바꾼다."""

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

    if price < 0:
        raise ValueError("가격은 0보다 작을 수 없습니다.")

    return round(price, 2)


def parse_rating(value: Any) -> float | None:
    """평점을 0~5 범위의 값으로 변환한다."""

    if value is None or value == "":
        return None

    rating = float(value)

    if not 0 <= rating <= 5:
        raise ValueError("평점은 0에서 5 사이여야 합니다.")

    return round(rating, 1)


def parse_review_count(value: Any) -> int | None:
    """리뷰 수를 정수로 변환한다."""

    if value is None or value == "":
        return None

    if isinstance(value, str):
        value = value.strip().replace(",", "")

    count = int(value)

    if count < 0:
        raise ValueError("리뷰 수는 0보다 작을 수 없습니다.")

    return count