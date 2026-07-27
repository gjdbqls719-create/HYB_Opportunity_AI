from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from app.domain.opportunity import (
    OpportunityDecision,
    OpportunityEvaluation,
    OpportunityReason,
    OpportunityScore,
)


@dataclass(frozen=True, slots=True)
class OpportunityDecisionPolicy:
    """Opportunity Score를 최종 판단과 근거로 변환하는 정책."""

    strong_buy_threshold: Decimal = Decimal("90")
    buy_threshold: Decimal = Decimal("75")
    watch_threshold: Decimal = Decimal("60")

    positive_reason_threshold: Decimal = Decimal("70")
    negative_reason_threshold: Decimal = Decimal("30")

    def __post_init__(self) -> None:
        threshold_names = (
            "strong_buy_threshold",
            "buy_threshold",
            "watch_threshold",
            "positive_reason_threshold",
            "negative_reason_threshold",
        )

        for field_name in threshold_names:
            value = getattr(self, field_name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{field_name}는 Decimal이어야 합니다.")
            if not value.is_finite():
                raise ValueError(f"{field_name}는 유한한 값이어야 합니다.")
            if value < Decimal("0") or value > Decimal("100"):
                raise ValueError(
                    f"{field_name}는 0 이상 100 이하여야 합니다."
                )

        if not (
            self.strong_buy_threshold
            > self.buy_threshold
            > self.watch_threshold
        ):
            raise ValueError(
                "의사결정 경계는 strong_buy > buy > watch 순이어야 합니다."
            )

        if self.negative_reason_threshold >= self.positive_reason_threshold:
            raise ValueError(
                "negative_reason_threshold는 "
                "positive_reason_threshold보다 작아야 합니다."
            )


class OpportunityDecisionEngine:
    """Opportunity Score로부터 최종 판단과 구조화된 근거를 생성한다."""

    def __init__(
        self,
        policy: OpportunityDecisionPolicy | None = None,
    ) -> None:
        self._policy = policy or OpportunityDecisionPolicy()

    def evaluate(
        self,
        score: OpportunityScore,
        *,
        evaluated_at: datetime | None = None,
    ) -> OpportunityEvaluation:
        if not isinstance(score, OpportunityScore):
            raise TypeError("score는 OpportunityScore여야 합니다.")

        resolved_evaluated_at = self._resolve_evaluated_at(evaluated_at)

        return OpportunityEvaluation(
            score=score,
            decision=self._determine_decision(score.score),
            reasons=self._determine_reasons(score),
            evaluated_at=resolved_evaluated_at,
        )

    def _determine_decision(self, score: Decimal) -> OpportunityDecision:
        if score >= self._policy.strong_buy_threshold:
            return OpportunityDecision.STRONG_BUY
        if score >= self._policy.buy_threshold:
            return OpportunityDecision.BUY
        if score >= self._policy.watch_threshold:
            return OpportunityDecision.WATCH
        return OpportunityDecision.SKIP

    def _determine_reasons(
        self,
        score: OpportunityScore,
    ) -> tuple[OpportunityReason, ...]:
        factors = score.factors
        reasons: list[OpportunityReason] = []

        self._append_reason(
            reasons,
            factors.price_score,
            OpportunityReason.PRICE_ADVANTAGE,
            OpportunityReason.PRICE_DISADVANTAGE,
        )
        self._append_reason(
            reasons,
            factors.trend_score,
            OpportunityReason.UPWARD_TREND,
            OpportunityReason.DOWNWARD_TREND,
        )
        self._append_reason(
            reasons,
            factors.demand_score,
            OpportunityReason.HIGH_DEMAND,
            OpportunityReason.LOW_DEMAND,
        )
        self._append_reason(
            reasons,
            factors.competition_score,
            OpportunityReason.LOW_COMPETITION,
            OpportunityReason.HIGH_COMPETITION,
        )
        self._append_reason(
            reasons,
            factors.risk_score,
            OpportunityReason.LOW_RISK,
            OpportunityReason.HIGH_RISK,
        )

        if not reasons:
            reasons.append(OpportunityReason.BALANCED_FACTORS)

        return tuple(reasons)

    def _append_reason(
        self,
        reasons: list[OpportunityReason],
        factor_score: Decimal,
        positive_reason: OpportunityReason,
        negative_reason: OpportunityReason,
    ) -> None:
        if factor_score >= self._policy.positive_reason_threshold:
            reasons.append(positive_reason)
        elif factor_score <= self._policy.negative_reason_threshold:
            reasons.append(negative_reason)

    @staticmethod
    def _resolve_evaluated_at(evaluated_at: datetime | None) -> datetime:
        if evaluated_at is None:
            return datetime.now(timezone.utc)
        if not isinstance(evaluated_at, datetime):
            raise TypeError("evaluated_at은 datetime이어야 합니다.")
        if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
            raise ValueError(
                "evaluated_at은 timezone-aware datetime이어야 합니다."
            )
        return evaluated_at
