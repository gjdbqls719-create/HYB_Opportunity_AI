from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.opportunity import (
    OpportunityFactors,
    OpportunityGrade,
    OpportunityScore,
)


def make_factors(
    **overrides: object,
) -> OpportunityFactors:
    values: dict[str, object] = {
        "price_score": Decimal("85.00"),
        "trend_score": Decimal("70.00"),
        "demand_score": Decimal("75.00"),
        "competition_score": Decimal("60.00"),
        "risk_score": Decimal("80.00"),
    }
    values.update(overrides)

    return OpportunityFactors(**values)


def make_score(
    **overrides: object,
) -> OpportunityScore:
    values: dict[str, object] = {
        "score": Decimal("76.50"),
        "grade": OpportunityGrade.GOOD,
        "confidence": Decimal("82.00"),
        "factors": make_factors(),
        "generated_at": datetime(
            2026,
            7,
            27,
            12,
            0,
            tzinfo=timezone.utc,
        ),
    }
    values.update(overrides)

    return OpportunityScore(**values)


def test_opportunity_grade_uses_stable_string_values() -> None:
    assert OpportunityGrade.EXCELLENT.value == "excellent"
    assert OpportunityGrade.GOOD.value == "good"
    assert OpportunityGrade.FAIR.value == "fair"
    assert OpportunityGrade.POOR.value == "poor"
    assert OpportunityGrade.REJECT.value == "reject"


def test_opportunity_factors_creation() -> None:
    factors = make_factors()

    assert factors.price_score == Decimal("85.00")
    assert factors.trend_score == Decimal("70.00")
    assert factors.demand_score == Decimal("75.00")
    assert factors.competition_score == Decimal("60.00")
    assert factors.risk_score == Decimal("80.00")


def test_opportunity_score_creation() -> None:
    result = make_score()

    assert result.score == Decimal("76.50")
    assert result.grade is OpportunityGrade.GOOD
    assert result.confidence == Decimal("82.00")
    assert result.factors == make_factors()
    assert result.generated_at.tzinfo is timezone.utc


def test_domain_models_are_immutable() -> None:
    factors = make_factors()
    result = make_score(factors=factors)

    with pytest.raises(FrozenInstanceError):
        factors.price_score = Decimal("90.00")

    with pytest.raises(FrozenInstanceError):
        result.score = Decimal("90.00")


@pytest.mark.parametrize(
    "field_name",
    [
        "price_score",
        "trend_score",
        "demand_score",
        "competition_score",
        "risk_score",
    ],
)
def test_factor_scores_require_decimal(
    field_name: str,
) -> None:
    with pytest.raises(TypeError):
        make_factors(**{field_name: 50.0})


@pytest.mark.parametrize(
    "field_name",
    [
        "price_score",
        "trend_score",
        "demand_score",
        "competition_score",
        "risk_score",
    ],
)
@pytest.mark.parametrize(
    "value",
    [Decimal("-0.01"), Decimal("100.01")],
)
def test_factor_scores_must_be_inside_range(
    field_name: str,
    value: Decimal,
) -> None:
    with pytest.raises(ValueError):
        make_factors(**{field_name: value})


@pytest.mark.parametrize(
    "field_name",
    [
        "price_score",
        "trend_score",
        "demand_score",
        "competition_score",
        "risk_score",
    ],
)
@pytest.mark.parametrize(
    "value",
    [Decimal("NaN"), Decimal("Infinity")],
)
def test_factor_scores_must_be_finite(
    field_name: str,
    value: Decimal,
) -> None:
    with pytest.raises(ValueError):
        make_factors(**{field_name: value})


@pytest.mark.parametrize(
    "value",
    [Decimal("0"), Decimal("100")],
)
def test_factor_scores_accept_boundaries(
    value: Decimal,
) -> None:
    factors = make_factors(price_score=value)

    assert factors.price_score == value


@pytest.mark.parametrize(
    "field_name",
    ["score", "confidence"],
)
def test_result_scores_require_decimal(
    field_name: str,
) -> None:
    with pytest.raises(TypeError):
        make_score(**{field_name: 50.0})


@pytest.mark.parametrize(
    "field_name",
    ["score", "confidence"],
)
@pytest.mark.parametrize(
    "value",
    [Decimal("-0.01"), Decimal("100.01")],
)
def test_result_scores_must_be_inside_range(
    field_name: str,
    value: Decimal,
) -> None:
    with pytest.raises(ValueError):
        make_score(**{field_name: value})


@pytest.mark.parametrize(
    "field_name",
    ["score", "confidence"],
)
@pytest.mark.parametrize(
    "value",
    [Decimal("NaN"), Decimal("Infinity")],
)
def test_result_scores_must_be_finite(
    field_name: str,
    value: Decimal,
) -> None:
    with pytest.raises(ValueError):
        make_score(**{field_name: value})


@pytest.mark.parametrize(
    "value",
    [Decimal("0"), Decimal("100")],
)
def test_result_scores_accept_boundaries(
    value: Decimal,
) -> None:
    result = make_score(
        score=value,
        confidence=value,
    )

    assert result.score == value
    assert result.confidence == value


def test_grade_requires_opportunity_grade() -> None:
    with pytest.raises(TypeError):
        make_score(grade="good")


def test_factors_require_opportunity_factors() -> None:
    with pytest.raises(TypeError):
        make_score(factors={})


def test_generated_at_requires_datetime() -> None:
    with pytest.raises(TypeError):
        make_score(generated_at="2026-07-27T12:00:00Z")


def test_generated_at_requires_timezone_aware_datetime() -> None:
    with pytest.raises(ValueError):
        make_score(generated_at=datetime(2026, 7, 27, 12, 0))
