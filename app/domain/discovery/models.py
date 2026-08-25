from __future__ import annotations

from dataclasses import dataclass, field, replace
from math import isfinite
from types import MappingProxyType
from typing import Any, Mapping

from app.models import Product


@dataclass(slots=True, frozen=True)
class DiscoveryResult:
    """Discovery 파이프라인이 외부 계층에 전달하는 표준 결과."""

    product: Product
    opportunity_score: float
    matched_product_count: int = 1
    recommendation_grade: str | None = None
    recommendation_action: str | None = None
    recommendation_summary: str | None = None
    rank: int | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    finalized_group_id: str | None = None

    def __post_init__(self) -> None:
        score = float(self.opportunity_score)

        if not isfinite(score):
            raise ValueError("opportunity_score는 유한한 숫자여야 합니다.")

        if not 0 <= score <= 100:
            raise ValueError("opportunity_score는 0 이상 100 이하여야 합니다.")

        if self.matched_product_count < 1:
            raise ValueError("matched_product_count는 1 이상이어야 합니다.")

        if self.rank is not None and self.rank < 1:
            raise ValueError("rank는 1 이상이어야 합니다.")

        if self.finalized_group_id is not None:
            if (
                not isinstance(self.finalized_group_id, str)
                or not self.finalized_group_id.strip()
            ):
                raise ValueError("finalized_group_id는 비어 있지 않은 문자열이어야 합니다.")

        object.__setattr__(self, "opportunity_score", score)
        object.__setattr__(
            self,
            "metadata",
            MappingProxyType(dict(self.metadata)),
        )

    @property
    def identity_key(self) -> str:
        """마켓 상품을 안정적으로 식별하기 위한 기본 키."""
        item_id = self.product.item_id.strip()

        if item_id:
            return f"{self.product.marketplace.lower()}:{item_id}"

        url = self.product.url.strip()

        if url:
            return f"{self.product.marketplace.lower()}:{url}"

        return (
            f"{self.product.marketplace.lower()}:"
            f"{self.product.title.strip().lower()}"
        )

    def with_rank(self, rank: int) -> DiscoveryResult:
        """원본을 변경하지 않고 순위가 지정된 새 결과를 반환한다."""
        return replace(self, rank=rank)
