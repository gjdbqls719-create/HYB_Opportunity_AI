from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from app.application.discovery import (
    DiscoveryCompletionReplayError,
    PersistedDiscoveryExecutionEntry,
)
from app.application.discovery_persistence import (
    DiscoveryReplayConflict,
    PersistDiscoveryCommand,
)
from app.domain.discovery_identity import DiscoveryExecutionResult
from app.infrastructure.discovery import (
    SQLiteDiscoveryCommandRepository,
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
    SQLiteDiscoveryResultRepository,
)
from tests.test_application_group_finalization import (
    RecordingFinalizedGroupIdentityProvider,
    RecordingGroupFinalizationClock,
)
from tests.test_discovery_correlation_contract import group, observation
from tests.test_discovery_execution_completion import COMPLETED_AT, sqlite_entry
from tests.test_persisted_discovery_execution_entry import (
    RecordingObservationIdentityProvider,
    RecordingObservationRepository,
    RecordingRuntime,
    command,
    persist_result,
)


class ReplayPersister:
    def __init__(self, events: list[str], *, fail: Exception | None = None) -> None:
        self.events = events
        self.fail = fail
        self.calls = []

    def execute(self, value):
        self.events.append("persist")
        self.calls.append(value)
        if self.fail is not None:
            raise self.fail
        return persist_result(value, replayed=True)


class ForbiddenRuntime:
    def __init__(self) -> None:
        self.calls = []

    def execute(self, value, **kwargs):
        self.calls.append(value)
        pytest.fail("completed replay must not execute Runtime or marketplace")


class ForbiddenObservationIdentityProvider:
    def provide_observation_id(self) -> str:
        pytest.fail("completed replay must not request an observation ID")


class ForbiddenFinalizedGroupIdentityProvider:
    def provide_finalized_group_id(self) -> str:
        pytest.fail("completed replay must not request a finalized Group ID")


class ForbiddenClock:
    def __call__(self):
        pytest.fail("completed replay must not call a clock")


def observations():
    return (
        observation(observation_id="observation-1"),
        observation(observation_id="observation-2"),
    )


def groups():
    return (
        group(
            finalized_group_id="group-1",
            observation_ids=("observation-2", "observation-1"),
            representative_observation_id="observation-1",
        ),
        group(
            finalized_group_id="group-2",
            observation_ids=("observation-1",),
            representative_observation_id="observation-1",
        ),
    )


def completed_result(*, group_ids=("group-2", "group-1")):
    return DiscoveryExecutionResult(
        command_id="command-1",
        discovery_execution_id="execution-1",
        finalized_group_ids=group_ids,
        completed_at=COMPLETED_AT,
    )


class ReplayResultRepository:
    def __init__(
        self,
        events: list[str],
        value,
        *,
        fail: Exception | None = None,
    ) -> None:
        self.events = events
        self.value = value
        self.fail = fail
        self.lookups = []

    def get_by_command(self, command_id):
        self.events.append("result-lookup")
        self.lookups.append(command_id)
        if self.fail is not None:
            raise self.fail
        return self.value

    def save_result(self, result):
        pytest.fail("completed replay must not save a result")


class ReplayObservationRepository:
    def __init__(self, events: list[str], values) -> None:
        self.events = events
        self.values = values
        self.lookups = []

    def get_by_execution(self, execution_id):
        self.events.append("observation-lookup")
        self.lookups.append(execution_id)
        return self.values

    def save_observation(self, value):
        pytest.fail("completed replay must not save an observation")


class ReplayGroupRepository:
    def __init__(self, events: list[str], values) -> None:
        self.events = events
        self.values = {
            value.finalized_group_id: value for value in values
        }
        self.lookups = []

    def get_group(self, group_id):
        self.events.append(f"group-lookup:{group_id}")
        self.lookups.append(group_id)
        return self.values.get(group_id)

    def save_group(self, value):
        pytest.fail("completed replay must not save a finalized Group")


def replay_entry(
    events,
    *,
    result=None,
    observation_values=None,
    group_values=None,
    persister=None,
    runtime=None,
    result_repository=None,
):
    return PersistedDiscoveryExecutionEntry(
        persist_command=persister or ReplayPersister(events),
        runtime=runtime or ForbiddenRuntime(),
        observation_identity_provider=ForbiddenObservationIdentityProvider(),
        observation_repository=ReplayObservationRepository(
            events,
            observations() if observation_values is None else observation_values,
        ),
        finalized_group_identity_provider=(
            ForbiddenFinalizedGroupIdentityProvider()
        ),
        group_finalization_clock=ForbiddenClock(),
        group_repository=ReplayGroupRepository(
            events,
            groups() if group_values is None else group_values,
        ),
        discovery_completion_clock=ForbiddenClock(),
        result_repository=(
            result_repository
            or ReplayResultRepository(
                events,
                completed_result() if result is None else result,
            )
        ),
    )


def test_completed_replay_restores_authoritative_lineage_without_runtime() -> None:
    events: list[str] = []
    application = replay_entry(events)

    response = application.execute(command())

    assert events == [
        "persist",
        "result-lookup",
        "observation-lookup",
        "group-lookup:group-2",
        "group-lookup:group-1",
    ]
    assert response.command_result.replayed is True
    assert response.completion_replayed is True
    assert response.execution_result == completed_result()
    assert response.finalized_groups == (groups()[1], groups()[0])
    assert response.observations == observations()
    assert response.finalized_groups[1].observation_ids == (
        "observation-2",
        "observation-1",
    )
    assert response.finalized_groups[1].representative_observation_id == (
        "observation-1"
    )
    assert response.discovery_results == ()
    assert response.collection_facts == ()
    assert response.grouping_correlations == ()


