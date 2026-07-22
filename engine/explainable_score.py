from __future__ import annotations

from dataclasses import dataclass

from engine.confidence import ConfidenceResult
from engine.price_trend import PriceTrend


@dataclass(slots=True, frozen=True)
class ScoreContribution:
    """
    최종 추천 점수를 구성하는 개별 점수 항목.
    """

    key: str
    label: str
    adjustment: float
    description: str

    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


@dataclass(slots=True, frozen=True)
class ExplainableScoreResult:
    """
    최종 추천 점수와 계산 근거.
    """

    base_score: float
    raw_total: float
    final_score: int

    contributions: tuple[ScoreContribution, ...]
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]


def build_explainable_score(
    *,
    base_score: float,
    roi: float,
    net_profit: float,
    competitor_count: int,
    risk_level: str,
    confidence: ConfidenceResult | None,
    price_trend: PriceTrend | None,
) -> ExplainableScoreResult:
    """
    추천 점수가 어떤 항목으로 구성됐는지 계산한다.

    추천 엔진에서 사용하는 점수와 판단 근거의
    단일 기준점 역할을 한다.
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

    contributions = (
        ScoreContribution(
            key="base_score",
            label="기회 점수",
            adjustment=float(base_score),
            description=(
                "Opportunity Engine에서 계산된 "
                "기본 기회 점수입니다."
            ),
            reasons=(),
            warnings=(),
        ),
        _build_profit_contribution(
            roi=roi,
            net_profit=net_profit,
        ),
        _build_confidence_contribution(
            confidence=confidence,
        ),
        _build_trend_contribution(
            price_trend=price_trend,
        ),
        _build_competition_contribution(
            competitor_count=competitor_count,
        ),
        _build_risk_contribution(
            risk_level=normalized_risk_level,
        ),
    )

    raw_total = sum(
        contribution.adjustment
        for contribution in contributions
    )

    final_score = int(
        round(
            max(
                0.0,
                min(100.0, raw_total),
            )
        )
    )

    reasons = tuple(
        reason
        for contribution in contributions
        for reason in contribution.reasons
    )

    warnings = tuple(
        warning
        for contribution in contributions
        for warning in contribution.warnings
    )

    return ExplainableScoreResult(
        base_score=float(base_score),
        raw_total=float(raw_total),
        final_score=final_score,
        contributions=contributions,
        reasons=reasons,
        warnings=warnings,
    )


def _build_profit_contribution(
    *,
    roi: float,
    net_profit: float,
) -> ScoreContribution:
    if net_profit <= 0:
        message = (
            "현재 계산 기준으로 예상 순이익이 없습니다."
        )

        return ScoreContribution(
            key="profit",
            label="수익성",
            adjustment=-25.0,
            description=message,
            reasons=(),
            warnings=(message,),
        )

    if roi >= 50:
        message = (
            "ROI가 50% 이상으로 매우 높습니다."
        )

        return ScoreContribution(
            key="profit",
            label="수익성",
            adjustment=18.0,
            description=message,
            reasons=(message,),
            warnings=(),
        )

    if roi >= 30:
        message = (
            "ROI가 30% 이상으로 우수합니다."
        )

        return ScoreContribution(
            key="profit",
            label="수익성",
            adjustment=12.0,
            description=message,
            reasons=(message,),
            warnings=(),
        )

    if roi >= 15:
        message = (
            "ROI가 15% 이상으로 검토할 만합니다."
        )

        return ScoreContribution(
            key="profit",
            label="수익성",
            adjustment=6.0,
            description=message,
            reasons=(message,),
            warnings=(),
        )

    if roi > 0:
        message = (
            "수익은 예상되지만 ROI가 낮습니다."
        )

        return ScoreContribution(
            key="profit",
            label="수익성",
            adjustment=-3.0,
            description=message,
            reasons=(),
            warnings=(message,),
        )

    message = "ROI가 0% 이하입니다."

    return ScoreContribution(
        key="profit",
        label="수익성",
        adjustment=-15.0,
        description=message,
        reasons=(),
        warnings=(message,),
    )


def _build_confidence_contribution(
    *,
    confidence: ConfidenceResult | None,
) -> ScoreContribution:
    if confidence is None:
        message = (
            "가격 신뢰도 정보가 없습니다."
        )

        return ScoreContribution(
            key="confidence",
            label="가격 신뢰도",
            adjustment=-5.0,
            description=message,
            reasons=(),
            warnings=(message,),
        )

    if confidence.confidence_score >= 80:
        message = (
            "가격 비교 표본의 신뢰도가 높습니다."
        )

        return ScoreContribution(
            key="confidence",
            label="가격 신뢰도",
            adjustment=10.0,
            description=message,
            reasons=(message,),
            warnings=(),
        )

    if confidence.confidence_score >= 60:
        message = (
            "가격 비교 표본의 신뢰도가 보통입니다."
        )

        return ScoreContribution(
            key="confidence",
            label="가격 신뢰도",
            adjustment=4.0,
            description=message,
            reasons=(message,),
            warnings=(),
        )

    warnings = [
        "가격 표본이 부족해 분석 신뢰도가 낮습니다."
    ]

    if confidence.used_fallback_price:
        warnings.append(
            "권장 판매가에 fallback 가격을 사용했습니다."
        )

    return ScoreContribution(
        key="confidence",
        label="가격 신뢰도",
        adjustment=-10.0,
        description=" ".join(warnings),
        reasons=(),
        warnings=tuple(warnings),
    )


def _build_trend_contribution(
    *,
    price_trend: PriceTrend | None,
) -> ScoreContribution:
    if price_trend is None:
        message = (
            "저장된 가격 추세 데이터가 없습니다."
        )

        return ScoreContribution(
            key="trend",
            label="가격 추세",
            adjustment=0.0,
            description=message,
            reasons=(),
            warnings=(message,),
        )

    if not price_trend.has_sufficient_history:
        message = (
            "가격 추세를 판단하기 위한 이력이 부족합니다."
        )

        return ScoreContribution(
            key="trend",
            label="가격 추세",
            adjustment=0.0,
            description=message,
            reasons=(),
            warnings=(message,),
        )

    price_is_unchanged = (
        price_trend.lowest_price
        == price_trend.highest_price
    )

    if price_is_unchanged:
        message = (
            "저장 기간 동안 가격이 안정적으로 유지됐습니다."
        )

        return ScoreContribution(
            key="trend",
            label="가격 추세",
            adjustment=1.0,
            description=message,
            reasons=(message,),
            warnings=(),
        )

    adjustment = 0.0

    reasons: list[str] = []
    warnings: list[str] = []

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

    descriptions = reasons + warnings

    if descriptions:
        description = " ".join(descriptions)
    else:
        description = (
            "현재 가격 추세에 따른 "
            "추가 점수 변화가 없습니다."
        )

    return ScoreContribution(
        key="trend",
        label="가격 추세",
        adjustment=adjustment,
        description=description,
        reasons=tuple(reasons),
        warnings=tuple(warnings),
    )


def _build_competition_contribution(
    *,
    competitor_count: int,
) -> ScoreContribution:
    if competitor_count <= 5:
        message = (
            "경쟁 상품 수가 매우 적습니다."
        )

        return ScoreContribution(
            key="competition",
            label="경쟁도",
            adjustment=8.0,
            description=message,
            reasons=(message,),
            warnings=(),
        )

    if competitor_count <= 15:
        message = (
            "경쟁 상품 수가 비교적 적습니다."
        )

        return ScoreContribution(
            key="competition",
            label="경쟁도",
            adjustment=4.0,
            description=message,
            reasons=(message,),
            warnings=(),
        )

    if competitor_count <= 40:
        return ScoreContribution(
            key="competition",
            label="경쟁도",
            adjustment=0.0,
            description=(
                "경쟁 상품 수가 보통 수준입니다."
            ),
            reasons=(),
            warnings=(),
        )

    if competitor_count <= 70:
        message = (
            "경쟁 상품 수가 많습니다."
        )

        return ScoreContribution(
            key="competition",
            label="경쟁도",
            adjustment=-5.0,
            description=message,
            reasons=(),
            warnings=(message,),
        )

    message = (
        "경쟁 상품 수가 매우 많습니다."
    )

    return ScoreContribution(
        key="competition",
        label="경쟁도",
        adjustment=-10.0,
        description=message,
        reasons=(),
        warnings=(message,),
    )


def _build_risk_contribution(
    *,
    risk_level: str,
) -> ScoreContribution:
    if risk_level == "low":
        message = (
            "위험도가 낮게 평가됐습니다."
        )

        return ScoreContribution(
            key="risk",
            label="위험도",
            adjustment=5.0,
            description=message,
            reasons=(message,),
            warnings=(),
        )

    if risk_level == "medium":
        return ScoreContribution(
            key="risk",
            label="위험도",
            adjustment=0.0,
            description=(
                "위험도가 보통 수준으로 평가됐습니다."
            ),
            reasons=(),
            warnings=(),
        )

    message = (
        "위험도가 높게 평가됐습니다."
    )

    return ScoreContribution(
        key="risk",
        label="위험도",
        adjustment=-10.0,
        description=message,
        reasons=(),
        warnings=(message,),
    )