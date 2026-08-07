from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import hashlib
import json
import sqlite3
from threading import Barrier
from uuid import uuid4

import pytest

from app.application.sourcing import (
    BindSourcingEconomicsSource,
    BindSourcingEconomicsSourceCommand,
    ComposeLandedCost,
    ComposeLandedCostCommand,
    LandedCostCompositionReplayConflictError,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing import (
    CommercialFactAvailability,
    LandedCostComponentKind,
    ShippingScope,
    ShippingTerm,
    SourcingMoneyFact,
)
from app.infrastructure.sourcing import (
    LandedCostCompositionCommitError,
    LandedCostCompositionHistoryError,
    LandedCostCompositionReceiptError,
    MalformedLandedCostCompositionPersistenceError,
    SQLiteLandedCostCompositionRepository,
    SQLiteSourcingAuthorityRepository,
    SQLiteSourcingEconomicsBindingRepository,
    UnsupportedLandedCostCompositionVersionError,
)
from test_sourcing_authority_contract import NOW, command
from test_sourcing_authority_sqlite_persistence import boundary


HISTORY = "landed_cost_composition_history"
RECEIPTS = "landed_cost_composition_receipts"


class Counter:
    def __init__(self, value, *, fail=False):
        self.value = value
        self.calls = 0
        self.fail = fail

    def __call__(self):
        self.calls += 1
        if self.fail:
            pytest.fail("fresh dependency called during replay")
        return self.value() if callable(self.value) else self.value


def seed(path, *, source_command=None):
    with SQLiteSourcingAuthorityRepository(path) as repository:
        admission = boundary(repository).execute(source_command or command()).admission
    with SQLiteSourcingEconomicsBindingRepository(path) as repository:
        binding = BindSourcingEconomicsSource(
            repository,
            binding_id_generator=lambda: "economics-binding-1",
            bound_clock=lambda: NOW + timedelta(minutes=1),
            committed_clock=lambda: NOW + timedelta(minutes=2),
        ).execute(BindSourcingEconomicsSourceCommand(
            "economics-binding-command-1",
            OpportunityIdentity("opp-1", "discovery-1"),
            admission.to_economics_source_reference(),
            NOW,
        )).binding
    return admission, binding


def composition_command(binding, **changes):
    values = dict(
        command_id="landed-cost-command-1",
        opportunity_identity=OpportunityIdentity("opp-1", "discovery-1"),
        binding_reference=binding.reference,
        requested_at=NOW,
    )
    values.update(changes)
    return ComposeLandedCostCommand(**values)


def use_case(repository, *, fail=False, identity=None):
    identity = identity or Counter("landed-cost-composition-1", fail=fail)
    composed = Counter(NOW + timedelta(minutes=3), fail=fail)
    committed = Counter(NOW + timedelta(minutes=4), fail=fail)
    owner = ComposeLandedCost(
        repository,
        composition_id_generator=identity,
        composed_clock=composed,
        committed_clock=committed,
    )
    return owner, identity, composed, committed


def counts(repository):
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (HISTORY, RECEIPTS)
    )


def test_fresh_round_trip_preserves_all_authoritative_facts_and_read_is_pure(tmp_path):
    path = tmp_path / "sourcing.sqlite3"
    _, binding = seed(path)
    with SQLiteLandedCostCompositionRepository(path) as repository:
        result = use_case(repository)[0].execute(composition_command(binding))
        before = repository._connection.total_changes
        assert repository.get_composition(result.composition.composition_id) == result.composition
        assert repository.get_receipt(result.receipt.command_id) == result.receipt
        assert repository.get_composition(result.composition.composition_id) == result.composition
        assert repository._connection.total_changes == before
        assert repository._connection.in_transaction is False
        assert result.composition.binding_reference == binding.reference
        assert tuple(item.kind for item in result.composition.components) == tuple(LandedCostComponentKind)


