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

    landed_cost: float = 0.0
    selling_cost: float = 0.0
    total_cost: float = 0.0
    margin_rate: float = 0.0
    landed_cost_roi: float = 0.0

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
class DashboardEvidence:
    """
    의사결정 단계의 근거 한 항목을 표현한다.

    label은 근거의 종류이고,
    value는 실제 근거 내용을 보관한다.
    """

    label: str
    value: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class DashboardDecisionStep:
    """
    HYB가 최종 판단에 도달하기까지 사용한
    하나의 분석 단계를 표현한다.

    Presentation 전용 모델이며 점수 계산이나
    비즈니스 판단을 직접 수행하지 않는다.
    """

    stage: str
    title: str
    summary: str
    evidence: tuple[DashboardEvidence, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "title": self.title,
            "summary": self.summary,
            "evidence": [
                item.to_dict()
                for item in self.evidence
            ],
        }


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

    decision_timeline: (
        tuple[DashboardDecisionStep, ...]
    ) = ()

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
            "decision_timeline": [
                step.to_dict()
                for step in self.decision_timeline
            ],
        }

@dataclass(slots=True, frozen=True)
class OpportunityListItem:
    """
    여러 상품 기회를 빠르게 비교하기 위한 목록 항목.

    엔진 객체를 직접 노출하지 않고 목록 화면에 필요한
    핵심 정보만 보관한다. rank는 현재 입력 순서를 기준으로 한다.
    """

    rank: int
    marketplace: str
    item_id: str
    title: str
    decision: str
    score: float
    net_profit: float
    roi: float
    confidence_level: str
    currency: str
    url: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True, frozen=True)
class OpportunityListCard:
    """
    Top Opportunity 목록을 표현하는 화면 독립적 ViewModel.

    CLI, Web, API, Export 계층이 동일한 목록 데이터를
    재사용할 수 있도록 항목과 전체 개수를 함께 보관한다.
    """

    items: tuple[OpportunityListItem, ...]
    total_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [
                item.to_dict()
                for item in self.items
            ],
            "total_count": self.total_count,
        }
