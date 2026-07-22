from __future__ import annotations

from engine.confidence import (
    calculate_price_confidence,
)
from engine.market_analyzer import (
    analyze_market,
)
from engine.price_trend import PriceTrend


def make_trend(
    *,
    current_price: float = 80.0,
    lowest_price: float = 80.0,
    highest_price: float = 120.0,
    average_price: float = 100.0,
    trend_direction: str = "하락",
    price_position: str = "기간 최저가",
    has_sufficient_history: bool = True,
) -> PriceTrend:
    return PriceTrend(
        marketplace="ebay",
        item_id="ITEM-001",
        title="Test Product",
        currency="USD",
        sample_size=3,
        period_days=7.0,
        oldest_price=120.0,
        current_price=current_price,
        lowest_price=lowest_price,
        highest_price=highest_price,
        average_price=average_price,
        absolute_change=current_price - 120.0,
        percentage_change=-33.33,
        trend_direction=trend_direction,
        price_position=price_position,
        recommendation="매입 검토",
        reason="테스트 가격 추세",
        has_sufficient_history=has_sufficient_history,
    )


def test_analyzes_favorable_market() -> None:
    confidence = calculate_price_confidence(6)

    result = analyze_market(
        competitor_count=4,
        confidence=confidence,
        price_trend=make_trend(),
    )

    assert result.market_condition == "유리"
    assert result.entry_difficulty == "낮음"
    assert result.buy_timing == "좋음"

    assert (
        "현재 가격이 저장 기간의 최저가입니다."
        in result.insights
    )

    assert (
        "가격이 하락 추세입니다."
        in result.insights
    )

    assert (
        "경쟁 상품 수가 매우 적습니다."
        in result.insights
    )


def test_analyzes_unfavorable_market() -> None:
    confidence = calculate_price_confidence(
        1,
        used_fallback_price=True,
    )

    result = analyze_market(
        competitor_count=80,
        confidence=confidence,
        price_trend=make_trend(
            current_price=120.0,
            price_position="기간 최고가",
            trend_direction="상승",
        ),
    )

    assert result.market_condition == "불리"
    assert result.entry_difficulty == "높음"
    assert result.buy_timing == "나쁨"

    assert (
        "현재 가격이 저장 기간의 최고가입니다."
        in result.risks
    )

    assert (
        "가격이 상승 추세입니다."
        in result.risks
    )

    assert (
        "경쟁 상품 수가 매우 많습니다."
        in result.risks
    )


def test_handles_missing_market_data() -> None:
    result = analyze_market(
        competitor_count=20,
        confidence=None,
        price_trend=None,
    )

    assert result.market_condition == "판단 보류"
    assert result.buy_timing == "판단 보류"

    assert (
        "가격 신뢰도 정보가 없습니다."
        in result.risks
    )

    assert (
        "저장된 가격 추세 데이터가 없습니다."
        in result.risks
    )


def test_handles_insufficient_price_history() -> None:
    confidence = calculate_price_confidence(4)

    result = analyze_market(
        competitor_count=10,
        confidence=confidence,
        price_trend=make_trend(
            has_sufficient_history=False,
        ),
    )

    assert result.buy_timing == "판단 보류"

    assert (
        "가격 추세를 판단하기 위한 이력이 부족합니다."
        in result.risks
    )


def test_builds_market_summary() -> None:
    confidence = calculate_price_confidence(6)

    result = analyze_market(
        competitor_count=4,
        confidence=confidence,
        price_trend=make_trend(),
    )

    assert "시장 상황은 유리합니다." in result.summary
    assert "시장 진입 난이도는 낮음입니다." in result.summary
    assert "현재 매입 시점은 좋음으로 평가됩니다." in result.summary


def test_rejects_negative_competitor_count() -> None:
    confidence = calculate_price_confidence(4)

    try:
        analyze_market(
            competitor_count=-1,
            confidence=confidence,
            price_trend=None,
        )
    except ValueError as error:
        assert (
            str(error)
            == "competitor_count는 0 이상이어야 합니다."
        )
    else:
        raise AssertionError(
            "ValueError가 발생해야 합니다."
        )