def test_known_zero_unknown_not_applicable_and_unspecified_allocation_round_trip(tmp_path):
    path = tmp_path / "sourcing.sqlite3"
    terms = command().shipping_terms
    source = command(shipping_terms=(
        replace(terms[0], cost=SourcingMoneyFact(
            CommercialFactAvailability.KNOWN, Decimal("0"), "CNY"
        )),
        replace(terms[1], cost=SourcingMoneyFact(CommercialFactAvailability.UNKNOWN)),
        replace(terms[2], cost=SourcingMoneyFact(CommercialFactAvailability.NOT_APPLICABLE)),
    ))
    admission, binding = seed(path, source_command=source)
    with SQLiteLandedCostCompositionRepository(path) as repository:
        saved = use_case(repository)[0].execute(composition_command(binding)).composition
    with SQLiteLandedCostCompositionRepository(path) as repository:
        restored = repository.get_composition(saved.composition_id)
    assert restored == saved
    assert restored.minimum_order_quantity == admission.quote_revision.minimum_order_quantity
    assert restored.quoted_quantity == admission.quote_revision.quoted_quantity
    shipping = restored.components[1:]
    assert (shipping[0].amount, shipping[0].currency) == (Decimal("0"), "CNY")
    assert (shipping[1].amount, shipping[1].currency) == (None, None)
    assert (shipping[2].amount, shipping[2].currency) == (None, None)
    assert len({item.availability for item in shipping}) == 3
    assert all(item.allocation_basis.value == "unspecified" for item in shipping)


def test_mixed_source_currencies_are_not_normalized(tmp_path):
    path = tmp_path / "sourcing.sqlite3"
    terms = command().shipping_terms
    source = command(shipping_terms=(
        replace(terms[0], cost=SourcingMoneyFact(
            CommercialFactAvailability.KNOWN, Decimal("2"), "CNY"
        )),
        replace(terms[1], cost=SourcingMoneyFact(
            CommercialFactAvailability.KNOWN, Decimal("3"), "USD"
        )),
        replace(terms[2], cost=SourcingMoneyFact(
            CommercialFactAvailability.KNOWN, Decimal("4"), "KRW"
        )),
    ))
    _, binding = seed(path, source_command=source)
    with SQLiteLandedCostCompositionRepository(path) as repository:
        saved = use_case(repository)[0].execute(composition_command(binding)).composition
    with SQLiteLandedCostCompositionRepository(path) as repository:
        restored = repository.get_composition(saved.composition_id)
    assert restored.known_currencies == ("CNY", "USD", "KRW")
    assert tuple(item.amount for item in restored.components) == (
        Decimal("12.3400"), Decimal("2"), Decimal("3"), Decimal("4")
    )


def test_exact_restart_replay_returns_original_without_identity_or_clocks(tmp_path):
    path = tmp_path / "sourcing.sqlite3"
    _, binding = seed(path)
    with SQLiteLandedCostCompositionRepository(path) as repository:
        first = use_case(repository)[0].execute(composition_command(binding))
    with SQLiteLandedCostCompositionRepository(path) as repository:
        replay = use_case(repository, fail=True)[0].execute(composition_command(binding))
        assert replay.composition == first.composition
        assert replay.receipt == first.receipt
        assert replay.replayed is True
        assert counts(repository) == (1, 1)


def test_changed_command_payload_conflicts_after_restart(tmp_path):
    path = tmp_path / "sourcing.sqlite3"
    _, binding = seed(path)
    with SQLiteLandedCostCompositionRepository(path) as repository:
        use_case(repository)[0].execute(composition_command(binding))
    with SQLiteLandedCostCompositionRepository(path) as repository:
        with pytest.raises(LandedCostCompositionReplayConflictError):
            use_case(repository, fail=True)[0].execute(composition_command(
                binding, requested_at=NOW + timedelta(seconds=1)
            ))
        assert counts(repository) == (1, 1)


@pytest.mark.parametrize("table", [HISTORY, RECEIPTS])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_history_and_receipt_are_append_only(table, operation, tmp_path):
    path = tmp_path / "sourcing.sqlite3"
    _, binding = seed(path)
    with SQLiteLandedCostCompositionRepository(path) as repository:
        use_case(repository)[0].execute(composition_command(binding))
        with pytest.raises(sqlite3.IntegrityError):
            if operation == "UPDATE":
                repository._connection.execute(f"UPDATE {table} SET inserted_at=inserted_at")
            else:
                repository._connection.execute(f"DELETE FROM {table}")
        repository._connection.rollback()


