from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.domain.trend import (
    PriceTrendAnalysis,
    PriceVolatility,
    TrendDirection,
)


class OpportunityTrendLevel(StrEnum):
    """가격 추세를 투자 검토 관점으로 해석한 등급."""

    STRONG_BUY_TREND = "strong_buy_trend"
    FAVORABLE_TREND = "favorable_trend"
    STABLE_OPPORTUNITY = "stable_opportunity"
    WATCH = "watch"
    HIGH_RISK_TREND = "high_risk_trend"


@dataclass(frozen=True, slots=True)
class OpportunityTrendAssessment:
    """가격 추세 분석 결과에 비즈니스 의미를 부여한 불변 결과."""

    level: OpportunityTrendLevel
    summary: str
    recommended_action: str
    favorable: bool
    requires_caution: bool

    def __post_init__(self) -> None:
        if not isinstance(self.level, OpportunityTrendLevel):
            raise TypeError("level은 OpportunityTrendLevel이어야 합니다.")

        for field_name in ("summary", "recommended_action"):
            value = getattr(self, field_name)
            if not isinstance(value, str):
                raise TypeError(f"{field_name}은 문자열이어야 합니다.")
            if not value.strip():
                raise ValueError(f"{field_name}은 비어 있을 수 없습니다.")

        if not isinstance(self.favorable, bool):
            raise TypeError("favorable은 bool이어야 합니다.")
        if not isinstance(self.requires_caution, bool):
            raise TypeError("requires_caution은 bool이어야 합니다.")

        if self.favorable and self.requires_caution:
            raise ValueError(
                "favorable과 requires_caution은 동시에 True일 수 없습니다."
            )


@dataclass(frozen=True, slots=True)
class OpportunityTrendPolicy:
    """가격 추세를 투자 의미로 해석할 때 사용하는 최소 표본 정책."""

    minimum_sample_count: int = 2

    def __post_init__(self) -> None:
        if not isinstance(self.minimum_sample_count, int):
            raise TypeError("minimum_sample_count는 int여야 합니다.")
        if isinstance(self.minimum_sample_count, bool):
            raise TypeError("minimum_sample_count는 bool일 수 없습니다.")
        if self.minimum_sample_count < 2:
            raise ValueError("minimum_sample_count는 2 이상이어야 합니다.")


class OpportunityTrendInterpreter:
    """PriceTrendAnalysis를 투자 검토용 Opportunity Trend로 해석한다."""

    def __init__(
        self,
        policy: OpportunityTrendPolicy | None = None,
    ) -> None:
        self._policy = policy or OpportunityTrendPolicy()

    def interpret(
        self,
        analysis: PriceTrendAnalysis,
    ) -> OpportunityTrendAssessment:
        if not isinstance(analysis, PriceTrendAnalysis):
            raise TypeError("analysis는 PriceTrendAnalysis여야 합니다.")

        if analysis.sample_count < self._policy.minimum_sample_count:
            return OpportunityTrendAssessment(
                level=OpportunityTrendLevel.WATCH,
                summary="추세를 판단하기에는 가격 이력 표본이 부족합니다.",
                recommended_action="추가 가격 관측 후 다시 평가하세요.",
                favorable=False,
                requires_caution=True,
            )

        if analysis.direction is TrendDirection.DOWN:
            return self._interpret_downtrend(analysis)

        if analysis.direction is TrendDirection.UP:
            return self._interpret_uptrend(analysis)

        return self._interpret_stable_trend(analysis)

    @staticmethod
    def _interpret_downtrend(
        analysis: PriceTrendAnalysis,
    ) -> OpportunityTrendAssessment:
        if (
            analysis.volatility is PriceVolatility.HIGH
            or analysis.near_highest
        ):
            return OpportunityTrendAssessment(
                level=OpportunityTrendLevel.HIGH_RISK_TREND,
                summary=(
                    "가격이 하락 중이며 변동성 또는 현재 가격 위치가 "
                    "매입 위험을 높이고 있습니다."
                ),
                recommended_action="가격 안정과 추가 하락 여부를 확인하기 전 매입을 보류하세요.",
                favorable=False,
                requires_caution=True,
            )

        return OpportunityTrendAssessment(
            level=OpportunityTrendLevel.WATCH,
            summary="가격이 하락 추세이므로 현재 가격만으로 기회를 확정하기 어렵습니다.",
            recommended_action="하락세가 멈추고 가격이 안정되는지 관찰하세요.",
            favorable=False,
            requires_caution=True,
        )

    @staticmethod
    def _interpret_uptrend(
        analysis: PriceTrendAnalysis,
    ) -> OpportunityTrendAssessment:
        if (
            analysis.volatility is PriceVolatility.LOW
            and analysis.near_lowest
        ):
            return OpportunityTrendAssessment(
                level=OpportunityTrendLevel.STRONG_BUY_TREND,
                summary="낮은 변동성의 상승 추세이며 현재 가격도 저점 부근입니다.",
                recommended_action="다른 수익성과 위험 지표가 양호하면 우선 매입 후보로 검토하세요.",
                favorable=True,
                requires_caution=False,
            )

        if analysis.volatility is PriceVolatility.HIGH:
            return OpportunityTrendAssessment(
                level=OpportunityTrendLevel.WATCH,
                summary="가격은 상승 중이지만 변동성이 높아 추세 지속성을 확신하기 어렵습니다.",
                recommended_action="급등 추격을 피하고 가격 변동이 완화되는지 확인하세요.",
                favorable=False,
                requires_caution=True,
            )

        return OpportunityTrendAssessment(
            level=OpportunityTrendLevel.FAVORABLE_TREND,
            summary="가격이 상승 추세를 보이며 변동성도 감내 가능한 범위입니다.",
            recommended_action="수익성과 신뢰도 지표를 함께 확인해 매입 여부를 결정하세요.",
            favorable=True,
            requires_caution=False,
        )

    @staticmethod
    def _interpret_stable_trend(
        analysis: PriceTrendAnalysis,
    ) -> OpportunityTrendAssessment:
        if analysis.price_range == 0:
            return OpportunityTrendAssessment(
                level=OpportunityTrendLevel.STABLE_OPPORTUNITY,
                summary="관측 기간 동안 가격이 일정하게 유지되었습니다.",
                recommended_action="안정적인 기준 가격으로 활용하되 거래량과 수익성을 함께 확인하세요.",
                favorable=True,
                requires_caution=False,
            )

        if (
            analysis.volatility is PriceVolatility.HIGH
            or analysis.near_highest
        ):
            return OpportunityTrendAssessment(
                level=OpportunityTrendLevel.WATCH,
                summary="전체 방향은 안정적이지만 변동성 또는 고점 근접 신호가 있습니다.",
                recommended_action="현재 가격이 일시적 고점인지 추가 관측으로 확인하세요.",
                favorable=False,
                requires_caution=True,
            )

        return OpportunityTrendAssessment(
            level=OpportunityTrendLevel.STABLE_OPPORTUNITY,
            summary="가격 방향과 변동성이 비교적 안정적입니다.",
            recommended_action="가격 안정성을 기준으로 수익성과 판매 가능성을 추가 검토하세요.",
            favorable=True,
            requires_caution=False,
        )
