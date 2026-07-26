from __future__ import annotations

from decimal import Decimal

from market_data.price_snapshot import PriceSnapshot
from storage.price_history import PriceHistoryRecord


def price_history_to_price_snapshot(
    record: PriceHistoryRecord,
) -> PriceSnapshot:
    """
    PriceHistoryRecord를 PriceSnapshot으로 변환한다.

    Storage Layer의 기록 데이터를
    Domain Snapshot 형태로 변환하는 Mapper.

    변환 책임:
    - float price → Decimal price
    - storage field → snapshot field 연결
    """

    return PriceSnapshot(
        snapshot_id=f"price_history_{record.id}",
        canonical_product_id=(
            record.canonical_product_id
        ),
        marketplace=record.marketplace,
        observed_at=record.observed_at,
        source_url=record.url,

        item_id=record.item_id,
        price=Decimal(str(record.price)),
        currency=record.currency,
        condition=record.condition,
        seller_id=record.seller_id,
    )