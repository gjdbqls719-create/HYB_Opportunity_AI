from decimal import Decimal

import pytest

from app.engine import (
    OpportunityRiskAssessment,
    OpportunityRiskEngine,
    OpportunityRiskLevel,
    OpportunityRiskPolicy,
)


def test_assess_low_risk_from_high_safety_score() -> None:
    result = OpportunityRiskEngine().assess(Decimal("85"))

    assert result == OpportunityRiskAssessment(
        safety_score=Decimal("85"),
        level=OpportunityRiskLevel.LOW,
        reason="현재 위험 안전성 지표가 양호합니다.",
        requires_caution=False,
    )


def test_assess_medium_risk_at_boundary() -> None:
    result = OpportunityRiskEngine().assess(Decimal("40"))

    assert result.level is OpportunityRiskLevel.MEDIUM
    assert result.requires_caution is True


def test_assess_high_risk_below_medium_boundary() -> None:
    result = OpportunityRiskEngine().assess(Decimal("39.99"))

    assert result.level is OpportunityRiskLevel.HIGH
    assert result.requires_caution is True


def test_custom_policy_changes_boundaries() -> None:
    engine = OpportunityRiskEngine(
        OpportunityRiskPolicy(
            medium_safety_threshold=Decimal("30"),
            low_risk_safety_threshold=Decimal("80"),
        )
    )

    assert engine.assess(Decimal("79")).level is OpportunityRiskLevel.MEDIUM
    assert engine.assess(Decimal("80")).level is OpportunityRiskLevel.LOW


@pytest.mark.parametrize("value", [Decimal("-0.01"), Decimal("100.01"), Decimal("NaN")])
def test_rejects_invalid_score_range(value: Decimal) -> None:
    with pytest.raises(ValueError):
        OpportunityRiskEngine().assess(value)


def test_rejects_non_decimal_score() -> None:
    with pytest.raises(TypeError):
        OpportunityRiskEngine().assess(70)  # type: ignore[arg-type]


def test_policy_requires_ordered_thresholds() -> None:
    with pytest.raises(ValueError):
        OpportunityRiskPolicy(
            medium_safety_threshold=Decimal("70"),
            low_risk_safety_threshold=Decimal("70"),
        )
