from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import json
import sqlite3
from threading import Barrier

import pytest

from app.application.sourcing import (
    AdmitFXObservation,
    AdmitShippingAllocationAuthority,
    NormalizeAcquisitionCosts,
    AcquisitionCostNormalizationReplayConflictError,
)
from app.domain.sourcing import (
    CommercialFactAvailability,
    CostAllocationBasis,
    LandedCostComponentKind,
    ShippingScope,
    ShippingTerm,
    SourcingMoneyFact,
)
from app.infrastructure.sourcing import (
    AcquisitionCostNormalizationCommitError,
    AcquisitionCostNormalizationHistoryError,
    AcquisitionCostNormalizationReceiptError,
    MalformedAcquisitionCostNormalizationPersistenceError,
    SQLiteAcquisitionCostNormalizationRepository,
    SQLiteFXObservationRepository,
    SQLiteLandedCostCompositionRepository,
    SQLiteShippingAllocationAuthorityRepository,
)
from test_acquisition_cost_normalization import Calls, command as normalization_command
from test_fx_observation_sqlite import command as fx_command
from test_landed_cost_composition_sqlite import (
    composition_command,
    seed,
    use_case as landed_owner,
)
from test_shipping_allocation_authority_reconciliation import command as allocation_command
from test_sourcing_authority_contract import NOW, command as sourcing_command


HISTORY = "acquisition_cost_normalization_history"
RECEIPTS = "acquisition_cost_normalization_receipts"


def seed_sources(path):
    source = sourcing_command(
        shipping_terms=(
            ShippingTerm(
                ShippingScope.SUPPLIER_SIDE,
                SourcingMoneyFact(CommercialFactAvailability.KNOWN, Decimal("20"), "CNY"),
            ),
            ShippingTerm(
                ShippingScope.INTERNATIONAL_FREIGHT,
                SourcingMoneyFact(CommercialFactAvailability.KNOWN, Decimal("30"), "CNY"),
            ),
            ShippingTerm(
                ShippingScope.DOMESTIC_INBOUND,
                SourcingMoneyFact(CommercialFactAvailability.KNOWN, Decimal("40"), "CNY"),
            ),
        )
    )
    _, binding = seed(path, source_command=source)
    with SQLiteLandedCostCompositionRepository(path) as repository:
        composition = landed_owner(repository)[0].execute(
            composition_command(binding)
        ).composition

    authorities = []
    specifications = (
        (LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING, CostAllocationBasis.PER_ORDER, 100),
        (LandedCostComponentKind.INTERNATIONAL_FREIGHT, CostAllocationBasis.PER_QUOTED_QUANTITY, None),
        (LandedCostComponentKind.DOMESTIC_INBOUND, CostAllocationBasis.PER_UNIT, None),
    )
    with SQLiteShippingAllocationAuthorityRepository(path) as repository:
        for index, (kind, basis, denominator) in enumerate(specifications, start=1):
            result = AdmitShippingAllocationAuthority(
                repository,
                authority_id_generator=lambda index=index: f"allocation-{index}",
                admitted_clock=lambda: NOW + timedelta(minutes=5),
                committed_clock=lambda: NOW + timedelta(minutes=6),
            ).execute(
                allocation_command(
                    composition,
                    command_id=f"allocation-command-{index}",
                    component_kind=kind,
                    effective_allocation_basis=basis,
                    per_order_denominator=denominator,
                    per_order_denominator_unit=("unit" if denominator else None),
                )
            )
            authorities.append(result.authority)

    with SQLiteFXObservationRepository(path) as repository:
        observation = AdmitFXObservation(
            repository,
            observation_id_generator=lambda: "fx-cny-krw",
            admitted_clock=lambda: NOW + timedelta(minutes=7),
            committed_clock=lambda: NOW + timedelta(minutes=8),
        ).execute(
            fx_command(
                command_id="fx-command-cny-krw",
                base_currency="CNY",
                quote_currency="KRW",
                rate=Decimal("190"),
            )
        ).observation
    return composition, tuple(authorities), (observation,)


def owner(repository, identity="normalization-1"):
    identity_call = Calls(identity)
    normalized = Calls(NOW + timedelta(minutes=9))
    committed = Calls(NOW + timedelta(minutes=10))
    return (
        NormalizeAcquisitionCosts(
            repository,
            normalization_id_generator=identity_call,
            normalized_clock=normalized,
            committed_clock=committed,
        ),
        identity_call,
        normalized,
        committed,
    )


def counts(repository):
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (HISTORY, RECEIPTS)
    )


