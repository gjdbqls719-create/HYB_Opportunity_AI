from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from app.domain.opportunity import (
    OpportunityFactors,
    OpportunityGrade,
    OpportunityScore,
)


_SCORE_QUANTUM = Decimal("0.01")
_WEIGHT_TOTAL = Decimal("1.00")


@dataclass(frozen=True, slots=True)
class OpportunityScorePolicy:
    """Opportunity Score 가중치와 등급 경계를 관리한다."""

    price_weight: Decimal = Decimal("0.30")
    trend_weight: Decimal = Decimal("0.20")
    demand_weight: Decimal = Decimal("0.20")
    competition_weight: Decimal = Decimal("0.15")
    risk_weight: Decimal = Decimal("0.15")

    excellent_threshold: Decimal = Decimal("90")
    good_threshold: Decimal = Decimal("75")
    fair_threshold: Decimal = Decimal("60")
    poor_threshold: Decimal = Decimal("40")

    def __post_init__(self) -> None:
        weight_names = (
            "price_weight",
            "trend_weight",
            "demand_weight",
            "competition_weight",
            "risk_weight",
        )
        threshold_names = (
            "excellent_threshold",
            "good_threshold",
            "fair_threshold",
            "poor_threshold",
        )

        for field_name in (*weight_names, *threshold_names):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{field_name}는 Decimal이어야 합니다.")
            if not value.is_finite():
                raise ValueError(f"{field_name}는 유한한 값이어야 합니다.")

        for field_name in weight_names:
            value = getattr(self, field_name)
            if value < Decimal("0") or value > Decimal("1"):
                raise ValueError(
                    f"{field_name}는 0 이상 1 이하여야 합니다."
                )

        weight_total = sum(
            (getattr(self, name) for name in weight_names),
            start=Decimal("0"),
        )
        if weight_total != _WEIGHT_TOTAL:
            raise ValueError("Opportunity Score 가중치 합계는 1.00이어야 합니다.")

        for field_name in threshold_names:
            value = getattr(self, field_name)
            if value < Decimal("0") or value > Decimal("100"):
                raise ValueError(
                    f"{field_name}는 0 이상 100 이하여야 합니다."
                )

        if not (
            self.excellent_threshold
            > self.good_threshold
            > self.fair_threshold
            > self.poor_threshold
        ):
            raise ValueError(
                "등급 경계는 excellent > good > fair > poor 순이어야 합니다."
            )


class OpportunityScoreEngine:
    """정규화된 요소 점수를 가중 합산해 최종 기회 점수를 생성한다."""

    def __init__(
        self,
        policy: OpportunityScorePolicy | None = None,
    ) -> None:
        self._policy = policy or OpportunityScorePolicy()

    def calculate(
        self,
        factors: OpportunityFactors,
        *,
        confidence: Decimal = Decimal("0"),
        generated_at: datetime | None = None,
    ) -> OpportunityScore:
        if not isinstance(factors, OpportunityFactors):
            raise TypeError("factors는 OpportunityFactors여야 합니다.")

        self._validate_confidence(confidence)
        resolved_generated_at = self._resolve_generated_at(generated_at)

        score = (
            factors.price_score * self._policy.price_weight
            + factors.trend_score * self._policy.trend_weight
            + factors.demand_score * self._policy.demand_weight
            + factors.competition_score * self._policy.competition_weight
            + factors.risk_score * self._policy.risk_weight
        ).quantize(_SCORE_QUANTUM, rounding=ROUND_HALF_UP)

        return OpportunityScore(
            score=score,
            grade=self._determine_grade(score),
            confidence=confidence,
            factors=factors,
            generated_at=resolved_generated_at,
        )

    def _determine_grade(self, score: Decimal) -> OpportunityGrade:
        if score >= self._policy.excellent_threshold:
            return OpportunityGrade.EXCELLENT
        if score >= self._policy.good_threshold:
            return OpportunityGrade.GOOD
        if score >= self._policy.fair_threshold:
            return OpportunityGrade.FAIR
        if score >= self._policy.poor_threshold:
            return OpportunityGrade.POOR
        return OpportunityGrade.REJECT

    @staticmethod
    def _validate_confidence(confidence: object) -> None:
        if not isinstance(confidence, Decimal):
            raise TypeError("confidence는 Decimal이어야 합니다.")
        if not confidence.is_finite():
            raise ValueError("confidence는 유한한 값이어야 합니다.")
        if confidence < Decimal("0") or confidence > Decimal("100"):
            raise ValueError("confidence는 0 이상 100 이하여야 합니다.")

    @staticmethod
    def _resolve_generated_at(generated_at: datetime | None) -> datetime:
        if generated_at is None:
            return datetime.now(timezone.utc)
        if not isinstance(generated_at, datetime):
            raise TypeError("generated_at은 datetime이어야 합니다.")
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            raise ValueError("generated_at은 timezone-aware datetime이어야 합니다.")
        return generated_at
