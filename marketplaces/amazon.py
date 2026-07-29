from __future__ import annotations

from typing import Any

from app.models import Product
from collectors.base import MarketplaceAdapter, parse_price


_FAKE_ITEM_TEMPLATES: tuple[dict[str, Any], ...] = (
    {
        "asin": "AMZ-001",
        "title_suffix": "Wireless Pro",
        "price": 89.99,
        "currency": "USD",
        "condition": "New",
        "url": "https://www.amazon.com/dp/AMZ-001",
    },
    {
        "asin": "AMZ-002",
        "title_suffix": "Wireless Pro Black",
        "price": 84.50,
        "currency": "USD",
        "condition": "New",
        "url": "https://www.amazon.com/dp/AMZ-002",
    },
    {
        "asin": "AMZ-003",
        "title_suffix": "Premium Edition",
        "price": 109.99,
        "currency": "USD",
        "condition": "New",
        "url": "https://www.amazon.com/dp/AMZ-003",
    },
)


class AmazonAdapter(MarketplaceAdapter):
    """Amazon 원본 상품 데이터를 공통 Product 모델로 변환한다."""

    marketplace_name = "amazon"

    def normalize(
        self,
        raw_product: dict[str, Any],
    ) -> Product:
        return Product(
            marketplace=self.marketplace_name,
            item_id=str(raw_product.get("asin", "")).strip(),
            title=str(raw_product.get("title", "제목 없음")).strip(),
            price=parse_price(raw_product.get("price", 0)),
            currency=str(raw_product.get("currency", "USD")).strip(),
            condition=str(raw_product.get("condition", "New")).strip(),
            url=str(raw_product.get("url", "")).strip(),
        )


def _build_fake_items(query: str) -> list[dict[str, Any]]:
    return [
        {
            key: value
            for key, value in template.items()
            if key != "title_suffix"
        }
        | {"title": f"{query} {template['title_suffix']}"}
        for template in _FAKE_ITEM_TEMPLATES
    ]


def search_items(
    query: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """실제 Amazon API 연결 전 사용하는 테스트용 상품 데이터."""

    cleaned_query = query.strip()

    if not cleaned_query:
        raise ValueError("검색어를 입력해야 합니다.")

    if limit < 1:
        raise ValueError("limit은 1 이상이어야 합니다.")

    return _build_fake_items(cleaned_query)[:limit]


def get_item_by_id(item_id: str) -> dict[str, Any] | None:
    """테스트용 Amazon 카탈로그에서 정확한 ASIN을 조회한다.

    실제 Amazon API 연결 전까지 계약과 호출 흐름을 검증하기 위한
    결정론적 구현이다. 검색 결과의 첫 항목을 대신 사용하지 않는다.
    """

    cleaned_item_id = item_id.strip()

    if not cleaned_item_id:
        raise ValueError("Amazon ASIN을 입력해야 합니다.")

    normalized_item_id = cleaned_item_id.upper()

    for raw_item in _build_fake_items("Amazon"):
        if str(raw_item["asin"]).upper() == normalized_item_id:
            return raw_item

    return None


def get_product_by_id(item_id: str) -> Product | None:
    """정확한 Amazon ASIN을 조회해 검증된 Product로 반환한다."""

    raw_item = get_item_by_id(item_id)

    if raw_item is None:
        return None

    return AmazonAdapter().normalize_and_validate(raw_item)


def search_products(
    query: str,
    limit: int = 10,
) -> list[Product]:
    """Amazon 상품을 검색하고 검증된 공통 Product 목록으로 반환한다."""

    adapter = AmazonAdapter()
    raw_items = search_items(query=query, limit=limit)

    return [adapter.normalize_and_validate(item) for item in raw_items]
