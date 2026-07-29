from __future__ import annotations

from decimal import Decimal

import pytest

from app.application.opportunity_intelligence.trend_interpreter import (
    OpportunityTrendAssessment,
    OpportunityTrendInterpreter,
    OpportunityTrendLevel,
    OpportunityTrendPolicy,
)
from app.domain.trend import (
    PriceTrendAnalysis,
    PriceVolatility,
    TrendDirection,
)


def analysis(
    *,
    direction: TrendDirection,
    volatility: PriceVolatility,
    near_lowest: bool = False,
    near_highest: bool = False,
    sample_count: int = 3,
    price_range: Decimal = Decimal("20"),
) -> PriceTrendAnalysis:
    if price_range == 0:
        current_price = Decimal("100")
        highest_price = Decimal("100")
        lowest_price = Decimal("100")
        average_price = Decimal("100")
        median_price = Decimal("100")
    else:
        lowest_price = Decimal("90")
        highest_price = Decimal("110")
        average_price = Decimal("100")
        median_price = Decimal("100")
        if near_lowest:
            current_price = Decimal("90")
        elif near_highest:
            current_price = Decimal("110")
        else:
            current_price = Decimal("100")

    change_rate = {
        TrendDirection.UP: Decimal("10"),
        TrendDirection.DOWN: Decimal("-10"),
        TrendDirection.STABLE: Decimal("0"),
    }[direction]

    return PriceTrendAnalysis(
        current_price=current_price,
        highest_price=highest_price,
        lowest_price=lowest_price,
        average_price=average_price,
        median_price=median_price,
        price_range=price_range,
        change_rate=change_rate,
        direction=direction,
        volatility=volatility,
        near_lowest=near_lowest,
        near_highest=near_highest,
        sample_count=sample_count,
    )


def test_rejects_non_trend_analysis() -> None:
    with pytest.raises(TypeError):
        OpportunityTrendInterpreter().interpret(object())


def test_insufficient_samples_return_watch() -> None:
    result = OpportunityTrendInterpreter().interpret(
        analysis(
            direction=TrendDirection.STABLE,
            volatility=PriceVolatility.LOW,
            sample_count=1,
            price_range=Decimal("0"),
            near_lowest=True,
            near_highest=True,
        )
    )

    assert result.level is OpportunityTrendLevel.WATCH
    assert result.favorable is False
    assert result.requires_caution is True


def test_up_low_volatility_near_lowest_is_strong_buy_trend() -> None:
    result = OpportunityTrendInterpreter().interpret(
        analysis(
            direction=TrendDirection.UP,
            volatility=PriceVolatility.LOW,
            near_lowest=True,
        )
    )

    assert result.level is OpportunityTrendLevel.STRONG_BUY_TREND
    assert result.favorable is True
    assert result.requires_caution is False


@pytest.mark.parametrize("volatility", [PriceVolatility.LOW, PriceVolatility.MEDIUM])
def test_uptrend_with_acceptable_volatility_is_favorable(
    volatility: PriceVolatility,
) -> None:
    result = OpportunityTrendInterpreter().interpret(
        analysis(
            direction=TrendDirection.UP,
            volatility=volatility,
        )
    )

    assert result.level is OpportunityTrendLevel.FAVORABLE_TREND
    assert result.favorable is True


def test_high_volatility_uptrend_returns_watch() -> None:
    result = OpportunityTrendInterpreter().interpret(
        analysis(
            direction=TrendDirection.UP,
            volatility=PriceVolatility.HIGH,
        )
    )

    assert result.level is OpportunityTrendLevel.WATCH
    assert result.requires_caution is True


@pytest.mark.parametrize(
    ("volatility", "near_highest"),
    [
        (PriceVolatility.HIGH, False),
        (PriceVolatility.LOW, True),
    ],
)
def test_downtrend_with_major_risk_signal_is_high_risk(
    volatility: PriceVolatility,
    near_highest: bool,
) -> None:
    result = OpportunityTrendInterpreter().interpret(
        analysis(
            direction=TrendDirection.DOWN,
            volatility=volatility,
            near_highest=near_highest,
        )
    )

    assert result.level is OpportunityTrendLevel.HIGH_RISK_TREND
    assert result.favorable is False
    assert result.requires_caution is True


def test_downtrend_without_major_risk_signal_returns_watch() -> None:
    result = OpportunityTrendInterpreter().interpret(
        analysis(
            direction=TrendDirection.DOWN,
            volatility=PriceVolatility.MEDIUM,
        )
    )

    assert result.level is OpportunityTrendLevel.WATCH


def test_flat_price_history_is_stable_opportunity() -> None:
    result = OpportunityTrendInterpreter().interpret(
        analysis(
            direction=TrendDirection.STABLE,
            volatility=PriceVolatility.LOW,
            near_lowest=True,
            near_highest=True,
            price_range=Decimal("0"),
        )
    )

    assert result.level is OpportunityTrendLevel.STABLE_OPPORTUNITY
    assert result.favorable is True


def test_stable_low_volatility_is_stable_opportunity() -> None:
    result = OpportunityTrendInterpreter().interpret(
        analysis(
            direction=TrendDirection.STABLE,
            volatility=PriceVolatility.LOW,
        )
    )

    assert result.level is OpportunityTrendLevel.STABLE_OPPORTUNITY


@pytest.mark.parametrize(
    ("volatility", "near_highest"),
    [
        (PriceVolatility.HIGH, False),
        (PriceVolatility.LOW, True),
    ],
)
def test_stable_trend_with_caution_signal_returns_watch(
    volatility: PriceVolatility,
    near_highest: bool,
) -> None:
    result = OpportunityTrendInterpreter().interpret(
        analysis(
            direction=TrendDirection.STABLE,
            volatility=volatility,
            near_highest=near_highest,
        )
    )

    assert result.level is OpportunityTrendLevel.WATCH
    assert result.requires_caution is True


def test_custom_minimum_sample_policy_is_applied() -> None:
    interpreter = OpportunityTrendInterpreter(
        OpportunityTrendPolicy(minimum_sample_count=4)
    )

    result = interpreter.interpret(
        analysis(
            direction=TrendDirection.UP,
            volatility=PriceVolatility.LOW,
            sample_count=3,
        )
    )

    assert result.level is OpportunityTrendLevel.WATCH


@pytest.mark.parametrize("minimum_sample_count", [0, 1])
def test_policy_rejects_sample_count_below_two(
    minimum_sample_count: int,
) -> None:
    with pytest.raises(ValueError):
        OpportunityTrendPolicy(
            minimum_sample_count=minimum_sample_count,
        )


def test_policy_rejects_boolean_sample_count() -> None:
    with pytest.raises(TypeError):
        OpportunityTrendPolicy(minimum_sample_count=True)


def test_assessment_rejects_conflicting_flags() -> None:
    with pytest.raises(ValueError):
        OpportunityTrendAssessment(
            level=OpportunityTrendLevel.FAVORABLE_TREND,
            summary="유효한 요약",
            recommended_action="유효한 행동",
            favorable=True,
            requires_caution=True,
        )
