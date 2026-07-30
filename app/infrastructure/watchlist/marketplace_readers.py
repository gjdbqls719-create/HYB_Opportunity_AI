from __future__ import annotations

from app.infrastructure.watchlist.listing_lookup_adapter import (
    MarketplaceListingLookupAdapter,
)
from app.models import Product
from marketplaces import amazon, ebay


class EbayListingReader:
    """기존 eBay exact-item lookup을 WatchList reader 계약에 연결한다."""

    def get_listing(
        self,
        *,
        item_id: str,
        url: str = "",
    ) -> Product | None:
        return ebay.get_product_by_id(item_id)


class AmazonListingReader:
    """기존 Amazon exact-item lookup을 WatchList reader 계약에 연결한다."""

    def get_listing(
        self,
        *,
        item_id: str,
        url: str = "",
    ) -> Product | None:
        return amazon.get_product_by_id(item_id)


def create_marketplace_listing_lookup_adapter(
) -> MarketplaceListingLookupAdapter:
    """지원 Marketplace reader registry가 등록된 Adapter를 생성한다."""

    return MarketplaceListingLookupAdapter(
        readers={
            "ebay": EbayListingReader(),
            "amazon": AmazonListingReader(),
        }
    )
