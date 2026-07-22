from __future__ import annotations

from dataclasses import dataclass

from engine.confidence import ConfidenceResult
from engine.price_trend import PriceTrend


@dataclass(slots=True, frozen=True)
class MarketAnalysisResult:
    """
    현재 시장 상황을 사람이 이해하기 쉬운 형태로 정리한 결과.
    """

    market_condition: str
    entry_difficulty: str
    buy_timing: str

    insights: tuple[str, ...]
    risks: tuple[str, ...]

    summary: str


def analyze_market(
    *,
    competitor_count: int,
    confidence: ConfidenceResult | None,
    price_trend: PriceTrend | None,
) -> MarketAnalysisResult:
    """
    경쟁도, 가격 신뢰도, 가격 추세를 바탕으로
    시장 상황과 매입 시점을 분석한다.
    """

    if competitor_count < 0:
        raise ValueError(
            "competitor_count는 0 이상이어야 합니다."
        )

    insights: list[str] = []
    risks: list[str] = []

    competition_score = _analyze_competition(
        competitor_count=competitor_count,
        insights=insights,
        risks=risks,
    )

    confidence_score = _analyze_confidence(
        confidence=confidence,
        insights=insights,
        risks=risks,
    )

    trend_score, buy_timing = _analyze_price_trend(
        price_trend=price_trend,
        insights=insights,
        risks=risks,
    )

    market_condition = _determine_market_condition(
        competition_score=competition_score,
        confidence_score=confidence_score,
        trend_score=trend_score,
        confidence=confidence,
        price_trend=price_trend,
    )

    entry_difficulty = _determine_entry_difficulty(
        competitor_count=competitor_count,
    )

    summary = _build_summary(
        market_condition=market_condition,
        entry_difficulty=entry_difficulty,
        buy_timing=buy_timing,
    )

    return MarketAnalysisResult(
        market_condition=market_condition,
        entry_difficulty=entry_difficulty,
        buy_timing=buy_timing,
        insights=tuple(insights),
        risks=tuple(risks),
        summary=summary,
    )


def _analyze_competition(
    *,
    competitor_count: int,
    insights: list[str],
    risks: list[str],
) -> int:
    if competitor_count <= 5:
        insights.append(
            "경쟁 상품 수가 매우 적습니다."
        )
        return 2

    if competitor_count <= 15:
        insights.append(
            "경쟁 상품 수가 비교적 적습니다."
        )
        return 1

    if competitor_count <= 40:
        return 0

    if competitor_count <= 70:
        risks.append(
            "경쟁 상품 수가 많습니다."
        )
        return -1

    risks.append(
        "경쟁 상품 수가 매우 많습니다."
    )
    return -2


def _analyze_confidence(
    *,
    confidence: ConfidenceResult | None,
    insights: list[str],
    risks: list[str],
) -> int:
    if confidence is None:
        risks.append(
            "가격 신뢰도 정보가 없습니다."
        )
        return -2

    if confidence.confidence_score >= 80:
        insights.append(
            "가격 비교 표본의 신뢰도가 높습니다."
        )
        return 2

    if confidence.confidence_score >= 60:
        insights.append(
            "가격 비교 표본의 신뢰도가 보통입니다."
        )
        return 1

    risks.append(
        "가격 표본이 부족해 분석 신뢰도가 낮습니다."
    )

    if confidence.used_fallback_price:
        risks.append(
            "권장 판매가에 fallback 가격을 사용했습니다."
        )

    return -2


def _analyze_price_trend(
    *,
    price_trend: PriceTrend | None,
    insights: list[str],
    risks: list[str],
) -> tuple[int, str]:
    if price_trend is None:
        risks.append(
            "저장된 가격 추세 데이터가 없습니다."
        )
        return -2, "판단 보류"

    if not price_trend.has_sufficient_history:
        risks.append(
            "가격 추세를 판단하기 위한 이력이 부족합니다."
        )
        return -1, "판단 보류"

    price_is_unchanged = (
        price_trend.lowest_price
        == price_trend.highest_price
    )

    if price_is_unchanged:
        insights.append(
            "저장 기간 동안 가격이 안정적으로 유지됐습니다."
        )
        return 1, "보통"

    trend_score = 0

    if price_trend.price_position == "기간 최저가":
        insights.append(
            "현재 가격이 저장 기간의 최저가입니다."
        )
        trend_score += 2

    elif price_trend.price_position == "평균보다 저렴":
        insights.append(
            "현재 가격이 기간 평균보다 저렴합니다."
        )
        trend_score += 1

    elif price_trend.price_position == "기간 최고가":
        risks.append(
            "현재 가격이 저장 기간의 최고가입니다."
        )
        trend_score -= 2

    if price_trend.trend_direction == "하락":
        insights.append(
            "가격이 하락 추세입니다."
        )
        trend_score += 1

    elif price_trend.trend_direction == "상승":
        risks.append(
            "가격이 상승 추세입니다."
        )
        trend_score -= 1

    if trend_score >= 2:
        buy_timing = "좋음"
    elif trend_score <= -2:
        buy_timing = "나쁨"
    else:
        buy_timing = "보통"

    return trend_score, buy_timing


def _determine_market_condition(
    *,
    competition_score: int,
    confidence_score: int,
    trend_score: int,
    confidence: ConfidenceResult | None,
    price_trend: PriceTrend | None,
) -> str:
    if confidence is None or price_trend is None:
        return "판단 보류"

    if not price_trend.has_sufficient_history:
        return "판단 보류"

    total_score = (
        competition_score
        + confidence_score
        + trend_score
    )

    if total_score >= 3:
        return "유리"

    if total_score <= -3:
        return "불리"

    return "보통"


def _determine_entry_difficulty(
    *,
    competitor_count: int,
) -> str:
    if competitor_count <= 15:
        return "낮음"

    if competitor_count <= 40:
        return "보통"

    return "높음"


def _build_summary(
    *,
    market_condition: str,
    entry_difficulty: str,
    buy_timing: str,
) -> str:
    return (
        f"시장 상황은 {market_condition}합니다. "
        f"시장 진입 난이도는 {entry_difficulty}입니다. "
        f"현재 매입 시점은 {buy_timing}으로 평가됩니다."
    )