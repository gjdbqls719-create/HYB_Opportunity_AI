from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping

from app.application.opportunity_intelligence import (
    OpportunityIntelligenceInput,
)
from app.domain.discovery import DiscoveryResult
from app.domain.opportunity import OpportunityFactors


_FACTOR_NAMES = (
    "price_score",
    "trend_score",
    "demand_score",
    "competition_score",
    "risk_score",
)

_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class DiscoveryFactorPolicy:
    """기존 Discovery 분석값을 0~100 Factor 점수로 정규화하는 정책."""

    low_risk_score: Decimal = Decimal("90")
    medium_risk_score: Decimal = Decimal("50")
    high_risk_score: Decimal = Decimal("10")

    def __post_init__(self) -> None:
        for field_name in (
            "low_risk_score",
            "medium_risk_score",
            "high_risk_score",
        ):
            value = getattr(self, field_name)
            _validate_normalized_score(field_name, value)

        if not (
            self.low_risk_score
            > self.medium_risk_score
            > self.high_risk_score
        ):
            raise ValueError(
                "위험 안전성 점수는 low > medium > high 순이어야 합니다."
            )

    def profitability_score(self, *, roi: Decimal) -> Decimal:
        """검증된 수익성 지표를 가격 Factor 점수로 정규화한다.

        현재 계약은 기존 동작과의 완전한 호환성을 위해 ROI만 사용한다.
        키워드 전용 인자를 사용해 향후 ``margin_rate`` 또는
        ``landed_cost_roi`` 같은 검증된 지표를 명시적으로 확장할 수 있는
        진입점을 제공한다.
        """
        if not isinstance(roi, Decimal):
            raise TypeError("roi는 Decimal이어야 합니다.")
        if not roi.is_finite():
            raise ValueError("roi는 유한한 값이어야 합니다.")

        return _piecewise_score(
            roi,
            (
                (Decimal("0"), Decimal("0")),
                (Decimal("15"), Decimal("40")),
                (Decimal("30"), Decimal("60")),
                (Decimal("50"), Decimal("80")),
                (Decimal("100"), Decimal("100")),
            ),
        )

    def price_score(self, roi: Decimal) -> Decimal:
        """기존 호출자를 위한 하위 호환 진입점."""
        return self.profitability_score(roi=roi)

    def trend_score(self, adjustment: Decimal) -> Decimal:
        return _piecewise_score(
            adjustment,
            (
                (Decimal("-18"), Decimal("0")),
                (Decimal("0"), Decimal("50")),
                (Decimal("15"), Decimal("100")),
            ),
        )

    def demand_score(self, monthly_sales: Decimal) -> Decimal:
        return _piecewise_score(
            monthly_sales,
            (
                (Decimal("0"), Decimal("0")),
                (Decimal("50"), Decimal("40")),
                (Decimal("200"), Decimal("70")),
                (Decimal("500"), Decimal("100")),
            ),
        )

    def competition_score(self, competitor_count: Decimal) -> Decimal:
        return _piecewise_score(
            competitor_count,
            (
                (Decimal("0"), Decimal("100")),
                (Decimal("5"), Decimal("90")),
                (Decimal("20"), Decimal("60")),
                (Decimal("50"), Decimal("30")),
                (Decimal("100"), Decimal("0")),
            ),
        )

    def risk_score(self, risk_level: str) -> Decimal:
        normalized = risk_level.strip().lower()
        if normalized == "low":
            return self.low_risk_score
        if normalized == "medium":
            return self.medium_risk_score
        if normalized == "high":
            return self.high_risk_score
        raise ValueError("risk_level은 low, medium, high 중 하나여야 합니다.")


