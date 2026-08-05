from __future__ import annotations

from datetime import timedelta
import sqlite3

import pytest

from app.application.discovery import (
    GroupingCorrelation,
    PersistedDiscoveryExecutionEntry,
)
from app.application.discovery_persistence import (
    DiscoveryGroupConflictError,
    PersistDiscoveryCommand,
)
from app.infrastructure.discovery import (
    SQLiteDiscoveryCommandRepository,
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
)
from engine import orchestrator
from tests.test_application_group_finalization import (
    FINALIZED_AT,
    RecordingFinalizedGroupIdentityProvider,
    RecordingGroupFinalizationClock,
)
from tests.test_discovery_phase_checkpoints import (
    CheckpointObservationRepository,
    CheckpointRuntime,
)
from tests.test_persisted_discovery_execution_entry import (
    NOW,
    RecordingObservationIdentityProvider,
    RecordingPersister,
    command,
)


class RecordingGroupRepository:
    def __init__(
        self,
        events: list[str],
        *,
        fail_at: int | None = None,
    ) -> None:
        self.events = events
        self.fail_at = fail_at
        self.calls = []

    def save_group(self, group):
        self.calls.append(group)
        self.events.append(f"group:{group.finalized_group_id}")
        if len(self.calls) == self.fail_at:
            raise RuntimeError("group persistence failed")
        return group


def entry(events, runtime, group_repository):
    return PersistedDiscoveryExecutionEntry(
        persist_command=RecordingPersister(events),
        runtime=runtime,
        observation_identity_provider=RecordingObservationIdentityProvider(
            "observation-one",
            "observation-two",
        ),
        observation_repository=CheckpointObservationRepository(events),
        finalized_group_identity_provider=(
            RecordingFinalizedGroupIdentityProvider("group-1", "group-2")
        ),
        group_finalization_clock=RecordingGroupFinalizationClock(
            FINALIZED_AT,
            FINALIZED_AT + timedelta(seconds=1),
        ),
        group_repository=group_repository,
    )


def test_entry_persists_finalized_groups_at_grouping_checkpoint() -> None:
    events: list[str] = []
    runtime = CheckpointRuntime(events)
    repository = RecordingGroupRepository(events)

    result = entry(events, runtime, repository).execute(command())

    assert events == [
        "persist",
        "runtime",
        "collection-checkpoint",
        "observation:one",
        "observation:two",
        "grouping",
        "group:group-1",
        "grouping-checkpoint",
        "analysis",
    ]
    assert result.finalized_groups == tuple(repository.calls)
    assert result.finalized_groups[0].observation_ids == (
        "observation-one",
        "observation-two",
    )
    assert result.finalized_groups[0].representative_observation_id == (
        "observation-one"
    )
    assert result.finalized_groups[0].grouping_policy_version == (
        orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR.policy_version
    )


def test_zero_finalized_groups_does_not_call_repository() -> None:
    events: list[str] = []
    runtime = CheckpointRuntime(events)
    runtime.collection_facts = ()
    runtime.grouping_correlations = ()
    repository = RecordingGroupRepository(events)

    result = PersistedDiscoveryExecutionEntry(
        persist_command=RecordingPersister(events),
        runtime=runtime,
        observation_identity_provider=RecordingObservationIdentityProvider(),
        observation_repository=CheckpointObservationRepository(events),
        finalized_group_identity_provider=(
            RecordingFinalizedGroupIdentityProvider()
        ),
        group_finalization_clock=RecordingGroupFinalizationClock(),
        group_repository=repository,
    ).execute(command())

    assert result.finalized_groups == ()
    assert repository.calls == []


def test_group_repository_failure_stops_downstream_analysis_after_prior_save() -> None:
    events: list[str] = []
    runtime = CheckpointRuntime(events)
    runtime.grouping_correlations = (
        GroupingCorrelation((0,), 0),
        GroupingCorrelation((1,), 1),
    )
    repository = RecordingGroupRepository(events, fail_at=2)

    with pytest.raises(RuntimeError, match="group persistence failed"):
        entry(events, runtime, repository).execute(command())

    assert tuple(group.finalized_group_id for group in repository.calls) == (
        "group-1",
        "group-2",
    )
    assert "grouping-checkpoint" not in events
    assert "analysis" not in events


def sqlite_entry(path, runtime, *, finalized_at=FINALIZED_AT, replay=False):
    commands = SQLiteDiscoveryCommandRepository(path)
    observations = SQLiteDiscoveryObservationRepository(path)
    groups = SQLiteDiscoveryGroupRepository(path)
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
        group_finalization_clock=RecordingGroupFinalizationClock(finalized_at),
        group_repository=groups,
    )
    return application, commands, observations, groups


def test_sqlite_group_replay_conflict_restart_and_append_only(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    first_runtime = CheckpointRuntime([])
    application, commands, observations, groups = sqlite_entry(
        path,
        first_runtime,
    )
    first = application.execute(command())
    persisted = first.finalized_groups[0]
    assert groups.get_group("group-1") == persisted
    member_rows = groups._connection.execute(
        """SELECT observation_id FROM discovery_finalized_group_members
        WHERE finalized_group_id = ? ORDER BY position""",
        ("group-1",),
    ).fetchall()
    assert tuple(row[0] for row in member_rows) == persisted.observation_ids
    commands.close()
    observations.close()
    groups.close()

    restarted = SQLiteDiscoveryGroupRepository(path)
    assert restarted.get_group("group-1") == persisted
    restarted.close()

    replay_runtime = CheckpointRuntime([])
    application, commands, observations, groups = sqlite_entry(
        path,
        replay_runtime,
        replay=True,
    )
    replayed = application.execute(command())
    assert replayed.command_result.replayed is True
    assert replayed.finalized_groups == (persisted,)
    assert groups._connection.execute(
        "SELECT COUNT(*) FROM discovery_finalized_group_history"
    ).fetchone()[0] == 1

    for statement in (
        "UPDATE discovery_finalized_group_history SET rowid = rowid",
        "DELETE FROM discovery_finalized_group_history",
        "UPDATE discovery_finalized_group_members SET rowid = rowid",
        "DELETE FROM discovery_finalized_group_members",
    ):
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            groups._connection.execute(statement)
    commands.close()
    observations.close()
    groups.close()

    changed_runtime = CheckpointRuntime([])
    application, commands, observations, groups = sqlite_entry(
        path,
        changed_runtime,
        finalized_at=FINALIZED_AT + timedelta(minutes=1),
        replay=True,
    )
    with pytest.raises(DiscoveryGroupConflictError):
        application.execute(command())
    commands.close()
    observations.close()
    groups.close()
