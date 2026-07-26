from __future__ import annotations

from datetime import datetime

from market_data.price_snapshot import PriceSnapshot
from storage.price_history import PriceHistoryRecord


def price_snapshots_to_history_records(
    snapshots: list[PriceSnapshot],
    *,
    title: str,
) -> list[PriceHistoryRecord]:
    """
    PriceSnapshot 목록을 기존 PriceTrend 분석용
    PriceHistoryRecord 목록으로 변환한다.

    기존 PriceTrend 로직은 유지하고,
    Snapshot 데이터를 분석 계층에서 사용할 수 있도록
    변환만 담당한다.
    """

    if not isinstance(snapshots, list):
        raise TypeError(
            "snapshots는 list여야 합니다."
        )

    if not snapshots:
        raise ValueError(
            "snapshots는 비어 있을 수 없습니다."
        )

    if not isinstance(title, str):
        raise TypeError(
            "title은 문자열이어야 합니다."
        )

    cleaned_title = title.strip()

    if not cleaned_title:
        raise ValueError(
            "title은 비어 있을 수 없습니다."
        )

    records: list[PriceHistoryRecord] = []

    for snapshot in snapshots:
        if not isinstance(snapshot, PriceSnapshot):
            raise TypeError(
                "snapshots에는 PriceSnapshot만 "
                "포함되어야 합니다."
            )

        observed_at = snapshot.observed_at

        if isinstance(observed_at, datetime):
            observed_at_value = (
                observed_at.isoformat()
            )
        else:
            observed_at_value = str(
                observed_at
            )

        records.append(
            PriceHistoryRecord(
                id=_snapshot_id_to_int(
                    snapshot.snapshot_id
                ),
                marketplace=snapshot.marketplace,
                item_id=snapshot.item_id,
                title=cleaned_title,
                price=snapshot.price,
                currency=snapshot.currency,
                condition=snapshot.condition,
                url=snapshot.source_url,
                observed_at=observed_at_value,
                canonical_product_id=(
                    snapshot.canonical_product_id
                ),
                seller_id=snapshot.seller_id,
            )
        )

    return records


def _snapshot_id_to_int(
    snapshot_id: str,
) -> int:
    """
    PriceHistoryRecord가 요구하는
    정수 ID 형태로 변환한다.

    Snapshot ID 자체를 변경하지 않고
    분석용 임시 식별자로 사용한다.
    """

    digits = "".join(
        char
        for char in snapshot_id
        if char.isdigit()
    )

    if digits:
        return int(digits)

    return abs(
        hash(snapshot_id)
    )