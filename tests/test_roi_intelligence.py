from __future__ import annotations

from decimal import Decimal

import pytest

from app.engine.roi_intelligence import (
    RoiGrade,
    RoiIntelligenceEngine,
    RoiIntelligencePolicy,
    RoiIntelligenceResult,
)


def test_calculates_roi_result_from_invested_capital_and_net_profit() -> None:
    result = RoiIntelligenceEngine().calculate(
        invested_capital=Decimal("100.00"),
        net_profit=Decimal("40.00"),
    )

    assert isinstance(result, RoiIntelligenceResult)
    assert result.roi_rate == Decimal("0.4000")
    assert result.roi_percent == Decimal("40.00")
    assert result.score == Decimal("70.00")
    assert result.grade is RoiGrade.B


@pytest.mark.parametrize(
    ("net_profit", "expected_score", "expected_grade"),
    [
        (Decimal("-10"), Decimal("0.00"), RoiGrade.F),
        (Decimal("0"), Decimal("0.00"), RoiGrade.F),
        (Decimal("5"), Decimal("10.00"), RoiGrade.D),
        (Decimal("10"), Decimal("20.00"), RoiGrade.D),
        (Decimal("20"), Decimal("40.00"), RoiGrade.C),
        (Decimal("40"), Decimal("70.00"), RoiGrade.B),
        (Decimal("60"), Decimal("85.00"), RoiGrade.A),
        (Decimal("80"), Decimal("100.00"), RoiGrade.A),
        (Decimal("120"), Decimal("100.00"), RoiGrade.A),
    ],
)
def test_roi_score_and_grade_boundaries(
    net_profit: Decimal,
    expected_score: Decimal,
    expected_grade: RoiGrade,
) -> None:
    result = RoiIntelligenceEngine().calculate(
        invested_capital=Decimal("100"),
        net_profit=net_profit,
    )

    assert result.score == expected_score
    assert result.grade is expected_grade


@pytest.mark.parametrize("value", [100, 100.0, "100", None])
def test_inputs_require_decimal(value: object) -> None:
    with pytest.raises(TypeError):
        RoiIntelligenceEngine().calculate(
            invested_capital=value,
            net_profit=Decimal("10"),
        )

    with pytest.raises(TypeError):
        RoiIntelligenceEngine().calculate(
            invested_capital=Decimal("100"),
            net_profit=value,
        )


@pytest.mark.parametrize(
    "value",
    [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")],
)
def test_inputs_must_be_finite(value: Decimal) -> None:
    with pytest.raises(ValueError):
        RoiIntelligenceEngine().calculate(
            invested_capital=value,
            net_profit=Decimal("10"),
        )

    with pytest.raises(ValueError):
        RoiIntelligenceEngine().calculate(
            invested_capital=Decimal("100"),
            net_profit=value,
        )


@pytest.mark.parametrize("value", [Decimal("0"), Decimal("-0.01")])
def test_invested_capital_must_be_positive(value: Decimal) -> None:
    with pytest.raises(ValueError):
        RoiIntelligenceEngine().calculate(
            invested_capital=value,
            net_profit=Decimal("10"),
        )


def test_custom_policy_changes_score_and_grade() -> None:
    policy = RoiIntelligencePolicy(
        minimum_viable_rate=Decimal("0.05"),
        healthy_rate=Decimal("0.10"),
        strong_rate=Decimal("0.20"),
        exceptional_rate=Decimal("0.40"),
        grade_a_rate=Decimal("0.30"),
        grade_b_rate=Decimal("0.20"),
        grade_c_rate=Decimal("0.10"),
        grade_d_rate=Decimal("0.00"),
    )

    result = RoiIntelligenceEngine(policy).calculate(
        invested_capital=Decimal("100"),
        net_profit=Decimal("30"),
    )

    assert result.score == Decimal("85.00")
    assert result.grade is RoiGrade.A


def test_policy_fields_require_decimal() -> None:
    with pytest.raises(TypeError):
        RoiIntelligencePolicy(healthy_rate=0.20)


def test_policy_score_boundaries_require_strict_order() -> None:
    with pytest.raises(ValueError):
        RoiIntelligencePolicy(
            healthy_rate=Decimal("0.10"),
        )


def test_policy_grade_boundaries_require_descending_order() -> None:
    with pytest.raises(ValueError):
        RoiIntelligencePolicy(
            grade_a_rate=Decimal("0.40"),
        )
