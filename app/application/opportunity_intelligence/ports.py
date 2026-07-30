from __future__ import annotations

from typing import Protocol

from storage.price_history import PriceHistoryRecord

from app.application.opportunity_intelligence.models import (
    OpportunityIntelligenceInput,
)
from app.domain.discovery import DiscoveryResult


class OpportunityIntelligenceInputAdapter(Protocol):
    """Discovery 결과를 Opportunity Intelligence 입력으로 변환하는 Port."""

    def adapt(
        self,
        discovery_result: DiscoveryResult,
    ) -> OpportunityIntelligenceInput:
        ...


class PriceHistoryReader(Protocol):
    """Opportunity 추세 분석에 필요한 Listing 가격 이력 조회 Port."""

    def get_product_history(
        self,
        *,
        marketplace: str,
        item_id: str,
        limit: int | None = None,
    ) -> list[PriceHistoryRecord]:
        ...
