from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.opportunity import (
    OpportunityFactors,
    OpportunityGrade,
    OpportunityScore,
)
from app.engine.opportunity_score import (
    OpportunityScoreEngine,
    OpportunityScorePolicy,
)


def make_factors(
    value: Decimal = Decimal("50"),
    **overrides: Decimal,
) -> OpportunityFactors:
    values = {
        "price_score": value,
        "trend_score": value,
        "demand_score": value,
        "competition_score": value,
        "risk_score": value,
    }
    values.update(overrides)
    return OpportunityFactors(**values)


def test_default_policy_weights_sum_to_one() -> None:
    policy = OpportunityScorePolicy()

    total = (
        policy.price_weight
        + policy.trend_weight
        + policy.demand_weight
        + policy.competition_weight
        + policy.risk_weight
    )

    assert total == Decimal("1.00")


def test_calculates_default_weighted_score() -> None:
    factors = make_factors(
        price_score=Decimal("90"),
        trend_score=Decimal("80"),
        demand_score=Decimal("70"),
        competition_score=Decimal("60"),
        risk_score=Decimal("50"),
    )
    generated_at = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)

    result = OpportunityScoreEngine().calculate(
        factors,
        confidence=Decimal("82.5"),
        generated_at=generated_at,
    )

    assert isinstance(result, OpportunityScore)
    assert result.score == Decimal("73.50")
    assert result.grade is OpportunityGrade.FAIR
    assert result.confidence == Decimal("82.5")
    assert result.factors is factors
    assert result.generated_at is generated_at


@pytest.mark.parametrize(
    ("score", "expected_grade"),
    [
        (Decimal("100"), OpportunityGrade.EXCELLENT),
        (Decimal("90"), OpportunityGrade.EXCELLENT),
        (Decimal("89.99"), OpportunityGrade.GOOD),
        (Decimal("75"), OpportunityGrade.GOOD),
        (Decimal("74.99"), OpportunityGrade.FAIR),
        (Decimal("60"), OpportunityGrade.FAIR),
        (Decimal("59.99"), OpportunityGrade.POOR),
        (Decimal("40"), OpportunityGrade.POOR),
        (Decimal("39.99"), OpportunityGrade.REJECT),
        (Decimal("0"), OpportunityGrade.REJECT),
    ],
)
def test_grade_boundaries(
    score: Decimal,
    expected_grade: OpportunityGrade,
) -> None:
    result = OpportunityScoreEngine().calculate(make_factors(score))

    assert result.score == score.quantize(Decimal("0.01"))
    assert result.grade is expected_grade


def test_rounds_weighted_score_half_up_to_two_decimals() -> None:
    factors = make_factors(
        price_score=Decimal("33.335"),
        trend_score=Decimal("33.335"),
        demand_score=Decimal("33.335"),
        competition_score=Decimal("33.335"),
        risk_score=Decimal("33.335"),
    )

    result = OpportunityScoreEngine().calculate(factors)

    assert result.score == Decimal("33.34")


def test_custom_policy_changes_weighted_score_and_grade() -> None:
    policy = OpportunityScorePolicy(
        price_weight=Decimal("1.00"),
        trend_weight=Decimal("0.00"),
        demand_weight=Decimal("0.00"),
        competition_weight=Decimal("0.00"),
        risk_weight=Decimal("0.00"),
        excellent_threshold=Decimal("80"),
        good_threshold=Decimal("60"),
        fair_threshold=Decimal("40"),
        poor_threshold=Decimal("20"),
    )
    factors = make_factors(
        value=Decimal("0"),
        price_score=Decimal("85"),
    )

    result = OpportunityScoreEngine(policy).calculate(factors)

    assert result.score == Decimal("85.00")
    assert result.grade is OpportunityGrade.EXCELLENT


def test_generated_at_defaults_to_timezone_aware_utc() -> None:
    result = OpportunityScoreEngine().calculate(make_factors())

    assert result.generated_at.tzinfo is timezone.utc


def test_factors_type_is_validated() -> None:
    with pytest.raises(TypeError):
        OpportunityScoreEngine().calculate({})


@pytest.mark.parametrize("value", [0.0, "50", None])
def test_confidence_requires_decimal(value: object) -> None:
    with pytest.raises(TypeError):
        OpportunityScoreEngine().calculate(
            make_factors(),
            confidence=value,
        )


@pytest.mark.parametrize(
    "value",
    [Decimal("-0.01"), Decimal("100.01"), Decimal("NaN"), Decimal("Infinity")],
)
def test_confidence_must_be_finite_and_inside_range(value: Decimal) -> None:
    with pytest.raises(ValueError):
        OpportunityScoreEngine().calculate(
            make_factors(),
            confidence=value,
        )


def test_generated_at_requires_datetime() -> None:
    with pytest.raises(TypeError):
        OpportunityScoreEngine().calculate(
            make_factors(),
            generated_at="2026-07-27T12:00:00Z",
        )


