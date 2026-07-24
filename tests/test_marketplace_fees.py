from decimal import Decimal

import pytest

from services.fees import (
    AMAZON_PROFILE,
    DEFAULT_PROFILE,
    EBAY_PROFILE,
    FeeProfile,
    calculate_marketplace_fee,
    get_fee_profile,
)


def test_get_ebay_fee_profile() -> None:
    profile = get_fee_profile("ebay")

    assert profile is EBAY_PROFILE
    assert profile.marketplace == "ebay"
    assert profile.marketplace_fee_rate == Decimal("0.13")
    assert profile.payment_fee_rate == Decimal("0.03")
    assert profile.fixed_fee == Decimal("0.30")


def test_get_amazon_fee_profile() -> None:
    profile = get_fee_profile("AMAZON")

    assert profile is AMAZON_PROFILE
    assert profile.marketplace == "amazon"
    assert profile.marketplace_fee_rate == Decimal("0.15")
    assert profile.payment_fee_rate == Decimal("0.03")
    assert profile.fixed_fee == Decimal("0.30")


def test_unknown_marketplace_uses_default_profile() -> None:
    profile = get_fee_profile("unknown-marketplace")

    assert profile is DEFAULT_PROFILE
    assert profile.marketplace == "default"


def test_calculate_ebay_marketplace_fee() -> None:
    result = calculate_marketplace_fee(
        marketplace="ebay",
        selling_price=100,
    )

    assert result.marketplace == "ebay"
    assert result.marketplace_fee == Decimal("13.00")
    assert result.payment_fee == Decimal("3.00")
    assert result.fixed_fee == Decimal("0.30")
    assert result.total_fee == Decimal("16.30")
    assert result.source == "profile"


def test_calculate_amazon_marketplace_fee() -> None:
    result = calculate_marketplace_fee(
        marketplace="amazon",
        selling_price=200,
    )

    assert result.marketplace == "amazon"
    assert result.marketplace_fee == Decimal("30.00")
    assert result.payment_fee == Decimal("6.00")
    assert result.fixed_fee == Decimal("0.30")
    assert result.total_fee == Decimal("36.30")


def test_fee_override_replaces_selected_values() -> None:
    result = calculate_marketplace_fee(
        marketplace="ebay",
        selling_price=100,
        marketplace_fee_rate=Decimal("0.10"),
        fixed_fee=Decimal("0.50"),
    )

    assert result.marketplace_fee_rate == Decimal("0.10")
    assert result.payment_fee_rate == Decimal("0.03")
    assert result.fixed_fee == Decimal("0.50")
    assert result.marketplace_fee == Decimal("10.00")
    assert result.payment_fee == Decimal("3.00")
    assert result.total_fee == Decimal("13.50")
    assert result.source == "override"


def test_fee_profile_rejects_invalid_rate() -> None:
    with pytest.raises(
        ValueError,
        match="0 이상 1 이하여야 합니다",
    ):
        FeeProfile(
            marketplace="invalid",
            marketplace_fee_rate=Decimal("1.01"),
        )


def test_calculator_rejects_negative_selling_price() -> None:
    with pytest.raises(
        ValueError,
        match="판매가는 0 이상이어야 합니다",
    ):
        calculate_marketplace_fee(
            marketplace="ebay",
            selling_price=-1,
        )