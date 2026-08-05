"""SQLite infrastructure for durable Discovery command correlation."""

from app.infrastructure.discovery.sqlite_repository import (
    SQLiteDiscoveryCommandRepository,
)
from app.infrastructure.discovery.sqlite_observation_group_repository import (
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
)
from app.infrastructure.discovery.sqlite_result_repository import (
    SQLiteDiscoveryResultRepository,
)
from app.infrastructure.discovery.sqlite_candidate_repository import (
    SQLiteCandidateIssuanceRepository,
)
from app.infrastructure.discovery.production_runtime import (
    OrchestratorProductionDiscoveryRuntime,
)
from app.infrastructure.discovery.orchestrator_gateway import (
    OrchestratorOpportunityDiscoveryGateway,
)
from app.infrastructure.discovery.identity_suppliers import (
    ProductionFinalizedGroupIdentityProvider,
    ProductionObservationIdentityProvider,
)

__all__ = [
    "OrchestratorOpportunityDiscoveryGateway",
    "OrchestratorProductionDiscoveryRuntime",
    "ProductionFinalizedGroupIdentityProvider",
    "ProductionObservationIdentityProvider",
    "SQLiteDiscoveryCommandRepository",
    "SQLiteDiscoveryGroupRepository",
    "SQLiteDiscoveryObservationRepository",
    "SQLiteDiscoveryResultRepository",
    "SQLiteCandidateIssuanceRepository",
]
