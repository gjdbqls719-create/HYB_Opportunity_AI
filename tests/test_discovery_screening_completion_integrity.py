from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import json
import sqlite3
from threading import Barrier

import pytest

from app.application.discovery import (
    DiscoveryScreeningCommitError,
    DiscoveryScreeningCompletionConflictError,
    MalformedDiscoveryScreeningPersistenceError,
    UnsupportedDiscoveryScreeningVersionError,
    serialize_discovery_screening_completion_binding,
)
from app.domain.discovery import (
    serialize_discovery_screening_ranking_publication,
)
from app.infrastructure.discovery import (
    SQLiteDiscoveryScreeningCompletionRepository,
)
from discovery_screening_persistence_support import (
    prepare_bundle,
    screening_state,
)


FAULT_POINTS = (
    "after_first_evaluation",
    "after_all_evaluations",
    "after_ranking_publication",
    "after_execution_result",
    "before_completion_binding",
    "after_completion_binding",
    "before_commit",
)


@pytest.mark.parametrize("fault_point", FAULT_POINTS)
def test_every_in_transaction_fault_rolls_back_the_complete_new_bundle(
    tmp_path,
    fault_point,
) -> None:
    class FailingRepository(SQLiteDiscoveryScreeningCompletionRepository):
        def _fault_point(self, name: str) -> None:
            if name == fault_point:
                raise RuntimeError(f"fault:{name}")

    path = tmp_path / f"{fault_point}.db"
    baseline = prepare_bundle(path)
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    repository.save_completion_bundle(baseline)
    before = screening_state(repository._connection)
    repository.close()

    attempted = prepare_bundle(
        path,
        command_id="command-2",
        execution_id="execution-2",
        suffix="2",
    )
    failing = FailingRepository(path)
    with pytest.raises(RuntimeError, match=f"fault:{fault_point}"):
        failing.save_completion_bundle(attempted)
    assert screening_state(failing._connection) == before
    assert failing._connection.in_transaction is False
    assert all(
        failing._connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE execution_id='execution-2'"
        ).fetchone()[0]
        == 0
        for table in (
            "discovery_screening_evaluation_history",
            "discovery_screening_ranking_publication_history",
            "discovery_screening_completion_binding_history",
            "discovery_execution_result_history",
        )
    )
    failing.close()

    retry = SQLiteDiscoveryScreeningCompletionRepository(path)
    assert retry.save_completion_bundle(attempted) == attempted
    assert retry.get_by_execution("execution-1") == baseline
    assert retry.get_by_execution("execution-2") == attempted
    retry.close()


def test_commit_failure_rolls_back_every_screening_completion_row(tmp_path) -> None:
    class CommitFailingRepository(
        SQLiteDiscoveryScreeningCompletionRepository
    ):
        def _commit(self) -> None:
            raise sqlite3.OperationalError("commit failure")

    path = tmp_path / "commit.db"
    bundle = prepare_bundle(path)
    repository = CommitFailingRepository(path)
    with pytest.raises(DiscoveryScreeningCommitError, match="commit failed"):
        repository.save_completion_bundle(bundle)
    assert all(not rows for _, rows in screening_state(repository._connection))
    assert repository._connection.in_transaction is False
    repository.close()


def _concurrent_save(path, left, right):
    barrier = Barrier(2)

    def save(value):
        repository = SQLiteDiscoveryScreeningCompletionRepository(path)
        try:
            barrier.wait()
            return repository.save_completion_bundle(value)
        finally:
            repository.close()

    results = []
    errors = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = (executor.submit(save, left), executor.submit(save, right))
        for future in futures:
            try:
                results.append(future.result())
            except Exception as error:
                errors.append(error)
    return results, errors


def _changed_completion(bundle):
    result = replace(
        bundle.execution_result,
        completed_at=bundle.execution_result.completed_at
        + timedelta(seconds=1),
    )
    binding = replace(
        bundle.completion_binding,
        result_fingerprint=result.fingerprint,
        integrity_fingerprint="",
    )
    return replace(
        bundle,
        execution_result=result,
        completion_binding=binding,
    )


def test_same_bundle_concurrency_converges_to_one_authoritative_result(
    tmp_path,
) -> None:
    path = tmp_path / "same.db"
    bundle = prepare_bundle(path)

    results, errors = _concurrent_save(path, bundle, bundle)

    assert errors == []
    assert results == [bundle, bundle]
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    assert all(
        repository._connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        == expected
        for table, expected in (
            ("discovery_screening_evaluation_history", 2),
            ("discovery_screening_ranking_publication_history", 1),
            ("discovery_screening_completion_binding_history", 1),
            ("discovery_execution_result_history", 1),
        )
    )
    repository.close()


