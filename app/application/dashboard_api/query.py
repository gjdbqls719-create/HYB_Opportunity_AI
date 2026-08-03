from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.application.dashboard import DashboardReadModel
from app.application.dashboard_api.assembler import DashboardApiAssembler
from app.application.dashboard_api.models import DashboardResponseDTO
from app.domain.decision_engine import OpportunityIdentity


class DashboardDecisionNotFoundError(LookupError):
    pass


class DashboardDecisionConflictError(RuntimeError):
    pass


class DashboardDecisionUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OpportunityDecisionDashboardSource:
    opportunity_identity: OpportunityIdentity
    read_model: DashboardReadModel

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.read_model, DashboardReadModel):
            raise TypeError("read_model must be DashboardReadModel")


class OpportunityDecisionDashboardProvider(Protocol):
    def get(self, opportunity_id: str) -> OpportunityDecisionDashboardSource:
        ...


class GetOpportunityDecisionDashboard:
    def __init__(
        self,
        provider: OpportunityDecisionDashboardProvider,
        assembler: DashboardApiAssembler | None = None,
    ) -> None:
        self._provider = provider
        self._assembler = assembler or DashboardApiAssembler()

    def execute(self, opportunity_id: str) -> DashboardResponseDTO:
        if not isinstance(opportunity_id, str) or not opportunity_id.strip():
            raise ValueError("opportunity_id must be non-empty text")
        normalized_id = opportunity_id.strip()
        source = self._provider.get(normalized_id)
        if not isinstance(source, OpportunityDecisionDashboardSource):
            raise TypeError(
                "provider must return OpportunityDecisionDashboardSource"
            )
        if source.opportunity_identity.opportunity_id != normalized_id:
            raise DashboardDecisionConflictError(
                "dashboard opportunity identity does not match request"
            )
        return self._assembler.assemble(source.read_model)


class UnconfiguredOpportunityDecisionDashboardProvider:
    def get(self, opportunity_id: str) -> OpportunityDecisionDashboardSource:
        raise DashboardDecisionUnavailableError(
            "decision dashboard production composition is unavailable"
        )