def test_generated_at_requires_timezone_awareness() -> None:
    with pytest.raises(ValueError):
        OpportunityScoreEngine().calculate(
            make_factors(),
            generated_at=datetime(2026, 7, 27, 12, 0),
        )


@pytest.mark.parametrize(
    "field_name",
    [
        "price_weight",
        "trend_weight",
        "demand_weight",
        "competition_weight",
        "risk_weight",
        "excellent_threshold",
        "good_threshold",
        "fair_threshold",
        "poor_threshold",
    ],
)
def test_policy_fields_require_decimal(field_name: str) -> None:
    with pytest.raises(TypeError):
        OpportunityScorePolicy(**{field_name: 0.5})


def test_policy_weights_must_sum_to_one() -> None:
    with pytest.raises(ValueError):
        OpportunityScorePolicy(price_weight=Decimal("0.31"))


def test_policy_grade_thresholds_require_descending_order() -> None:
    with pytest.raises(ValueError):
        OpportunityScorePolicy(
            excellent_threshold=Decimal("75"),
            good_threshold=Decimal("75"),
        )


def test_fee_score_changes_weighted_opportunity_score() -> None:
    factors = make_factors(Decimal("50"))

    low_fee_result = OpportunityScoreEngine().calculate(
        factors,
        fee_score=Decimal("100"),
    )
    high_fee_result = OpportunityScoreEngine().calculate(
        factors,
        fee_score=Decimal("0"),
    )

    assert low_fee_result.score == Decimal("55.00")
    assert high_fee_result.score == Decimal("45.00")


@pytest.mark.parametrize("value", [0.0, "50", object()])
def test_fee_score_requires_decimal_or_none(value: object) -> None:
    with pytest.raises(TypeError):
        OpportunityScoreEngine().calculate(
            make_factors(),
            fee_score=value,
        )


@pytest.mark.parametrize(
    "value",
    [Decimal("-0.01"), Decimal("100.01"), Decimal("NaN")],
)
def test_fee_score_must_be_finite_and_inside_range(value: Decimal) -> None:
    with pytest.raises(ValueError):
        OpportunityScoreEngine().calculate(
            make_factors(),
            fee_score=value,
        )


def test_fee_weight_requires_decimal() -> None:
    with pytest.raises(TypeError):
        OpportunityScorePolicy(fee_weight=0.10)


@pytest.mark.parametrize(
    "value",
    [Decimal("-0.01"), Decimal("1.01"), Decimal("NaN")],
)
def test_fee_weight_requires_finite_unit_range(value: Decimal) -> None:
    with pytest.raises(ValueError):
        OpportunityScorePolicy(fee_weight=value)


def test_roi_score_changes_weighted_opportunity_score() -> None:
    factors = make_factors(Decimal("50"))

    high_roi_result = OpportunityScoreEngine().calculate(
        factors,
        roi_score=Decimal("100"),
    )
    low_roi_result = OpportunityScoreEngine().calculate(
        factors,
        roi_score=Decimal("0"),
    )

    assert high_roi_result.score == Decimal("55.00")
    assert low_roi_result.score == Decimal("45.00")


def test_fee_and_roi_scores_are_combined_without_double_counting_base() -> None:
    factors = make_factors(Decimal("50"))

    result = OpportunityScoreEngine().calculate(
        factors,
        fee_score=Decimal("100"),
        roi_score=Decimal("0"),
    )

    assert result.score == Decimal("50.00")


@pytest.mark.parametrize("value", [0.0, "50", object()])
def test_roi_score_requires_decimal_or_none(value: object) -> None:
    with pytest.raises(TypeError):
        OpportunityScoreEngine().calculate(
            make_factors(),
            roi_score=value,
        )


@pytest.mark.parametrize(
    "value",
    [Decimal("-0.01"), Decimal("100.01"), Decimal("NaN")],
)
def test_roi_score_must_be_finite_and_inside_range(value: Decimal) -> None:
    with pytest.raises(ValueError):
        OpportunityScoreEngine().calculate(
            make_factors(),
            roi_score=value,
        )


def test_roi_weight_requires_decimal() -> None:
    with pytest.raises(TypeError):
        OpportunityScorePolicy(roi_weight=0.10)


@pytest.mark.parametrize(
    "value",
    [Decimal("-0.01"), Decimal("1.01"), Decimal("NaN")],
)
def test_roi_weight_requires_finite_unit_range(value: Decimal) -> None:
    with pytest.raises(ValueError):
        OpportunityScorePolicy(roi_weight=value)


def test_fee_and_roi_weights_cannot_exceed_one_together() -> None:
    with pytest.raises(ValueError):
        OpportunityScorePolicy(
            fee_weight=Decimal("0.60"),
            roi_weight=Decimal("0.50"),
        )
