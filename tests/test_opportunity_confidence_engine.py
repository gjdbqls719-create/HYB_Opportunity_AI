from __future__ import annotations

from decimal import Decimal

import pytest

from app.engine import (
    OpportunityConfidenceEngine,
    OpportunityConfidenceLevel,
    OpportunityConfidencePolicy,
)


@pytest.mark.parametrize(
    ("score", "expected_level"),
    [
        (Decimal("0"), OpportunityConfidenceLevel.LOW),
        (Decimal("39.99"), OpportunityConfidenceLevel.LOW),
        (Decimal("40"), OpportunityConfidenceLevel.MEDIUM),
        (Decimal("69.99"), OpportunityConfidenceLevel.MEDIUM),
        (Decimal("70"), OpportunityConfidenceLevel.HIGH),
        (Decimal("89.99"), OpportunityConfidenceLevel.HIGH),
        (Decimal("90"), OpportunityConfidenceLevel.VERY_HIGH),
        (Decimal("100"), OpportunityConfidenceLevel.VERY_HIGH),
    ],
)
def test_engine_classifies_confidence_score(
    score: Decimal,
    expected_level: OpportunityConfidenceLevel,
) -> None:
    assessment = OpportunityConfidenceEngine().assess(score)

    assert assessment.score == score
    assert assessment.level is expected_level
    assert assessment.reason


@pytest.mark.parametrize(
    "score",
    [
        Decimal("-0.01"),
        Decimal("100.01"),
        Decimal("NaN"),
        Decimal("Infinity"),
    ],
)
def test_engine_rejects_invalid_decimal_score(score: Decimal) -> None:
    with pytest.raises(ValueError):
        OpportunityConfidenceEngine().assess(score)


def test_engine_rejects_non_decimal_score() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        OpportunityConfidenceEngine().assess(80)  # type: ignore[arg-type]


def test_policy_requires_ordered_thresholds() -> None:
    with pytest.raises(ValueError, match="medium < high < very_high"):
        OpportunityConfidencePolicy(
            medium_threshold=Decimal("70"),
            high_threshold=Decimal("70"),
            very_high_threshold=Decimal("90"),
        )
