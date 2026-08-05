from __future__ import annotations

import sqlite3

import pytest

from app.application.discovery import PersistedDiscoveryExecutionEntry
from app.application.discovery_persistence import (
    DiscoveryObservationConflictError,
    PersistDiscoveryCommand,
)
from app.infrastructure.discovery import (
    SQLiteDiscoveryCommandRepository,
    SQLiteDiscoveryObservationRepository,
)
from tests.test_discovery_observation_assembly import (
    SequentialObservationIdentityProvider,
    fact,
)
from tests.test_persisted_discovery_execution_entry import (
    NOW,
    RecordingObservationIdentityProvider,
    RecordingPersister,
    RecordingRuntime,
    command,
)


class RecordingObservationRepository:
    def __init__(self, events: list[str], *, fail_at: int | None = None) -> None:
        self.events = events
        self.fail_at = fail_at
        self.calls = []

    def save_observation(self, observation):
        self.calls.append(observation)
        self.events.append(f"observation:{observation.observation_id}")
        if len(self.calls) == self.fail_at:
            raise RuntimeError("observation persistence failed")
        return observation


def execute(runtime, provider, repository, *, persister=None):
    return PersistedDiscoveryExecutionEntry(
        persist_command=persister or RecordingPersister(runtime.events),
        runtime=runtime,
        observation_identity_provider=provider,
        observation_repository=repository,
    ).execute(command())


def test_entry_persists_assembled_observations_in_order_and_returns_saved_values() -> None:
    events: list[str] = []
    runtime = RecordingRuntime(events)
    runtime.collection_facts = (fact("item-1", 11.5), fact("item-2", 22.75))
    repository = RecordingObservationRepository(events)

    result = execute(
        runtime,
        SequentialObservationIdentityProvider("observation-1", "observation-2"),
        repository,
    )

    assert events == [
        "persist",
        "runtime",
        "observation:observation-1",
        "observation:observation-2",
    ]
    assert tuple(repository.calls) == result.observations
    assert result.discovery_results is runtime.results
    assert result.collection_facts is runtime.collection_facts


def test_zero_observations_does_not_call_repository() -> None:
    events: list[str] = []
    runtime = RecordingRuntime(events)
    repository = RecordingObservationRepository(events)

    result = execute(
        runtime,
        RecordingObservationIdentityProvider(),
        repository,
    )

    assert result.observations == ()
    assert repository.calls == []
    assert events == ["persist", "runtime"]


def test_repository_failure_propagates_after_prior_single_fact_commit() -> None:
    events: list[str] = []
    runtime = RecordingRuntime(events)
    runtime.collection_facts = (fact("item-1", 11.5), fact("item-2", 22.75))
    repository = RecordingObservationRepository(events, fail_at=2)

    with pytest.raises(RuntimeError, match="observation persistence failed"):
        execute(
            runtime,
            SequentialObservationIdentityProvider("observation-1", "observation-2"),
            repository,
        )

    assert tuple(value.observation_id for value in repository.calls) == (
        "observation-1",
        "observation-2",
    )
    assert events[:2] == ["persist", "runtime"]


def test_runtime_failure_does_not_call_observation_repository() -> None:
    events: list[str] = []
    runtime = RecordingRuntime(events, fail=RuntimeError("runtime failed"))
    repository = RecordingObservationRepository(events)

    with pytest.raises(RuntimeError, match="runtime failed"):
        execute(runtime, RecordingObservationIdentityProvider(), repository)

    assert repository.calls == []
    assert events == ["persist", "runtime"]


def sqlite_entry(path, runtime, observation_id, *, replay_clock=False):
    command_repository = SQLiteDiscoveryCommandRepository(path)
    observation_repository = SQLiteDiscoveryObservationRepository(path)
    clock = (
        (lambda: pytest.fail("command replay must not call clock"))
        if replay_clock
        else (lambda: NOW)
    )
    entry = PersistedDiscoveryExecutionEntry(
        persist_command=PersistDiscoveryCommand(command_repository, clock=clock),
        runtime=runtime,
        observation_identity_provider=SequentialObservationIdentityProvider(
            observation_id
        ),
        observation_repository=observation_repository,
    )
    return entry, command_repository, observation_repository


def test_sqlite_save_exact_replay_restart_and_conflict(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    first_runtime = RecordingRuntime([])
    first_runtime.collection_facts = (fact("item-1", 11.5),)
    first_entry, commands, observations = sqlite_entry(
        path, first_runtime, "observation-1"
    )
    first = first_entry.execute(command())
    assert observations.get_observation("observation-1") == first.observations[0]
    commands.close()
    observations.close()

    replay_runtime = RecordingRuntime([])
    replay_runtime.collection_facts = (fact("item-1", 11.5),)
    replay_entry, commands, observations = sqlite_entry(
        path,
        replay_runtime,
        "observation-1",
        replay_clock=True,
    )
    replay = replay_entry.execute(command())
    assert replay.command_result.replayed is True
    assert replay.observations == first.observations
    assert observations._connection.execute(
        "SELECT COUNT(*) FROM discovery_collected_observation_history"
    ).fetchone()[0] == 1
    commands.close()
    observations.close()

    restarted = SQLiteDiscoveryObservationRepository(path)
    assert restarted.get_observation("observation-1") == first.observations[0]
    restarted.close()

    changed_runtime = RecordingRuntime([])
    changed_runtime.collection_facts = (fact("item-1", 99.0),)
    conflict_entry, commands, observations = sqlite_entry(
        path,
        changed_runtime,
        "observation-1",
        replay_clock=True,
    )
    with pytest.raises(DiscoveryObservationConflictError):
        conflict_entry.execute(command())
    commands.close()
    observations.close()


def test_sqlite_observation_history_is_append_only_by_trigger(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    runtime = RecordingRuntime([])
    runtime.collection_facts = (fact("item-1", 11.5),)
    entry, commands, observations = sqlite_entry(path, runtime, "observation-1")
    entry.execute(command())

    for statement in (
        "UPDATE discovery_collected_observation_history SET rowid = rowid",
        "DELETE FROM discovery_collected_observation_history",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            observations._connection.execute(statement)

    commands.close()
    observations.close()