def test_fresh_persistence_round_trip_and_read_path_are_exact_and_pure(tmp_path):
    path = tmp_path / "normalization.sqlite3"
    composition, authorities, observations = seed_sources(path)
    with SQLiteAcquisitionCostNormalizationRepository(path) as repository:
        result = owner(repository)[0].execute(
            normalization_command(composition, authorities, observations)
        )
        before = repository._connection.total_changes
        assert repository.get_normalization(result.normalization.normalization_id) == result.normalization
        assert repository.get_receipt(result.receipt.command_id) == result.receipt
        assert repository._connection.total_changes == before
        assert counts(repository) == (1, 1)
        assert repository._connection.in_transaction is False


def test_restart_replay_uses_persisted_result_without_identity_or_clocks(tmp_path):
    path = tmp_path / "normalization.sqlite3"
    composition, authorities, observations = seed_sources(path)
    request = normalization_command(composition, authorities, observations)
    with SQLiteAcquisitionCostNormalizationRepository(path) as repository:
        first = owner(repository)[0].execute(request)

    class Never:
        def __call__(self):
            raise AssertionError("fresh dependency called during replay")

    with SQLiteAcquisitionCostNormalizationRepository(path) as repository:
        replay = NormalizeAcquisitionCosts(
            repository,
            normalization_id_generator=Never(),
            normalized_clock=Never(),
            committed_clock=Never(),
        ).execute(request)
        assert replay.replayed is True
        assert replay.normalization == first.normalization
        assert replay.receipt == first.receipt
        assert counts(repository) == (1, 1)


def test_changed_exact_source_or_target_conflicts(tmp_path):
    path = tmp_path / "normalization.sqlite3"
    composition, authorities, observations = seed_sources(path)
    with SQLiteAcquisitionCostNormalizationRepository(path) as repository:
        boundary = owner(repository)[0]
        boundary.execute(normalization_command(composition, authorities, observations))
        with pytest.raises(AcquisitionCostNormalizationReplayConflictError):
            boundary.execute(
                normalization_command(
                    composition,
                    authorities,
                    observations,
                    target_currency="USD",
                )
            )


@pytest.mark.parametrize("table", [HISTORY, RECEIPTS])
@pytest.mark.parametrize("operation", ["UPDATE", "DELETE"])
def test_history_and_receipt_are_append_only(tmp_path, table, operation):
    path = tmp_path / "normalization.sqlite3"
    composition, authorities, observations = seed_sources(path)
    with SQLiteAcquisitionCostNormalizationRepository(path) as repository:
        owner(repository)[0].execute(normalization_command(composition, authorities, observations))
        with pytest.raises(sqlite3.IntegrityError):
            repository._connection.execute(
                f"{operation} FROM {table}"
                if operation == "DELETE"
                else f"UPDATE {table} SET inserted_at=inserted_at"
            )
        repository._connection.rollback()


@pytest.mark.parametrize(
    ("failure", "error_type"),
    [
        ("history", AcquisitionCostNormalizationHistoryError),
        ("receipt", AcquisitionCostNormalizationReceiptError),
        ("commit", AcquisitionCostNormalizationCommitError),
    ],
)
def test_transaction_failures_roll_back_without_partial_authority(
    tmp_path, monkeypatch, failure, error_type
):
    path = tmp_path / "normalization.sqlite3"
    composition, authorities, observations = seed_sources(path)
    with SQLiteAcquisitionCostNormalizationRepository(path) as repository:
        if failure in {"history", "receipt"}:
            table = HISTORY if failure == "history" else RECEIPTS
            repository._connection.execute(
                f"CREATE TRIGGER forced_failure BEFORE INSERT ON {table} "
                "BEGIN SELECT RAISE(ABORT,'forced'); END"
            )
        else:
            monkeypatch.setattr(
                repository,
                "_commit",
                lambda: (_ for _ in ()).throw(sqlite3.OperationalError("forced")),
            )
        with pytest.raises(error_type):
            owner(repository)[0].execute(
                normalization_command(composition, authorities, observations)
            )
        assert counts(repository) == (0, 0)
        assert repository._connection.in_transaction is False


def test_concurrent_same_command_converges(tmp_path):
    path = tmp_path / "normalization.sqlite3"
    composition, authorities, observations = seed_sources(path)
    request = normalization_command(composition, authorities, observations)
    barrier = Barrier(2)

    def run(identity):
        with SQLiteAcquisitionCostNormalizationRepository(path) as repository:
            barrier.wait()
            return owner(repository, identity)[0].execute(request)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, ("normalization-a", "normalization-b")))
    assert len({value.normalization.normalization_id for value in results}) == 1


