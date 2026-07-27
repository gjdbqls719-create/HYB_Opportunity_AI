from __future__ import annotations

from decimal import Decimal, InvalidOperation

from app.application.opportunity_intelligence import (
    OpportunityIntelligenceInput,
)
from app.domain.discovery import DiscoveryResult


_MISSING_FACTORS = (
    "price_score",
    "trend_score",
    "demand_score",
    "competition_score",
    "risk_score",
)


class DiscoveryResultOpportunityIntelligenceAdapter:
    """기존 DiscoveryResult에서 현재 검증 가능한 입력만 추출한다."""

    def adapt(
        self,
        discovery_result: DiscoveryResult,
    ) -> OpportunityIntelligenceInput:
        if not isinstance(discovery_result, DiscoveryResult):
            raise TypeError("discovery_result는 DiscoveryResult여야 합니다.")

        return OpportunityIntelligenceInput(
            factors=None,
            confidence=self._parse_confidence(
                discovery_result.metadata.get("confidence_score")
            ),
            missing_factors=_MISSING_FACTORS,
        )

    @staticmethod
    def _parse_confidence(value: object) -> Decimal | None:
        if value is None:
            return None

        if isinstance(value, bool):
            raise TypeError("confidence_score는 bool일 수 없습니다.")

        if isinstance(value, Decimal):
            confidence = value
        elif isinstance(value, (int, float, str)):
            try:
                confidence = Decimal(str(value).strip())
            except (InvalidOperation, ValueError) as error:
                raise ValueError(
                    "confidence_score를 Decimal로 변환할 수 없습니다."
                ) from error
        else:
            raise TypeError(
                "confidence_score는 Decimal로 변환 가능한 값이어야 합니다."
            )

        if not confidence.is_finite():
            raise ValueError("confidence_score는 유한한 값이어야 합니다.")
        if confidence < Decimal("0") or confidence > Decimal("100"):
            raise ValueError("confidence_score는 0 이상 100 이하여야 합니다.")

        return confidence