def test_completed_zero_result_replay_is_explicit_and_runtime_free() -> None:
    events: list[str] = []
    zero = completed_result(group_ids=())

    response = replay_entry(events, result=zero, group_values=()).execute(command())

    assert response.execution_result is zero
    assert response.execution_result.is_zero_result is True
    assert response.finalized_groups == ()
    assert response.completion_replayed is True
    assert not any(event.startswith("group-lookup") for event in events)


def test_incomplete_command_replay_runs_existing_live_workflow() -> None:
    events: list[str] = []
    runtime = RecordingRuntime(events)

    class IncompleteResultRepository:
        def __init__(self) -> None:
            self.saved = []

        def get_by_command(self, command_id):
            events.append("result-lookup")
            return None

        def save_result(self, result):
            events.append("result-save")
            self.saved.append(result)
            return result

    results = IncompleteResultRepository()
    response = PersistedDiscoveryExecutionEntry(
        persist_command=ReplayPersister(events),
        runtime=runtime,
        observation_identity_provider=RecordingObservationIdentityProvider(),
        observation_repository=RecordingObservationRepository(),
        finalized_group_identity_provider=(
            RecordingFinalizedGroupIdentityProvider()
        ),
        group_finalization_clock=RecordingGroupFinalizationClock(),
        group_repository=ReplayGroupRepository(events, ()),
        discovery_completion_clock=lambda: COMPLETED_AT,
        result_repository=results,
    ).execute(command())

    assert events[:3] == ["persist", "result-lookup", "runtime"]
    assert runtime.calls == [command()]
    assert len(results.saved) == 1
    assert response.completion_replayed is False


def test_command_conflict_and_result_lookup_failure_never_run_runtime() -> None:
    events: list[str] = []
    result_repository = ReplayResultRepository(events, completed_result())
    with pytest.raises(DiscoveryReplayConflict):
        replay_entry(
            events,
            persister=ReplayPersister(
                events,
                fail=DiscoveryReplayConflict("changed command"),
            ),
            result_repository=result_repository,
        ).execute(command())
    assert result_repository.lookups == []
    assert events == ["persist"]

    events = []
    result_repository = ReplayResultRepository(
        events,
        completed_result(),
        fail=RuntimeError("result lookup failed"),
    )
    with pytest.raises(RuntimeError, match="result lookup failed"):
        replay_entry(
            events,
            result_repository=result_repository,
        ).execute(command())
    assert events == ["persist", "result-lookup"]


def test_completed_replay_rejects_malformed_result_contract() -> None:
    with pytest.raises(DiscoveryCompletionReplayError, match="malformed completion"):
        replay_entry([], result=object()).execute(command())


@pytest.mark.parametrize(
    ("result", "observation_values", "group_values", "message"),
    (
        (completed_result(), observations(), (groups()[0],), "missing finalized group"),
        (
            replace(completed_result(), discovery_execution_id="other-execution"),
            observations(),
            groups(),
            "execution",
        ),
        (
            completed_result(),
            (observations()[0],),
            groups(),
            "missing observation",
        ),
        (
            completed_result(),
            (
                observations()[0],
                replace(
                    observations()[1],
                    discovery_execution_id="other-execution",
                ),
            ),
            groups(),
            "observation execution",
        ),
        (
            completed_result(),
            observations(),
            (
                groups()[0],
                replace(groups()[1], discovery_execution_id="other-execution"),
            ),
            "group execution",
        ),
    ),
)
def test_completed_replay_rejects_missing_or_mismatched_lineage(
    result,
    observation_values,
    group_values,
    message,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        replay_entry(
            [],
            result=result,
            observation_values=observation_values,
            group_values=group_values,
        ).execute(command())


def sqlite_replay(path):
    commands = SQLiteDiscoveryCommandRepository(path)
    observations_repository = SQLiteDiscoveryObservationRepository(path)
    groups_repository = SQLiteDiscoveryGroupRepository(path)
    results_repository = SQLiteDiscoveryResultRepository(path)
    runtime = ForbiddenRuntime()
    application = PersistedDiscoveryExecutionEntry(
        persist_command=PersistDiscoveryCommand(
            commands,
            clock=lambda: pytest.fail("command replay must not call clock"),
        ),
        runtime=runtime,
        observation_identity_provider=ForbiddenObservationIdentityProvider(),
        observation_repository=observations_repository,
        finalized_group_identity_provider=(
            ForbiddenFinalizedGroupIdentityProvider()
        ),
        group_finalization_clock=ForbiddenClock(),
        group_repository=groups_repository,
        discovery_completion_clock=ForbiddenClock(),
        result_repository=results_repository,
    )
    try:
        return application.execute(command())
    finally:
        commands.close()
        observations_repository.close()
        groups_repository.close()
        results_repository.close()


def test_sqlite_restart_and_concurrent_completed_replays_are_runtime_free(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    application, *repositories = sqlite_entry(path, RecordingRuntime([]))
    live = application.execute(command())
    for repository in repositories:
        repository.close()

    restarted = sqlite_replay(path)
    assert restarted.execution_result == live.execution_result
    assert restarted.completion_replayed is True

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = tuple(pool.map(lambda _: sqlite_replay(path), range(2)))
    assert all(response.execution_result == live.execution_result for response in responses)
    assert all(response.completion_replayed is True for response in responses)
