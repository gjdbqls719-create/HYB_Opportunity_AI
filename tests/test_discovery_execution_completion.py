from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from app.application.discovery import (
    DiscoveryCompletionClock,
    GroupingCorrelation,
    PersistedDiscoveryExecutionEntry,
)
from app.application.discovery_persistence import (
    DiscoveryExecutionReplayConflict,
    PersistDiscoveryCommand,
)
from app.infrastructure.discovery import (
    SQLiteDiscoveryCommandRepository,
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
    SQLiteDiscoveryResultRepository,
)
from tests.test_application_group_finalization import (
    FINALIZED_AT,
    RecordingFinalizedGroupIdentityProvider,
    RecordingGroupFinalizationClock,
)
from tests.test_discovery_phase_checkpoints import (
    CheckpointObservationRepository,
    CheckpointRuntime,
)
from tests.test_finalized_group_persistence import RecordingGroupRepository
from tests.test_persisted_discovery_execution_entry import (
    NOW,
    RecordingObservationIdentityProvider,
    RecordingPersister,
    command,
)


COMPLETED_AT = datetime(2026, 8, 6, 4, 0, tzinfo=timezone.utc)


class RecordingDiscoveryCompletionClock:
    def __init__(
        self,
        value: datetime = COMPLETED_AT,
        *,
        events: list[str] | None = None,
        fail: Exception | None = None,
    ) -> None:
        self.value = value
        self.events = events
        self.fail = fail
        self.calls = 0

    def __call__(self) -> datetime:
        self.calls += 1
        if self.events is not None:
            self.events.append("completion-clock")
        if self.fail is not None:
            raise self.fail
        return self.value


class RecordingResultRepository:
    def __init__(
        self,
        events: list[str],
        *,
        fail: Exception | None = None,
        copy_on_return: bool = False,
    ) -> None:
        self.events = events
        self.fail = fail
        self.copy_on_return = copy_on_return
        self.calls = []
        self.returned = None

    def save_result(self, result):
        self.calls.append(result)
        self.events.append(f"result:{result.discovery_execution_id}")
        if self.fail is not None:
            raise self.fail
        self.returned = replace(result) if self.copy_on_return else result
        return self.returned


def entry(
    events,
    runtime,
    completion_clock,
    result_repository,
    *,
    persister=None,
    observation_repository=None,
    group_repository=None,
):
    return PersistedDiscoveryExecutionEntry(
        persist_command=persister or RecordingPersister(events),
        runtime=runtime,
        observation_identity_provider=RecordingObservationIdentityProvider(
            "observation-one",
            "observation-two",
        ),
        observation_repository=(
            observation_repository or CheckpointObservationRepository(events)
        ),
        finalized_group_identity_provider=(
            RecordingFinalizedGroupIdentityProvider("group-1", "group-2")
        ),
        group_finalization_clock=RecordingGroupFinalizationClock(
            FINALIZED_AT,
            FINALIZED_AT + timedelta(seconds=1),
        ),
        group_repository=group_repository or RecordingGroupRepository(events),
        discovery_completion_clock=completion_clock,
        result_repository=result_repository,
    )


def test_completion_clock_is_an_explicit_application_contract() -> None:
    assert isinstance(RecordingDiscoveryCompletionClock(), DiscoveryCompletionClock)
    assert not isinstance(object(), DiscoveryCompletionClock)


def test_success_commits_result_after_runtime_and_preserves_repository_return() -> None:
    events: list[str] = []
    runtime = CheckpointRuntime(events)
    runtime.grouping_correlations = (
        GroupingCorrelation((0,), 0),
        GroupingCorrelation((1,), 1),
    )
    clock = RecordingDiscoveryCompletionClock(events=events)
    repository = RecordingResultRepository(events, copy_on_return=True)

    response = entry(events, runtime, clock, repository).execute(command())

    assert events[-3:] == [
        "analysis",
        "completion-clock",
        "result:execution-1",
    ]
    assert clock.calls == 1
    assert len(repository.calls) == 1
    assembled = repository.calls[0]
    assert assembled.command_id == "command-1"
    assert assembled.discovery_execution_id == "execution-1"
    assert assembled.finalized_group_ids == ("group-1", "group-2")
    assert assembled.completed_at == COMPLETED_AT
    assert response.execution_result is repository.returned
    assert response.discovery_results == ()
    assert tuple(group.finalized_group_id for group in response.finalized_groups) == (
        "group-1",
        "group-2",
    )


def test_successful_zero_group_execution_commits_authoritative_zero_result() -> None:
    events: list[str] = []
    runtime = CheckpointRuntime(events)
    runtime.collection_facts = ()
    runtime.grouping_correlations = ()
    clock = RecordingDiscoveryCompletionClock(events=events)
    repository = RecordingResultRepository(events)

    response = PersistedDiscoveryExecutionEntry(
        persist_command=RecordingPersister(events),
        runtime=runtime,
        observation_identity_provider=RecordingObservationIdentityProvider(),
        observation_repository=CheckpointObservationRepository(events),
        finalized_group_identity_provider=(
            RecordingFinalizedGroupIdentityProvider()
        ),
        group_finalization_clock=RecordingGroupFinalizationClock(),
        group_repository=RecordingGroupRepository(events),
        discovery_completion_clock=clock,
        result_repository=repository,
    ).execute(command())

    assert response.execution_result.finalized_group_ids == ()
    assert response.execution_result.is_zero_result is True
    assert clock.calls == 1
    assert len(repository.calls) == 1