@pytest.mark.parametrize(("failure", "error_type"), [
    ("composition", LandedCostCompositionHistoryError),
    ("receipt", LandedCostCompositionReceiptError),
    ("commit", LandedCostCompositionCommitError),
])
def test_atomic_failures_rollback_all_rows_and_allow_retry(
    failure, error_type, tmp_path, monkeypatch
):
    path = tmp_path / "sourcing.sqlite3"
    _, binding = seed(path)
    with SQLiteLandedCostCompositionRepository(path) as repository:
        original_commit = repository._commit
        if failure == "composition":
            repository._connection.execute(
                f"CREATE TRIGGER force_composition_failure BEFORE INSERT ON {HISTORY} "
                "BEGIN SELECT RAISE(ABORT,'forced'); END"
            )
            repository._connection.commit()
        elif failure == "receipt":
            repository._connection.execute(
                f"CREATE TRIGGER force_receipt_failure BEFORE INSERT ON {RECEIPTS} "
                "BEGIN SELECT RAISE(ABORT,'forced'); END"
            )
            repository._connection.commit()
        else:
            monkeypatch.setattr(
                repository,
                "_commit",
                lambda: (_ for _ in ()).throw(sqlite3.OperationalError("forced")),
            )
        with pytest.raises(error_type):
            use_case(repository)[0].execute(composition_command(binding))
        assert counts(repository) == (0, 0)
        assert repository._connection.in_transaction is False
        if failure == "composition":
            repository._connection.execute("DROP TRIGGER force_composition_failure")
            repository._connection.commit()
        elif failure == "receipt":
            repository._connection.execute("DROP TRIGGER force_receipt_failure")
            repository._connection.commit()
        else:
            monkeypatch.setattr(repository, "_commit", original_commit)
        retry = use_case(repository)[0].execute(composition_command(binding))
        assert retry.replayed is False
        assert counts(repository) == (1, 1)


def _rewrite_payload(repository, mutate, *, preserve_fingerprint=True):
    row = repository._connection.execute(
        f"SELECT payload_json FROM {HISTORY}"
    ).fetchone()
    payload = json.loads(row[0])
    mutate(payload)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    fingerprint = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    repository._connection.execute(
        f"DROP TRIGGER trg_{HISTORY}_no_update"
    )
    repository._connection.execute(
        f"UPDATE {HISTORY} SET payload_json=?, integrity_fingerprint=?",
        (encoded, fingerprint if preserve_fingerprint else "0" * 64),
    )
    repository._connection.commit()


@pytest.mark.parametrize("corruption", [
    "invalid_kind", "invalid_availability", "invalid_basis", "unknown_amount",
    "known_missing_amount", "invalid_currency", "missing_component",
    "duplicate_component", "wrong_order",
])
def test_malformed_component_persistence_is_rejected(corruption, tmp_path):
    path = tmp_path / f"{corruption}.sqlite3"
    _, binding = seed(path)
    with SQLiteLandedCostCompositionRepository(path) as repository:
        result = use_case(repository)[0].execute(composition_command(binding))

        def mutate(payload):
            components = payload["components"]
            if corruption == "invalid_kind":
                components[0]["kind"] = "future"
            elif corruption == "invalid_availability":
                components[1]["availability"] = "future"
            elif corruption == "invalid_basis":
                components[1]["allocation_basis"] = "future"
            elif corruption == "unknown_amount":
                components[1].update(availability="unknown", amount="0", currency="CNY")
            elif corruption == "known_missing_amount":
                components[0].update(amount=None, currency=None)
            elif corruption == "invalid_currency":
                components[0]["currency"] = "INVALID"
            elif corruption == "missing_component":
                components.pop()
            elif corruption == "duplicate_component":
                components[-1] = dict(components[-2])
            else:
                components[1], components[2] = components[2], components[1]

        _rewrite_payload(repository, mutate)
        with pytest.raises(MalformedLandedCostCompositionPersistenceError):
            repository.get_composition(result.composition.composition_id)


