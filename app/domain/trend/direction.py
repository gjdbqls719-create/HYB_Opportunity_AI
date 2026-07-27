from __future__ import annotations

from enum import StrEnum


class TrendDirection(StrEnum):
    """
    가격 이력의 전체적인 이동 방향.
    """

    UP = "up"
    DOWN = "down"
    STABLE = "stable"
