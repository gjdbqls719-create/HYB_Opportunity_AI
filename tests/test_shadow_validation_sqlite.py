from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import hashlib
import json
import sqlite3

import pytest

from app.application.shadow_validation_persistence import (
    MalformedShadowRegistrationPersistenceError,
    PersistShadowRegistrationCommand,
    ShadowRegistrationCommitError,
    ShadowRegistrationReplayConflictError,
    UnsupportedShadowRegistrationPersistenceVersionError,
)
from app.domain.opportunity import (
    ShadowBaselineAvailability,
    ShadowBaselineCompleteness,
    ShadowBaselineEvidenceDimension,
    ShadowBaselineSourceOwner,
    ShadowBaselineSourceReference,
    ShadowBaselineSourceRole,
    ShadowBaselineTruthScope,
    ShadowCalibrationEligibility,
    ShadowCalibrationEligibilityReason,
    ShadowEvidenceClass,
    serialize_shadow_baseline_snapshot,
    serialize_shadow_validation_registration,
)
from app.infrastructure.shadow_validation import (
    BASELINE_HISTORY_TABLE,
    RECEIPT_TABLE,
    REGISTRATION_HISTORY_TABLE,
    SQLiteShadowRegistrationBaselineRepository,
    deserialize_shadow_baseline_snapshot,
    deserialize_shadow_validation_registration,
)
from test_shadow_validation_domain import (
    BASELINE_CREATED_AT,
    _baseline,
    _manifest,
    _registration,
)


def _command(
    suffix: str = "1",
    *,
    command_id: str | None = None,
    registration_reason: str = "preserve exact historical machine thesis",
) -> PersistShadowRegistrationCommand:
    registration = _registration(
        shadow_validation_id=f"shadow-{suffix}",
        baseline_snapshot_id=f"baseline-{suffix}",
        registration_reason=registration_reason,
    )
    return PersistShadowRegistrationCommand(
        command_id=command_id or f"persist-shadow-{suffix}",
        registration=registration,
        baseline=_baseline(registration_value=registration),
        committed_at=BASELINE_CREATED_AT + timedelta(minutes=1),
    )


def _counts(repository: SQLiteShadowRegistrationBaselineRepository) -> tuple[int, int, int]:
    connection = repository._connection
    return tuple(
        connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (REGISTRATION_HISTORY_TABLE, BASELINE_HISTORY_TABLE, RECEIPT_TABLE)
    )


def _drop_trigger(
    repository: SQLiteShadowRegistrationBaselineRepository,
    table: str,
    operation: str,
) -> None:
    repository._connection.execute(
        f"DROP TRIGGER trg_{table}_no_{operation.lower()}"
    )


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _payload_fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def test_shadow_serialization_adapter_strictly_round_trips_pr2_contracts() -> None:
    command = _command()
    registration_payload = serialize_shadow_validation_registration(command.registration)
    baseline_payload = serialize_shadow_baseline_snapshot(command.baseline)

    assert deserialize_shadow_validation_registration(registration_payload) == command.registration
    assert deserialize_shadow_baseline_snapshot(baseline_payload) == command.baseline
    assert serialize_shadow_validation_registration(
        deserialize_shadow_validation_registration(registration_payload)
    ) == registration_payload
    assert serialize_shadow_baseline_snapshot(
        deserialize_shadow_baseline_snapshot(baseline_payload)
    ) == baseline_payload

    malformed = json.loads(registration_payload)
    malformed["unexpected"] = True
    with pytest.raises(ValueError, match="fields are malformed"):
        deserialize_shadow_validation_registration(_canonical_json(malformed))


