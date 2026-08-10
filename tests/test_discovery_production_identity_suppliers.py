from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import re

import pytest

from app.application.discovery import (
    CandidateDiscoveryReferenceProvider,
    FinalizedGroupIdentityProvider,
    ObservationIdentityProvider,
    PersistedDiscoveryExecutionEntry,
)
from app.infrastructure.discovery import (
    ProductionCandidateDiscoveryReferenceProvider,
    ProductionFinalizedGroupIdentityProvider,
    ProductionObservationIdentityProvider,
)
import app.infrastructure.discovery.identity_suppliers as identity_suppliers
from tests.test_application_group_finalization import (
    FINALIZED_AT,
    RecordingGroupFinalizationClock,
)
from tests.test_discovery_completion_replay import (
    ForbiddenClock,
    ForbiddenRuntime,
    ReplayGroupRepository,
    ReplayObservationRepository,
    ReplayPersister,
    ReplayResultRepository,
    completed_result,
    groups,
    observations,
)
from tests.test_discovery_execution_completion import (
    COMPLETED_AT,
    RecordingDiscoveryCompletionClock,
    RecordingResultRepository,
)
from tests.test_discovery_phase_checkpoints import (
    CheckpointObservationRepository,
    CheckpointRuntime,
)
from tests.test_finalized_group_persistence import RecordingGroupRepository
from tests.test_persisted_discovery_execution_entry import (
    RecordingPersister,
    RecordingRuntime,
    command,
)


OPAQUE_ID = re.compile(r"^[0-9a-f]{32}$")


def test_production_suppliers_implement_the_existing_application_ports() -> None:
    observation = ProductionObservationIdentityProvider()
    candidate_reference = ProductionCandidateDiscoveryReferenceProvider()
    finalized_group = ProductionFinalizedGroupIdentityProvider()

    assert isinstance(observation, ObservationIdentityProvider)
    assert isinstance(candidate_reference, CandidateDiscoveryReferenceProvider)
    assert isinstance(finalized_group, FinalizedGroupIdentityProvider)
    assert not hasattr(observation, "__dict__")
    assert not hasattr(candidate_reference, "__dict__")
    assert not hasattr(finalized_group, "__dict__")


def test_production_suppliers_issue_fresh_input_free_opaque_identities() -> None:
    observation = ProductionObservationIdentityProvider()
    candidate_reference = ProductionCandidateDiscoveryReferenceProvider()
    finalized_group = ProductionFinalizedGroupIdentityProvider()

    opaque_values = (
        observation.provide_observation_id(),
        observation.provide_observation_id(),
        finalized_group.provide_finalized_group_id(),
        finalized_group.provide_finalized_group_id(),
    )
    candidate_references = (
        candidate_reference.provide_candidate_discovery_reference(),
        candidate_reference.provide_candidate_discovery_reference(),
    )

    assert all(OPAQUE_ID.fullmatch(value) for value in opaque_values)
    assert all(
        value.startswith("discovery-candidate-handoff:")
        and OPAQUE_ID.fullmatch(value.split(":", 1)[1])
        for value in candidate_references
    )
    assert len(set(opaque_values + candidate_references)) == (
        len(opaque_values) + len(candidate_references)
    )


def test_production_suppliers_have_no_shared_mutable_concurrent_state() -> None:
    observation = ProductionObservationIdentityProvider()
    finalized_group = ProductionFinalizedGroupIdentityProvider()

    def issue(position: int) -> str:
        if position % 2:
            return observation.provide_observation_id()
        return finalized_group.provide_finalized_group_id()

    with ThreadPoolExecutor(max_workers=16) as pool:
        values = tuple(pool.map(issue, range(512)))

    assert all(OPAQUE_ID.fullmatch(value) for value in values)
    assert len(set(values)) == len(values)


