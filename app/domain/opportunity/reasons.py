from __future__ import annotations

from enum import Enum


class OpportunityReason(str, Enum):
    """Opportunity 의사결정을 설명하는 구조화된 근거 코드."""

    PRICE_ADVANTAGE = "price_advantage"
    UPWARD_TREND = "upward_trend"
    HIGH_DEMAND = "high_demand"
    LOW_COMPETITION = "low_competition"
    LOW_RISK = "low_risk"

    PRICE_DISADVANTAGE = "price_disadvantage"
    DOWNWARD_TREND = "downward_trend"
    LOW_DEMAND = "low_demand"
    HIGH_COMPETITION = "high_competition"
    HIGH_RISK = "high_risk"
