"""Application owner for a persisted production discovery execution entry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.application.discovery_persistence import (
    DiscoveryObservationRepository,
    PersistDiscoveryCommand,
    PersistDiscoveryCommandResult,
)
from app.application.discovery.observation_assembly import (
    assemble_collected_product_observations,
)
from app.application.discovery.ports import ObservationIdentityProvider
from app.domain.discovery import DiscoveryResult
from app.domain.discovery_identity import CollectedProductObservation, DiscoveryCommand
from collectors.collection_fact import CollectionFact
from engine.grouping_policy import GroupingPolicyDescriptor


class DiscoveryRuntimeCorrelationError(RuntimeError):
    pass


CollectionCheckpointHandler = Callable[[tuple[CollectionFact, ...]], None]


@dataclass(frozen=True, slots=True)
class GroupingCorrelation:
    ordered_member_collection_positions: tuple[int, ...]
    representative_collection_position: int

    def __post_init__(self) -> None:
        positions = self.ordered_member_collection_positions
        if not isinstance(positions, tuple) or not positions:
            raise ValueError(
                "ordered_member_collection_positions must be a non-empty tuple"
            )
        if any(
            isinstance(position, bool)
            or not isinstance(position, int)
            or position < 0
            for position in positions
        ):
            raise ValueError("collection positions must be non-negative integers")
        if len(set(positions)) != len(positions):
            raise ValueError("member collection positions must be unique")
        representative = self.representative_collection_position
        if (
            isinstance(representative, bool)
            or not isinstance(representative, int)
            or representative < 0
        ):
            raise ValueError(
                "representative_collection_position must be a non-negative integer"
            )
        if representative not in positions:
            raise ValueError(
                "representative collection position must belong to the group"
            )


GroupingCheckpointHandler = Callable[
    [tuple[GroupingCorrelation, ...], GroupingPolicyDescriptor],
    None,
]


@dataclass(frozen=True, slots=True)
class ProductionDiscoveryRuntimeResult:
    discovery_execution_id: str
    discovery_results: tuple[DiscoveryResult, ...]
    collection_facts: tuple[CollectionFact, ...]
    grouping_correlations: tuple[GroupingCorrelation, ...] = ()

    def __post_init__(self) -> None:
        if (
            not isinstance(self.discovery_execution_id, str)
            or not self.discovery_execution_id.strip()
        ):
            raise ValueError("discovery_execution_id must be non-empty text")
        if not isinstance(self.discovery_results, tuple):
            raise TypeError("discovery_results must be tuple")
        if not all(
            isinstance(result, DiscoveryResult)
            for result in self.discovery_results
        ):
            raise TypeError(
                "discovery_results must contain DiscoveryResult values"
            )
        if not isinstance(self.collection_facts, tuple):
            raise TypeError("collection_facts must be tuple")
        if not all(
            isinstance(fact, CollectionFact) for fact in self.collection_facts
        ):
            raise TypeError("collection_facts must contain CollectionFact values")
        if not isinstance(self.grouping_correlations, tuple):
            raise TypeError("grouping_correlations must be tuple")
        if not all(
            isinstance(correlation, GroupingCorrelation)
            for correlation in self.grouping_correlations
        ):
            raise TypeError(
                "grouping_correlations must contain GroupingCorrelation values"
            )
        if any(
            position >= len(self.collection_facts)
            for correlation in self.grouping_correlations
            for position in correlation.ordered_member_collection_positions
        ):
            raise ValueError("grouping correlation references a missing collection fact")


class ProductionDiscoveryRuntime(Protocol):
    """Runs discovery from an already committed command."""

    def execute(
        self,
        command: DiscoveryCommand,
        *,
        collection_checkpoint_handler: CollectionCheckpointHandler | None = None,
        grouping_checkpoint_handler: GroupingCheckpointHandler | None = None,
    ) -> ProductionDiscoveryRuntimeResult: ...


@dataclass(frozen=True, slots=True)
class PersistedDiscoveryExecutionResult:
    command_result: PersistDiscoveryCommandResult
    discovery_results: tuple[DiscoveryResult, ...]
    collection_facts: tuple[CollectionFact, ...]
    observations: tuple[CollectedProductObservation, ...]
    grouping_correlations: tuple[GroupingCorrelation, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.command_result, PersistDiscoveryCommandResult):
            raise TypeError(
                "command_result must be PersistDiscoveryCommandResult"
            )
        if not isinstance(self.discovery_results, tuple):
            raise TypeError("discovery_results must be tuple")
        if not all(
            isinstance(result, DiscoveryResult)
            for result in self.discovery_results
        ):
            raise TypeError(
                "discovery_results must contain DiscoveryResult values"
            )
        if not isinstance(self.collection_facts, tuple):
            raise TypeError("collection_facts must be tuple")
        if not all(
            isinstance(fact, CollectionFact) for fact in self.collection_facts
        ):
            raise TypeError("collection_facts must contain CollectionFact values")
        if not isinstance(self.grouping_correlations, tuple):
            raise TypeError("grouping_correlations must be tuple")
        if not all(
            isinstance(correlation, GroupingCorrelation)
            for correlation in self.grouping_correlations
        ):
            raise TypeError(
                "grouping_correlations must contain GroupingCorrelation values"
            )
        if any(
            position >= len(self.collection_facts)
            for correlation in self.grouping_correlations
            for position in correlation.ordered_member_collection_positions
        ):
            raise ValueError("grouping correlation references a missing collection fact")
        if not isinstance(self.observations, tuple):
            raise TypeError("observations must be tuple")
        if not all(
            isinstance(observation, CollectedProductObservation)
            for observation in self.observations
        ):
            raise TypeError(
                "observations must contain CollectedProductObservation values"
            )


class PersistedDiscoveryExecutionEntry:
    """Persists command identity before running the production discovery runtime."""

    def __init__(
        self,
        *,
        persist_command: PersistDiscoveryCommand,
        runtime: ProductionDiscoveryRuntime,
        observation_identity_provider: ObservationIdentityProvider,
        observation_repository: DiscoveryObservationRepository,
    ) -> None:
        if not isinstance(observation_identity_provider, ObservationIdentityProvider):
            raise TypeError(
                "observation_identity_provider must be ObservationIdentityProvider"
            )
        self._persist_command = persist_command
        self._runtime = runtime
        self._observation_identity_provider = observation_identity_provider
        self._observation_repository = observation_repository

    def execute(
        self,
        command: DiscoveryCommand,
    ) -> PersistedDiscoveryExecutionResult:
        if not isinstance(command, DiscoveryCommand):
            raise TypeError("command must be DiscoveryCommand")

        command_result = self._persist_command.execute(command)
        persisted_observations: tuple[CollectedProductObservation, ...] = ()
        checkpointed_grouping_correlations: tuple[GroupingCorrelation, ...] = ()

        def persist_collection_checkpoint(
            collection_facts: tuple[CollectionFact, ...],
        ) -> None:
            nonlocal persisted_observations
            observations = assemble_collected_product_observations(
                discovery_execution_id=(
                    command_result.command.discovery_execution_id
                ),
                collection_facts=collection_facts,
                identity_provider=self._observation_identity_provider,
            )
            persisted_observations = tuple(
                self._observation_repository.save_observation(observation)
                for observation in observations
            )

        def receive_grouping_checkpoint(
            grouping_correlations: tuple[GroupingCorrelation, ...],
            grouping_policy_descriptor: GroupingPolicyDescriptor,
        ) -> None:
            nonlocal checkpointed_grouping_correlations
            checkpointed_grouping_correlations = grouping_correlations

        runtime_result = self._runtime.execute(
            command_result.command,
            collection_checkpoint_handler=persist_collection_checkpoint,
            grouping_checkpoint_handler=receive_grouping_checkpoint,
        )
        if not isinstance(runtime_result, ProductionDiscoveryRuntimeResult):
            raise TypeError(
                "runtime must return ProductionDiscoveryRuntimeResult"
            )
        if (
            runtime_result.discovery_execution_id
            != command_result.command.discovery_execution_id
        ):
            raise DiscoveryRuntimeCorrelationError(
                "runtime execution identity conflicts with committed command"
            )

        return PersistedDiscoveryExecutionResult(
            command_result=command_result,
            discovery_results=runtime_result.discovery_results,
            collection_facts=runtime_result.collection_facts,
            observations=persisted_observations,
            grouping_correlations=checkpointed_grouping_correlations,
        )


__all__ = [
    "CollectionCheckpointHandler",
    "DiscoveryRuntimeCorrelationError",
    "GroupingCorrelation",
    "GroupingCheckpointHandler",
    "PersistedDiscoveryExecutionEntry",
    "PersistedDiscoveryExecutionResult",
    "ProductionDiscoveryRuntime",
    "ProductionDiscoveryRuntimeResult",
]
