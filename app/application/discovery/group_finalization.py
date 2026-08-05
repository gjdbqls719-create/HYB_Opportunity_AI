"""Application assembly of Engine grouping facts into finalized Groups."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.application.discovery.ports import (
    FinalizedGroupIdentityProvider,
    GroupFinalizationClock,
)
from app.domain.discovery_identity import (
    CollectedProductObservation,
    FinalizedProductGroup,
)
from engine.grouping_policy import GroupingPolicyDescriptor

if TYPE_CHECKING:
    from app.application.discovery.production_execution import GroupingCorrelation


class GroupFinalizationCorrelationError(RuntimeError):
    pass


def assemble_finalized_product_groups(
    *,
    discovery_execution_id: str,
    observations: tuple[CollectedProductObservation, ...],
    grouping_correlations: tuple[GroupingCorrelation, ...],
    grouping_policy_descriptor: GroupingPolicyDescriptor,
    identity_provider: FinalizedGroupIdentityProvider,
    clock: GroupFinalizationClock,
) -> tuple[FinalizedProductGroup, ...]:
    if not isinstance(observations, tuple):
        raise TypeError("observations must be tuple")
    if not isinstance(grouping_correlations, tuple):
        raise TypeError("grouping_correlations must be tuple")
    if not isinstance(grouping_policy_descriptor, GroupingPolicyDescriptor):
        raise TypeError(
            "grouping_policy_descriptor must be GroupingPolicyDescriptor"
        )
    if not isinstance(identity_provider, FinalizedGroupIdentityProvider):
        raise TypeError(
            "identity_provider must be FinalizedGroupIdentityProvider"
        )
    if not isinstance(clock, GroupFinalizationClock):
        raise TypeError("clock must be GroupFinalizationClock")
    if any(
        observation.discovery_execution_id != discovery_execution_id
        for observation in observations
    ):
        raise GroupFinalizationCorrelationError(
            "observation execution identity conflicts with finalization execution"
        )
    if any(
        position >= len(observations)
        for correlation in grouping_correlations
        for position in correlation.ordered_member_collection_positions
    ):
        raise GroupFinalizationCorrelationError(
            "grouping correlation references a missing observation position"
        )

    return tuple(
        _assemble_group(
            discovery_execution_id=discovery_execution_id,
            observations=observations,
            correlation=correlation,
            grouping_policy_descriptor=grouping_policy_descriptor,
            identity_provider=identity_provider,
            clock=clock,
        )
        for correlation in grouping_correlations
    )


def _assemble_group(
    *,
    discovery_execution_id: str,
    observations: tuple[CollectedProductObservation, ...],
    correlation: GroupingCorrelation,
    grouping_policy_descriptor: GroupingPolicyDescriptor,
    identity_provider: FinalizedGroupIdentityProvider,
    clock: GroupFinalizationClock,
) -> FinalizedProductGroup:
    return FinalizedProductGroup(
        finalized_group_id=identity_provider.provide_finalized_group_id(),
        discovery_execution_id=discovery_execution_id,
        observation_ids=tuple(
            observations[position].observation_id
            for position in correlation.ordered_member_collection_positions
        ),
        grouping_policy_version=grouping_policy_descriptor.policy_version,
        representative_observation_id=(
            observations[
                correlation.representative_collection_position
            ].observation_id
        ),
        finalized_at=clock(),
    )


__all__ = [
    "GroupFinalizationCorrelationError",
    "assemble_finalized_product_groups",
]
