from __future__ import annotations

from dataclasses import dataclass

from market_data.inventory_snapshot import (
    InventorySnapshot,
)


@dataclass(frozen=True, slots=True)
class InventoryAnalysisResult:
    """
    InventorySnapshot 기반 재고 분석 결과.
    """

    availability: str
    stock_level: str
    risk_level: str

    can_purchase: bool

    insights: tuple[str, ...]
    risks: tuple[str, ...]

    summary: str


def analyze_inventory(
    snapshot: InventorySnapshot | None,
) -> InventoryAnalysisResult:
    """
    재고 Snapshot을 기반으로
    현재 매입 가능성을 분석한다.
    """

    if snapshot is None:
        return InventoryAnalysisResult(
            availability="데이터 없음",
            stock_level="판단 불가",
            risk_level="높음",
            can_purchase=False,
            insights=(),
            risks=(
                "재고 정보가 없습니다.",
            ),
            summary=(
                "재고 정보 부족으로 "
                "매입 가능 여부를 판단할 수 없습니다."
            ),
        )

    insights: list[str] = []
    risks: list[str] = []

    if snapshot.available:
        availability = "재고 있음"
        can_purchase = True

        insights.append(
            "현재 판매 가능한 재고가 확인됩니다."
        )
    else:
        availability = "품절"
        can_purchase = False

        risks.append(
            "현재 구매 가능한 재고가 없습니다."
        )

    stock_level = _analyze_stock_level(
        snapshot=snapshot,
        insights=insights,
        risks=risks,
    )

    risk_level = _determine_risk_level(
        snapshot=snapshot,
    )

    summary = _build_summary(
        availability=availability,
        stock_level=stock_level,
        risk_level=risk_level,
    )

    return InventoryAnalysisResult(
        availability=availability,
        stock_level=stock_level,
        risk_level=risk_level,
        can_purchase=can_purchase,
        insights=tuple(insights),
        risks=tuple(risks),
        summary=summary,
    )


def _analyze_stock_level(
    *,
    snapshot: InventorySnapshot,
    insights: list[str],
    risks: list[str],
) -> str:
    if snapshot.quantity is None:
        return "수량 미확인"

    if snapshot.quantity == 0:
        risks.append(
            "재고 수량이 없습니다."
        )
        return "없음"

    if snapshot.quantity <= 5:
        risks.append(
            "재고 수량이 적습니다."
        )
        return "부족"

    insights.append(
        "충분한 재고가 확인됩니다."
    )
    return "충분"


def _determine_risk_level(
    *,
    snapshot: InventorySnapshot,
) -> str:
    if not snapshot.available:
        return "높음"

    if (
        snapshot.quantity is not None
        and snapshot.quantity <= 5
    ):
        return "중간"

    return "낮음"


def _build_summary(
    *,
    availability: str,
    stock_level: str,
    risk_level: str,
) -> str:
    return (
        f"재고 상태는 {availability}이며, "
        f"수량 수준은 {stock_level}입니다. "
        f"재고 위험도는 {risk_level}입니다."
    )