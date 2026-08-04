from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import requests

from app.models import Product, ProductDataSource
from collectors.base import MarketplaceAdapter, parse_price
from collectors.collection_fact import CollectionFact
from config.settings import get_settings
from services.ebay_auth import get_application_token


DEFAULT_MARKETPLACE_ID = "EBAY_US"


class EbayAdapter(MarketplaceAdapter):
    """eBay 원본 상품 데이터를 공통 Product 모델로 변환한다."""

    marketplace_name = "ebay"

    def normalize(self, raw_product: dict[str, Any]) -> Product:
        price_data = raw_product.get("price")

        if not isinstance(price_data, dict):
            raise ValueError("eBay 가격 정보는 dict 형식이어야 합니다.")

        return Product(
            marketplace=self.marketplace_name,
            item_id=str(raw_product.get("itemId", "")).strip(),
            title=str(raw_product.get("title", "제목 없음")).strip(),
            price=parse_price(price_data.get("value")),
            currency=str(price_data.get("currency", "")).strip(),
            condition=str(
                raw_product.get("condition", "상태 정보 없음")
            ).strip(),
            url=str(raw_product.get("itemWebUrl", "")).strip(),
            data_source=ProductDataSource.PRODUCTION,
        )


def _build_browse_headers(
    *,
    access_token: str,
    marketplace_id: str,
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "X-EBAY-C-MARKETPLACE-ID": marketplace_id,
        "Accept": "application/json",
    }


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
        headers=_build_browse_headers(
            access_token=access_token,
            marketplace_id=marketplace_id,
        ),
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


def get_item_by_id(
    item_id: str,
    marketplace_id: str = DEFAULT_MARKETPLACE_ID,
) -> dict[str, Any] | None:
    """eBay Browse API에서 정확한 item ID의 원본 상품을 조회한다.

    존재하지 않거나 더 이상 조회할 수 없는 상품(HTTP 404)은 ``None``을
    반환한다. 그 밖의 HTTP 실패는 호출자에게 명확한 오류로 전달한다.
    """

    cleaned_item_id = item_id.strip()
    cleaned_marketplace_id = marketplace_id.strip()

    if not cleaned_item_id:
        raise ValueError("eBay 상품 ID를 입력해야 합니다.")

    if not cleaned_marketplace_id:
        raise ValueError("eBay marketplace_id를 입력해야 합니다.")

    settings = get_settings()
    token_data = get_application_token()
    access_token = token_data["access_token"]

    encoded_item_id = quote(cleaned_item_id, safe="")
    url = f"{settings.ebay_browse_api_url}/item/{encoded_item_id}"

    response = requests.get(
        url,
        headers=_build_browse_headers(
            access_token=access_token,
            marketplace_id=cleaned_marketplace_id,
        ),
        timeout=30,
    )

    if response.status_code == 404:
        return None

    if not response.ok:
        raise RuntimeError(
            "eBay 단일 상품 조회 실패\n"
            f"상품 ID: {cleaned_item_id}\n"
            f"HTTP 상태: {response.status_code}\n"
            f"응답: {response.text}"
        )

    response_data = response.json()

    if not isinstance(response_data, dict):
        raise RuntimeError("eBay 단일 상품 응답은 dict 형식이어야 합니다.")

    return response_data


def ebay_item_to_product(
    item: dict[str, Any],
    *,
    collection_fact_sink: Callable[[CollectionFact], None] | None = None,
    observed_at: Callable[[], datetime] | None = None,
) -> Product:
    """이전 함수형 호출과의 호환을 유지하는 검증된 변환 함수."""

    product = EbayAdapter().normalize_and_validate(item)

    if collection_fact_sink is not None:
        clock = observed_at or (lambda: datetime.now(timezone.utc))
        collection_fact_sink(
            CollectionFact(
                product=product,
                observed_at=clock(),
                collector_name=EbayAdapter.marketplace_name,
                source_reference=product.url,
            )
        )

    return product


def get_product_by_id(
    item_id: str,
    marketplace_id: str = DEFAULT_MARKETPLACE_ID,
) -> Product | None:
    """정확한 eBay item ID를 조회해 검증된 Product로 반환한다."""

    raw_item = get_item_by_id(
        item_id=item_id,
        marketplace_id=marketplace_id,
    )

    if raw_item is None:
        return None

    return EbayAdapter().normalize_and_validate(raw_item)


def search_products(
    query: str,
    limit: int = 10,
    marketplace_id: str = DEFAULT_MARKETPLACE_ID,
    *,
    collection_fact_sink: Callable[[CollectionFact], None] | None = None,
    observed_at: Callable[[], datetime] | None = None,
) -> list[Product]:
    """eBay 상품을 검색하고 검증된 공통 Product 목록으로 반환한다."""

    raw_items = search_items(
        query=query,
        limit=limit,
        marketplace_id=marketplace_id,
    )

    return [
        ebay_item_to_product(
            item,
            collection_fact_sink=collection_fact_sink,
            observed_at=observed_at,
        )
        for item in raw_items
    ]
