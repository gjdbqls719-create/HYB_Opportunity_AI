from concurrent.futures import ThreadPoolExecutor
from concurrent.futures._base import Future
from datetime import datetime, timezone
from decimal import Decimal
from threading import Barrier
from typing import Callable
from uuid import uuid4

import pytest
import sqlite3

from app.application.sourcing import (
    AdmitFXObservation,
    AdmitFXObservationCommand,
    FXObservationReplayConflictError,
    FX_OBSERVATION_COMMAND_SCHEMA_VERSION,
)
from app.domain.sourcing import FX_OBSERVATION_SCHEMA_VERSION
from app.infrastructure.sourcing import (
    FXObservationCommitError,
    FXObservationHistoryError,
    FXObservationReceiptError,
    MalformedFXObservationPersistenceError,
    SQLiteFXObservationRepository,
    UnsupportedFXObservationVersionError,
)

BASE_NOW = datetime(2026, 8, 9, 9, 0, 0, tzinfo=timezone.utc)


def command(**changes):
    values = dict(
        command_id="fx-observation-command-1",
        base_currency="USD",
        quote_currency="KRW",
        rate=Decimal("1380.10"),
        observed_at=BASE_NOW,
        provider="provider-alpha",
        source_reference="ext:obs:1",
        collection_method="scheduled-pull",
        schema_version=FX_OBSERVATION_COMMAND_SCHEMA_VERSION,
    )
    values.update(changes)
    return AdmitFXObservationCommand(**values)


class Counting:
    def __init__(self, value, *, fail: bool = False):
        self.value = value
        self.fail = fail
        self.calls = 0

    def __call__(self):
        self.calls += 1
        if self.fail:
            raise AssertionError("call should not happen during replay")
        return self.value() if callable(self.value) else self.value


def owner_with(
    repository,
    *,
    observation_id: str,
    fail_identity: bool = False,
    fail_clock: bool = False,
):
    identity = Counting(observation_id, fail=fail_identity)
    admitted = Counting(BASE_NOW, fail=fail_clock)
    committed = Counting(BASE_NOW, fail=fail_clock)
    owner = AdmitFXObservation(
        repository,
        observation_id_generator=identity,
        admitted_clock=admitted,
        committed_clock=committed,
    )
    return owner, identity, admitted, committed


def count_rows(repository: SQLiteFXObservationRepository) -> tuple[int, int]:
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
        for name in ("fx_observation_history", "fx_observation_receipts")
    )


def rewrite_payload(
    repository: SQLiteFXObservationRepository,
    observation_id: str,
    mutate: Callable[[dict], None],
    *,
    preserve_fingerprint: bool,
) -> None:
    import json

    row = repository._connection.execute(
        "SELECT * FROM fx_observation_history WHERE observation_id=?",
        (observation_id,),
    ).fetchone()
    assert row is not None
    payload = json.loads(row["payload_json"])
    mutate(payload)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if preserve_fingerprint:
        fingerprint = __import__("hashlib").sha256(encoded.encode("utf-8")).hexdigest()
    else:
        fingerprint = "0" * 64

    repository._connection.execute("DROP TRIGGER IF EXISTS trg_fx_observation_history_no_update")
    repository._connection.execute(
        "UPDATE fx_observation_history SET payload_json=?, integrity_fingerprint=? "
        "WHERE observation_id=?",
        (encoded, fingerprint, observation_id),
    )
    repository._connection.execute(
        """CREATE TRIGGER IF NOT EXISTS trg_fx_observation_history_no_update
        BEFORE UPDATE ON fx_observation_history
        BEGIN SELECT RAISE(ABORT,'fx_observation_history is append-only'); END"""
    )
    repository._connection.commit()


def test_fresh_observation_persistence_and_read_purity(tmp_path):
    path = tmp_path / "fx.sqlite3"
    with SQLiteFXObservationRepository(path) as repository:
        owner, identity, admitted, committed = owner_with(repository, observation_id="obs-1")
        result = owner.execute(command())

        assert result.replayed is False
        assert result.observation.observation_id == "obs-1"
        assert result.observation.base_currency == "USD"
        assert result.observation.quote_currency == "KRW"
        assert result.observation.rate == Decimal("1380.10")
        assert result.observation.schema_version == FX_OBSERVATION_SCHEMA_VERSION
        assert result.observation.pair == "USD/KRW"
        assert result.observation.provenance.provider == "provider-alpha"

        fetched_observation = repository.get_observation("obs-1")
        fetched_receipt = repository.get_receipt("fx-observation-command-1")

        assert fetched_observation == result.observation
        assert fetched_receipt == result.receipt
        assert fetched_receipt is not None
        assert fetched_receipt.command_fingerprint == command().fingerprint

        assert count_rows(repository) == (1, 1)
        assert repository._connection.in_transaction is False
        assert identity.calls == 1
        assert admitted.calls == 1
        assert committed.calls == 1


