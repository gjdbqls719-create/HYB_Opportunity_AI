from __future__ import annotations

import sqlite3
from typing import Protocol

from app.application.dashboard_api.query import (
    DashboardCompositionUnavailableError,
    DashboardIdentityConflictError,
    DashboardOpportunityNotFoundError,
    OpportunityDecisionDashboardSource,
)
from app.application.opportunity_validation import ValidationQueueItem
from app.domain.decision_engine import OpportunityIdentity


MISSING_MARKET_IDENTITY_LINK = (
    "persisted opportunity has no explicit MarketObservationIdentity link"
)


class ValidationQueueItemReader(Protocol):
    def get_queue_item(self, opportunity_id: str) -> ValidationQueueItem | None:
        ...


class ProductionOpportunityDecisionDashboardProvider:
    """Resolve authoritative persisted identity before Decision composition.

    The current admission/lifecycle schema does not preserve the explicit
    MarketObservationIdentity required by DecisionInput. Composition stops at
    that boundary instead of deriving an identity from display fields or a
    discovery-reference string.
    """

    def __init__(self, validation_repository: ValidationQueueItemReader) -> None:
        self._validation_repository = validation_repository

    def get(self, opportunity_id: str) -> OpportunityDecisionDashboardSource:
        try:
            item = self._validation_repository.get_queue_item(opportunity_id)
        except sqlite3.Error as error:
            raise DashboardCompositionUnavailableError(
                "validation persistence is unavailable"
            ) from error
        if item is None:
            raise DashboardOpportunityNotFoundError(
                "dashboard opportunity not found"
            )
        if item.opportunity_id != opportunity_id:
            raise DashboardIdentityConflictError(
                "persisted opportunity identity does not match request"
            )

        # Validate the persisted HYB subject independently from market evidence.
        OpportunityIdentity(
            opportunity_id=item.opportunity_id,
            discovery_reference=item.discovery_reference,
        )
        raise DashboardCompositionUnavailableError(MISSING_MARKET_IDENTITY_LINK)
