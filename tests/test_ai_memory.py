from __future__ import annotations

import pytest

from engine.ai_memory import (
    AIMemoryInsight,
    HistoricalOpportunity,
    analyze_ai_memory,
)


def test_analyze_ai_memory_without_history() -> None:
    """
    과거 분석 기록이 없으면 비교 데이터 부족 결과를 반환해야 한다.
    """
    insight = analyze_ai_memory(
        current_opportunity_score=80.0,
        current_roi=30.0,
        current_net_profit=25.0,
        current_success_probability=75.0,
        history=(),
    )

    assert isinstance(insight, AIMemoryInsight)

    assert insight.sample_size == 0

    assert insight.score_percentile == 0.0
    assert insight.roi_percentile == 0.0
    assert insight.profit_percentile == 0.0
    assert insight.success_probability_percentile == 0.0

    assert insight.average_score == 0.0
    assert insight.average_roi == 0.0
    assert insight.average_profit == 0.0
    assert insight.average_success_probability == 0.0

    assert insight.score_difference == 0.0
    assert insight.roi_difference == 0.0
    assert insight.profit_difference == 0.0
    assert insight.success_probability_difference == 0.0

    assert insight.overall_percentile == 0.0
    assert insight.rank_label == "비교 데이터 부족"

    assert (
        "과거 분석 기록이 없어"
        in insight.summary
    )


def test_analyze_ai_memory_calculates_percentiles() -> None:
    """
    현재 상품이 모든 과거 기록보다 높으면
    각 지표가 100 백분위가 되어야 한다.
    """
    history = (
        HistoricalOpportunity(
            opportunity_score=40.0,
            roi=10.0,
            net_profit=5.0,
            success_probability=40.0,
        ),
        HistoricalOpportunity(
            opportunity_score=50.0,
            roi=15.0,
            net_profit=10.0,
            success_probability=50.0,
        ),
        HistoricalOpportunity(
            opportunity_score=60.0,
            roi=20.0,
            net_profit=15.0,
            success_probability=60.0,
        ),
        HistoricalOpportunity(
            opportunity_score=70.0,
            roi=25.0,
            net_profit=20.0,
            success_probability=70.0,
        ),
    )

    insight = analyze_ai_memory(
        current_opportunity_score=80.0,
        current_roi=30.0,
        current_net_profit=25.0,
        current_success_probability=80.0,
        history=history,
    )

    assert insight.sample_size == 4

    assert insight.score_percentile == 100.0
    assert insight.roi_percentile == 100.0
    assert insight.profit_percentile == 100.0
    assert (
        insight.success_probability_percentile
        == 100.0
    )

    assert insight.overall_percentile == 100.0
    assert insight.rank_label == "최상위"

    assert "최근 4건" in insight.summary
    assert "최상위" in insight.summary
    assert "상위 약 0.0%" in insight.summary


def test_analyze_ai_memory_calculates_average_differences() -> None:
    """
    현재 상품과 과거 평균의 차이를 정확히 계산해야 한다.
    """
    history = (
        HistoricalOpportunity(
            opportunity_score=50.0,
            roi=10.0,
            net_profit=5.0,
            success_probability=40.0,
        ),
        HistoricalOpportunity(
            opportunity_score=70.0,
            roi=30.0,
            net_profit=15.0,
            success_probability=60.0,
        ),
    )

    insight = analyze_ai_memory(
        current_opportunity_score=75.0,
        current_roi=25.0,
        current_net_profit=8.0,
        current_success_probability=55.0,
        history=history,
    )

    assert insight.average_score == pytest.approx(
        60.0
    )
    assert insight.average_roi == pytest.approx(
        20.0
    )
    assert insight.average_profit == pytest.approx(
        10.0
    )
    assert (
        insight.average_success_probability
        == pytest.approx(50.0)
    )

    assert insight.score_difference == pytest.approx(
        15.0
    )
    assert insight.roi_difference == pytest.approx(
        5.0
    )
    assert insight.profit_difference == pytest.approx(
        -2.0
    )
    assert (
        insight.success_probability_difference
        == pytest.approx(5.0)
    )

    assert (
        "기회 점수은 과거 평균보다 "
        "15.00점 높습니다."
        in insight.summary
    )
    assert (
        "ROI은 과거 평균보다 "
        "5.00%p 높습니다."
        in insight.summary
    )
    assert (
        "예상 순이익은 과거 평균보다 "
        "2.00 낮습니다."
        in insight.summary
    )
    assert (
        "성공 확률은 과거 평균보다 "
        "5.00%p 높습니다."
        in insight.summary
    )


def test_analyze_ai_memory_handles_equal_values() -> None:
    """
    현재 값이 모든 과거 값과 같으면
    동점의 절반을 반영해 50 백분위가 되어야 한다.
    """
    history = (
        HistoricalOpportunity(
            opportunity_score=60.0,
            roi=20.0,
            net_profit=10.0,
            success_probability=50.0,
        ),
        HistoricalOpportunity(
            opportunity_score=60.0,
            roi=20.0,
            net_profit=10.0,
            success_probability=50.0,
        ),
        HistoricalOpportunity(
            opportunity_score=60.0,
            roi=20.0,
            net_profit=10.0,
            success_probability=50.0,
        ),
        HistoricalOpportunity(
            opportunity_score=60.0,
            roi=20.0,
            net_profit=10.0,
            success_probability=50.0,
        ),
    )

    insight = analyze_ai_memory(
        current_opportunity_score=60.0,
        current_roi=20.0,
        current_net_profit=10.0,
        current_success_probability=50.0,
        history=history,
    )

    assert insight.score_percentile == 50.0
    assert insight.roi_percentile == 50.0
    assert insight.profit_percentile == 50.0
    assert (
        insight.success_probability_percentile
        == 50.0
    )

    assert insight.overall_percentile == 50.0
    assert insight.rank_label == "평균 이상"

    assert insight.score_difference == 0.0
    assert insight.roi_difference == 0.0
    assert insight.profit_difference == 0.0
    assert (
        insight.success_probability_difference
        == 0.0
    )

    assert (
        "기회 점수은 과거 평균과 동일합니다."
        in insight.summary
    )
    assert (
        "ROI은 과거 평균과 동일합니다."
        in insight.summary
    )
    assert (
        "예상 순이익은 과거 평균과 동일합니다."
        in insight.summary
    )
    assert (
        "성공 확률은 과거 평균과 동일합니다."
        in insight.summary
    )