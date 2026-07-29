from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum


class OpportunityRiskLevel(str, Enum):
    """Opportunity의 투자 위험 구간."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


@dataclass(frozen=True, slots=True)
class OpportunityRiskAssessment:
    """위험 안전성 점수를 투자 위험 의미로 변환한 결과."""

    safety_score: Decimal
    level: OpportunityRiskLevel
    reason: str
    requires_caution: bool

    def __post_init__(self) -> None:
        _validate_score("safety_score", self.safety_score)
        if not isinstance(self.level, OpportunityRiskLevel):
            raise TypeError("level은 OpportunityRiskLevel이어야 합니다.")
        if not isinstance(self.reason, str):
            raise TypeError("reason은 문자열이어야 합니다.")
        if not self.reason.strip():
            raise ValueError("reason은 비어 있을 수 없습니다.")
        if not isinstance(self.requires_caution, bool):
            raise TypeError("requires_caution은 bool이어야 합니다.")


@dataclass(frozen=True, slots=True)
class OpportunityRiskPolicy:
    """위험 안전성 점수를 실제 투자 위험 수준으로 분류하는 정책."""

    medium_safety_threshold: Decimal = Decimal("40")
    low_risk_safety_threshold: Decimal = Decimal("70")

    def __post_init__(self) -> None:
        _validate_score("medium_safety_threshold", self.medium_safety_threshold)
        _validate_score("low_risk_safety_threshold", self.low_risk_safety_threshold)
        if self.medium_safety_threshold >= self.low_risk_safety_threshold:
            raise ValueError(
                "위험 경계는 medium_safety_threshold < "
                "low_risk_safety_threshold 순이어야 합니다."
            )


class OpportunityRiskEngine:
    """0~100 위험 안전성 점수를 구조화된 투자 위험 평가로 변환한다."""

    def __init__(self, policy: OpportunityRiskPolicy | None = None) -> None:
        self._policy = policy or OpportunityRiskPolicy()

    def assess(self, safety_score: Decimal) -> OpportunityRiskAssessment:
        _validate_score("safety_score", safety_score)

        if safety_score >= self._policy.low_risk_safety_threshold:
            return OpportunityRiskAssessment(
                safety_score=safety_score,
                level=OpportunityRiskLevel.LOW,
                reason="현재 위험 안전성 지표가 양호합니다.",
                requires_caution=False,
            )

        if safety_score >= self._policy.medium_safety_threshold:
            return OpportunityRiskAssessment(
                safety_score=safety_score,
                level=OpportunityRiskLevel.MEDIUM,
                reason="일부 위험 요인이 있으므로 매입 전 추가 확인이 필요합니다.",
                requires_caution=True,
            )

        return OpportunityRiskAssessment(
            safety_score=safety_score,
            level=OpportunityRiskLevel.HIGH,
            reason="위험 안전성 지표가 낮으므로 현재 매입에는 주의가 필요합니다.",
            requires_caution=True,
        )


def _validate_score(field_name: str, value: object) -> None:
    if not isinstance(value, Decimal):
        raise TypeError(f"{field_name}는 Decimal이어야 합니다.")
    if not value.is_finite():
        raise ValueError(f"{field_name}는 유한한 값이어야 합니다.")
    if value < Decimal("0") or value > Decimal("100"):
        raise ValueError(f"{field_name}는 0 이상 100 이하여야 합니다.")
