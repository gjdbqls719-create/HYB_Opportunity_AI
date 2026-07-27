from __future__ import annotations

from enum import StrEnum


class PriceVolatility(StrEnum):
    """
    가격 이력의 변동성 등급.
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
