from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from market_data.price_snapshot import PriceSnapshot
from storage.price_history import PriceHistoryRecord


def _parse_observed_at(
    value: str | datetime,
) -> datetime:
    """
    PriceHistoryRecord의 관찰 시각을
    timezone-aware datetime으로 정규화한다.

    지원 형식:
    - ISO 8601 문자열
    - datetime 객체

    timezone 정보가 없는 경우 UTC로 간주한다.
    """
    if isinstance(value, datetime):
        observed_at = value

    elif isinstance(value, str):
        cleaned_value = value.strip()

        if not cleaned_value:
            raise ValueError(
                "PriceHistoryRecord.observed_at은 "
                "비어 있을 수 없습니다."
            )

        normalized_value = cleaned_value

        if normalized_value.endswith("Z"):
            normalized_value = (
                f"{normalized_value[:-1]}+00:00"
            )

        try:
            observed_at = datetime.fromisoformat(
                normalized_value
            )
        except ValueError as error:
            raise ValueError(
                "PriceHistoryRecord.observed_at은 "
                "유효한 ISO 8601 형식이어야 합니다."
            ) from error

    else:
        raise TypeError(
            "PriceHistoryRecord.observed_at은 "
            "문자열 또는 datetime이어야 합니다."
        )

    if observed_at.tzinfo is None:
        observed_at = observed_at.replace(
            tzinfo=timezone.utc
        )

    return observed_at


def _require_canonical_product_id(
    value: str | None,
) -> str:
    """
    Domain PriceSnapshot 생성에 필요한
    Canonical Product ID를 검증한다.
    """
    if value is None:
        raise ValueError(
            "PriceSnapshot으로 변환하려면 "
            "canonical_product_id가 필요합니다."
        )

    cleaned_value = value.strip()

    if not cleaned_value:
        raise ValueError(
            "PriceSnapshot으로 변환하려면 "
            "canonical_product_id가 필요합니다."
        )

    return cleaned_value


def price_history_to_price_snapshot(
    record: PriceHistoryRecord,
) -> PriceSnapshot:
    """
    PriceHistoryRecord를 PriceSnapshot으로 변환한다.

    Storage Layer의 기록 데이터를 Domain Snapshot 형태로
    변환하며, Storage 표현이 Domain 경계 안으로 유출되지
    않도록 다음 변환을 수행한다.

    - float price → Decimal price
    - ISO 8601 문자열 또는 datetime
      → timezone-aware datetime
    - 선택적 Storage 식별자
      → 필수 Domain 식별자 검증
    """
    if not isinstance(record, PriceHistoryRecord):
        raise TypeError(
            "record는 PriceHistoryRecord여야 합니다."
        )

    return PriceSnapshot(
        snapshot_id=f"price_history_{record.id}",
        canonical_product_id=(
            _require_canonical_product_id(
                record.canonical_product_id
            )
        ),
        marketplace=record.marketplace,
        observed_at=_parse_observed_at(
            record.observed_at
        ),
        source_url=record.url,
        item_id=record.item_id,
        price=Decimal(str(record.price)),
        currency=record.currency,
        condition=record.condition,
        seller_id=record.seller_id,
    )