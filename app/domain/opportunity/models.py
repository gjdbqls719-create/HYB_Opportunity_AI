from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


_SCORE_MIN = Decimal("0")
_SCORE_MAX = Decimal("100")


class OpportunityGrade(str, Enum):
    """Opportunity Score의 안정적인 외부 표현 값."""

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class OpportunityFactors:
    """
    Opportunity Score를 구성하는 정규화된 요소 점수.

    모든 값은 0 이상 100 이하의 Decimal이다. ``risk_score``는
    위험의 크기가 아니라 위험 안전성 점수이므로 값이 높을수록
    더 안전하고 기회에 유리하다는 뜻이다.
    """

    price_score: Decimal
    trend_score: Decimal
    demand_score: Decimal
    competition_score: Decimal
    risk_score: Decimal

    def __post_init__(self) -> None:
        for field_name in (
            "price_score",
            "trend_score",
            "demand_score",
            "competition_score",
            "risk_score",
        ):
            _validate_score(
                field_name,
                getattr(self, field_name),
            )


@dataclass(frozen=True, slots=True)
class OpportunityScore:
    """Opportunity Engine이 외부 계층에 전달하는 불변 결과 모델."""

    score: Decimal
    grade: OpportunityGrade
    confidence: Decimal
    factors: OpportunityFactors
    generated_at: datetime

    def __post_init__(self) -> None:
        _validate_score("score", self.score)
        _validate_score("confidence", self.confidence)

        if not isinstance(self.grade, OpportunityGrade):
            raise TypeError(
                "grade는 OpportunityGrade여야 합니다."
            )

        if not isinstance(self.factors, OpportunityFactors):
            raise TypeError(
                "factors는 OpportunityFactors여야 합니다."
            )

        if not isinstance(self.generated_at, datetime):
            raise TypeError(
                "generated_at은 datetime이어야 합니다."
            )

        if (
            self.generated_at.tzinfo is None
            or self.generated_at.utcoffset() is None
        ):
            raise ValueError(
                "generated_at은 timezone-aware datetime이어야 합니다."
            )


def _validate_score(
    field_name: str,
    value: object,
) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(
            f"{field_name}는 Decimal이어야 합니다."
        )

    if not value.is_finite():
        raise ValueError(
            f"{field_name}는 유한한 값이어야 합니다."
        )

    if not _SCORE_MIN <= value <= _SCORE_MAX:
        raise ValueError(
            f"{field_name}는 0 이상 100 이하여야 합니다."
        )
