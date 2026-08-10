from dataclasses import replace
from decimal import Decimal

import pytest

from app.domain.opportunity.conservative_actual_variance import (
    CONSERVATIVE_ACTUAL_VARIANCE_POLICY_NAME,
    ConservativeActualVarianceMetric,
    VarianceFavorability,
    VarianceMetricComparability,
    VarianceMetricDirection,
    expected_favorability,
)


def test_variance_v2_policy_identity_exists():
    assert CONSERVATIVE_ACTUAL_VARIANCE_POLICY_NAME == "conservative-actual-variance"


def _money_metric(*, direction=VarianceMetricDirection.COST):
    return ConservativeActualVarianceMetric(
        metric_name="acquisition_cost_per_unit",
        direction=direction,
        comparability=VarianceMetricComparability.COMPARABLE,
        predicted_value=Decimal("100"),
        actual_value=Decimal("90"),
        variance=Decimal("-10"),
        relative_variance_percent=Decimal("-10.0"),
        variance_percentage_points=None,
        favorability=expected_favorability(direction, Decimal("-10")),
        unit="money_per_unit",
        currency="KRW",
    )


def test_metric_exact_arithmetic_relative_variance_and_directional_favorability():
    cost = _money_metric()
    benefit = _money_metric(direction=VarianceMetricDirection.BENEFIT)
    assert cost.variance == Decimal("-10")
    assert cost.relative_variance_percent == Decimal("-10.0")
    assert cost.favorability is VarianceFavorability.FAVORABLE
    assert benefit.favorability is VarianceFavorability.UNFAVORABLE


def test_metric_rejects_derived_arithmetic_and_fake_unavailable_values():
    with pytest.raises(ValueError, match="arithmetic"):
        replace(_money_metric(), variance=Decimal("10"))
    with pytest.raises(ValueError, match="cannot carry derived variance"):
        ConservativeActualVarianceMetric(
            metric_name="margin",
            direction=VarianceMetricDirection.BENEFIT,
            comparability=VarianceMetricComparability.UNAVAILABLE,
            predicted_value=Decimal("0.2"),
            actual_value=None,
            variance=Decimal("0"),
            relative_variance_percent=None,
            variance_percentage_points=None,
            favorability=VarianceFavorability.UNAVAILABLE,
            unit="percentage_points",
            currency=None,
            reason_codes=("actual_unavailable",),
        )


def test_zero_predicted_value_has_no_invented_relative_percentage():
    metric = ConservativeActualVarianceMetric(
        metric_name="fixed_fee_per_sold_unit",
        direction=VarianceMetricDirection.COST,
        comparability=VarianceMetricComparability.COMPARABLE,
        predicted_value=Decimal("0"),
        actual_value=Decimal("3"),
        variance=Decimal("3"),
        relative_variance_percent=None,
        variance_percentage_points=None,
        favorability=VarianceFavorability.UNFAVORABLE,
        unit="money_per_unit",
        currency="KRW",
    )
    assert metric.relative_variance_percent is None
