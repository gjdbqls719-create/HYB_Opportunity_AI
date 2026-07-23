from __future__ import annotations

from dataclasses import dataclass
from statistics import mean
from typing import Iterable


@dataclass(slots=True, frozen=True)
class HistoricalOpportunity:
    """
    AI Memory가 비교에 사용하는 과거 상품 분석 기록.

    저장소나 UI 구조에 의존하지 않고,
    비교에 필요한 핵심 수치만 보관한다.
    """

    opportunity_score: float
    roi: float
    net_profit: float
    success_probability: float


@dataclass(slots=True, frozen=True)
class AIMemoryInsight:
    """
    현재 상품을 과거 분석 기록과 비교한 결과.
    """

    sample_size: int

    score_percentile: float
    roi_percentile: float
    profit_percentile: float
    success_probability_percentile: float

    average_score: float
    average_roi: float
    average_profit: float
    average_success_probability: float

    score_difference: float
    roi_difference: float
    profit_difference: float
    success_probability_difference: float

    overall_percentile: float
    rank_label: str
    summary: str


def analyze_ai_memory(
    *,
    current_opportunity_score: float,
    current_roi: float,
    current_net_profit: float,
    current_success_probability: float,
    history: Iterable[HistoricalOpportunity],
) -> AIMemoryInsight:
    """
    현재 상품을 과거 기회 분석 기록과 비교한다.

    과거 기록을 기준으로 다음 정보를 계산한다.

    - 기회 점수 백분위
    - ROI 백분위
    - 순이익 백분위
    - 성공 확률 백분위
    - 과거 평균 대비 차이
    - 종합 백분위와 순위 등급
    """
    historical_records = tuple(history)

    if not historical_records:
        return _build_empty_insight()

    historical_scores = tuple(
        float(record.opportunity_score)
        for record in historical_records
    )
    historical_rois = tuple(
        float(record.roi)
        for record in historical_records
    )
    historical_profits = tuple(
        float(record.net_profit)
        for record in historical_records
    )
    historical_probabilities = tuple(
        float(record.success_probability)
        for record in historical_records
    )

    current_score = float(current_opportunity_score)
    current_roi_value = float(current_roi)
    current_profit = float(current_net_profit)
    current_probability = float(
        current_success_probability
    )

    average_score = mean(historical_scores)
    average_roi = mean(historical_rois)
    average_profit = mean(historical_profits)
    average_probability = mean(
        historical_probabilities
    )

    score_percentile = _calculate_percentile(
        current_score,
        historical_scores,
    )
    roi_percentile = _calculate_percentile(
        current_roi_value,
        historical_rois,
    )
    profit_percentile = _calculate_percentile(
        current_profit,
        historical_profits,
    )
    success_probability_percentile = (
        _calculate_percentile(
            current_probability,
            historical_probabilities,
        )
    )

    overall_percentile = round(
        mean(
            (
                score_percentile,
                roi_percentile,
                profit_percentile,
                success_probability_percentile,
            )
        ),
        1,
    )

    rank_label = _build_rank_label(
        overall_percentile
    )

    score_difference = round(
        current_score - average_score,
        2,
    )
    roi_difference = round(
        current_roi_value - average_roi,
        2,
    )
    profit_difference = round(
        current_profit - average_profit,
        2,
    )
    probability_difference = round(
        current_probability - average_probability,
        2,
    )

    summary = _build_summary(
        sample_size=len(historical_records),
        overall_percentile=overall_percentile,
        rank_label=rank_label,
        score_difference=score_difference,
        roi_difference=roi_difference,
        profit_difference=profit_difference,
        probability_difference=(
            probability_difference
        ),
    )

    return AIMemoryInsight(
        sample_size=len(historical_records),
        score_percentile=score_percentile,
        roi_percentile=roi_percentile,
        profit_percentile=profit_percentile,
        success_probability_percentile=(
            success_probability_percentile
        ),
        average_score=round(average_score, 2),
        average_roi=round(average_roi, 2),
        average_profit=round(average_profit, 2),
        average_success_probability=round(
            average_probability,
            2,
        ),
        score_difference=score_difference,
        roi_difference=roi_difference,
        profit_difference=profit_difference,
        success_probability_difference=(
            probability_difference
        ),
        overall_percentile=overall_percentile,
        rank_label=rank_label,
        summary=summary,
    )


