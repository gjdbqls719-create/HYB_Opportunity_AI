from __future__ import annotations

from datetime import datetime
from sqlite3 import Row
from typing import Any, Mapping

from app.domain.watchlist import (
    WatchItem,
    WatchItemStatus,
)


WatchItemRecord = dict[str, Any]
WatchItemRow = Row | Mapping[str, Any]


def watch_item_to_record(
    item: WatchItem,
) -> WatchItemRecord:
    """
    WatchItem을 SQLite 저장용 레코드로 변환한다.

    datetime은 timezone 정보를 보존하는 ISO 8601 문자열로 저장한다.
    identity_key는 조회 및 중복 방지를 위해 별도 컬럼으로 보관한다.
    """
    if not isinstance(item, WatchItem):
        raise TypeError(
            "item은 WatchItem이어야 합니다."
        )

    return {
        "watch_id": item.watch_id,
        "identity_key": item.identity_key,
        "marketplace": item.marketplace,
        "item_id": item.item_id,
        "canonical_product_id": (
            item.canonical_product_id
        ),
        "title": item.title,
        "current_price": item.current_price,
        "currency": item.currency,
        "url": item.url,
        "brand": item.brand,
        "model_number": item.model_number,
        "target_roi": item.target_roi,
        "target_net_profit": item.target_net_profit,
        "note": item.note,
        "status": item.status.value,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "last_analyzed_at": (
            item.last_analyzed_at.isoformat()
            if item.last_analyzed_at is not None
            else None
        ),
    }


def watch_item_from_row(
    row: WatchItemRow,
) -> WatchItem:
    """
    SQLite 조회 결과를 WatchItem으로 변환한다.

    WatchItem 생성자를 통과시키므로 저장 데이터도 동일한
    도메인 검증 규칙을 적용받는다.
    """
    if row is None:
        raise TypeError(
            "row는 None일 수 없습니다."
        )

    return WatchItem(
        watch_id=_required_string(
            row,
            "watch_id",
        ),
        marketplace=_required_string(
            row,
            "marketplace",
        ),
        item_id=_optional_string(
            row,
            "item_id",
        )
        or "",
        canonical_product_id=_optional_string(
            row,
            "canonical_product_id",
        ),
        title=_required_string(
            row,
            "title",
        ),
        current_price=_required_float(
            row,
            "current_price",
        ),
        currency=_required_string(
            row,
            "currency",
        ),
        url=_optional_string(
            row,
            "url",
        )
        or "",
        brand=_optional_string(
            row,
            "brand",
        ),
        model_number=_optional_string(
            row,
            "model_number",
        ),
        target_roi=_optional_float(
            row,
            "target_roi",
        ),
        target_net_profit=_optional_float(
            row,
            "target_net_profit",
        ),
        note=_optional_string(
            row,
            "note",
        )
        or "",
        status=WatchItemStatus(
            _required_string(
                row,
                "status",
            )
        ),
        created_at=_required_datetime(
            row,
            "created_at",
        ),
        updated_at=_required_datetime(
            row,
            "updated_at",
        ),
        last_analyzed_at=_optional_datetime(
            row,
            "last_analyzed_at",
        ),
    )


def _get_value(
    row: WatchItemRow,
    field_name: str,
) -> Any:
    try:
        return row[field_name]
    except (KeyError, IndexError) as error:
        raise ValueError(
            f"필수 저장 필드가 없습니다: {field_name}"
        ) from error


def _required_string(
    row: WatchItemRow,
    field_name: str,
) -> str:
    value = _get_value(
        row,
        field_name,
    )

    if not isinstance(value, str):
        raise TypeError(
            f"{field_name}은 문자열이어야 합니다."
        )

    cleaned_value = value.strip()

    if not cleaned_value:
        raise ValueError(
            f"{field_name}은 비어 있을 수 없습니다."
        )

    return cleaned_value


def _optional_string(
    row: WatchItemRow,
    field_name: str,
) -> str | None:
    value = _get_value(
        row,
        field_name,
    )

    if value is None:
        return None

    if not isinstance(value, str):
        raise TypeError(
            f"{field_name}은 문자열 또는 None이어야 합니다."
        )

    cleaned_value = value.strip()

    return cleaned_value or None


def _required_float(
    row: WatchItemRow,
    field_name: str,
) -> float:
    value = _get_value(
        row,
        field_name,
    )

    if value is None:
        raise ValueError(
            f"{field_name}은 None일 수 없습니다."
        )

    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise TypeError(
            f"{field_name}은 숫자여야 합니다."
        ) from error


def _optional_float(
    row: WatchItemRow,
    field_name: str,
) -> float | None:
    value = _get_value(
        row,
        field_name,
    )

    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise TypeError(
            f"{field_name}은 숫자 또는 None이어야 합니다."
        ) from error


def _required_datetime(
    row: WatchItemRow,
    field_name: str,
) -> datetime:
    value = _required_string(
        row,
        field_name,
    )

    return _parse_datetime(
        value,
        field_name=field_name,
    )


def _optional_datetime(
    row: WatchItemRow,
    field_name: str,
) -> datetime | None:
    value = _optional_string(
        row,
        field_name,
    )

    if value is None:
        return None

    return _parse_datetime(
        value,
        field_name=field_name,
    )


def _parse_datetime(
    value: str,
    *,
    field_name: str,
) -> datetime:
    try:
        parsed_value = datetime.fromisoformat(
            value
        )
    except ValueError as error:
        raise ValueError(
            f"{field_name}의 datetime 형식이 올바르지 않습니다."
        ) from error

    if parsed_value.tzinfo is None:
        raise ValueError(
            f"{field_name}은 timezone-aware datetime이어야 합니다."
        )

    return parsed_value