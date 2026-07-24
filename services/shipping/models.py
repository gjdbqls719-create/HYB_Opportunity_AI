from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ShippingCostResolution:
    """분석에 사용할 배송비와 그 출처를 표현한다."""

    cost: float
    source: str
    is_free_shipping: bool
