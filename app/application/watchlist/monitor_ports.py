from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.application.change.models import ChangeDetectionResponse
from app.models import Product
from market_data.price_snapshot import PriceSnapshot


@runtime_checkable
class ListingLookupPort(Protocol):
    """
    Watch Item이 가리키는 Marketplace Listing을 다시 조회하기 위한
    Application Port.

    Application 계층은 eBay, Amazon 또는 HTTP Client 같은 구체적인
    수집 기술을 알지 않고 이 계약에만 의존한다.

    item_id가 제공되는 Listing은 Marketplace 식별자로 조회하고,
    item_id가 없는 URL 기반 Listing은 url을 조회 단서로 사용할 수 있다.
    구체적인 Adapter가 어떤 조회 방식을 지원하는지는 Infrastructure
    계층이 결정한다.
    """

    def get_listing(
        self,
        *,
        marketplace: str,
        item_id: str,
        url: str = "",
    ) -> Product | None:
        """
        현재 Marketplace Listing을 반환한다.

        Listing이 존재하지 않거나 현재 조회할 수 없으면 None을
        반환한다. 네트워크 오류, 인증 오류와 같은 실행 실패는
        예외로 전달하며 Monitor Use Case가 항목별로 격리한다.
        """
        ...


@runtime_checkable
class LatestPriceChangeDetector(Protocol):
    """현재 PriceSnapshot과 최근 과거 Snapshot의 변화를 탐지하는 Port."""

    def execute(
        self,
        *,
        current_snapshot: PriceSnapshot,
    ) -> ChangeDetectionResponse:
        ...
