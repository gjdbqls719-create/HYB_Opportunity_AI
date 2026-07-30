from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class OpportunityConfidenceLevel(str, Enum):
    """Opportunity Intelligence 신뢰도 구간."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    VERY_HIGH = "VERY_HIGH"


@dataclass(frozen=True, slots=True)
class OpportunityConfidenceAssessment:
    """정규화된 Opportunity Intelligence 신뢰도 평가 결과."""

    score: Decimal
    level: OpportunityConfidenceLevel
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.score, Decimal):
            raise TypeError("score는 Decimal이어야 합니다.")
        if not self.score.is_finite():
            raise ValueError("score는 유한한 값이어야 합니다.")
        if self.score < Decimal("0") or self.score > Decimal("100"):
            raise ValueError("score는 0 이상 100 이하여야 합니다.")
        if not isinstance(self.level, OpportunityConfidenceLevel):
            raise TypeError("level은 OpportunityConfidenceLevel이어야 합니다.")
        if not isinstance(self.reason, str):
            raise TypeError("reason은 문자열이어야 합니다.")
        if not self.reason.strip():
            raise ValueError("reason은 비어 있을 수 없습니다.")


@dataclass(frozen=True, slots=True)
class OpportunityConfidencePolicy:
    """신뢰도 점수를 의미 있는 구간으로 분류하는 정책."""

    medium_threshold: Decimal = Decimal("40")
    high_threshold: Decimal = Decimal("70")
    very_high_threshold: Decimal = Decimal("90")

    def __post_init__(self) -> None:
        for field_name in (
            "medium_threshold",
            "high_threshold",
            "very_high_threshold",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{field_name}는 Decimal이어야 합니다.")
            if not value.is_finite():
                raise ValueError(f"{field_name}는 유한한 값이어야 합니다.")
            if value < Decimal("0") or value > Decimal("100"):
                raise ValueError(f"{field_name}는 0 이상 100 이하여야 합니다.")

        if not (
            self.medium_threshold
            < self.high_threshold
            < self.very_high_threshold
        ):
            raise ValueError(
                "신뢰도 경계는 medium < high < very_high 순이어야 합니다."
            )


class OpportunityConfidenceEngine:
    """원시 신뢰도 점수를 표준 평가 결과로 변환한다."""

    def __init__(
        self,
        policy: OpportunityConfidencePolicy | None = None,
    ) -> None:
        self._policy = policy or OpportunityConfidencePolicy()

    def assess(self, score: Decimal) -> OpportunityConfidenceAssessment:
        self._validate_score(score)

        if score >= self._policy.very_high_threshold:
            level = OpportunityConfidenceLevel.VERY_HIGH
            reason = "판단을 뒷받침하는 신뢰도 데이터가 매우 충분합니다."
        elif score >= self._policy.high_threshold:
            level = OpportunityConfidenceLevel.HIGH
            reason = "판단을 뒷받침하는 신뢰도 데이터가 충분합니다."
        elif score >= self._policy.medium_threshold:
            level = OpportunityConfidenceLevel.MEDIUM
            reason = "판단에 활용할 수 있으나 추가 데이터 확인이 권장됩니다."
        else:
            level = OpportunityConfidenceLevel.LOW
            reason = "판단 근거가 부족하므로 추가 데이터 확보가 필요합니다."

        return OpportunityConfidenceAssessment(
            score=score,
            level=level,
            reason=reason,
        )

    @staticmethod
    def _validate_score(score: object) -> None:
        if not isinstance(score, Decimal):
            raise TypeError("score는 Decimal이어야 합니다.")
        if not score.is_finite():
            raise ValueError("score는 유한한 값이어야 합니다.")
        if score < Decimal("0") or score > Decimal("100"):
            raise ValueError("score는 0 이상 100 이하여야 합니다.")