def _calculate_percentile(
    current_value: float,
    historical_values: tuple[float, ...],
) -> float:
    """
    현재 값이 과거 기록보다 얼마나 높은지
    0~100 백분위로 계산한다.

    동일한 값은 절반만 앞선 것으로 처리해
    동점이 지나치게 높게 평가되는 것을 막는다.
    """
    if not historical_values:
        return 0.0

    lower_count = sum(
        1
        for value in historical_values
        if value < current_value
    )
    equal_count = sum(
        1
        for value in historical_values
        if value == current_value
    )

    percentile = (
        lower_count + equal_count * 0.5
    ) / len(historical_values) * 100

    return round(percentile, 1)


def _build_rank_label(
    overall_percentile: float,
) -> str:
    """
    종합 백분위를 사람이 이해하기 쉬운
    순위 등급으로 변환한다.
    """
    if overall_percentile >= 90:
        return "최상위"

    if overall_percentile >= 75:
        return "상위"

    if overall_percentile >= 50:
        return "평균 이상"

    if overall_percentile >= 25:
        return "평균 이하"

    return "하위"


def _build_summary(
    *,
    sample_size: int,
    overall_percentile: float,
    rank_label: str,
    score_difference: float,
    roi_difference: float,
    profit_difference: float,
    probability_difference: float,
) -> str:
    """
    과거 기록과의 비교 결과를 자연어로 요약한다.
    """
    top_percentage = max(
        0.0,
        round(100 - overall_percentile, 1),
    )

    comparison_parts = [
        (
            f"최근 {sample_size}건의 분석 기록과 "
            f"비교한 결과 종합 {rank_label}에 해당하며, "
            f"상위 약 {top_percentage:.1f}% 수준입니다."
        )
    ]

    comparison_parts.append(
        _format_difference(
            label="기회 점수",
            difference=score_difference,
            suffix="점",
        )
    )
    comparison_parts.append(
        _format_difference(
            label="ROI",
            difference=roi_difference,
            suffix="%p",
        )
    )
    comparison_parts.append(
        _format_difference(
            label="예상 순이익",
            difference=profit_difference,
            suffix="",
        )
    )
    comparison_parts.append(
        _format_difference(
            label="성공 확률",
            difference=probability_difference,
            suffix="%p",
        )
    )

    return " ".join(comparison_parts)


def _format_difference(
    *,
    label: str,
    difference: float,
    suffix: str,
) -> str:
    """
    평균 대비 차이를 자연어 문장으로 변환한다.
    """
    absolute_difference = abs(difference)

    if difference > 0:
        return (
            f"{label}은 과거 평균보다 "
            f"{absolute_difference:.2f}{suffix} 높습니다."
        )

    if difference < 0:
        return (
            f"{label}은 과거 평균보다 "
            f"{absolute_difference:.2f}{suffix} 낮습니다."
        )

    return (
        f"{label}은 과거 평균과 동일합니다."
    )


def _build_empty_insight() -> AIMemoryInsight:
    """
    비교할 과거 기록이 없을 때의 기본 결과를 생성한다.
    """
    return AIMemoryInsight(
        sample_size=0,
        score_percentile=0.0,
        roi_percentile=0.0,
        profit_percentile=0.0,
        success_probability_percentile=0.0,
        average_score=0.0,
        average_roi=0.0,
        average_profit=0.0,
        average_success_probability=0.0,
        score_difference=0.0,
        roi_difference=0.0,
        profit_difference=0.0,
        success_probability_difference=0.0,
        overall_percentile=0.0,
        rank_label="비교 데이터 부족",
        summary=(
            "아직 비교할 과거 분석 기록이 없어 "
            "상대적인 순위를 계산할 수 없습니다."
        ),
    )