def test_downstream_runtime_failure_does_not_commit_completion() -> None:
    events: list[str] = []
    runtime = CheckpointRuntime(
        events,
        fail_after_grouping=RuntimeError("downstream failed"),
    )
    clock = RecordingDiscoveryCompletionClock(events=events)
    repository = RecordingResultRepository(events)
    groups = RecordingGroupRepository(events)

    with pytest.raises(RuntimeError, match="downstream failed"):
        entry(
            events,
            runtime,
            clock,
            repository,
            group_repository=groups,
        ).execute(command())

    assert len(groups.calls) == 1
    assert clock.calls == 0
    assert repository.calls == []


def test_earlier_persistence_failures_do_not_commit_completion() -> None:
    class FailingObservationRepository(CheckpointObservationRepository):
        def save_observation(self, observation):
            super().save_observation(observation)
            raise RuntimeError("observation persistence failed")

    cases = (
        {
            "persister": RecordingPersister(
                [], fail=RuntimeError("command persistence failed")
            ),
            "match": "command persistence failed",
        },
        {
            "observation_repository": FailingObservationRepository([]),
            "match": "observation persistence failed",
        },
        {
            "group_repository": RecordingGroupRepository([], fail_at=1),
            "match": "group persistence failed",
        },
    )
    for case in cases:
        events: list[str] = []
        runtime = CheckpointRuntime(events)
        clock = RecordingDiscoveryCompletionClock(events=events)
        repository = RecordingResultRepository(events)
        kwargs = {key: value for key, value in case.items() if key != "match"}

        with pytest.raises(RuntimeError, match=case["match"]):
            entry(events, runtime, clock, repository, **kwargs).execute(command())

        assert clock.calls == 0
        assert repository.calls == []


def test_clock_and_result_repository_failures_propagate_after_prior_facts() -> None:
    events: list[str] = []
    persister = RecordingPersister(events)
    observations = CheckpointObservationRepository(events)
    clock = RecordingDiscoveryCompletionClock(
        events=events,
        fail=RuntimeError("completion clock failed"),
    )
    repository = RecordingResultRepository(events)
    groups = RecordingGroupRepository(events)

    with pytest.raises(RuntimeError, match="completion clock failed"):
        entry(
            events,
            CheckpointRuntime(events),
            clock,
            repository,
            persister=persister,
            observation_repository=observations,
            group_repository=groups,
        ).execute(command())

    assert len(groups.calls) == 1
    assert persister.calls == [command()]
    assert len(observations.calls) == 2
    assert repository.calls == []

    events = []
    persister = RecordingPersister(events)
    observations = CheckpointObservationRepository(events)
    groups = RecordingGroupRepository(events)
    repository = RecordingResultRepository(
        events,
        fail=RuntimeError("result persistence failed"),
    )
    with pytest.raises(RuntimeError, match="result persistence failed"):
        entry(
            events,
            CheckpointRuntime(events),
            RecordingDiscoveryCompletionClock(events=events),
            repository,
            persister=persister,
            observation_repository=observations,
            group_repository=groups,
        ).execute(command())

    assert len(groups.calls) == 1
    assert persister.calls == [command()]
    assert len(observations.calls) == 2
    assert len(repository.calls) == 1


def sqlite_entry(path, runtime, *, completed_at=COMPLETED_AT, replay=False):
    commands = SQLiteDiscoveryCommandRepository(path)
    observations = SQLiteDiscoveryObservationRepository(path)
    groups = SQLiteDiscoveryGroupRepository(path)
    results = SQLiteDiscoveryResultRepository(path)
    command_clock = (
        (lambda: pytest.fail("command replay must not call clock"))
        if replay
        else (lambda: NOW)
    )
    application = PersistedDiscoveryExecutionEntry(
        persist_command=PersistDiscoveryCommand(commands, clock=command_clock),
        runtime=runtime,
        observation_identity_provider=RecordingObservationIdentityProvider(
            "observation-one",
            "observation-two",
        ),
        observation_repository=observations,
        finalized_group_identity_provider=(
            RecordingFinalizedGroupIdentityProvider("group-1")
        ),
        group_finalization_clock=RecordingGroupFinalizationClock(FINALIZED_AT),
        group_repository=groups,
        discovery_completion_clock=RecordingDiscoveryCompletionClock(completed_at),
        result_repository=results,
    )
    return application, commands, observations, groups, results


def close_all(*repositories) -> None:
    for repository in repositories:
        repository.close()


def test_sqlite_completion_replay_conflict_restart_and_append_only(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    application, *repositories = sqlite_entry(path, CheckpointRuntime([]))
    first = application.execute(command())
    persisted = first.execution_result
    assert repositories[-1].get_by_command("command-1") == persisted
    close_all(*repositories)

    restarted = SQLiteDiscoveryResultRepository(path)
    assert restarted.get_by_execution("execution-1") == persisted
    restarted.close()

    replay_runtime = CheckpointRuntime([])
    application, *repositories = sqlite_entry(
        path,
        replay_runtime,
        replay=True,
    )
    replayed = application.execute(command())
    assert replayed.command_result.replayed is True
    assert replay_runtime.calls == []
    assert replayed.completion_replayed is True
    assert replayed.execution_result == persisted
    results = repositories[-1]
    assert results._connection.execute(
        "SELECT COUNT(*) FROM discovery_execution_result_history"
    ).fetchone()[0] == 1
    for statement in (
        "UPDATE discovery_execution_result_history SET rowid = rowid",
        "DELETE FROM discovery_execution_result_history",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            results._connection.execute(statement)
    close_all(*repositories)

    results = SQLiteDiscoveryResultRepository(path)
    with pytest.raises(DiscoveryExecutionReplayConflict):
        results.save_result(
            replace(
                persisted,
                completed_at=COMPLETED_AT + timedelta(minutes=1),
            )
        )
    results.close()
