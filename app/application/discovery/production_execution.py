"""Application owner for a persisted production discovery execution entry."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from app.application.discovery_persistence import (
    DiscoveryGroupRepository,
    DiscoveryObservationRepository,
    DiscoveryResultRepository,
    PersistDiscoveryCommand,
    PersistDiscoveryCommandResult,
)
from app.application.discovery.observation_assembly import (
    assemble_collected_product_observations,
)
from app.application.discovery.group_finalization import (
    assemble_finalized_product_groups,
)
from app.application.discovery.ports import (
    CandidateDiscoveryReferenceProvider,
    DiscoveryCompletionClock,
    FinalizedGroupIdentityProvider,
    GroupFinalizationClock,
    ObservationIdentityProvider,
)
from app.domain.discovery import DiscoveryResult
from app.domain.discovery_identity import (
    CollectedProductObservation,
    DiscoveryCommand,
    DiscoveryExecutionResult,
    FinalizedProductGroup,
)
from collectors.collection_fact import CollectionFact
from engine.grouping_policy import GroupingPolicyDescriptor


class DiscoveryRuntimeCorrelationError(RuntimeError):
    pass


class DiscoveryCompletionReplayError(RuntimeError):
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
    tuple[str, ...],
]


def _validate_result_group_correlation(
    discovery_results: tuple[DiscoveryResult, ...],
    finalized_groups: tuple[FinalizedProductGroup, ...],
) -> None:
    expected_ids = tuple(group.finalized_group_id for group in finalized_groups)
    result_ids = tuple(result.finalized_group_id for result in discovery_results)
    if len(result_ids) != len(expected_ids):
        raise DiscoveryRuntimeCorrelationError(
            "runtime result correlation count differs from finalized group count"
        )
    if any(group_id is None for group_id in result_ids):
        raise DiscoveryRuntimeCorrelationError(
            "runtime result is missing finalized group correlation"
        )
    if len(set(result_ids)) != len(result_ids):
        raise DiscoveryRuntimeCorrelationError(
            "runtime result contains duplicate finalized group correlation"
        )
    unknown_ids = set(result_ids) - set(expected_ids)
    if unknown_ids:
        raise DiscoveryRuntimeCorrelationError(
            "runtime result contains unknown finalized group correlation"
        )
    lost_ids = set(expected_ids) - set(result_ids)
    if lost_ids:
        raise DiscoveryRuntimeCorrelationError(
            "finalized group result correlation was lost after analysis or sorting"
        )


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
    execution_result: DiscoveryExecutionResult
    grouping_correlations: tuple[GroupingCorrelation, ...] = ()
    finalized_groups: tuple[FinalizedProductGroup, ...] = ()
    completion_replayed: bool = False

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
        if not isinstance(self.execution_result, DiscoveryExecutionResult):
            raise TypeError("execution_result must be DiscoveryExecutionResult")
        if not isinstance(self.finalized_groups, tuple):
            raise TypeError("finalized_groups must be tuple")
        if not all(
            isinstance(group, FinalizedProductGroup)
            for group in self.finalized_groups
        ):
            raise TypeError(
                "finalized_groups must contain FinalizedProductGroup values"
            )
        if not isinstance(self.completion_replayed, bool):
            raise TypeError("completion_replayed must be bool")


class PersistedDiscoveryExecutionEntry:
    """Persists command identity before running the production discovery runtime."""

    def __init__(
        self,
        *,
        persist_command: PersistDiscoveryCommand,
        runtime: ProductionDiscoveryRuntime,
        observation_identity_provider: ObservationIdentityProvider,
        observation_repository: DiscoveryObservationRepository,
        finalized_group_identity_provider: FinalizedGroupIdentityProvider,
        group_finalization_clock: GroupFinalizationClock,
        group_repository: DiscoveryGroupRepository,
        discovery_completion_clock: DiscoveryCompletionClock,
        result_repository: DiscoveryResultRepository,
        candidate_discovery_reference_provider: (
            CandidateDiscoveryReferenceProvider | None
        ) = None,
    ) -> None:
        if not isinstance(observation_identity_provider, ObservationIdentityProvider):
            raise TypeError(
                "observation_identity_provider must be ObservationIdentityProvider"
            )
        if not isinstance(
            finalized_group_identity_provider,
            FinalizedGroupIdentityProvider,
        ):
            raise TypeError(
                "finalized_group_identity_provider must be "
                "FinalizedGroupIdentityProvider"
            )
        if (
            candidate_discovery_reference_provider is not None
            and not isinstance(
                candidate_discovery_reference_provider,
                CandidateDiscoveryReferenceProvider,
            )
        ):
            raise TypeError(
                "candidate_discovery_reference_provider must be "
                "CandidateDiscoveryReferenceProvider"
            )
        if not isinstance(group_finalization_clock, GroupFinalizationClock):
            raise TypeError(
                "group_finalization_clock must be GroupFinalizationClock"
            )
        if not isinstance(discovery_completion_clock, DiscoveryCompletionClock):
            raise TypeError(
                "discovery_completion_clock must be DiscoveryCompletionClock"
            )
        self._persist_command = persist_command
        self._runtime = runtime
        self._observation_identity_provider = observation_identity_provider
        self._candidate_discovery_reference_provider = (
            candidate_discovery_reference_provider
        )
        self._observation_repository = observation_repository
        self._finalized_group_identity_provider = (
            finalized_group_identity_provider
        )
        self._group_finalization_clock = group_finalization_clock
        self._group_repository = group_repository
        self._discovery_completion_clock = discovery_completion_clock
        self._result_repository = result_repository

    def _completed_replay_response(
        self,
        command_result: PersistDiscoveryCommandResult,
        execution_result: DiscoveryExecutionResult,
    ) -> PersistedDiscoveryExecutionResult:
        committed_command = command_result.command
        if (
            execution_result.command_id != committed_command.command_id
            or execution_result.discovery_execution_id
            != committed_command.discovery_execution_id
        ):
            raise DiscoveryCompletionReplayError(
                "completed result execution identity conflicts with committed command"
            )

        observations = self._observation_repository.get_by_execution(
            execution_result.discovery_execution_id
        )
        if not isinstance(observations, tuple) or not all(
            isinstance(observation, CollectedProductObservation)
            for observation in observations
        ):
            raise DiscoveryCompletionReplayError(
                "observation repository returned malformed replay lineage"
            )
        if any(
            observation.discovery_execution_id
            != execution_result.discovery_execution_id
            for observation in observations
        ):
            raise DiscoveryCompletionReplayError(
                "observation execution conflicts with completed result"
            )
        observations_by_id = {
            observation.observation_id: observation
            for observation in observations
        }
        if len(observations_by_id) != len(observations):
            raise DiscoveryCompletionReplayError(
                "completed replay contains duplicate observation identity"
            )

        finalized_groups = []
        for finalized_group_id in execution_result.finalized_group_ids:
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
            if (
                group.discovery_execution_id
                != execution_result.discovery_execution_id
            ):
                raise DiscoveryCompletionReplayError(
                    "group execution conflicts with completed result"
                )
            if any(
                observation_id not in observations_by_id
                for observation_id in group.observation_ids
            ):
                raise DiscoveryCompletionReplayError(
                    "finalized group references a missing observation"
                )
            finalized_groups.append(group)

        return PersistedDiscoveryExecutionResult(
            command_result=command_result,
            discovery_results=(),
            collection_facts=(),
            observations=observations,
            execution_result=execution_result,
            grouping_correlations=(),
            finalized_groups=tuple(finalized_groups),
            completion_replayed=True,
        )

    def execute(
        self,
        command: DiscoveryCommand,
    ) -> PersistedDiscoveryExecutionResult:
        if not isinstance(command, DiscoveryCommand):
            raise TypeError("command must be DiscoveryCommand")

        command_result = self._persist_command.execute(command)
        if command_result.replayed:
            completed_result = self._result_repository.get_by_command(
                command_result.command.command_id
            )
            if completed_result is not None:
                if not isinstance(completed_result, DiscoveryExecutionResult):
                    raise DiscoveryCompletionReplayError(
                        "result repository returned malformed completion"
                    )
                return self._completed_replay_response(
                    command_result,
                    completed_result,
                )
        persisted_observations: tuple[CollectedProductObservation, ...] = ()
        checkpointed_grouping_correlations: tuple[GroupingCorrelation, ...] = ()
        finalized_groups: tuple[FinalizedProductGroup, ...] = ()

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
                candidate_discovery_reference_provider=(
                    self._candidate_discovery_reference_provider
                ),
            )
            persisted_observations = tuple(
                self._observation_repository.save_observation(observation)
                for observation in observations
            )

        def receive_grouping_checkpoint(
            grouping_correlations: tuple[GroupingCorrelation, ...],
            grouping_policy_descriptor: GroupingPolicyDescriptor,
        ) -> tuple[str, ...]:
            nonlocal checkpointed_grouping_correlations, finalized_groups
            checkpointed_grouping_correlations = grouping_correlations
            assembled_groups = assemble_finalized_product_groups(
                discovery_execution_id=(
                    command_result.command.discovery_execution_id
                ),
                observations=persisted_observations,
                grouping_correlations=grouping_correlations,
                grouping_policy_descriptor=grouping_policy_descriptor,
                identity_provider=self._finalized_group_identity_provider,
                clock=self._group_finalization_clock,
            )
            finalized_groups = tuple(
                self._group_repository.save_group(group)
                for group in assembled_groups
            )
            return tuple(group.finalized_group_id for group in finalized_groups)

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
        _validate_result_group_correlation(
            runtime_result.discovery_results,
            finalized_groups,
        )

        execution_result = DiscoveryExecutionResult(
            command_id=command_result.command.command_id,
            discovery_execution_id=(
                command_result.command.discovery_execution_id
            ),
            finalized_group_ids=tuple(
                group.finalized_group_id for group in finalized_groups
            ),
            completed_at=self._discovery_completion_clock(),
        )
        persisted_execution_result = self._result_repository.save_result(
            execution_result
        )

        return PersistedDiscoveryExecutionResult(
            command_result=command_result,
            discovery_results=runtime_result.discovery_results,
            collection_facts=runtime_result.collection_facts,
            observations=persisted_observations,
            execution_result=persisted_execution_result,
            grouping_correlations=checkpointed_grouping_correlations,
            finalized_groups=finalized_groups,
        )


__all__ = [
    "CollectionCheckpointHandler",
    "DiscoveryCompletionReplayError",
    "DiscoveryRuntimeCorrelationError",
    "GroupingCorrelation",
    "GroupingCheckpointHandler",
    "PersistedDiscoveryExecutionEntry",
    "PersistedDiscoveryExecutionResult",
    "ProductionDiscoveryRuntime",
    "ProductionDiscoveryRuntimeResult",
]
