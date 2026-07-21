from __future__ import annotations

from dataclasses import dataclass

from engine.confidence import ConfidenceResult
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
    기회 점수, ROI, 순이익, 경쟁도, 위험도,
    가격 신뢰도와 가격 추세를 종합해
    최종 추천 결과를 생성한다.

    같은 입력에는 항상 같은 결과가 반환되는
    규칙 기반 추천 엔진이다.
    """
    if competitor_count < 0:
        raise ValueError(
            "competitor_count는 0 이상이어야 합니다."
        )

    normalized_risk_level = risk_level.strip().lower()

    if normalized_risk_level not in {
        "low",
        "medium",
        "high",
    }:
        raise ValueError(
            "risk_level은 low, medium, high 중 "
            "하나여야 합니다."
        )

    score = float(final_opportunity_score)

    reasons: list[str] = []
    warnings: list[str] = []

    score += _apply_profit_score(
        roi=roi,
        net_profit=net_profit,
        reasons=reasons,
        warnings=warnings,
    )

    score += _apply_confidence_score(
        confidence=confidence,
        reasons=reasons,
        warnings=warnings,
    )

    score += _apply_trend_score(
        price_trend=price_trend,
        reasons=reasons,
        warnings=warnings,
    )

    score += _apply_competition_score(
        competitor_count=competitor_count,
        reasons=reasons,
        warnings=warnings,
    )

    score += _apply_risk_score(
        risk_level=normalized_risk_level,
        reasons=reasons,
        warnings=warnings,
    )

    normalized_score = int(
        round(
            max(
                0.0,
                min(100.0, score),
            )
        )
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
        success_probability=(
            success_probability
        ),
        reasons=tuple(reasons),
        warnings=tuple(warnings),
        summary=summary,
    )


def _apply_profit_score(
    *,
    roi: float,
    net_profit: float,
    reasons: list[str],
    warnings: list[str],
) -> float:
    if net_profit <= 0:
        warnings.append(
            "현재 계산 기준으로 예상 순이익이 없습니다."
        )
        return -25.0

    if roi >= 50:
        reasons.append(
            "ROI가 50% 이상으로 매우 높습니다."
        )
        return 18.0

    if roi >= 30:
        reasons.append(
            "ROI가 30% 이상으로 우수합니다."
        )
        return 12.0

    if roi >= 15:
        reasons.append(
            "ROI가 15% 이상으로 검토할 만합니다."
        )
        return 6.0

    if roi > 0:
        warnings.append(
            "수익은 예상되지만 ROI가 낮습니다."
        )
        return -3.0

    warnings.append(
        "ROI가 0% 이하입니다."
    )
    return -15.0


def _apply_confidence_score(
    *,
    confidence: ConfidenceResult | None,
    reasons: list[str],
    warnings: list[str],
) -> float:
    if confidence is None:
        warnings.append(
            "가격 신뢰도 정보가 없습니다."
        )
        return -5.0

    if confidence.confidence_score >= 80:
        reasons.append(
            "가격 비교 표본의 신뢰도가 높습니다."
        )
        return 10.0

    if confidence.confidence_score >= 60:
        reasons.append(
            "가격 비교 표본의 신뢰도가 보통입니다."
        )
        return 4.0

    warnings.append(
        "가격 표본이 부족해 분석 신뢰도가 낮습니다."
    )

    if confidence.used_fallback_price:
        warnings.append(
            "권장 판매가에 fallback 가격을 사용했습니다."
        )

    return -10.0


def _apply_trend_score(
    *,
    price_trend: PriceTrend | None,
    reasons: list[str],
    warnings: list[str],
) -> float:
    if price_trend is None:
        warnings.append(
            "저장된 가격 추세 데이터가 없습니다."
        )
        return 0.0

    if not price_trend.has_sufficient_history:
        warnings.append(
            "가격 추세를 판단하기 위한 이력이 부족합니다."
        )
        return 0.0

    price_is_unchanged = (
        price_trend.lowest_price
        == price_trend.highest_price
    )

    if price_is_unchanged:
        reasons.append(
            "저장 기간 동안 가격이 안정적으로 유지됐습니다."
        )
        return 1.0

    adjustment = 0.0

    if price_trend.price_position == "기간 최저가":
        reasons.append(
            "현재 가격이 저장 기간의 최저가입니다."
        )
        adjustment += 8.0

    elif price_trend.price_position == "평균보다 저렴":
        reasons.append(
            "현재 가격이 기간 평균보다 저렴합니다."
        )
        adjustment += 5.0

    elif price_trend.price_position == "기간 최고가":
        warnings.append(
            "현재 가격이 저장 기간의 최고가입니다."
        )
        adjustment -= 8.0

    if price_trend.trend_direction == "하락":
        reasons.append(
            "가격이 하락 추세입니다."
        )
        adjustment += 3.0

    elif price_trend.trend_direction == "상승":
        warnings.append(
            "가격이 상승 추세입니다."
        )
        adjustment -= 5.0

    return adjustment


def _apply_competition_score(
    *,
    competitor_count: int,
    reasons: list[str],
    warnings: list[str],
) -> float:
    if competitor_count <= 5:
        reasons.append(
            "경쟁 상품 수가 매우 적습니다."
        )
        return 8.0

    if competitor_count <= 15:
        reasons.append(
            "경쟁 상품 수가 비교적 적습니다."
        )
        return 4.0

    if competitor_count <= 40:
        return 0.0

    if competitor_count <= 70:
        warnings.append(
            "경쟁 상품 수가 많습니다."
        )
        return -5.0

    warnings.append(
        "경쟁 상품 수가 매우 많습니다."
    )
    return -10.0


def _apply_risk_score(
    *,
    risk_level: str,
    reasons: list[str],
    warnings: list[str],
) -> float:
    if risk_level == "low":
        reasons.append(
            "위험도가 낮게 평가됐습니다."
        )
        return 5.0

    if risk_level == "medium":
        return 0.0

    warnings.append(
        "위험도가 높게 평가됐습니다."
    )
    return -10.0


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