def test_schema_enables_foreign_keys_and_creates_append_only_authorities(tmp_path) -> None:
    with SQLiteShadowRegistrationBaselineRepository(tmp_path / "shadow.db") as repository:
        connection = repository._connection
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert {
            REGISTRATION_HISTORY_TABLE,
            BASELINE_HISTORY_TABLE,
            RECEIPT_TABLE,
        } <= tables

        repository.save(_command())
        for table in (
            REGISTRATION_HISTORY_TABLE,
            BASELINE_HISTORY_TABLE,
            RECEIPT_TABLE,
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                connection.execute(f"UPDATE {table} SET inserted_at=inserted_at")
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                connection.execute(f"DELETE FROM {table}")
            connection.rollback()


def test_atomic_round_trip_preserves_exact_registration_baseline_and_lineage(tmp_path) -> None:
    command = _command()
    with SQLiteShadowRegistrationBaselineRepository(tmp_path / "shadow.db") as repository:
        result = repository.save(command)

        assert not result.replayed
        assert not result.aliased
        assert result.registration == command.registration
        assert result.baseline == command.baseline
        assert result.receipt.command_fingerprint == command.fingerprint
        assert _counts(repository) == (1, 1, 1)

        registration = repository.get_registration("shadow-1")
        baseline = repository.get_baseline("baseline-1")
        bundle = repository.get_bundle("shadow-1")
        assert registration == command.registration
        assert baseline == command.baseline
        assert bundle is not None
        assert bundle.registration.subject == command.registration.subject
        assert bundle.registration.screening_lineage == command.registration.screening_lineage
        assert bundle.baseline.source_manifest == command.baseline.source_manifest
        assert bundle.baseline.knowledge_cutoff_at == command.baseline.knowledge_cutoff_at
        assert bundle.baseline.calibration_eligibility == command.baseline.calibration_eligibility
        assert bundle.baseline.missing_evidence_dimensions == ()
        assert bundle.baseline.evidence_class is ShadowEvidenceClass.SHADOW_MARKET_THESIS
        assert bundle.registration.integrity_fingerprint == command.registration.integrity_fingerprint
        assert bundle.baseline.integrity_fingerprint == command.baseline.integrity_fingerprint
        assert repository.get_registration("missing") is None
        assert repository.get_baseline("missing") is None
        assert repository.get_bundle("missing") is None

        partial_registration = _registration(
            shadow_validation_id="shadow-partial",
            baseline_snapshot_id="baseline-partial",
        )
        unsupported = ShadowBaselineSourceReference(
            reference_id="missing.economics",
            source_owner=ShadowBaselineSourceOwner.ECONOMICS,
            source_kind="verified-economics",
            source_id="unsupported-economics",
            baseline_role=ShadowBaselineSourceRole.MISSING_EVIDENCE_MARKER,
            availability=ShadowBaselineAvailability.UNSUPPORTED,
            truth_scope=ShadowBaselineTruthScope.NOT_APPLICABLE,
            availability_reason="no supported economics scope was available",
        )
        partial_baseline = _baseline(
            registration_value=partial_registration,
            source_manifest=_manifest(partial_registration, unsupported),
            completeness=ShadowBaselineCompleteness.PARTIAL,
            missing_evidence_dimensions=(ShadowBaselineEvidenceDimension.ECONOMICS,),
            calibration_eligibility=ShadowCalibrationEligibility.INELIGIBLE,
            calibration_reason_codes=(
                ShadowCalibrationEligibilityReason.INCOMPLETE_BASELINE,
                ShadowCalibrationEligibilityReason.UNSUPPORTED_EVIDENCE_SCOPE,
            ),
        )
        partial_command = PersistShadowRegistrationCommand(
            command_id="persist-shadow-partial",
            registration=partial_registration,
            baseline=partial_baseline,
            committed_at=BASELINE_CREATED_AT + timedelta(minutes=1),
        )
        repository.save(partial_command)
        reconstructed = repository.get_baseline("baseline-partial")
        assert reconstructed == partial_baseline
        marker = next(
            source
            for source in reconstructed.source_manifest.sources
            if source.reference_id == "missing.economics"
        )
        assert marker.availability is ShadowBaselineAvailability.UNSUPPORTED
        assert reconstructed.missing_evidence_dimensions == (
            ShadowBaselineEvidenceDimension.ECONOMICS,
        )
        assert reconstructed.calibration_eligibility is ShadowCalibrationEligibility.INELIGIBLE


def test_exact_retry_reconstructs_original_bundle_without_duplicate_rows(tmp_path) -> None:
    command = _command()
    with SQLiteShadowRegistrationBaselineRepository(tmp_path / "shadow.db") as repository:
        first = repository.save(command)
        replay = repository.save(command)

        assert not first.replayed
        assert replay.replayed
        assert not replay.aliased
        assert replay.registration == first.registration
        assert replay.baseline == first.baseline
        assert replay.receipt == first.receipt
        assert _counts(repository) == (1, 1, 1)


def test_same_command_with_changed_authoritative_payload_conflicts(tmp_path) -> None:
    original = _command(command_id="same-command")
    changed = _command(
        command_id="same-command",
        registration_reason="a different historical machine thesis",
    )
    with SQLiteShadowRegistrationBaselineRepository(tmp_path / "shadow.db") as repository:
        repository.save(original)
        with pytest.raises(ShadowRegistrationReplayConflictError, match="payload conflicts"):
            repository.save(changed)
        assert repository.get_bundle("shadow-1").registration == original.registration
        assert _counts(repository) == (1, 1, 1)


@pytest.mark.parametrize(
    "first,conflicting",
    [
        (
            _command(),
            _command(
                command_id="different-command",
                registration_reason="conflicting payload",
            ),
        ),
        (
            _command(),
            PersistShadowRegistrationCommand(
                command_id="different-command",
                registration=_registration(
                    shadow_validation_id="shadow-2",
                    baseline_snapshot_id="baseline-1",
                ),
                baseline=_baseline(
                    registration_value=_registration(
                        shadow_validation_id="shadow-2",
                        baseline_snapshot_id="baseline-1",
                    )
                ),
                committed_at=BASELINE_CREATED_AT + timedelta(minutes=1),
            ),
        ),
    ],
    ids=("reused-shadow-id", "reused-baseline-id"),
)
def test_conflicting_authoritative_identity_is_rejected(first, conflicting, tmp_path) -> None:
    with SQLiteShadowRegistrationBaselineRepository(tmp_path / "shadow.db") as repository:
        repository.save(first)
        with pytest.raises(ShadowRegistrationReplayConflictError, match="identity payload conflicts"):
            repository.save(conflicting)
        assert _counts(repository) == (1, 1, 1)


def test_different_command_can_alias_only_the_exact_authoritative_bundle(tmp_path) -> None:
    first = _command(command_id="command-1")
    alias = replace(first, command_id="command-2")
    with SQLiteShadowRegistrationBaselineRepository(tmp_path / "shadow.db") as repository:
        repository.save(first)
        aliased = repository.save(alias)
        replayed_alias = repository.save(alias)

        assert aliased.aliased and not aliased.replayed
        assert replayed_alias.replayed and not replayed_alias.aliased
        assert aliased.registration == first.registration
        assert aliased.baseline == first.baseline
        assert aliased.receipt.command_id == "command-2"
        assert replayed_alias.receipt == aliased.receipt
        assert _counts(repository) == (1, 1, 2)


@pytest.mark.parametrize(
    "table,column,value,error_type",
    [
        (REGISTRATION_HISTORY_TABLE, "payload_json", "{}", MalformedShadowRegistrationPersistenceError),
        (REGISTRATION_HISTORY_TABLE, "integrity_fingerprint", "0" * 64, MalformedShadowRegistrationPersistenceError),
        (REGISTRATION_HISTORY_TABLE, "schema_version", "future-v9", UnsupportedShadowRegistrationPersistenceVersionError),
        (REGISTRATION_HISTORY_TABLE, "o2_opportunity_id", "wrong-o2", MalformedShadowRegistrationPersistenceError),
        (REGISTRATION_HISTORY_TABLE, "screening_evaluation_id", "wrong-screening", MalformedShadowRegistrationPersistenceError),
        (BASELINE_HISTORY_TABLE, "payload_json", "{}", MalformedShadowRegistrationPersistenceError),
        (BASELINE_HISTORY_TABLE, "integrity_fingerprint", "0" * 64, MalformedShadowRegistrationPersistenceError),
        (BASELINE_HISTORY_TABLE, "schema_version", "future-v9", UnsupportedShadowRegistrationPersistenceVersionError),
    ],
)
def test_corrupt_payload_fingerprint_schema_and_lineage_fail_closed(
    tmp_path, table, column, value, error_type
) -> None:
    with SQLiteShadowRegistrationBaselineRepository(tmp_path / "shadow.db") as repository:
        repository.save(_command())
        _drop_trigger(repository, table, "update")
        repository._connection.execute(f"UPDATE {table} SET {column}=?", (value,))
        repository._connection.commit()

        with pytest.raises(error_type):
            repository.get_bundle("shadow-1")


@pytest.mark.parametrize(
    "table,mutate",
    [
        (
            REGISTRATION_HISTORY_TABLE,
            lambda value: value.__setitem__("registered_at", "not-a-datetime"),
        ),
        (
            REGISTRATION_HISTORY_TABLE,
            lambda value: value.__setitem__("evidence_class", "ACTUAL_OUTCOME"),
        ),
        (
            BASELINE_HISTORY_TABLE,
            lambda value: value.__setitem__("baseline_created_at", "not-a-datetime"),
        ),
        (
            BASELINE_HISTORY_TABLE,
            lambda value: value.__setitem__("evidence_class", "ACTUAL_OUTCOME"),
        ),
    ],
    ids=(
        "registration-datetime",
        "registration-evidence-class",
        "baseline-datetime",
        "baseline-evidence-class",
    ),
)
def test_semantically_malformed_canonical_payload_fails_closed(tmp_path, table, mutate) -> None:
    with SQLiteShadowRegistrationBaselineRepository(tmp_path / "shadow.db") as repository:
        repository.save(_command())
        row = repository._connection.execute(
            f"SELECT payload_json FROM {table}"
        ).fetchone()
        payload = json.loads(row[0])
        mutate(payload)
        encoded = _canonical_json(payload)
        _drop_trigger(repository, table, "update")
        repository._connection.execute(
            f"UPDATE {table} SET payload_json=?, payload_fingerprint=?",
            (encoded, _payload_fingerprint(encoded)),
        )
        repository._connection.commit()

        with pytest.raises(MalformedShadowRegistrationPersistenceError):
            repository.get_bundle("shadow-1")


def test_orphan_and_receipt_binding_corruption_fail_closed(tmp_path) -> None:
    database_path = tmp_path / "shadow.db"
    with SQLiteShadowRegistrationBaselineRepository(database_path) as repository:
        repository.save(_command())
        _drop_trigger(repository, RECEIPT_TABLE, "update")
        repository._connection.execute("PRAGMA foreign_keys=OFF")
        repository._connection.execute(
            f"UPDATE {RECEIPT_TABLE} SET baseline_snapshot_id='wrong-baseline'"
        )
        repository._connection.commit()
        with pytest.raises(MalformedShadowRegistrationPersistenceError, match="receipt"):
            repository.get_bundle("shadow-1")

    orphan_path = tmp_path / "orphan.db"
    with SQLiteShadowRegistrationBaselineRepository(orphan_path) as repository:
        repository.save(_command())
        _drop_trigger(repository, BASELINE_HISTORY_TABLE, "delete")
        repository._connection.execute("PRAGMA foreign_keys=OFF")
        repository._connection.execute(f"DELETE FROM {BASELINE_HISTORY_TABLE}")
        repository._connection.commit()
        with pytest.raises(MalformedShadowRegistrationPersistenceError, match="orphaned"):
            repository.get_registration("shadow-1")


@pytest.mark.parametrize(
    "point",
    (
        "before_registration",
        "after_registration",
        "after_baseline",
        "before_receipt",
        "after_receipt",
        "before_commit",
    ),
)
def test_fault_injection_rolls_back_entire_boundary_and_clean_retry_succeeds(
    tmp_path, monkeypatch, point
) -> None:
    with SQLiteShadowRegistrationBaselineRepository(tmp_path / f"{point}.db") as repository:
        repository.save(_command("prior"))

        def fail(selected: str) -> None:
            if selected == point:
                raise RuntimeError(f"fault at {point}")

        monkeypatch.setattr(repository, "_fault_point", fail)
        with pytest.raises(RuntimeError, match=point):
            repository.save(_command("new"))
        assert _counts(repository) == (1, 1, 1)
        assert repository.get_bundle("shadow-prior") is not None
        assert repository.get_bundle("shadow-new") is None

        monkeypatch.setattr(repository, "_fault_point", lambda _: None)
        assert repository.save(_command("new")).registration.shadow_validation_id == "shadow-new"
        assert _counts(repository) == (2, 2, 2)


def test_commit_failure_rolls_back_all_and_preserves_unrelated_history(
    tmp_path, monkeypatch
) -> None:
    with SQLiteShadowRegistrationBaselineRepository(tmp_path / "shadow.db") as repository:
        repository.save(_command("prior"))
        real_commit = repository._commit

        def fail_commit() -> None:
            raise sqlite3.OperationalError("injected commit failure")

        monkeypatch.setattr(repository, "_commit", fail_commit)
        with pytest.raises(ShadowRegistrationCommitError, match="commit failed"):
            repository.save(_command("new"))
        assert _counts(repository) == (1, 1, 1)
        assert repository.get_bundle("shadow-prior") is not None

        monkeypatch.setattr(repository, "_commit", real_commit)
        repository.save(_command("new"))
        assert _counts(repository) == (2, 2, 2)


def test_restart_reconstructs_exact_bundle_and_replay(tmp_path) -> None:
    database_path = tmp_path / "shadow.db"
    command = _command()
    with SQLiteShadowRegistrationBaselineRepository(database_path) as repository:
        first = repository.save(command)

    with SQLiteShadowRegistrationBaselineRepository(database_path) as restarted:
        bundle = restarted.get_bundle("shadow-1")
        replay = restarted.save(command)
        assert bundle is not None
        assert bundle.registration == first.registration
        assert bundle.baseline == first.baseline
        assert replay.replayed
        assert replay.receipt == first.receipt
        assert _counts(restarted) == (1, 1, 1)


def test_concurrent_identical_commands_converge_to_one_authoritative_bundle(tmp_path) -> None:
    database_path = tmp_path / "shadow.db"
    command = _command()
    with SQLiteShadowRegistrationBaselineRepository(database_path):
        pass

    def save():
        with SQLiteShadowRegistrationBaselineRepository(database_path) as repository:
            return repository.save(command)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(lambda _: save(), range(2)))

    assert sorted(result.replayed for result in results) == [False, True]
    assert all(result.registration == command.registration for result in results)
    with SQLiteShadowRegistrationBaselineRepository(database_path) as repository:
        assert _counts(repository) == (1, 1, 1)


