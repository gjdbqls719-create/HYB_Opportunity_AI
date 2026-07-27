from __future__ import annotations

from typing import Protocol

from market_data.price_snapshot import PriceSnapshot


class PriceSnapshotProvider(Protocol):
    """
    Application Layer가 과거 가격 Snapshot을
    조회하기 위해 요구하는 최소 계약.

    SQLite, 파일, 메모리, 외부 데이터베이스 등
    구체적인 저장 기술은 이 계약에 포함하지 않는다.
    """

    def get_latest_for_listing(
        self,
        *,
        marketplace: str,
        item_id: str,
    ) -> PriceSnapshot | None:
        """
        특정 Marketplace Listing의 가장 최근
        가격 Snapshot을 반환한다.
        """
        ...

    def get_latest_for_canonical_product(
        self,
        *,
        canonical_product_id: str,
    ) -> PriceSnapshot | None:
        """
        Canonical Product에 연결된 가장 최근
        가격 Snapshot을 반환한다.
        """
        ...