class DiscoveryResultOpportunityIntelligenceAdapter:
    """DiscoveryResult의 검증된 분석값을 Opportunity 입력으로 변환한다."""

    def __init__(
        self,
        *,
        factor_policy: DiscoveryFactorPolicy | None = None,
    ) -> None:
        self._factor_policy = factor_policy or DiscoveryFactorPolicy()

    def adapt(
        self,
        discovery_result: DiscoveryResult,
    ) -> OpportunityIntelligenceInput:
        if not isinstance(discovery_result, DiscoveryResult):
            raise TypeError("discovery_result는 DiscoveryResult여야 합니다.")

        confidence = self._parse_decimal(
            discovery_result.metadata.get("confidence_score"),
            "confidence_score",
            minimum=_ZERO,
            maximum=_HUNDRED,
        )
        factors, missing_factors = self._build_factors(discovery_result.metadata)

        return OpportunityIntelligenceInput(
            factors=factors,
            confidence=confidence,
            missing_factors=missing_factors,
        )

    def _build_factors(
        self,
        metadata: Mapping[str, object],
    ) -> tuple[OpportunityFactors | None, tuple[str, ...]]:
        analysis_value = metadata.get("analysis")
        analysis = (
            analysis_value
            if isinstance(analysis_value, Mapping)
            else None
        )

        source_values: dict[str, object | None] = {
            "price_score": analysis.get("roi") if analysis is not None else None,
            "trend_score": metadata.get("trend_score_adjustment"),
            "demand_score": (
                analysis.get("estimated_monthly_sales")
                if analysis is not None
                else None
            ),
            "competition_score": (
                analysis.get("competitor_count")
                if analysis is not None
                else None
            ),
            "risk_score": analysis.get("risk_level") if analysis is not None else None,
        }
        missing_factors = tuple(
            name for name in _FACTOR_NAMES if source_values[name] is None
        )
        if missing_factors:
            return None, missing_factors

        roi = self._parse_decimal(
            source_values["price_score"],
            "analysis.roi",
        )
        trend_adjustment = self._parse_decimal(
            source_values["trend_score"],
            "trend_score_adjustment",
        )
        monthly_sales = self._parse_decimal(
            source_values["demand_score"],
            "analysis.estimated_monthly_sales",
            minimum=_ZERO,
        )
        competitor_count = self._parse_decimal(
            source_values["competition_score"],
            "analysis.competitor_count",
            minimum=_ZERO,
        )
        risk_level = source_values["risk_score"]
        if not isinstance(risk_level, str):
            raise TypeError("analysis.risk_level은 문자열이어야 합니다.")

        assert roi is not None
        assert trend_adjustment is not None
        assert monthly_sales is not None
        assert competitor_count is not None

        return (
            OpportunityFactors(
                price_score=self._factor_policy.profitability_score(roi=roi),
                trend_score=self._factor_policy.trend_score(trend_adjustment),
                demand_score=self._factor_policy.demand_score(monthly_sales),
                competition_score=self._factor_policy.competition_score(
                    competitor_count
                ),
                risk_score=self._factor_policy.risk_score(risk_level),
            ),
            (),
        )

    @staticmethod
    def _parse_decimal(
        value: object,
        field_name: str,
        *,
        minimum: Decimal | None = None,
        maximum: Decimal | None = None,
    ) -> Decimal | None:
        if value is None:
            return None

        if isinstance(value, bool):
            raise TypeError(f"{field_name}는 bool일 수 없습니다.")

        if isinstance(value, Decimal):
            parsed = value
        elif isinstance(value, (int, float, str)):
            try:
                parsed = Decimal(str(value).strip())
            except (InvalidOperation, ValueError) as error:
                raise ValueError(
                    f"{field_name}을 Decimal로 변환할 수 없습니다."
                ) from error
        else:
            raise TypeError(
                f"{field_name}은 Decimal로 변환 가능한 값이어야 합니다."
            )

        if not parsed.is_finite():
            raise ValueError(f"{field_name}은 유한한 값이어야 합니다.")
        if (
            minimum is not None
            and maximum is not None
            and not minimum <= parsed <= maximum
        ):
            raise ValueError(
                f"{field_name}은 {minimum} 이상 {maximum} 이하여야 합니다."
            )
        if minimum is not None and parsed < minimum:
            raise ValueError(f"{field_name}은 {minimum} 이상이어야 합니다.")
        if maximum is not None and parsed > maximum:
            raise ValueError(f"{field_name}은 {maximum} 이하여야 합니다.")

        return parsed


def _piecewise_score(
    value: Decimal,
    points: tuple[tuple[Decimal, Decimal], ...],
) -> Decimal:
    if value <= points[0][0]:
        return points[0][1]
    if value >= points[-1][0]:
        return points[-1][1]

    for (left_x, left_y), (right_x, right_y) in zip(points, points[1:]):
        if left_x <= value <= right_x:
            ratio = (value - left_x) / (right_x - left_x)
            score = left_y + ((right_y - left_y) * ratio)
            return score.quantize(Decimal("0.01"))

    raise RuntimeError("정규화 구간을 결정할 수 없습니다.")


def _validate_normalized_score(field_name: str, value: object) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name}는 Decimal이어야 합니다.")
    if not value.is_finite():
        raise ValueError(f"{field_name}는 유한한 값이어야 합니다.")
    if not _ZERO <= value <= _HUNDRED:
        raise ValueError(f"{field_name}는 0 이상 100 이하여야 합니다.")