def test_concurrent_discovery_executions_receive_distinct_identities() -> None:
    observation = ProductionObservationIdentityProvider()
    finalized_group = ProductionFinalizedGroupIdentityProvider()

    def execute(position: int) -> tuple[str, ...]:
        events: list[str] = []
        value = replace(
            command(),
            command_id=f"command-{position}",
            discovery_execution_id=f"execution-{position}",
        )
        result = PersistedDiscoveryExecutionEntry(
            persist_command=RecordingPersister(events),
            runtime=CheckpointRuntime(events),
            observation_identity_provider=observation,
            observation_repository=CheckpointObservationRepository(events),
            finalized_group_identity_provider=finalized_group,
            group_finalization_clock=RecordingGroupFinalizationClock(FINALIZED_AT),
            group_repository=RecordingGroupRepository(events),
            discovery_completion_clock=RecordingDiscoveryCompletionClock(
                COMPLETED_AT
            ),
            result_repository=RecordingResultRepository(events),
        ).execute(value)
        return tuple(item.observation_id for item in result.observations) + tuple(
            item.finalized_group_id for item in result.finalized_groups
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        identities = tuple(
            identity
            for execution_ids in pool.map(execute, range(32))
            for identity in execution_ids
        )

    assert len(identities) == 32 * 3
    assert len(set(identities)) == len(identities)


def test_production_suppliers_flow_unchanged_through_discovery_persistence() -> None:
    events: list[str] = []
    runtime = CheckpointRuntime(events)
    observation_repository = CheckpointObservationRepository(events)
    group_repository = RecordingGroupRepository(events)

    result = PersistedDiscoveryExecutionEntry(
        persist_command=RecordingPersister(events),
        runtime=runtime,
        observation_identity_provider=ProductionObservationIdentityProvider(),
        candidate_discovery_reference_provider=(
            ProductionCandidateDiscoveryReferenceProvider()
        ),
        observation_repository=observation_repository,
        finalized_group_identity_provider=(
            ProductionFinalizedGroupIdentityProvider()
        ),
        group_finalization_clock=RecordingGroupFinalizationClock(FINALIZED_AT),
        group_repository=group_repository,
        discovery_completion_clock=RecordingDiscoveryCompletionClock(COMPLETED_AT),
        result_repository=RecordingResultRepository(events),
    ).execute(command())

    observation_ids = tuple(value.observation_id for value in result.observations)
    group_ids = tuple(value.finalized_group_id for value in result.finalized_groups)
    assert len(observation_ids) == len(runtime.collection_facts) == 2
    assert len(group_ids) == len(runtime.grouping_correlations) == 1
    assert all(OPAQUE_ID.fullmatch(value) for value in observation_ids + group_ids)
    assert tuple(value.observation_id for value in observation_repository.calls) == (
        observation_ids
    )
    assert tuple(value.finalized_group_id for value in group_repository.calls) == (
        group_ids
    )
    assert result.execution_result.finalized_group_ids == group_ids


def test_zero_result_does_not_request_either_identity(monkeypatch) -> None:
    def fail() -> object:
        pytest.fail("zero-result execution must not request an identity")

    monkeypatch.setattr(identity_suppliers, "uuid4", fail)
    events: list[str] = []
    runtime = RecordingRuntime(events)

    result = PersistedDiscoveryExecutionEntry(
        persist_command=RecordingPersister(events),
        runtime=runtime,
        observation_identity_provider=ProductionObservationIdentityProvider(),
        candidate_discovery_reference_provider=(
            ProductionCandidateDiscoveryReferenceProvider()
        ),
        observation_repository=CheckpointObservationRepository(events),
        finalized_group_identity_provider=(
            ProductionFinalizedGroupIdentityProvider()
        ),
        group_finalization_clock=RecordingGroupFinalizationClock(),
        group_repository=RecordingGroupRepository(events),
        discovery_completion_clock=RecordingDiscoveryCompletionClock(COMPLETED_AT),
        result_repository=RecordingResultRepository(events),
    ).execute(command())

    assert result.observations == ()
    assert result.finalized_groups == ()
    assert result.execution_result.is_zero_result is True


def test_completed_replay_does_not_request_either_identity(monkeypatch) -> None:
    def fail() -> object:
        pytest.fail("completed replay must not request an identity")

    monkeypatch.setattr(identity_suppliers, "uuid4", fail)
    events: list[str] = []

    result = PersistedDiscoveryExecutionEntry(
        persist_command=ReplayPersister(events),
        runtime=ForbiddenRuntime(),
        observation_identity_provider=ProductionObservationIdentityProvider(),
        candidate_discovery_reference_provider=(
            ProductionCandidateDiscoveryReferenceProvider()
        ),
        observation_repository=ReplayObservationRepository(events, observations()),
        finalized_group_identity_provider=(
            ProductionFinalizedGroupIdentityProvider()
        ),
        group_finalization_clock=ForbiddenClock(),
        group_repository=ReplayGroupRepository(events, groups()),
        discovery_completion_clock=ForbiddenClock(),
        result_repository=ReplayResultRepository(events, completed_result()),
    ).execute(command())

    assert result.completion_replayed is True
    assert result.execution_result == completed_result()
