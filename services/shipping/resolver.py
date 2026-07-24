from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from services.shipping.models import ShippingCostResolution


MONEY_QUANTUM = Decimal("0.01")


def _normalize_cost(value: Any, field_name: str) -> float:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError(f"{field_name}은(는) 숫자여야 합니다.") from error

    if not amount.is_finite():
        raise ValueError(f"{field_name}은(는) 유한한 숫자여야 합니다.")

    if amount < 0:
        raise ValueError(f"{field_name}은(는) 0 이상이어야 합니다.")

    return float(amount.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP))


def resolve_shipping_cost(
    marketplace_shipping_cost: Any,
    override_shipping_cost: Any | None = None,
) -> ShippingCostResolution:
    """마켓 수집 배송비와 사용자 재정의 값 중 분석 배송비를 결정한다.

    override_shipping_cost가 None이면 수집된 상품 배송비를 사용한다.
    0을 명시하면 무료배송으로 재정의한 것으로 처리한다.
    """
    if override_shipping_cost is None:
        cost = _normalize_cost(
            marketplace_shipping_cost,
            "상품 배송비",
        )
        source = "marketplace"
    else:
        cost = _normalize_cost(
            override_shipping_cost,
            "재정의 배송비",
        )
        source = "override"

    return ShippingCostResolution(
        cost=cost,
        source=source,
        is_free_shipping=(cost == 0.0),
    )
