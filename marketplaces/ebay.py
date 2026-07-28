from __future__ import annotations

from typing import Any

import requests

from app.models import Product
from collectors.base import MarketplaceAdapter, parse_price
from config.settings import get_settings
from services.ebay_auth import get_application_token


DEFAULT_MARKETPLACE_ID = "EBAY_US"
DEFAULT_PRICE = 0.0


class EbayAdapter(MarketplaceAdapter):
    """eBay 원본 상품 데이터를 공통 Product 모델로 변환한다."""

    marketplace_name = "ebay"

    def normalize(self, raw_product: dict[str, Any]) -> Product:
        price_data = raw_product.get("price", {})

        if not isinstance(price_data, dict):
            price_data = {}

        raw_price = price_data.get("value", DEFAULT_PRICE)
        currency = str(price_data.get("currency", "")).strip()

        try:
            price = parse_price(raw_price)
        except (TypeError, ValueError):
            price = DEFAULT_PRICE

        return Product(
            marketplace=self.marketplace_name,
            item_id=str(raw_product.get("itemId", "")).strip(),
            title=str(raw_product.get("title", "제목 없음")).strip(),
            price=price,
            currency=currency,
            condition=str(
                raw_product.get("condition", "상태 정보 없음")
            ).strip(),
            url=str(raw_product.get("itemWebUrl", "")).strip(),
        )


def search_items(
    query: str,
    limit: int = 10,
    marketplace_id: str = DEFAULT_MARKETPLACE_ID,
) -> list[dict[str, Any]]:
    """eBay Browse API에서 원본 상품 데이터를 검색한다."""

    cleaned_query = query.strip()

    if not cleaned_query:
        raise ValueError("검색어를 입력해야 합니다.")

    if not 1 <= limit <= 200:
        raise ValueError("limit은 1 이상 200 이하여야 합니다.")

    settings = get_settings()
    token_data = get_application_token()
    access_token = token_data["access_token"]

    url = f"{settings.ebay_browse_api_url}/item_summary/search"

    response = requests.get(
        url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-EBAY-C-MARKETPLACE-ID": marketplace_id,
            "Accept": "application/json",
        },
        params={
            "q": cleaned_query,
            "limit": limit,
        },
        timeout=30,
    )

    if not response.ok:
        raise RuntimeError(
            "eBay 상품 검색 실패\n"
            f"HTTP 상태: {response.status_code}\n"
            f"응답: {response.text}"
        )

    response_data = response.json()
    item_summaries = response_data.get("itemSummaries", [])

    if not isinstance(item_summaries, list):
        raise RuntimeError(
            "eBay 응답의 itemSummaries 형식이 올바르지 않습니다."
        )

    return item_summaries


def ebay_item_to_product(item: dict[str, Any]) -> Product:
    """이전 함수형 호출과의 호환을 유지하는 변환 함수."""

    return EbayAdapter().normalize(item)


def search_products(
    query: str,
    limit: int = 10,
    marketplace_id: str = DEFAULT_MARKETPLACE_ID,
) -> list[Product]:
    """eBay 상품을 검색하고 공통 Product 객체 목록으로 반환한다."""

    adapter = EbayAdapter()
    raw_items = search_items(
        query=query,
        limit=limit,
        marketplace_id=marketplace_id,
    )

    return [adapter.normalize(item) for item in raw_items]
