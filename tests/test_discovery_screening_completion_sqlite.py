from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import inspect
import sqlite3

import pytest

from app.application.discovery import (
    DiscoveryScreeningCompletionBundle,
    DiscoveryScreeningCompletionConflictError,
    DiscoveryScreeningCompletionLineageError,
    DiscoveryScreeningCompletionRepository,
)
from app.domain.discovery import (
    DiscoveryScreeningRecordingState,
    serialize_discovery_screening_evaluation,
    serialize_discovery_screening_ranking_publication,
)
from app.domain.discovery_identity import DiscoveryExecutionResult
from app.infrastructure.discovery import (
    SQLiteDiscoveryResultRepository,
    SQLiteDiscoveryScreeningCompletionRepository,
)
from discovery_screening_persistence_support import (
    SCREENING_TABLES,
    completion_bundle,
    prepare_bundle,
    prepare_completion_lineage,
    screening_state,
)


def test_schema_is_additive_foreign_keyed_and_append_only(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    bundle = prepare_bundle(path)
    repository: DiscoveryScreeningCompletionRepository = (
        SQLiteDiscoveryScreeningCompletionRepository(path)
    )
    connection = repository._connection

    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'discovery_screening_%'"
        )
    }
    assert tables == set(SCREENING_TABLES[:-1])
    assert [
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(discovery_screening_evaluation_history)"
        )
    ] == [
        "screening_evaluation_id",
        "command_id",
        "execution_id",
        "finalized_group_id",
        "group_membership_fingerprint",
        "canonical_payload_json",
        "integrity_fingerprint",
        "evaluated_at",
        "schema_version",
    ]

    repository.save_completion_bundle(bundle)
    for table in SCREENING_TABLES[:-1]:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(f"UPDATE {table} SET rowid=rowid")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(f"DELETE FROM {table}")
    repository.close()


def test_exact_round_trip_preserves_pr2_pr3_pr4_semantics(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    expected = prepare_bundle(path)
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)

    assert repository.save_completion_bundle(expected) == expected
    by_execution = repository.get_by_execution("execution-1")
    assert by_execution == expected
    assert repository.get_by_command("command-1") == expected
    assert repository.get_by_publication("publication-1") == expected
    assert repository.get_ranking_publication("publication-1") == (
        expected.ranking_publication
    )
    assert repository.get_evaluation("evaluation-1-1") == (
        expected.evaluations[0]
    )
    assert repository.get_recording_state("execution-1") is (
        DiscoveryScreeningRecordingState.RECORDED
    )

    first = by_execution.evaluations[0]
    assert first.finalized_group_id == by_execution.finalized_groups[0].finalized_group_id
    assert first.group_membership_fingerprint == (
        by_execution.finalized_groups[0].membership_fingerprint
    )
    assert isinstance(first.ranking_economics_key.value, Decimal)
    assert first.ranking_economics_key.value == Decimal("12.34")
    assert first.evaluated_at == expected.evaluations[0].evaluated_at
    assert first.screening_recommendation.raw_grade == "BUY"
    assert first.screening_recommendation.effective_grade == "WATCH"
    assert first.screening_recommendation.safety_intervention_occurred is True
    assert first.structured_reasons == expected.evaluations[0].structured_reasons
    assert first.screening_policy_manifest == (
        expected.evaluations[0].screening_policy_manifest
    )
    assert first.input_manifest == expected.evaluations[0].input_manifest
    assert first.expected_economics == expected.evaluations[0].expected_economics

    publication = by_execution.ranking_publication
    assert tuple(value.rank for value in publication.ranked_entries) == (1,)
    assert tuple(
        value.screening_evaluation_id
        for value in publication.not_ranked_entries
    ) == ("evaluation-1-2",)
    assert publication.ranked_entries[0].evaluation_fingerprint == (
        first.integrity_fingerprint
    )
    assert publication.ranking_created_at == (
        expected.ranking_publication.ranking_created_at
    )

    rows = connection_rows = repository._connection.execute(
        "SELECT screening_evaluation_id,canonical_payload_json "
        "FROM discovery_screening_evaluation_history "
        "ORDER BY screening_evaluation_id"
    ).fetchall()
    assert tuple(row[1] for row in rows) == tuple(
        serialize_discovery_screening_evaluation(value)
        for value in expected.evaluations
    )
    publication_payload = repository._connection.execute(
        "SELECT canonical_payload_json FROM "
        "discovery_screening_ranking_publication_history"
    ).fetchone()[0]
    assert publication_payload == (
        serialize_discovery_screening_ranking_publication(
            expected.ranking_publication
        )
    )
    assert connection_rows
    repository.close()


def test_exact_retry_restart_and_changed_payload_conflict(tmp_path) -> None:
    path = tmp_path / "discovery.db"
    expected = prepare_bundle(path)
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    first = repository.save_completion_bundle(expected)
    before = screening_state(repository._connection)

    assert repository.save_completion_bundle(expected) == first
    assert screening_state(repository._connection) == before
    repository.close()

    restarted = SQLiteDiscoveryScreeningCompletionRepository(path)
    assert restarted.save_completion_bundle(expected) == first
    assert restarted.get_by_execution("execution-1") == first
    assert screening_state(restarted._connection) == before

    changed_result = replace(
        expected.execution_result,
        completed_at=expected.execution_result.completed_at
        + timedelta(seconds=1),
    )
    changed_binding = replace(
        expected.completion_binding,
        result_fingerprint=changed_result.fingerprint,
        integrity_fingerprint="",
    )
    changed = replace(
        expected,
        execution_result=changed_result,
        completion_binding=changed_binding,
    )
    with pytest.raises(DiscoveryScreeningCompletionConflictError):
        restarted.save_completion_bundle(changed)
    assert screening_state(restarted._connection) == before
    restarted.close()