def test_round_trip_preserves_decimal_and_pair_and_provenance(tmp_path):
    path = tmp_path / "fx.sqlite3"
    with SQLiteFXObservationRepository(path) as repository:
        owner, _, _, _ = owner_with(repository, observation_id="obs-1")
        result = owner.execute(command(base_currency="GBP", quote_currency="JPY", rate=Decimal("151.20")))
        assert result.observation.rate == Decimal("151.20")

    with SQLiteFXObservationRepository(path) as repository:
        loaded = repository.get_observation("obs-1")
        assert loaded is not None
        assert loaded.base_currency == "GBP"
        assert loaded.quote_currency == "JPY"
        assert loaded.rate == Decimal("151.20")
        assert loaded.pair == "GBP/JPY"
        assert loaded.schema_version == FX_OBSERVATION_SCHEMA_VERSION
        assert loaded.provenance.provider == "provider-alpha"
        assert loaded.provenance.source_reference == "ext:obs:1"
        assert loaded.provenance.collection_method == "scheduled-pull"


def test_exact_replay_preserves_identity_and_timestamps_without_replay_calls(tmp_path):
    path = tmp_path / "fx.sqlite3"
    with SQLiteFXObservationRepository(path) as repository:
        first_owner, first_identity, first_admitted, first_committed = owner_with(
            repository, observation_id="obs-1"
        )
        first = first_owner.execute(command())
        assert first.replayed is False

    with SQLiteFXObservationRepository(path) as repository:
        replay_owner, replay_identity, replay_admitted, replay_committed = owner_with(
            repository,
            observation_id=str(uuid4()),
            fail_identity=True,
            fail_clock=True,
        )
        replay = replay_owner.execute(command())
        assert replay.replayed is True
        assert replay.observation == first.observation
        assert replay.receipt == first.receipt
        assert replay_identity.calls == 0
        assert replay_admitted.calls == 0
        assert replay_committed.calls == 0

        assert first_identity.calls == 1
        assert first_admitted.calls == 1
        assert first_committed.calls == 1


def test_changed_payload_causes_replay_conflict(tmp_path):
    path = tmp_path / "fx.sqlite3"
    with SQLiteFXObservationRepository(path) as repository:
        owner, _, _, _ = owner_with(repository, observation_id="obs-1")
        owner.execute(command())
        with pytest.raises(FXObservationReplayConflictError):
            owner.execute(command(rate=Decimal("1390")))
        assert count_rows(repository) == (1, 1)


def test_changed_pair_causes_replay_conflict(tmp_path):
    path = tmp_path / "fx.sqlite3"
    with SQLiteFXObservationRepository(path) as repository:
        owner, _, _, _ = owner_with(repository, observation_id="obs-1")
        owner.execute(command(quote_currency="KRW"))
        with pytest.raises(FXObservationReplayConflictError):
            owner.execute(command(quote_currency="CNY"))


def test_restart_replay_convergence(tmp_path):
    path = tmp_path / "fx.sqlite3"
    with SQLiteFXObservationRepository(path) as repository:
        owner, _, _, _ = owner_with(repository, observation_id="obs-1")
        first = owner.execute(command())

    with SQLiteFXObservationRepository(path) as repository:
        replay_owner, identity, admitted, committed = owner_with(
            repository,
            observation_id="obs-2",
            fail_identity=True,
            fail_clock=True,
        )
        replay = replay_owner.execute(command())
        assert replay.replayed
        assert replay.observation == first.observation
        assert replay.receipt == first.receipt
        assert identity.calls == 0
        assert admitted.calls == 0
        assert committed.calls == 0


