from __future__ import annotations

from dataclasses import dataclass

from engine.confidence import ConfidenceResult
from engine.explainable_score import (
    build_explainable_score,
)
from engine.price_trend import PriceTrend


@dataclass(slots=True, frozen=True)
class RecommendationResult:
    """
    모든 분석 결과를 종합한 최종 추천 결과.
    """

    score: int
    stars: int
    star_display: str

    grade: str
    action: str

    success_probability: int

    reasons: tuple[str, ...]
    warnings: tuple[str, ...]

    summary: str


def generate_recommendation(
    *,
    final_opportunity_score: float,
    roi: float,
    net_profit: float,
    competitor_count: int,
    risk_level: str,
    confidence: ConfidenceResult | None,
    price_trend: PriceTrend | None,
) -> RecommendationResult:
    """
    Explainable Score 결과를 기반으로
    최종 추천 등급과 행동 지침을 생성한다.

    점수 계산 규칙은 explainable_score 모듈에서
    단일하게 관리한다.
    """

    explainable_score = build_explainable_score(
        base_score=final_opportunity_score,
        roi=roi,
        net_profit=net_profit,
        competitor_count=competitor_count,
        risk_level=risk_level,
        confidence=confidence,
        price_trend=price_trend,
    )

    normalized_score = explainable_score.final_score

    reasons = list(
        explainable_score.reasons
    )

    warnings = list(
        explainable_score.warnings
    )

    stars = _score_to_stars(
        normalized_score
    )

    grade, action = _score_to_grade(
        normalized_score
    )

    success_probability = _estimate_success_probability(
        score=normalized_score,
        confidence=confidence,
        net_profit=net_profit,
    )

    star_display = (
        "★" * stars
        + "☆" * (5 - stars)
    )

    if not reasons:
        reasons.append(
            "현재 조건에서 뚜렷한 긍정 요소가 없습니다."
        )

    summary = _build_summary(
        action=action,
        score=normalized_score,
        reasons=reasons,
        warnings=warnings,
    )

    return RecommendationResult(
        score=normalized_score,
        stars=stars,
        star_display=star_display,
        grade=grade,
        action=action,
        success_probability=success_probability,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
        summary=summary,
    )


def _score_to_stars(
    score: int,
) -> int:
    if score >= 80:
        return 5

    if score >= 65:
        return 4

    if score >= 45:
        return 3

    if score >= 25:
        return 2

    return 1


def _score_to_grade(
    score: int,
) -> tuple[str, str]:
    if score >= 80:
        return (
            "STRONG_BUY",
            "강력 매입 추천",
        )

    if score >= 65:
        return (
            "BUY",
            "매입 추천",
        )

    if score >= 45:
        return (
            "WATCH",
            "추가 검토",
        )

    if score >= 25:
        return (
            "CAUTION",
            "주의",
        )

    return (
        "AVOID",
        "매입 비추천",
    )


def _estimate_success_probability(
    *,
    score: int,
    confidence: ConfidenceResult | None,
    net_profit: float,
) -> int:
    probability = float(score)

    if confidence is None:
        probability *= 0.75
    else:
        confidence_factor = (
            0.5
            + (
                confidence.confidence_score
                / 200
            )
        )

        probability *= confidence_factor

    if net_profit <= 0:
        probability *= 0.6

    return int(
        round(
            max(
                1.0,
                min(95.0, probability),
            )
        )
    )


def _build_summary(
    *,
    action: str,
    score: int,
    reasons: list[str],
    warnings: list[str],
) -> str:
    if reasons:
        main_reason = reasons[0]
    else:
        main_reason = (
            "명확한 긍정 요인이 확인되지 않았습니다."
        )

    if warnings:
        main_warning = warnings[0]

        return (
            f"{action}입니다. "
            f"추천 점수는 {score}점입니다. "
            f"{main_reason} "
            f"다만 {main_warning}"
        )

    return (
        f"{action}입니다. "
        f"추천 점수는 {score}점입니다. "
        f"{main_reason}"
    )