def test_conflicting_bundle_concurrency_cannot_create_split_brain(
    tmp_path,
) -> None:
    path = tmp_path / "conflict.db"
    bundle = prepare_bundle(path)
    changed = _changed_completion(bundle)

    results, errors = _concurrent_save(path, bundle, changed)

    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], DiscoveryScreeningCompletionConflictError)
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    persisted = repository.get_by_execution("execution-1")
    assert persisted in (bundle, changed)
    assert repository._connection.execute(
        "SELECT COUNT(*) FROM discovery_screening_completion_binding_history"
    ).fetchone()[0] == 1
    assert repository._connection.execute(
        "SELECT COUNT(*) FROM discovery_execution_result_history"
    ).fetchone()[0] == 1
    repository.close()


@pytest.mark.parametrize(
    ("corruption", "error_type"),
    (
        ("evaluation_payload", MalformedDiscoveryScreeningPersistenceError),
        ("evaluation_fingerprint", MalformedDiscoveryScreeningPersistenceError),
        ("publication_fingerprint", MalformedDiscoveryScreeningPersistenceError),
        ("malformed_payload", MalformedDiscoveryScreeningPersistenceError),
        ("unsupported_schema", UnsupportedDiscoveryScreeningVersionError),
    ),
)
def test_payload_fingerprint_and_version_corruption_fail_closed(
    tmp_path,
    corruption,
    error_type,
) -> None:
    path = tmp_path / f"{corruption}.db"
    prepare_bundle_value = prepare_bundle(path)
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    repository.save_completion_bundle(prepare_bundle_value)
    connection = repository._connection

    if corruption in {
        "evaluation_payload",
        "evaluation_fingerprint",
        "malformed_payload",
        "unsupported_schema",
    }:
        connection.execute(
            "DROP TRIGGER "
            "trg_discovery_screening_evaluation_history_no_update"
        )
    else:
        connection.execute(
            "DROP TRIGGER "
            "trg_discovery_screening_ranking_publication_history_no_update"
        )
    if corruption == "evaluation_payload":
        payload = connection.execute(
            "SELECT canonical_payload_json FROM "
            "discovery_screening_evaluation_history "
            "WHERE screening_evaluation_id='evaluation-1-1'"
        ).fetchone()[0]
        data = json.loads(payload)
        data["final_opportunity_score"]["value"]["value"] = "81.6"
        connection.execute(
            "UPDATE discovery_screening_evaluation_history "
            "SET canonical_payload_json=? "
            "WHERE screening_evaluation_id='evaluation-1-1'",
            (
                json.dumps(
                    data,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                ),
            ),
        )
    elif corruption == "evaluation_fingerprint":
        connection.execute(
            "UPDATE discovery_screening_evaluation_history "
            "SET integrity_fingerprint=? "
            "WHERE screening_evaluation_id='evaluation-1-1'",
            ("a" * 64,),
        )
    elif corruption == "publication_fingerprint":
        connection.execute(
            "UPDATE discovery_screening_ranking_publication_history "
            "SET integrity_fingerprint=?",
            ("a" * 64,),
        )
    elif corruption == "malformed_payload":
        connection.execute(
            "UPDATE discovery_screening_evaluation_history "
            "SET canonical_payload_json='{' "
            "WHERE screening_evaluation_id='evaluation-1-1'"
        )
    else:
        connection.execute(
            "UPDATE discovery_screening_evaluation_history "
            "SET schema_version='future' "
            "WHERE screening_evaluation_id='evaluation-1-1'"
        )
    connection.commit()

    with pytest.raises(error_type):
        repository.get_by_execution("execution-1")
    repository.close()


def _replace_publication_and_binding(repository, publication) -> None:
    binding = replace(
        repository.get_by_execution("execution-1").completion_binding,
        ranking_publication_fingerprint=publication.integrity_fingerprint,
        integrity_fingerprint="",
    )
    connection = repository._connection
    connection.execute(
        "DROP TRIGGER "
        "trg_discovery_screening_ranking_publication_history_no_update"
    )
    connection.execute(
        "DROP TRIGGER "
        "trg_discovery_screening_completion_binding_history_no_update"
    )
    connection.execute(
        "UPDATE discovery_screening_ranking_publication_history "
        "SET canonical_payload_json=?,integrity_fingerprint=?",
        (
            serialize_discovery_screening_ranking_publication(publication),
            publication.integrity_fingerprint,
        ),
    )
    connection.execute(
        "UPDATE discovery_screening_completion_binding_history "
        "SET ranking_publication_fingerprint=?,canonical_payload_json=?,"
        "integrity_fingerprint=?",
        (
            publication.integrity_fingerprint,
            serialize_discovery_screening_completion_binding(binding),
            binding.integrity_fingerprint,
        ),
    )
    connection.commit()


