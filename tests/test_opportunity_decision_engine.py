from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.opportunity import (
    OpportunityDecision,
    OpportunityFactors,
    OpportunityGrade,
    OpportunityReason,
    OpportunityScore,
)
from app.engine.opportunity_decision import (
    OpportunityDecisionEngine,
    OpportunityDecisionPolicy,
)


def make_score(
    score: Decimal = Decimal("80"),
    *,
    price_score: Decimal = Decimal("50"),
    trend_score: Decimal = Decimal("50"),
    demand_score: Decimal = Decimal("50"),
    competition_score: Decimal = Decimal("50"),
    risk_score: Decimal = Decimal("50"),
) -> OpportunityScore:
    return OpportunityScore(
        score=score,
        grade=OpportunityGrade.GOOD,
        confidence=Decimal("85"),
        factors=OpportunityFactors(
            price_score=price_score,
            trend_score=trend_score,
            demand_score=demand_score,
            competition_score=competition_score,
            risk_score=risk_score,
        ),
        generated_at=datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc),
    )


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (Decimal("100"), OpportunityDecision.STRONG_BUY),
        (Decimal("90"), OpportunityDecision.STRONG_BUY),
        (Decimal("89.99"), OpportunityDecision.BUY),
        (Decimal("75"), OpportunityDecision.BUY),
        (Decimal("74.99"), OpportunityDecision.WATCH),
        (Decimal("60"), OpportunityDecision.WATCH),
        (Decimal("59.99"), OpportunityDecision.SKIP),
        (Decimal("0"), OpportunityDecision.SKIP),
    ],
)
def test_decision_boundaries(
    score: Decimal,
    expected: OpportunityDecision,
) -> None:
    result = OpportunityDecisionEngine().evaluate(make_score(score))

    assert result.decision is expected


def test_generates_positive_reasons_in_stable_factor_order() -> None:
    result = OpportunityDecisionEngine().evaluate(
        make_score(
            price_score=Decimal("70"),
            trend_score=Decimal("80"),
            demand_score=Decimal("90"),
            competition_score=Decimal("75"),
            risk_score=Decimal("85"),
        )
    )

    assert result.reasons == (
        OpportunityReason.PRICE_ADVANTAGE,
        OpportunityReason.UPWARD_TREND,
        OpportunityReason.HIGH_DEMAND,
        OpportunityReason.LOW_COMPETITION,
        OpportunityReason.LOW_RISK,
    )


def test_generates_negative_reasons_in_stable_factor_order() -> None:
    result = OpportunityDecisionEngine().evaluate(
        make_score(
            price_score=Decimal("30"),
            trend_score=Decimal("20"),
            demand_score=Decimal("10"),
            competition_score=Decimal("25"),
            risk_score=Decimal("15"),
        )
    )

    assert result.reasons == (
        OpportunityReason.PRICE_DISADVANTAGE,
        OpportunityReason.DOWNWARD_TREND,
        OpportunityReason.LOW_DEMAND,
        OpportunityReason.HIGH_COMPETITION,
        OpportunityReason.HIGH_RISK,
    )


def test_omits_neutral_factors_and_keeps_mixed_reasons() -> None:
    result = OpportunityDecisionEngine().evaluate(
        make_score(
            price_score=Decimal("71"),
            trend_score=Decimal("50"),
            demand_score=Decimal("29"),
            competition_score=Decimal("69"),
            risk_score=Decimal("31"),
        )
    )

    assert result.reasons == (
        OpportunityReason.PRICE_ADVANTAGE,
        OpportunityReason.LOW_DEMAND,
    )


def test_balanced_factors_create_explicit_fallback_reason() -> None:
    result = OpportunityDecisionEngine().evaluate(make_score())

    assert result.reasons == (OpportunityReason.BALANCED_FACTORS,)


def test_evaluated_at_defaults_to_timezone_aware_utc() -> None:
    result = OpportunityDecisionEngine().evaluate(make_score())

    assert result.evaluated_at.tzinfo is timezone.utc


def test_preserves_explicit_evaluated_at() -> None:
    evaluated_at = datetime(2026, 7, 27, 12, 5, tzinfo=timezone.utc)

    result = OpportunityDecisionEngine().evaluate(
        make_score(),
        evaluated_at=evaluated_at,
    )

    assert result.evaluated_at is evaluated_at


def test_score_requires_opportunity_score() -> None:
    with pytest.raises(TypeError):
        OpportunityDecisionEngine().evaluate({})


def test_evaluated_at_requires_datetime() -> None:
    with pytest.raises(TypeError):
        OpportunityDecisionEngine().evaluate(
            make_score(),
            evaluated_at="2026-07-27T12:05:00Z",
        )


def test_evaluated_at_requires_timezone_awareness() -> None:
    with pytest.raises(ValueError):
        OpportunityDecisionEngine().evaluate(
            make_score(),
            evaluated_at=datetime(2026, 7, 27, 12, 5),
        )


def test_custom_policy_changes_decision_and_reason_boundaries() -> None:
    policy = OpportunityDecisionPolicy(
        strong_buy_threshold=Decimal("80"),
        buy_threshold=Decimal("60"),
        watch_threshold=Decimal("40"),
        positive_reason_threshold=Decimal("60"),
        negative_reason_threshold=Decimal("40"),
    )

    result = OpportunityDecisionEngine(policy).evaluate(
        make_score(
            score=Decimal("85"),
            price_score=Decimal("60"),
            trend_score=Decimal("40"),
        )
    )

    assert result.decision is OpportunityDecision.STRONG_BUY
    assert result.reasons == (
        OpportunityReason.PRICE_ADVANTAGE,
        OpportunityReason.DOWNWARD_TREND,
    )


@pytest.mark.parametrize(
    "field_name",
    [
        "strong_buy_threshold",
        "buy_threshold",
        "watch_threshold",
        "positive_reason_threshold",
        "negative_reason_threshold",
    ],
)
def test_policy_fields_require_decimal(field_name: str) -> None:
    with pytest.raises(TypeError):
        OpportunityDecisionPolicy(**{field_name: 50})


@pytest.mark.parametrize(
    "value",
    [Decimal("-0.01"), Decimal("100.01"), Decimal("NaN")],
)
def test_policy_fields_require_finite_range(value: Decimal) -> None:
    with pytest.raises(ValueError):
        OpportunityDecisionPolicy(positive_reason_threshold=value)


def test_policy_decision_thresholds_require_descending_order() -> None:
    with pytest.raises(ValueError):
        OpportunityDecisionPolicy(
            strong_buy_threshold=Decimal("75"),
            buy_threshold=Decimal("75"),
        )


def test_policy_reason_thresholds_must_not_overlap() -> None:
    with pytest.raises(ValueError):
        OpportunityDecisionPolicy(
            positive_reason_threshold=Decimal("50"),
            negative_reason_threshold=Decimal("50"),
        )
