from decimal import Decimal

import pytest

from app.engine.fee_efficiency import FeeEfficiencyPolicy, FeeEfficiencyScorer
from services.fees import calculate_marketplace_fee


def test_low_effective_fee_rate_receives_full_score() -> None:
    fees = calculate_marketplace_fee(
        "ebay",
        Decimal("100"),
        marketplace_fee_rate=Decimal("0.05"),
        payment_fee_rate=Decimal("0.02"),
        fixed_fee=Decimal("0"),
    )

    assert FeeEfficiencyScorer().calculate(fees) == Decimal("100.00")


def test_ebay_profile_fee_rate_is_scored_with_fixed_fee_included() -> None:
    fees = calculate_marketplace_fee("ebay", Decimal("100"))

    assert FeeEfficiencyScorer().calculate(fees) == Decimal("74.80")


def test_high_fee_rate_is_capped_at_zero() -> None:
    fees = calculate_marketplace_fee(
        "ebay",
        Decimal("100"),
        marketplace_fee_rate=Decimal("0.30"),
        payment_fee_rate=Decimal("0.15"),
        fixed_fee=Decimal("0"),
    )

    assert FeeEfficiencyScorer().calculate(fees) == Decimal("0.00")


def test_zero_selling_price_returns_zero_score() -> None:
    fees = calculate_marketplace_fee("ebay", Decimal("0"))

    assert FeeEfficiencyScorer().calculate(fees) == Decimal("0.00")


def test_fee_breakdown_type_is_required() -> None:
    with pytest.raises(TypeError):
        FeeEfficiencyScorer().calculate({})


def test_policy_requires_ascending_rate_boundaries() -> None:
    with pytest.raises(ValueError):
        FeeEfficiencyPolicy(
            excellent_rate=Decimal("0.20"),
            acceptable_rate=Decimal("0.20"),
        )