def test_bundle_rejects_group_and_evaluation_reference_mismatch_before_write(
    tmp_path,
) -> None:
    path = tmp_path / "invalid-bundle.db"
    bundle = prepare_bundle(path)
    mismatched_evaluation = replace(
        bundle.evaluations[0],
        group_membership_fingerprint="a" * 64,
        integrity_fingerprint="",
    )
    with pytest.raises(DiscoveryScreeningCompletionLineageError, match="Group lineage"):
        replace(
            bundle,
            evaluations=(mismatched_evaluation, *bundle.evaluations[1:]),
        )

    wrong_entry = replace(
        bundle.ranking_publication.ranked_entries[0],
        evaluation_fingerprint="a" * 64,
    )
    mismatched_publication = replace(
        bundle.ranking_publication,
        ranked_entries=(wrong_entry,),
        integrity_fingerprint="",
    )
    with pytest.raises(
        DiscoveryScreeningCompletionLineageError,
        match="evaluation integrity lineage",
    ):
        replace(bundle, ranking_publication=mismatched_publication)

    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    assert all(not rows for _, rows in screening_state(repository._connection))
    repository.close()


def test_zero_result_bundle_is_explicit_and_atomic(tmp_path) -> None:
    path = tmp_path / "zero.db"
    expected = prepare_bundle(path, group_count=0)
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)

    persisted = repository.save_completion_bundle(expected)
    assert persisted.execution_result.is_zero_result is True
    assert persisted.finalized_groups == ()
    assert persisted.evaluations == ()
    assert persisted.ranking_publication.zero_result is True
    assert persisted.ranking_publication.ranked_entries == ()
    assert persisted.ranking_publication.not_ranked_entries == ()
    assert repository.get_by_execution("execution-1") == expected
    assert repository._connection.execute(
        "SELECT COUNT(*) FROM discovery_screening_evaluation_history"
    ).fetchone()[0] == 0
    repository.close()


def test_legacy_result_and_screening_recorded_result_coexist_without_backfill(
    tmp_path,
) -> None:
    path = tmp_path / "coexist.db"
    legacy_command, legacy_groups = prepare_completion_lineage(
        path,
        group_count=1,
    )
    legacy_result = DiscoveryExecutionResult(
        command_id=legacy_command.command_id,
        discovery_execution_id=legacy_command.discovery_execution_id,
        finalized_group_ids=(legacy_groups[0].finalized_group_id,),
        completed_at=legacy_groups[0].finalized_at + timedelta(minutes=1),
    )
    legacy_repository = SQLiteDiscoveryResultRepository(path)
    legacy_repository.save_result(legacy_result)
    legacy_repository.close()

    recorded = prepare_bundle(
        path,
        command_id="command-2",
        execution_id="execution-2",
        suffix="2",
    )
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    assert repository.get_recording_state("execution-1") is (
        DiscoveryScreeningRecordingState.SCREENING_NOT_RECORDED_LEGACY
    )
    assert repository.get_by_execution("execution-1") is None
    assert repository.get_ranking_publication("missing") is None
    assert repository._connection.execute(
        "SELECT COUNT(*) FROM discovery_screening_ranking_publication_history "
        "WHERE execution_id='execution-1'"
    ).fetchone()[0] == 0

    repository.save_completion_bundle(recorded)
    assert repository.get_recording_state("execution-1") is (
        DiscoveryScreeningRecordingState.SCREENING_NOT_RECORDED_LEGACY
    )
    assert repository.get_recording_state("execution-2") is (
        DiscoveryScreeningRecordingState.RECORDED
    )
    repository.close()

    results = SQLiteDiscoveryResultRepository(path)
    assert results.get_by_execution("execution-1") == legacy_result
    assert results.get_by_execution("execution-2") == recorded.execution_result
    results.close()


def test_existing_unbound_result_cannot_be_non_atomically_upgraded(tmp_path) -> None:
    path = tmp_path / "legacy-upgrade.db"
    command_value, groups = prepare_completion_lineage(path, group_count=1)
    bundle = completion_bundle(command_value, groups)
    results = SQLiteDiscoveryResultRepository(path)
    results.save_result(bundle.execution_result)
    results.close()
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)

    with pytest.raises(
        DiscoveryScreeningCompletionConflictError,
        match="unbound result",
    ):
        repository.save_completion_bundle(bundle)
    assert repository.get_recording_state("execution-1") is (
        DiscoveryScreeningRecordingState.SCREENING_NOT_RECORDED_LEGACY
    )
    assert all(not rows for _, rows in screening_state(repository._connection)[:3])
    repository.close()


def test_composite_repository_is_wired_into_live_web_completion() -> None:
    import app.web

    source = inspect.getsource(app.web.get_authoritative_discovery_entry)
    assert "SQLiteDiscoveryScreeningCompletionRepository" in source
    assert "ProductionScreeningIdentityProvider" in source
    assert "screening_completion_repository=" in source
    assert "screening_identity_provider=" in source
