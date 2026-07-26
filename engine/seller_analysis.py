from __future__ import annotations

from dataclasses import dataclass

from market_data.seller_snapshot import (
    SellerSnapshot,
)


@dataclass(frozen=True, slots=True)
class SellerAnalysisResult:
    """
    SellerSnapshot 기반 판매자 분석 결과.
    """

    competition_level: str
    seller_quality: str
    risk_level: str

    insights: tuple[str, ...]
    risks: tuple[str, ...]

    summary: str


def analyze_seller(
    snapshot: SellerSnapshot | None,
) -> SellerAnalysisResult:
    """
    판매자 Snapshot을 기반으로
    경쟁 환경과 판매자 신뢰도를 분석한다.
    """

    if snapshot is None:
        return SellerAnalysisResult(
            competition_level="데이터 없음",
            seller_quality="판단 불가",
            risk_level="높음",
            insights=(),
            risks=(
                "판매자 정보가 없습니다.",
            ),
            summary=(
                "판매자 정보 부족으로 "
                "경쟁 환경을 판단할 수 없습니다."
            ),
        )

    insights: list[str] = []
    risks: list[str] = []

    competition_level = _analyze_competition(
        snapshot=snapshot,
        insights=insights,
        risks=risks,
    )

    seller_quality = _analyze_quality(
        snapshot=snapshot,
        insights=insights,
        risks=risks,
    )

    risk_level = _determine_risk_level(
        competition_level=competition_level,
        seller_quality=seller_quality,
    )

    summary = _build_summary(
        competition_level=competition_level,
        seller_quality=seller_quality,
        risk_level=risk_level,
    )

    return SellerAnalysisResult(
        competition_level=competition_level,
        seller_quality=seller_quality,
        risk_level=risk_level,
        insights=tuple(insights),
        risks=tuple(risks),
        summary=summary,
    )


def _analyze_competition(
    *,
    snapshot: SellerSnapshot,
    insights: list[str],
    risks: list[str],
) -> str:
    if snapshot.seller_count <= 1:
        insights.append(
            "경쟁 판매자가 거의 없습니다."
        )
        return "낮음"

    if snapshot.seller_count <= 5:
        insights.append(
            "경쟁 판매자 수가 적당합니다."
        )
        return "보통"

    risks.append(
        "경쟁 판매자가 많습니다."
    )
    return "높음"


def _analyze_quality(
    *,
    snapshot: SellerSnapshot,
    insights: list[str],
    risks: list[str],
) -> str:
    if snapshot.seller_rating is None:
        risks.append(
            "판매자 평점 정보가 없습니다."
        )
        return "판단 제한"

    if snapshot.seller_rating >= 4.5:
        insights.append(
            "판매자 평점이 높습니다."
        )
        return "양호"

    if snapshot.seller_rating >= 3.0:
        return "보통"

    risks.append(
        "판매자 평점이 낮습니다."
    )
    return "위험"


def _determine_risk_level(
    *,
    competition_level: str,
    seller_quality: str,
) -> str:
    if (
        competition_level == "높음"
        or seller_quality == "위험"
    ):
        return "높음"

    if (
        competition_level == "보통"
        or seller_quality == "보통"
        or seller_quality == "판단 제한"
    ):
        return "중간"

    return "낮음"


def _build_summary(
    *,
    competition_level: str,
    seller_quality: str,
    risk_level: str,
) -> str:
    return (
        f"판매자 경쟁 수준은 {competition_level}이며, "
        f"판매자 품질은 {seller_quality}입니다. "
        f"판매자 관련 위험도는 {risk_level}입니다."
    )