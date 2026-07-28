from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from services.fees import FeeBreakdown


_SCORE_QUANTUM = Decimal("0.01")
_ZERO = Decimal("0")
_ONE = Decimal("1")
_HUNDRED = Decimal("100")


@dataclass(frozen=True, slots=True)
class FeeEfficiencyPolicy:
    """판매가 대비 총수수료율을 0~100 효율 점수로 변환하는 정책."""

    excellent_rate: Decimal = Decimal("0.10")
    acceptable_rate: Decimal = Decimal("0.20")
    maximum_rate: Decimal = Decimal("0.40")

    def __post_init__(self) -> None:
        for field_name in (
            "excellent_rate",
            "acceptable_rate",
            "maximum_rate",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{field_name}는 Decimal이어야 합니다.")
            if not value.is_finite():
                raise ValueError(f"{field_name}는 유한한 값이어야 합니다.")
            if value < _ZERO or value > _ONE:
                raise ValueError(f"{field_name}는 0 이상 1 이하여야 합니다.")

        if not (
            self.excellent_rate
            < self.acceptable_rate
            < self.maximum_rate
        ):
            raise ValueError(
                "수수료율 경계는 excellent < acceptable < maximum 순이어야 합니다."
            )


class FeeEfficiencyScorer:
    """FeeBreakdown을 Opportunity Score용 수수료 효율 점수로 변환한다."""

    def __init__(self, policy: FeeEfficiencyPolicy | None = None) -> None:
        self._policy = policy or FeeEfficiencyPolicy()

    def calculate(self, fee_breakdown: FeeBreakdown) -> Decimal:
        if not isinstance(fee_breakdown, FeeBreakdown):
            raise TypeError("fee_breakdown은 FeeBreakdown이어야 합니다.")

        if fee_breakdown.selling_price == _ZERO:
            return _ZERO.quantize(_SCORE_QUANTUM)

        effective_rate = (
            fee_breakdown.total_fee / fee_breakdown.selling_price
        )

        if effective_rate <= self._policy.excellent_rate:
            score = _HUNDRED
        elif effective_rate <= self._policy.acceptable_rate:
            score = self._interpolate(
                effective_rate,
                self._policy.excellent_rate,
                self._policy.acceptable_rate,
                Decimal("100"),
                Decimal("60"),
            )
        elif effective_rate <= self._policy.maximum_rate:
            score = self._interpolate(
                effective_rate,
                self._policy.acceptable_rate,
                self._policy.maximum_rate,
                Decimal("60"),
                _ZERO,
            )
        else:
            score = _ZERO

        return max(_ZERO, min(_HUNDRED, score)).quantize(
            _SCORE_QUANTUM,
            rounding=ROUND_HALF_UP,
        )

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