def test_unsupported_corrupt_json_integrity_and_orphan_receipt_are_rejected(tmp_path):
    path = tmp_path / "sourcing.sqlite3"
    _, binding = seed(path)
    with SQLiteLandedCostCompositionRepository(path) as repository:
        result = use_case(repository)[0].execute(composition_command(binding))
        original_payload = repository._connection.execute(
            f"SELECT payload_json FROM {HISTORY}"
        ).fetchone()[0]
        repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
        repository._connection.execute(
            f"UPDATE {HISTORY} SET schema_version='future'"
        )
        repository._connection.commit()
        with pytest.raises(UnsupportedLandedCostCompositionVersionError):
            repository.get_composition(result.composition.composition_id)
        repository._connection.execute(
            f"UPDATE {HISTORY} SET schema_version='landed-cost-composition-v1', payload_json='{{'"
        )
        repository._connection.commit()
        with pytest.raises(MalformedLandedCostCompositionPersistenceError):
            repository.get_composition(result.composition.composition_id)
        repository._connection.execute(
            f"UPDATE {HISTORY} SET payload_json=?, integrity_fingerprint=?",
            (original_payload, "0" * 64),
        )
        repository._connection.commit()
        with pytest.raises(MalformedLandedCostCompositionPersistenceError):
            repository.get_composition(result.composition.composition_id)

    orphan_path = tmp_path / "orphan.sqlite3"
    with SQLiteLandedCostCompositionRepository(orphan_path) as repository:
        repository._connection.execute("PRAGMA foreign_keys = OFF")
        repository._connection.execute(
            f"INSERT INTO {RECEIPTS} VALUES(?,?,?,?,?,?)",
            ("orphan-command", "missing-composition", "0" * 64,
             NOW.isoformat(), "landed-cost-composition-receipt-v1", NOW.isoformat()),
        )
        repository._connection.commit()
        with pytest.raises(MalformedLandedCostCompositionPersistenceError):
            repository.validate_replay("orphan-command", "0" * 64)


def test_concurrent_same_command_converges_and_changed_payload_conflicts(tmp_path):
    path = tmp_path / "sourcing.sqlite3"
    _, binding = seed(path)

    def concurrent_run(offsets):
        barrier = Barrier(2)

        def run(offset):
            with SQLiteLandedCostCompositionRepository(path) as repository:
                barrier.wait()
                identity = Counter(lambda: uuid4().hex)
                try:
                    return use_case(repository, identity=identity)[0].execute(
                        composition_command(
                            binding, requested_at=NOW + timedelta(seconds=offset)
                        )
                    )
                except LandedCostCompositionReplayConflictError as error:
                    return error

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, offsets))

    same = concurrent_run([0, 0])
    assert same[0].composition == same[1].composition
    with SQLiteLandedCostCompositionRepository(path) as repository:
        assert counts(repository) == (1, 1)

    conflict_path = tmp_path / "conflict.sqlite3"
    _, conflict_binding = seed(conflict_path)
    path = conflict_path
    changed = concurrent_run([0, 1])
    assert sum(isinstance(value, LandedCostCompositionReplayConflictError) for value in changed) == 1
    with SQLiteLandedCostCompositionRepository(path) as repository:
        assert counts(repository) == (1, 1)
        assert repository._connection.in_transaction is False


def test_connection_ownership_and_failure_cleanup(tmp_path):
    owned = SQLiteLandedCostCompositionRepository(tmp_path / "owned.sqlite3")
    owned.close()
    with pytest.raises(sqlite3.ProgrammingError):
        owned._connection.execute("SELECT 1")

    connection = sqlite3.connect(tmp_path / "injected.sqlite3")
    repository = SQLiteLandedCostCompositionRepository(connection=connection)
    repository.close()
    assert connection.execute("SELECT 1").fetchone()[0] == 1
    assert connection.in_transaction is False
    connection.close()