def test_update_and_delete_blocked(tmp_path):
    path = tmp_path / "fx.sqlite3"
    with SQLiteFXObservationRepository(path) as repository:
        owner, _, _, _ = owner_with(repository, observation_id="obs-1")
        owner.execute(command())

        with pytest.raises(sqlite3.IntegrityError):
            repository._connection.execute("UPDATE fx_observation_history SET inserted_at=inserted_at")
        with pytest.raises(sqlite3.IntegrityError):
            repository._connection.execute("DELETE FROM fx_observation_receipts")


def test_observation_insert_rollback(tmp_path):
    path = tmp_path / "fx.sqlite3"
    with SQLiteFXObservationRepository(path) as repository:
        repository._connection.execute(
            "CREATE TRIGGER trg_force_observation_insert "
            "BEFORE INSERT ON fx_observation_history "
            "BEGIN SELECT RAISE(ABORT,'forced'); END"
        )
        repository._connection.commit()

        owner, _, _, _ = owner_with(repository, observation_id="obs-1")
        with pytest.raises(FXObservationHistoryError):
            owner.execute(command())
        assert count_rows(repository) == (0, 0)
        assert repository._connection.in_transaction is False


def test_receipt_insert_rollback(tmp_path):
    path = tmp_path / "fx.sqlite3"
    with SQLiteFXObservationRepository(path) as repository:
        repository._connection.execute(
            "CREATE TRIGGER trg_force_receipt_insert "
            "BEFORE INSERT ON fx_observation_receipts "
            "BEGIN SELECT RAISE(ABORT,'forced'); END"
        )
        repository._connection.commit()

        owner, _, _, _ = owner_with(repository, observation_id="obs-1")
        with pytest.raises(FXObservationReceiptError):
            owner.execute(command())
        assert count_rows(repository) == (0, 0)
        assert repository._connection.in_transaction is False


def test_commit_failure_rollback(tmp_path, monkeypatch):
    path = tmp_path / "fx.sqlite3"
    with SQLiteFXObservationRepository(path) as repository:
        owner, _, _, _ = owner_with(repository, observation_id="obs-1")
        monkeypatch.setattr(
            repository,
            "_commit",
            lambda: (_ for _ in ()).throw(sqlite3.OperationalError("forced")),
        )
        with pytest.raises(FXObservationCommitError):
            owner.execute(command())
        assert count_rows(repository) == (0, 0)
        assert repository._connection.in_transaction is False


def test_rewrite_payload_malformed_and_unsupported_schema_cases(tmp_path):
    path = tmp_path / "fx.sqlite3"
    with SQLiteFXObservationRepository(path) as repository:
        owner, _, _, _ = owner_with(repository, observation_id="obs-1")
        result = owner.execute(command())
        oid = result.observation.observation_id

        rewrite_payload(
            repository,
            oid,
            lambda payload: payload.__setitem__("base_currency", "USDD"),
            preserve_fingerprint=True,
        )
        with pytest.raises(MalformedFXObservationPersistenceError):
            repository.get_observation(oid)

    with SQLiteFXObservationRepository(tmp_path / "fx_unsupported.sqlite3") as repository:
        owner, _, _, _ = owner_with(repository, observation_id="obs-1")
        result = owner.execute(command(base_currency="EUR", quote_currency="USD"))
        oid = result.observation.observation_id

        rewrite_payload(
            repository,
            oid,
            lambda payload: payload.update({"schema_version": "future"}),
            preserve_fingerprint=True,
        )
        with pytest.raises(UnsupportedFXObservationVersionError):
            repository.get_observation(oid)

    with SQLiteFXObservationRepository(tmp_path / "fx_corrupt_provider.sqlite3") as repository:
        owner, _, _, _ = owner_with(repository, observation_id="obs-1")
        result = owner.execute(command(base_currency="GBP", quote_currency="USD"))
        oid = result.observation.observation_id

        rewrite_payload(
            repository,
            oid,
            lambda payload: payload["provenance"].update({"provider": ""}),
            preserve_fingerprint=True,
        )
        with pytest.raises(MalformedFXObservationPersistenceError):
            repository.get_observation(oid)

    with SQLiteFXObservationRepository(tmp_path / "fx_corrupt_fp.sqlite3") as repository:
        owner, _, _, _ = owner_with(repository, observation_id="obs-1")
        result = owner.execute(command(base_currency="AUD", quote_currency="USD"))
        oid = result.observation.observation_id

        rewrite_payload(
            repository,
            oid,
            lambda payload: payload.__setitem__("schema_version", "fx-observation-v1"),
            preserve_fingerprint=False,
        )
        with pytest.raises(MalformedFXObservationPersistenceError):
            repository.get_observation(oid)


