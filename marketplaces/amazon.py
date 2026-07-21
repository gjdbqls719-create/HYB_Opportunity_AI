from __future__ import annotations

from typing import Any

from app.models import Product
from collectors.base import MarketplaceAdapter, parse_price


class AmazonAdapter(MarketplaceAdapter):
    """
    Amazon 원본 상품 데이터를 공통 Product 모델로 변환한다.
    """

    marketplace_name = "amazon"

    def normalize(
        self,
        raw_product: dict[str, Any],
    ) -> Product:
        return Product(
            marketplace=self.marketplace_name,
            item_id=str(
                raw_product.get("asin", "")
            ).strip(),
            title=str(
                raw_product.get("title", "제목 없음")
            ).strip(),
            price=parse_price(
                raw_product.get("price", 0)
            ),
            currency=str(
                raw_product.get("currency", "USD")
            ).strip(),
            condition=str(
                raw_product.get("condition", "New")
            ).strip(),
            url=str(
                raw_product.get("url", "")
            ).strip(),
        )


def search_items(
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    실제 Amazon API 연결 전 사용하는 테스트용 상품 데이터.
    """
    cleaned_query = query.strip()

    if not cleaned_query:
        raise ValueError("검색어를 입력해야 합니다.")

    if limit < 1:
        raise ValueError("limit은 1 이상이어야 합니다.")

    fake_items = [
        {
            "asin": "AMZ-001",
            "title": f"{cleaned_query} Wireless Pro",
            "price": 89.99,
            "currency": "USD",
            "condition": "New",
            "url": "https://www.amazon.com/dp/AMZ-001",
        },
        {
            "asin": "AMZ-002",
            "title": f"{cleaned_query} Wireless Pro Black",
            "price": 84.50,
            "currency": "USD",
            "condition": "New",
            "url": "https://www.amazon.com/dp/AMZ-002",
        },
        {
            "asin": "AMZ-003",
            "title": f"{cleaned_query} Premium Edition",
            "price": 109.99,
            "currency": "USD",
            "condition": "New",
            "url": "https://www.amazon.com/dp/AMZ-003",
        },
    ]

    return fake_items[:limit]


def search_products(
    query: str,
    limit: int = 10,
) -> list[Product]:
    """
    Amazon 상품을 검색하고 공통 Product 목록으로 반환한다.
    """
    adapter = AmazonAdapter()

    raw_items = search_items(
        query=query,
        limit=limit,
    )

    return [
        adapter.normalize(item)
        for item in raw_items
    ]