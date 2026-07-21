from __future__ import annotations

from dataclasses import dataclass

from engine.price_trend import PriceTrend


@dataclass(slots=True, frozen=True)
class TrendScoreResult:
    """
    가격 추세가 기회 점수에 미치는 보정 결과.
    """

    adjustment: float
    reasons: tuple[str, ...]


def calculate_trend_score(
    trend: PriceTrend | None,
) -> TrendScoreResult:
    """
    가격 추세 분석 결과를 기회 점수 보정값으로 변환한다.

    보정 기준:
        가격 이력 부족:
            0점

        기간 최저가:
            +10점

        평균보다 저렴:
            +7점

        하락 추세:
            +3점

        기간 최고가:
            -10점

        상승 추세:
            -5점

    저장 기간 동안 가격이 모두 같으면
    추세 점수를 보정하지 않는다.
    """
    if trend is None:
        return TrendScoreResult(
            adjustment=0.0,
            reasons=(
                "저장된 가격 추세 정보가 없습니다.",
            ),
        )

    if not trend.has_sufficient_history:
        return TrendScoreResult(
            adjustment=0.0,
            reasons=(
                "가격 이력이 부족하여 "
                "추세 점수를 적용하지 않았습니다.",
            ),
        )

    price_is_unchanged = (
        trend.lowest_price
        == trend.highest_price
    )

    if price_is_unchanged:
        return TrendScoreResult(
            adjustment=0.0,
            reasons=(
                "저장 기간 동안 가격이 동일하여 "
                "추세 점수를 보정하지 않았습니다.",
            ),
        )

    adjustment = 0.0
    reasons: list[str] = []

    if trend.price_position == "기간 최저가":
        adjustment += 10.0
        reasons.append(
            "현재 가격이 저장 기간의 최저가여서 "
            "10점을 가산했습니다."
        )

    elif trend.price_position == "평균보다 저렴":
        adjustment += 7.0
        reasons.append(
            "현재 가격이 기간 평균보다 저렴하여 "
            "7점을 가산했습니다."
        )

    if trend.trend_direction == "하락":
        adjustment += 3.0
        reasons.append(
            "가격이 하락 추세여서 "
            "3점을 가산했습니다."
        )

    if trend.price_position == "기간 최고가":
        adjustment -= 10.0
        reasons.append(
            "현재 가격이 저장 기간의 최고가여서 "
            "10점을 감점했습니다."
        )

    if trend.trend_direction == "상승":
        adjustment -= 5.0
        reasons.append(
            "가격이 상승 추세여서 "
            "5점을 감점했습니다."
        )

    if not reasons:
        reasons.append(
            "현재 가격 추세에 따른 "
            "점수 보정이 없습니다."
        )

    return TrendScoreResult(
        adjustment=round(adjustment, 2),
        reasons=tuple(reasons),
    )