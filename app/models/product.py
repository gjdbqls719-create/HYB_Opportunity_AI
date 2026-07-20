from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Product:
    """
    모든 마켓플레이스가 공통으로 사용하는 상품 모델.
    """

    marketplace: str
    item_id: str
    title: str

    price: float
    currency: str

    condition: str
    url: str