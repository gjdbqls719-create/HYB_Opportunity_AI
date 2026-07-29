from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from app.models import Product


class UnsupportedMarketplaceError(LookupError):
    """등록되지 않은 Marketplace Listing 조회가 요청된 경우 발생한다."""


@runtime_checkable
class MarketplaceListingReader(Protocol):
    """특정 Marketplace에서 단일 Listing을 조회하는 Infrastructure 계약."""

    def get_listing(
        self,
        *,
        item_id: str,
        url: str = "",
    ) -> Product | None:
        ...


class MarketplaceListingLookupAdapter:
    """
    Marketplace별 단일 Listing Reader를 선택해 ListingLookupPort를 구현한다.

    이 Adapter는 Marketplace 선택과 반환 계약 검증만 담당한다.
    실제 HTTP 요청, 인증, 응답 정규화는 등록된 Reader가 책임진다.
    """

    def __init__(
        self,
        *,
        readers: Mapping[str, MarketplaceListingReader],
    ) -> None:
        if not isinstance(readers, Mapping):
            raise TypeError("readers는 Mapping이어야 합니다.")

        normalized: dict[str, MarketplaceListingReader] = {}

        for marketplace, reader in readers.items():
            key = self._normalize_marketplace(marketplace)

            if key in normalized:
                raise ValueError(
                    f"Marketplace Reader가 중복 등록되었습니다: {key}"
                )

            if not isinstance(reader, MarketplaceListingReader):
                raise TypeError(
                    f"{key} Reader는 get_listing()을 제공해야 합니다."
                )

            normalized[key] = reader

        self._readers = normalized

    def get_listing(
        self,
        *,
        marketplace: str,
        item_id: str,
        url: str = "",
    ) -> Product | None:
        key = self._normalize_marketplace(marketplace)
        normalized_item_id = self._normalize_optional_text(item_id, "item_id")
        normalized_url = self._normalize_optional_text(url, "url")

        if not normalized_item_id and not normalized_url:
            raise ValueError("item_id 또는 url 중 하나는 필요합니다.")

        reader = self._readers.get(key)
        if reader is None:
            raise UnsupportedMarketplaceError(
                f"지원하지 않는 Marketplace입니다: {key}"
            )

        product = reader.get_listing(
            item_id=normalized_item_id,
            url=normalized_url,
        )

        if product is not None and not isinstance(product, Product):
            raise TypeError(
                "MarketplaceListingReader는 Product 또는 None을 반환해야 합니다."
            )

        return product

    @staticmethod
    def _normalize_marketplace(value: str) -> str:
        if not isinstance(value, str):
            raise TypeError("marketplace는 문자열이어야 합니다.")

        normalized = value.strip().casefold()
        if not normalized:
            raise ValueError("marketplace는 비어 있을 수 없습니다.")

        return normalized

    @staticmethod
    def _normalize_optional_text(value: str, field_name: str) -> str:
        if not isinstance(value, str):
            raise TypeError(f"{field_name}는 문자열이어야 합니다.")
        return value.strip()