def test_orphan_receipt_rejected(tmp_path):
    path = tmp_path / "fx.sqlite3"
    with SQLiteFXObservationRepository(path) as repository:
        repository._connection.execute("PRAGMA foreign_keys = OFF")
        repository._connection.execute(
            """INSERT INTO fx_observation_receipts
            VALUES(?,?,?,?,?,?)""",
            (
                "orphan-command",
                "missing-observation-id",
                "a" * 64,
                BASE_NOW.isoformat(),
                "fx-observation-receipt-v1",
                BASE_NOW.isoformat(),
            ),
        )
        repository._connection.commit()
        with pytest.raises(MalformedFXObservationPersistenceError):
            repository.validate_replay("orphan-command", "a" * 64)


def test_replay_and_validation_idempotence(tmp_path):
    path = tmp_path / "fx.sqlite3"
    with SQLiteFXObservationRepository(path) as repository:
        owner, _, _, _ = owner_with(repository, observation_id="obs-1")
        original = owner.execute(command())
        replayed = owner.execute(command())

        assert replayed.observation == original.observation
        assert replayed.receipt == original.receipt
        assert replayed.replayed is True
        assert count_rows(repository) == (1, 1)


def _run_concurrency(path, payload):
    with SQLiteFXObservationRepository(path) as repository:
        owner, _, _, _ = owner_with(repository, observation_id="obs-concurrent")
        return owner.execute(payload)


def test_concurrency_same_payload_converges(tmp_path):
    path = tmp_path / "fx.sqlite3"
    barrier = Barrier(2)
    results: list[sqlite3.Row | Exception] = []

    def worker(cmd):
        barrier.wait()
        try:
            return _run_concurrency(path, cmd)
        except Exception as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(worker, [command(), command()]))

    assert all(not isinstance(item, Exception) for item in results)
    first, second = results
    assert first.observation == second.observation
    assert first.receipt == second.receipt

    with SQLiteFXObservationRepository(path) as repository:
        assert count_rows(repository) == (1, 1)


def test_concurrency_conflict_with_different_payload(tmp_path):
    path = tmp_path / "fx.sqlite3"
    barrier = Barrier(2)

    def worker(cmd):
        barrier.wait()
        try:
            return _run_concurrency(path, cmd)
        except FXObservationReplayConflictError:
            return "conflict"
        except Exception as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as executor:
        first, second = list(
            executor.map(worker, [command(rate=Decimal("1380.10")), command(rate=Decimal("1390"))])
        )

    assert any(item == "conflict" for item in [first, second])
    assert sum(isinstance(item, BaseException) for item in [first, second]) == 0


def test_read_path_does_not_mutate_state(tmp_path):
    path = tmp_path / "fx.sqlite3"
    with SQLiteFXObservationRepository(path) as repository:
        owner, _, _, _ = owner_with(repository, observation_id="obs-1")
        result = owner.execute(command())
        before = repository._connection.total_changes
        first = repository.get_observation(result.observation.observation_id)
        second_receipt = repository.get_receipt(result.receipt.command_id)

        assert first == result.observation
        assert second_receipt == result.receipt

        assert repository.get_observation(result.observation.observation_id) == result.observation
        assert repository.get_receipt(result.receipt.command_id) == result.receipt
        assert repository._connection.total_changes == before


def test_no_normalization_or_freshness_authority_in_repository(tmp_path):
    path = tmp_path / "fx.sqlite3"
    with SQLiteFXObservationRepository(path) as repository:
        owner, _, _, _ = owner_with(repository, observation_id="obs-1")
        result = owner.execute(command(rate=Decimal("1380"), base_currency="USD", quote_currency="KRW"))
        assert result.observation.rate == Decimal("1380")
        assert result.observation.pair == "USD/KRW"


def test_connection_ownership_and_injected_connection(tmp_path):
    path = tmp_path / "owned.sqlite3"
    repository = SQLiteFXObservationRepository(path)
    repository.close()
    with pytest.raises(sqlite3.ProgrammingError):
        repository._connection.execute("SELECT 1")

    conn = sqlite3.connect(tmp_path / "shared.sqlite3")
    injected = SQLiteFXObservationRepository(connection=conn)
    injected.close()
    assert conn.execute("SELECT 1").fetchone()[0] == 1
    assert conn.in_transaction is False
    conn.close()
