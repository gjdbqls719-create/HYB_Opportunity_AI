from __future__ import annotations

from typing import Any

import requests

from config.settings import get_settings
from services.ebay_auth import get_application_token


DEFAULT_MARKETPLACE_ID = "EBAY_US"


def search_items(
    query: str,
    limit: int = 10,
    marketplace_id: str = DEFAULT_MARKETPLACE_ID,
) -> list[dict[str, Any]]:
    """
    eBay Browse API에서 상품을 검색한다.

    Args:
        query:
            검색할 상품명 또는 키워드.
        limit:
            가져올 상품 개수.
        marketplace_id:
            검색할 eBay 마켓플레이스 ID.

    Returns:
        eBay 상품 정보 딕셔너리 목록.
    """
    cleaned_query = query.strip()

    if not cleaned_query:
        raise ValueError("검색어를 입력해야 합니다.")

    if not 1 <= limit <= 200:
        raise ValueError("limit은 1 이상 200 이하여야 합니다.")

    settings = get_settings()
    token_data = get_application_token()
    access_token = token_data["access_token"]

    url = (
        f"{settings.ebay_browse_api_url}"
        "/item_summary/search"
    )

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