def test_concurrent_conflicting_command_has_one_winner_and_no_split_brain(tmp_path) -> None:
    database_path = tmp_path / "shadow.db"
    commands = (
        _command(command_id="same-command"),
        _command(
            command_id="same-command",
            registration_reason="concurrent conflicting payload",
        ),
    )
    with SQLiteShadowRegistrationBaselineRepository(database_path):
        pass

    def save(command):
        try:
            with SQLiteShadowRegistrationBaselineRepository(database_path) as repository:
                return repository.save(command)
        except ShadowRegistrationReplayConflictError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(save, commands))

    assert sum(result == "conflict" for result in results) == 1
    with SQLiteShadowRegistrationBaselineRepository(database_path) as repository:
        assert _counts(repository) == (1, 1, 1)
        persisted = repository.get_bundle("shadow-1")
        assert persisted is not None
        assert persisted.registration in {command.registration for command in commands}


def test_concurrent_unrelated_commands_both_persist(tmp_path) -> None:
    database_path = tmp_path / "shadow.db"
    commands = (_command("left"), _command("right"))
    with SQLiteShadowRegistrationBaselineRepository(database_path):
        pass

    def save(command):
        with SQLiteShadowRegistrationBaselineRepository(database_path) as repository:
            return repository.save(command)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(save, commands))

    assert all(not result.replayed for result in results)
    with SQLiteShadowRegistrationBaselineRepository(database_path) as repository:
        assert _counts(repository) == (2, 2, 2)
        assert repository.get_bundle("shadow-left") is not None
        assert repository.get_bundle("shadow-right") is not None