def test_concurrent_changed_payload_commits_one_and_conflicts_the_other(tmp_path):
    path = tmp_path / "normalization.sqlite3"
    composition, authorities, observations = seed_sources(path)
    requests = (
        normalization_command(composition, authorities, observations),
        normalization_command(
            composition,
            authorities,
            observations,
            target_currency="CNY",
            fx_observation_ids=(),
        ),
    )
    barrier = Barrier(2)

    def run(arguments):
        identity, request = arguments
        try:
            with SQLiteAcquisitionCostNormalizationRepository(path) as repository:
                barrier.wait()
                return owner(repository, identity)[0].execute(request)
        except AcquisitionCostNormalizationReplayConflictError as error:
            return error

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(run, zip(("normalization-a", "normalization-b"), requests)))
    assert sum(not isinstance(value, Exception) for value in results) == 1
    assert sum(
        isinstance(value, AcquisitionCostNormalizationReplayConflictError)
        for value in results
    ) == 1
    with SQLiteAcquisitionCostNormalizationRepository(path) as repository:
        assert counts(repository) == (1, 1)


def _tamper_total(payload):
    payload["total_per_unit_acquisition_cost"] = "999"


def _tamper_component(payload):
    payload["components"][0]["kind"] = "invalid"


def _tamper_decimal(payload):
    payload["components"][0]["normalized_per_unit_amount"] = "NaN"


def _tamper_target(payload):
    payload["target_currency"] = "INVALID"


def _tamper_allocation_manifest(payload):
    payload["allocation_authority_ids"] = []


def _tamper_allocation_reference(payload):
    payload["components"][1]["allocation_authority_id"] = "missing-allocation"
    payload["allocation_authority_ids"][0] = "missing-allocation"


def _tamper_fx_reference(payload):
    payload["components"][0]["fx_observation_id"] = "missing-fx"
    payload["fx_observation_ids"][0] = "missing-fx"


def _tamper_mixed_target(payload):
    payload["components"][0]["target_currency"] = "USD"


def _tamper_policy(payload):
    payload["policy_version"] = "2.0.0"


@pytest.mark.parametrize(
    "tamper",
    [
        _tamper_total,
        _tamper_component,
        _tamper_decimal,
        _tamper_target,
        _tamper_allocation_manifest,
        _tamper_allocation_reference,
        _tamper_fx_reference,
        _tamper_mixed_target,
        _tamper_policy,
    ],
)
def test_malformed_normalization_payload_is_rejected(tmp_path, tamper):
    path = tmp_path / "normalization.sqlite3"
    composition, authorities, observations = seed_sources(path)
    with SQLiteAcquisitionCostNormalizationRepository(path) as repository:
        result = owner(repository)[0].execute(
            normalization_command(composition, authorities, observations)
        )
        repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
        row = repository._connection.execute(
            f"SELECT payload_json FROM {HISTORY} WHERE normalization_id=?",
            (result.normalization.normalization_id,),
        ).fetchone()
        payload = json.loads(row[0])
        tamper(payload)
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        fingerprint = __import__("hashlib").sha256(encoded.encode()).hexdigest()
        repository._connection.execute(
            f"UPDATE {HISTORY} SET payload_json=?,integrity_fingerprint=?",
            (encoded, fingerprint),
        )
        repository._connection.commit()
        with pytest.raises(MalformedAcquisitionCostNormalizationPersistenceError):
            repository.get_normalization(result.normalization.normalization_id)


def test_fingerprint_mismatch_and_orphan_receipt_are_rejected(tmp_path):
    path = tmp_path / "normalization.sqlite3"
    composition, authorities, observations = seed_sources(path)
    with SQLiteAcquisitionCostNormalizationRepository(path) as repository:
        result = owner(repository)[0].execute(
            normalization_command(composition, authorities, observations)
        )
        repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
        repository._connection.execute(
            f"UPDATE {HISTORY} SET integrity_fingerprint='{'0' * 64}'"
        )
        repository._connection.commit()
        with pytest.raises(MalformedAcquisitionCostNormalizationPersistenceError):
            repository.get_normalization(result.normalization.normalization_id)

    orphan_path = tmp_path / "orphan.sqlite3"
    composition, authorities, observations = seed_sources(orphan_path)
    with SQLiteAcquisitionCostNormalizationRepository(orphan_path) as repository:
        result = owner(repository)[0].execute(
            normalization_command(composition, authorities, observations)
        )
        repository._connection.execute(f"DROP TRIGGER trg_{RECEIPTS}_no_update")
        repository._connection.execute("PRAGMA foreign_keys = OFF")
        repository._connection.execute(
            f"UPDATE {RECEIPTS} SET normalization_id='missing-normalization'"
        )
        repository._connection.commit()
        with pytest.raises(MalformedAcquisitionCostNormalizationPersistenceError):
            repository.get_receipt(result.receipt.command_id)
