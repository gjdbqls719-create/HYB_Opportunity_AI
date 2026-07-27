from __future__ import annotations

from typing import Protocol

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