@pytest.mark.parametrize("corruption", ("unknown_evaluation", "wrong_fingerprint"))
def test_publication_evaluation_reference_corruption_fails_closed(
    tmp_path,
    corruption,
) -> None:
    path = tmp_path / f"{corruption}.db"
    bundle = prepare_bundle(path)
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    repository.save_completion_bundle(bundle)
    entry = bundle.ranking_publication.ranked_entries[0]
    if corruption == "unknown_evaluation":
        entry = replace(entry, screening_evaluation_id="evaluation-missing")
    else:
        entry = replace(entry, evaluation_fingerprint="a" * 64)
    publication = replace(
        bundle.ranking_publication,
        ranked_entries=(entry,),
        integrity_fingerprint="",
    )
    _replace_publication_and_binding(repository, publication)

    with pytest.raises(MalformedDiscoveryScreeningPersistenceError):
        repository.get_by_execution("execution-1")
    repository.close()


@pytest.mark.parametrize(
    "corruption",
    ("wrong_execution", "wrong_group", "wrong_membership_fingerprint"),
)
def test_evaluation_and_group_lineage_corruption_fails_closed(
    tmp_path,
    corruption,
) -> None:
    path = tmp_path / f"{corruption}.db"
    bundle = prepare_bundle(path)
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    repository.save_completion_bundle(bundle)
    connection = repository._connection

    if corruption == "wrong_membership_fingerprint":
        connection.execute(
            "DROP TRIGGER trg_discovery_finalized_group_history_no_update"
        )
        connection.execute(
            "UPDATE discovery_finalized_group_history "
            "SET membership_fingerprint=? "
            "WHERE finalized_group_id='group-1-1'",
            ("a" * 64,),
        )
    else:
        connection.commit()
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "DROP TRIGGER "
            "trg_discovery_screening_evaluation_history_no_update"
        )
        column = (
            "execution_id" if corruption == "wrong_execution" else "finalized_group_id"
        )
        connection.execute(
            f"UPDATE discovery_screening_evaluation_history SET {column}=? "
            "WHERE screening_evaluation_id='evaluation-1-1'",
            ("other-execution" if corruption == "wrong_execution" else "other-group",),
        )
    connection.commit()

    with pytest.raises(MalformedDiscoveryScreeningPersistenceError):
        repository.get_by_execution("execution-1")
    repository.close()


@pytest.mark.parametrize("orphan", ("publication_without_binding", "binding_without_publication"))
def test_orphan_publication_or_binding_fails_closed(tmp_path, orphan) -> None:
    path = tmp_path / f"{orphan}.db"
    bundle = prepare_bundle(path)
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    repository.save_completion_bundle(bundle)
    connection = repository._connection
    if orphan == "publication_without_binding":
        connection.execute(
            "DROP TRIGGER "
            "trg_discovery_screening_completion_binding_history_no_delete"
        )
        connection.execute(
            "DELETE FROM discovery_screening_completion_binding_history"
        )
        connection.commit()
        with pytest.raises(MalformedDiscoveryScreeningPersistenceError):
            repository.get_by_publication("publication-1")
    else:
        connection.commit()
        connection.execute("PRAGMA foreign_keys=OFF")
        connection.execute(
            "DROP TRIGGER "
            "trg_discovery_screening_ranking_publication_history_no_delete"
        )
        connection.execute(
            "DELETE FROM discovery_screening_ranking_publication_history"
        )
        connection.commit()
        with pytest.raises(MalformedDiscoveryScreeningPersistenceError):
            repository.get_by_execution("execution-1")
    repository.close()


def test_sqlite_constraints_reject_duplicate_authoritative_identities(
    tmp_path,
) -> None:
    path = tmp_path / "duplicates.db"
    bundle = prepare_bundle(path)
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    repository.save_completion_bundle(bundle)

    with pytest.raises(sqlite3.IntegrityError):
        repository._connection.execute(
            "INSERT INTO discovery_screening_evaluation_history "
            "SELECT * FROM discovery_screening_evaluation_history "
            "WHERE screening_evaluation_id='evaluation-1-1'"
        )
    with pytest.raises(sqlite3.IntegrityError):
        repository._connection.execute(
            "INSERT INTO discovery_screening_ranking_publication_history "
            "SELECT * FROM discovery_screening_ranking_publication_history"
        )
    repository.close()
