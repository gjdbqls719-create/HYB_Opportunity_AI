from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(slots=True, frozen=True)
class DashboardProduct:
    """
    Dashboard에서 표시할 상품 기본 정보.

    엔진의 Product 객체를 화면에 직접 노출하지 않고,
    Presentation 계층에서 필요한 값만 안전하게 보관한다.
    """

    marketplace: str
    item_id: str
    title: str
    price: float
    shipping_cost: float
    total_cost: float
    currency: str
    condition: str
    url: str
    image_url: str
    seller: str
    in_stock: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class DashboardMetrics:
    """
    상품 기회 분석의 핵심 수치.

    CLI, Web, API가 동일한 필드 이름을 사용할 수 있도록
    분석 결과의 수치 데이터를 하나로 묶는다.
    """

    expected_selling_price: float
    net_profit: float
    roi: float
    opportunity_score: float
    adjusted_opportunity_score: float
    final_opportunity_score: float
    matched_product_count: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class DashboardRecommendation:
    """
    AI Recommendation 결과를 Dashboard에 표시하기 위한 모델.
    """

    grade: str
    action: str
    score: float
    success_probability: float
    summary: str
    reasons: tuple[str, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["reasons"] = list(self.reasons)
        data["warnings"] = list(self.warnings)
        return data


@dataclass(slots=True, frozen=True)
class DashboardAIPartner:
    """
    AI Partner의 최종 판단과 행동 제안을 표현한다.
    """

    title: str
    summary: str
    recommendation: str
    next_action: str
    memory_summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class DashboardMemory:
    """
    AI Memory가 계산한 과거 분석 대비 위치.
    """

    sample_size: int
    rank_label: str
    overall_percentile: float
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class DashboardCard:
    """
    하나의 상품 기회를 Dashboard에 표시하기 위한 최종 모델.

    DashboardCard는 특정 화면 기술에 의존하지 않는다.
    따라서 CLI, 웹 화면, API 응답에서 공통으로 사용할 수 있다.
    """

    product: DashboardProduct
    metrics: DashboardMetrics
    recommendation: DashboardRecommendation | None
    ai_partner: DashboardAIPartner | None
    memory: DashboardMemory | None

    confidence_level: str
    trend_direction: str
    decision: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "product": self.product.to_dict(),
            "metrics": self.metrics.to_dict(),
            "recommendation": (
                self.recommendation.to_dict()
                if self.recommendation is not None
                else None
            ),
            "ai_partner": (
                self.ai_partner.to_dict()
                if self.ai_partner is not None
                else None
            ),
            "memory": (
                self.memory.to_dict()
                if self.memory is not None
                else None
            ),
            "confidence_level": self.confidence_level,
            "trend_direction": self.trend_direction,
            "decision": self.decision,
        }