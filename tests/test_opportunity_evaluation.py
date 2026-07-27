from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.opportunity import (
    OpportunityDecision,
    OpportunityEvaluation,
    OpportunityFactors,
    OpportunityGrade,
    OpportunityReason,
    OpportunityScore,
)


def make_score() -> OpportunityScore:
    return OpportunityScore(
        score=Decimal("81.50"),
        grade=OpportunityGrade.GOOD,
        confidence=Decimal("88.00"),
        factors=OpportunityFactors(
            price_score=Decimal("90.00"),
            trend_score=Decimal("80.00"),
            demand_score=Decimal("75.00"),
            competition_score=Decimal("70.00"),
            risk_score=Decimal("85.00"),
        ),
        generated_at=datetime(
            2026,
            7,
            27,
            12,
            0,
            tzinfo=timezone.utc,
        ),
    )


def make_evaluation(
    **overrides: object,
) -> OpportunityEvaluation:
    values: dict[str, object] = {
        "score": make_score(),
        "decision": OpportunityDecision.BUY,
        "reasons": (
            OpportunityReason.PRICE_ADVANTAGE,
            OpportunityReason.UPWARD_TREND,
            OpportunityReason.LOW_RISK,
        ),
        "evaluated_at": datetime(
            2026,
            7,
            27,
            12,
            5,
            tzinfo=timezone.utc,
        ),
    }
    values.update(overrides)
    return OpportunityEvaluation(**values)


def test_decision_uses_stable_string_values() -> None:
    assert OpportunityDecision.STRONG_BUY.value == "strong_buy"
    assert OpportunityDecision.BUY.value == "buy"
    assert OpportunityDecision.WATCH.value == "watch"
    assert OpportunityDecision.SKIP.value == "skip"


def test_reason_uses_stable_string_values() -> None:
    assert OpportunityReason.PRICE_ADVANTAGE.value == "price_advantage"
    assert OpportunityReason.UPWARD_TREND.value == "upward_trend"
    assert OpportunityReason.HIGH_DEMAND.value == "high_demand"
    assert OpportunityReason.LOW_COMPETITION.value == "low_competition"
    assert OpportunityReason.LOW_RISK.value == "low_risk"
    assert OpportunityReason.PRICE_DISADVANTAGE.value == "price_disadvantage"
    assert OpportunityReason.DOWNWARD_TREND.value == "downward_trend"
    assert OpportunityReason.LOW_DEMAND.value == "low_demand"
    assert OpportunityReason.HIGH_COMPETITION.value == "high_competition"
    assert OpportunityReason.HIGH_RISK.value == "high_risk"


def test_evaluation_creation() -> None:
    evaluation = make_evaluation()

    assert evaluation.score == make_score()
    assert evaluation.decision is OpportunityDecision.BUY
    assert evaluation.reasons == (
        OpportunityReason.PRICE_ADVANTAGE,
        OpportunityReason.UPWARD_TREND,
        OpportunityReason.LOW_RISK,
    )
    assert evaluation.evaluated_at.tzinfo is timezone.utc


def test_evaluation_is_immutable() -> None:
    evaluation = make_evaluation()

    with pytest.raises(FrozenInstanceError):
        evaluation.decision = OpportunityDecision.SKIP


def test_score_requires_opportunity_score() -> None:
    with pytest.raises(TypeError):
        make_evaluation(score={})


def test_decision_requires_opportunity_decision() -> None:
    with pytest.raises(TypeError):
        make_evaluation(decision="buy")


def test_reasons_require_tuple() -> None:
    with pytest.raises(TypeError):
        make_evaluation(reasons=[OpportunityReason.LOW_RISK])


def test_reasons_require_at_least_one_reason() -> None:
    with pytest.raises(ValueError):
        make_evaluation(reasons=())


def test_each_reason_requires_opportunity_reason() -> None:
    with pytest.raises(TypeError):
        make_evaluation(reasons=("low_risk",))


def test_reasons_reject_duplicates() -> None:
    with pytest.raises(ValueError):
        make_evaluation(
            reasons=(
                OpportunityReason.LOW_RISK,
                OpportunityReason.LOW_RISK,
            )
        )


def test_evaluated_at_requires_datetime() -> None:
    with pytest.raises(TypeError):
        make_evaluation(evaluated_at="2026-07-27T12:05:00Z")


def test_evaluated_at_requires_timezone_aware_datetime() -> None:
    with pytest.raises(ValueError):
        make_evaluation(evaluated_at=datetime(2026, 7, 27, 12, 5))
