from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum


_SCORE_QUANTUM = Decimal("0.01")
_RATE_QUANTUM = Decimal("0.0001")
_PERCENT_QUANTUM = Decimal("0.01")
_ZERO = Decimal("0")
_HUNDRED = Decimal("100")


class RoiGrade(str, Enum):
    """ROI 분석 결과의 안정적인 외부 표현 값."""

    A = "A"
    B = "B"
    C = "C"
    D = "D"
    F = "F"


@dataclass(frozen=True, slots=True)
class RoiIntelligencePolicy:
    """ROI 비율을 점수와 등급으로 변환하는 정책."""

    minimum_viable_rate: Decimal = Decimal("0.10")
    healthy_rate: Decimal = Decimal("0.20")
    strong_rate: Decimal = Decimal("0.40")
    exceptional_rate: Decimal = Decimal("0.80")

    grade_a_rate: Decimal = Decimal("0.60")
    grade_b_rate: Decimal = Decimal("0.40")
    grade_c_rate: Decimal = Decimal("0.20")
    grade_d_rate: Decimal = Decimal("0.00")

    def __post_init__(self) -> None:
        field_names = (
            "minimum_viable_rate",
            "healthy_rate",
            "strong_rate",
            "exceptional_rate",
            "grade_a_rate",
            "grade_b_rate",
            "grade_c_rate",
            "grade_d_rate",
        )

        for field_name in field_names:
            value = getattr(self, field_name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{field_name}는 Decimal이어야 합니다.")
            if not value.is_finite():
                raise ValueError(f"{field_name}는 유한한 값이어야 합니다.")

        if not (
            _ZERO
            < self.minimum_viable_rate
            < self.healthy_rate
            < self.strong_rate
            < self.exceptional_rate
        ):
            raise ValueError(
                "ROI 점수 경계는 0 < minimum_viable < healthy < "
                "strong < exceptional 순이어야 합니다."
            )

        if not (
            self.grade_a_rate
            > self.grade_b_rate
            > self.grade_c_rate
            > self.grade_d_rate
        ):
            raise ValueError(
                "ROI 등급 경계는 A > B > C > D 순이어야 합니다."
            )


@dataclass(frozen=True, slots=True)
class RoiIntelligenceResult:
    """투자금과 순이익으로부터 계산한 ROI 분석 결과."""

    invested_capital: Decimal
    net_profit: Decimal
    roi_rate: Decimal
    roi_percent: Decimal
    score: Decimal
    grade: RoiGrade

    def __post_init__(self) -> None:
        decimal_fields = (
            "invested_capital",
            "net_profit",
            "roi_rate",
            "roi_percent",
            "score",
        )

        for field_name in decimal_fields:
            value = getattr(self, field_name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{field_name}는 Decimal이어야 합니다.")
            if not value.is_finite():
                raise ValueError(f"{field_name}는 유한한 값이어야 합니다.")

        if self.invested_capital <= _ZERO:
            raise ValueError("invested_capital은 0보다 커야 합니다.")
        if self.score < _ZERO or self.score > _HUNDRED:
            raise ValueError("score는 0 이상 100 이하여야 합니다.")
        if not isinstance(self.grade, RoiGrade):
            raise TypeError("grade는 RoiGrade여야 합니다.")


class RoiIntelligenceEngine:
    """투입 자본 대비 순이익을 ROI 점수와 등급으로 변환한다."""

    def __init__(self, policy: RoiIntelligencePolicy | None = None) -> None:
        self._policy = policy or RoiIntelligencePolicy()

    def calculate(
        self,
        *,
        invested_capital: Decimal,
        net_profit: Decimal,
    ) -> RoiIntelligenceResult:
        self._validate_money("invested_capital", invested_capital)
        self._validate_money("net_profit", net_profit)

        if invested_capital <= _ZERO:
            raise ValueError("invested_capital은 0보다 커야 합니다.")

        roi_rate = (net_profit / invested_capital).quantize(
            _RATE_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        roi_percent = (roi_rate * _HUNDRED).quantize(
            _PERCENT_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
        score = self._calculate_score(roi_rate)
        grade = self._determine_grade(roi_rate)

        return RoiIntelligenceResult(
            invested_capital=invested_capital,
            net_profit=net_profit,
            roi_rate=roi_rate,
            roi_percent=roi_percent,
            score=score,
            grade=grade,
        )

    def _calculate_score(self, roi_rate: Decimal) -> Decimal:
        if roi_rate <= _ZERO:
            score = _ZERO
        elif roi_rate <= self._policy.minimum_viable_rate:
            score = self._interpolate(
                roi_rate,
                _ZERO,
                self._policy.minimum_viable_rate,
                Decimal("0"),
                Decimal("20"),
            )
        elif roi_rate <= self._policy.healthy_rate:
            score = self._interpolate(
                roi_rate,
                self._policy.minimum_viable_rate,
                self._policy.healthy_rate,
                Decimal("20"),
                Decimal("40"),
            )
        elif roi_rate <= self._policy.strong_rate:
            score = self._interpolate(
                roi_rate,
                self._policy.healthy_rate,
                self._policy.strong_rate,
                Decimal("40"),
                Decimal("70"),
            )
        elif roi_rate <= self._policy.exceptional_rate:
            score = self._interpolate(
                roi_rate,
                self._policy.strong_rate,
                self._policy.exceptional_rate,
                Decimal("70"),
                Decimal("100"),
            )
        else:
            score = _HUNDRED

        return max(_ZERO, min(_HUNDRED, score)).quantize(
            _SCORE_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

    def _determine_grade(self, roi_rate: Decimal) -> RoiGrade:
        if roi_rate >= self._policy.grade_a_rate:
            return RoiGrade.A
        if roi_rate >= self._policy.grade_b_rate:
            return RoiGrade.B
        if roi_rate >= self._policy.grade_c_rate:
            return RoiGrade.C
        if roi_rate > self._policy.grade_d_rate:
            return RoiGrade.D
        return RoiGrade.F

    @staticmethod
    def _interpolate(
        value: Decimal,
        start_x: Decimal,
        end_x: Decimal,
        start_y: Decimal,
        end_y: Decimal,
    ) -> Decimal:
        progress = (value - start_x) / (end_x - start_x)
        return start_y + (end_y - start_y) * progress

    @staticmethod
    def _validate_money(field_name: str, value: object) -> None:
        if not isinstance(value, Decimal):
            raise TypeError(f"{field_name}는 Decimal이어야 합니다.")
        if not value.is_finite():
            raise ValueError(f"{field_name}는 유한한 값이어야 합니다.")
