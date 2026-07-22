from __future__ import annotations

from engine.confidence import (
    calculate_price_confidence,
)
from engine.explainable_score import (
    build_explainable_score,
)
from engine.price_trend import PriceTrend
from engine.score_formatter import (
    format_explainable_score,
)


def make_trend() -> PriceTrend:
    return PriceTrend(
        marketplace="ebay",
        item_id="ITEM-001",
        title="Test Product",
        currency="USD",
        sample_size=3,
        period_days=7.0,
        oldest_price=120.0,
        current_price=80.0,
        lowest_price=80.0,
        highest_price=120.0,
        average_price=100.0,
        absolute_change=-40.0,
        percentage_change=-33.33,
        trend_direction="하락",
        price_position="기간 최저가",
        recommendation="매입 검토",
        reason="테스트 가격 추세",
        has_sufficient_history=True,
    )


def test_formats_score_summary() -> None:
    confidence = calculate_price_confidence(6)

    score_result = build_explainable_score(
        base_score=65.0,
        roi=55.0,
        net_profit=100.0,
        competitor_count=4,
        risk_level="low",
        confidence=confidence,
        price_trend=make_trend(),
    )

    formatted = format_explainable_score(
        score_result
    )

    assert formatted.title == "HYB Explainable Score"
    assert formatted.final_score == 100
    assert formatted.raw_total == 117.0

    assert formatted.lines == (
        "기회 점수: +65",
        "수익성: +18",
        "가격 신뢰도: +10",
        "가격 추세: +11",
        "경쟁도: +8",
        "위험도: +5",
    )


def test_formats_negative_adjustments() -> None:
    confidence = calculate_price_confidence(
        1,
        used_fallback_price=True,
    )

    score_result = build_explainable_score(
        base_score=30.0,
        roi=-15.0,
        net_profit=-10.0,
        competitor_count=80,
        risk_level="high",
        confidence=confidence,
        price_trend=None,
    )

    formatted = format_explainable_score(
        score_result
    )

    assert "수익성: -25" in formatted.lines
    assert "가격 신뢰도: -10" in formatted.lines
    assert "경쟁도: -10" in formatted.lines
    assert "위험도: -10" in formatted.lines

    assert formatted.final_score == 0


def test_formats_strengths_and_warnings() -> None:
    confidence = calculate_price_confidence(6)

    score_result = build_explainable_score(
        base_score=65.0,
        roi=55.0,
        net_profit=100.0,
        competitor_count=4,
        risk_level="low",
        confidence=confidence,
        price_trend=make_trend(),
    )

    formatted = format_explainable_score(
        score_result
    )

    assert (
        "ROI가 50% 이상으로 매우 높습니다."
        in formatted.strengths
    )

    assert (
        "현재 가격이 저장 기간의 최저가입니다."
        in formatted.strengths
    )

    assert formatted.warnings == ()


def test_formats_missing_data_warning() -> None:
    score_result = build_explainable_score(
        base_score=50.0,
        roi=20.0,
        net_profit=30.0,
        competitor_count=20,
        risk_level="medium",
        confidence=None,
        price_trend=None,
    )

    formatted = format_explainable_score(
        score_result
    )

    assert (
        "가격 신뢰도 정보가 없습니다."
        in formatted.warnings
    )

    assert (
        "저장된 가격 추세 데이터가 없습니다."
        in formatted.warnings
    )


def test_builds_plain_text_output() -> None:
    confidence = calculate_price_confidence(6)

    score_result = build_explainable_score(
        base_score=65.0,
        roi=55.0,
        net_profit=100.0,
        competitor_count=4,
        risk_level="low",
        confidence=confidence,
        price_trend=make_trend(),
    )

    formatted = format_explainable_score(
        score_result
    )

    assert "HYB Explainable Score" in formatted.text
    assert "최종 점수: 100" in formatted.text
    assert "기회 점수: +65" in formatted.text
    assert "강점" in formatted.text