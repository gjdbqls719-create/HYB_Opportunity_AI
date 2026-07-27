from __future__ import annotations

from enum import Enum


class OpportunityDecision(str, Enum):
    """Opportunity 평가의 안정적인 최종 의사결정 값."""

    STRONG_BUY = "strong_buy"
    BUY = "buy"
    WATCH = "watch"
    SKIP = "skip"
