"""Read-only Application query for completed Discovery results and Groups."""

from __future__ import annotations

from dataclasses import dataclass

from app.application.discovery.production_execution import (
    DiscoveryCompletionReplayError,
)
from app.application.discovery_persistence import (
    DiscoveryExecutionResultNotFound,
    DiscoveryGroupRepository,
    DiscoveryObservationRepository,
    DiscoveryResultRepository,
)
from app.domain.discovery_identity import (
    CollectedProductObservation,
    DiscoveryExecutionResult,
    FinalizedProductGroup,
)


@dataclass(frozen=True, slots=True)
class RepresentativeObservationPreview:
    title: str
    image_url: str
    marketplace: str
    price: float
    currency: str
    url: str


@dataclass(frozen=True, slots=True)
class FinalizedGroupReadModel:
    group: FinalizedProductGroup
    representative_observation: RepresentativeObservationPreview
    observation_count: int


class PersistedDiscoveryResultReader:
    """Reconstructs persisted completion facts without mutating repositories."""

    def __init__(
        self,
        *,
        result_repository: DiscoveryResultRepository,
        group_repository: DiscoveryGroupRepository,
        observation_repository: DiscoveryObservationRepository,
    ) -> None:
        self._result_repository = result_repository
        self._group_repository = group_repository
        self._observation_repository = observation_repository

    def get_execution_result(
        self, discovery_execution_id: str
    ) -> DiscoveryExecutionResult:
        result = self._result_repository.get_by_execution(
            discovery_execution_id
        )
        if result is None:
            raise DiscoveryExecutionResultNotFound(
                "completed discovery execution not found: "
                f"{discovery_execution_id}"
            )
        if not isinstance(result, DiscoveryExecutionResult):
            raise DiscoveryCompletionReplayError(
                "result repository returned malformed completion"
            )
        return result

    def get_finalized_groups(
        self, discovery_execution_id: str
    ) -> tuple[FinalizedProductGroup, ...]:
        result = self.get_execution_result(discovery_execution_id)
        groups = []
        for finalized_group_id in result.finalized_group_ids:
            group = self._group_repository.get_group(finalized_group_id)
            if group is None:
                raise DiscoveryCompletionReplayError(
                    "completed result references a missing finalized group"
                )
            if not isinstance(group, FinalizedProductGroup):
                raise DiscoveryCompletionReplayError(
                    "group repository returned malformed replay lineage"
                )
            if group.finalized_group_id != finalized_group_id:
                raise DiscoveryCompletionReplayError(
                    "group repository returned conflicting finalized group identity"
                )
            if group.discovery_execution_id != result.discovery_execution_id:
                raise DiscoveryCompletionReplayError(
                    "group execution conflicts with completed result"
                )
            groups.append(group)
        return tuple(groups)

    def get_finalized_group_read_models(
        self, discovery_execution_id: str
    ) -> tuple[FinalizedGroupReadModel, ...]:
        read_models = []
        for group in self.get_finalized_groups(discovery_execution_id):
            observation = self._observation_repository.get_observation(
                group.representative_observation_id
            )
            if observation is None:
                raise DiscoveryCompletionReplayError(
                    "completed group references a missing representative observation"
                )
            if not isinstance(observation, CollectedProductObservation):
                raise DiscoveryCompletionReplayError(
                    "observation repository returned malformed representative lineage"
                )
            if (
                observation.observation_id != group.representative_observation_id
                or observation.discovery_execution_id
                != group.discovery_execution_id
            ):
                raise DiscoveryCompletionReplayError(
                    "representative observation conflicts with finalized group lineage"
                )
            product = observation.product
            read_models.append(
                FinalizedGroupReadModel(
                    group=group,
                    representative_observation=RepresentativeObservationPreview(
                        title=product.title,
                        image_url=product.image_url,
                        marketplace=product.marketplace,
                        price=product.price,
                        currency=product.currency,
                        url=product.url,
                    ),
                    observation_count=len(group.observation_ids),
                )
            )
        return tuple(read_models)


__all__ = [
    "FinalizedGroupReadModel",
    "PersistedDiscoveryResultReader",
    "RepresentativeObservationPreview",
]
