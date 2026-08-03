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
from app.application.opportunity_market_identity import (
    GetOpportunityMarketIdentity,
    MalformedOpportunityMarketIdentityBindingError,
    OpportunityMarketIdentityBindingNotFoundError,
    OpportunityMarketIdentityConflictError,
    OpportunityMarketIdentityRepository,
)
from app.application.verified_economics_snapshot import (
    GetVerifiedEconomicsSnapshot,
    MalformedVerifiedEconomicsSnapshotError,
    VerifiedEconomicsSnapshotIdentityConflictError,
    VerifiedEconomicsSnapshotNotFoundError,
    VerifiedEconomicsSnapshotRepository,
)
from app.application.production_safety_snapshot import (
    GetProductionSafetySnapshot,
    MalformedProductionSafetySnapshotError,
    ProductionSafetySnapshotIdentityConflictError,
    ProductionSafetySnapshotNotFoundError,
    ProductionSafetySnapshotRepository,
)


MISSING_MARKET_IDENTITY_LINK = (
    "persisted opportunity has no explicit MarketObservationIdentity link"
)
MISSING_VERIFIED_ECONOMICS = (
    "persisted opportunity has no authoritative VerifiedEconomicsInput source"
)
MISSING_PRODUCTION_SAFETY = (
    "persisted opportunity has no authoritative ProductionSafetyAssessment source"
)
MISSING_MARKET_EVIDENCE_COMPOSITION = (
    "production dashboard composition has no connected Competition and Demand evidence sources"
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

    def __init__(
        self,
        validation_repository: ValidationQueueItemReader,
        market_identity_repository: OpportunityMarketIdentityRepository | None = None,
        verified_economics_repository: VerifiedEconomicsSnapshotRepository | None = None,
        production_safety_repository: ProductionSafetySnapshotRepository | None = None,
    ) -> None:
        self._validation_repository = validation_repository
        self._market_identity_repository = (
            market_identity_repository or validation_repository
        )
        self._verified_economics_repository = (
            verified_economics_repository or validation_repository
        )
        self._production_safety_repository = (
            production_safety_repository or validation_repository
        )

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
        try:
            GetOpportunityMarketIdentity(
                self._market_identity_repository
            ).execute(opportunity_id)
        except OpportunityMarketIdentityBindingNotFoundError as error:
            raise DashboardCompositionUnavailableError(
                MISSING_MARKET_IDENTITY_LINK
            ) from error
        except OpportunityMarketIdentityConflictError as error:
            raise DashboardIdentityConflictError(str(error)) from error
        except MalformedOpportunityMarketIdentityBindingError as error:
            raise DashboardCompositionUnavailableError(str(error)) from error
        try:
            GetVerifiedEconomicsSnapshot(
                self._verified_economics_repository
            ).execute(opportunity_id)
        except VerifiedEconomicsSnapshotNotFoundError as error:
            raise DashboardCompositionUnavailableError(
                MISSING_VERIFIED_ECONOMICS
            ) from error
        except VerifiedEconomicsSnapshotIdentityConflictError as error:
            raise DashboardIdentityConflictError(str(error)) from error
        except MalformedVerifiedEconomicsSnapshotError as error:
            raise DashboardCompositionUnavailableError(str(error)) from error
        try:
            GetProductionSafetySnapshot(
                self._production_safety_repository
            ).execute(opportunity_id)
        except ProductionSafetySnapshotNotFoundError as error:
            raise DashboardCompositionUnavailableError(
                MISSING_PRODUCTION_SAFETY
            ) from error
        except ProductionSafetySnapshotIdentityConflictError as error:
            raise DashboardIdentityConflictError(str(error)) from error
        except MalformedProductionSafetySnapshotError as error:
            raise DashboardCompositionUnavailableError(str(error)) from error
        raise DashboardCompositionUnavailableError(
            MISSING_MARKET_EVIDENCE_COMPOSITION
        )
