from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ConfidenceResult:
    """
    가격 분석 결과의 신뢰도 정보.
    """

    sample_size: int
    confidence_score: int
    confidence_multiplier: float
    confidence_level: str
    used_fallback_price: bool
    reason: str


def _base_confidence(
    sample_size: int,
) -> tuple[int, str, str]:
    """
    표본 수를 기준으로 기본 신뢰도를 계산한다.
    """

    if sample_size == 1:
        return (
            35,
            "낮음",
            (
                "가격 표본이 1개뿐이어서 "
                "시장 가격 신뢰도가 낮습니다."
            ),
        )

    if sample_size == 2:
        return (
            60,
            "보통",
            (
                "가격 표본이 2개이므로 "
                "추가 시장 데이터가 필요합니다."
            ),
        )

    if sample_size <= 5:
        return (
            80,
            "높음",
            (
                "가격 표본이 3개 이상이어서 "
                "시장 가격을 비교할 수 있습니다."
            ),
        )

    return (
        100,
        "매우 높음",
        (
            "충분한 가격 표본이 확보되어 "
            "시장 가격 신뢰도가 높습니다."
        ),
    )


def calculate_price_confidence(
    sample_size: int,
    *,
    used_fallback_price: bool = False,
) -> ConfidenceResult:
    """
    가격 표본 수를 기준으로 분석 신뢰도를 계산한다.
    """

    if sample_size < 1:
        raise ValueError(
            "sample_size는 1 이상이어야 합니다."
        )

    (
        confidence_score,
        confidence_level,
        reason,
    ) = _base_confidence(sample_size)

    if used_fallback_price:
        reason += (
            " 권장 판매가는 실제 비교 가격이 아니라 "
            "fallback 배수를 사용했습니다."
        )

    return ConfidenceResult(
        sample_size=sample_size,
        confidence_score=confidence_score,
        confidence_multiplier=round(
            confidence_score / 100,
            2,
        ),
        confidence_level=confidence_level,
        used_fallback_price=used_fallback_price,
        reason=reason,
    )