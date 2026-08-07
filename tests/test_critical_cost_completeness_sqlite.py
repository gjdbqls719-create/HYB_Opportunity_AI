from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
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
    CriticalCostCompletenessReplayConflictError,
    DOMESTIC_COMMERCE_CRITICAL_COST_POLICY,
    PersistCriticalCostCompleteness,
    PersistCriticalCostCompletenessCommand,
)
from app.application.verified_economics_admission import (
    FinalizeVerifiedEconomicsAdmission,
    FinalizeVerifiedEconomicsAdmissionCommand,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing import (
    CommercialFactAvailability,
    CriticalCostCompletenessState,
    CriticalCostReasonCode,
    ShippingTerm,
    SourcingMoneyFact,
)
from app.infrastructure.sourcing import (
    CriticalCostCompletenessCommitError,
    CriticalCostCompletenessHistoryError,
    CriticalCostCompletenessReceiptError,
    MalformedCriticalCostCompletenessPersistenceError,
    ProductionCriticalCostCompletenessIdentityGenerator,
    SQLiteCriticalCostCompletenessRepository,
    SQLiteLandedCostCompositionRepository,
    SQLiteSourcingAuthorityRepository,
    SQLiteSourcingEconomicsBindingRepository,
    UnsupportedCriticalCostCompletenessVersionError,
)
from test_critical_cost_completeness import economics
from test_economics_calculation_snapshot import NOW as ECONOMICS_NOW
from test_economics_calculation_snapshot_sqlite import cleanup, setup
from test_sourcing_authority_contract import NOW, command as sourcing_command
from test_sourcing_authority_sqlite_persistence import boundary


HISTORY = "critical_cost_completeness_history"
RECEIPTS = "critical_cost_completeness_receipts"


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


def seed(path, *, incomplete=False):
    resources, candidates, validation, economics_repository = setup(
        path, verified=False
    )
    verified = FinalizeVerifiedEconomicsAdmission(validation).execute(
        FinalizeVerifiedEconomicsAdmissionCommand(
            "opportunity-1",
            "critical-cost-verified-command-1",
            "founder",
            economics(currency="USD"),
            ECONOMICS_NOW,
        )
    ).snapshot
    cleanup(resources, candidates, validation, economics_repository)

    source = sourcing_command()
    lineage = replace(
        source.selling_product_lineage,
        opportunity_identity=OpportunityIdentity(
            "opportunity-1", "collector:ebay:item-1"
        ),
    )
    terms = source.shipping_terms
    if incomplete:
        shipping = (
            SourcingMoneyFact(CommercialFactAvailability.UNKNOWN),
            SourcingMoneyFact(CommercialFactAvailability.UNKNOWN),
            SourcingMoneyFact(CommercialFactAvailability.NOT_APPLICABLE),
        )
    else:
        shipping = (
            SourcingMoneyFact(
                CommercialFactAvailability.KNOWN, economics().shipping_cost.amount, "USD"
            ),
            SourcingMoneyFact(CommercialFactAvailability.NOT_APPLICABLE),
            SourcingMoneyFact(CommercialFactAvailability.NOT_APPLICABLE),
        )
    source = sourcing_command(
        selling_product_lineage=lineage,
        quoted_unit_price=SourcingMoneyFact(
            CommercialFactAvailability.KNOWN, economics().purchase_cost.amount, "USD"
        ),
        shipping_terms=tuple(
            ShippingTerm(term.scope, value)
            for term, value in zip(terms, shipping, strict=True)
        ),
        quote_valid_until=NOW + timedelta(days=1),
    )
    with SQLiteSourcingAuthorityRepository(path) as repository:
        admission = boundary(repository).execute(source).admission
    with SQLiteSourcingEconomicsBindingRepository(path) as repository:
        binding = BindSourcingEconomicsSource(
            repository,
            binding_id_generator=lambda: "critical-cost-binding-1",
            bound_clock=lambda: NOW + timedelta(minutes=1),
            committed_clock=lambda: NOW + timedelta(minutes=2),
        ).execute(
            BindSourcingEconomicsSourceCommand(
                "critical-cost-binding-command-1",
                lineage.opportunity_identity,
                admission.to_economics_source_reference(),
                NOW,
            )
        ).binding
    with SQLiteLandedCostCompositionRepository(path) as repository:
        composition = ComposeLandedCost(
            repository,
            composition_id_generator=lambda: "critical-cost-composition-1",
            composed_clock=lambda: NOW + timedelta(minutes=3),
            committed_clock=lambda: NOW + timedelta(minutes=4),
        ).execute(
            ComposeLandedCostCommand(
                "critical-cost-composition-command-1",
                lineage.opportunity_identity,
                binding.reference,
                NOW,
            )
        ).composition
    return composition, verified


def persistence_command(composition, verified, **changes):
    values = dict(
        command_id="critical-cost-command-1",
        composition_id=composition.composition_id,
        verified_economics_opportunity_id=verified.opportunity_id,
        verified_economics_snapshot_at=verified.snapshot_at,
        verified_economics_schema_version=verified.schema_version,
        policy_name=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY.name,
        policy_version=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY.version,
        requested_at=NOW,
    )
    values.update(changes)
    return PersistCriticalCostCompletenessCommand(**values)


def owner(repository, *, fail=False, identity=None, evaluated_at=None, committed_at=None):
    identity = identity or Counter("critical-cost-assessment-1", fail=fail)
    evaluated = Counter(evaluated_at or NOW + timedelta(minutes=5), fail=fail)
    committed = Counter(committed_at or NOW + timedelta(minutes=6), fail=fail)
    value = PersistCriticalCostCompleteness(
        repository,
        assessment_id_generator=identity,
        evaluated_clock=evaluated,
        committed_clock=committed,
        policy=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY,
    )
    return value, identity, evaluated, committed


def counts(repository):
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (HISTORY, RECEIPTS)
    )


def test_fresh_complete_assessment_round_trip_preserves_exact_sources_policy_and_reasons(tmp_path):
    path = tmp_path / "critical-cost.sqlite3"
    composition, verified = seed(path)
    with SQLiteCriticalCostCompletenessRepository(path) as repository:
        use_case, identity, evaluated, committed = owner(repository)
        result = use_case.execute(persistence_command(composition, verified))
        assert result.assessment.state is CriticalCostCompletenessState.COMPLETE
        assert result.receipt.assessment_id == "critical-cost-assessment-1"
        assert result.assessment.composition_id == composition.composition_id
        assert result.assessment.binding_reference == composition.binding_reference
        assert result.assessment.verified_economics_snapshot_at == verified.snapshot_at
        assert result.assessment.policy_name == DOMESTIC_COMMERCE_CRITICAL_COST_POLICY.name
        assert result.assessment.policy_version == DOMESTIC_COMMERCE_CRITICAL_COST_POLICY.version
        assert repository.get_assessment(result.receipt.assessment_id) == result.assessment
        assert repository.get_receipt(result.receipt.command_id) == result.receipt
        assert identity.calls == evaluated.calls == committed.calls == 1
        assert counts(repository) == (1, 1)
        assert result.assessment.source_reference == repository.get_binding(
            composition.binding_reference
        ).source_reference
        assert result.assessment.evaluated_at == NOW + timedelta(minutes=5)
        assert result.receipt.committed_at == NOW + timedelta(minutes=6)
        history_columns = {
            row[1] for row in repository._connection.execute(f"PRAGMA table_info({HISTORY})")
        }
        receipt_columns = {
            row[1] for row in repository._connection.execute(f"PRAGMA table_info({RECEIPTS})")
        }
        assert history_columns == {
            "assessment_id", "opportunity_id", "discovery_reference",
            "composition_id", "verified_economics_opportunity_id", "policy_name",
            "policy_version", "payload_json", "integrity_fingerprint",
            "schema_version", "inserted_at",
        }
        assert receipt_columns == {
            "command_id", "assessment_id", "command_fingerprint", "committed_at",
            "schema_version", "inserted_at",
        }
        assert not repository._connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name LIKE 'critical_cost_completeness_current%'"
        ).fetchall()


def test_production_assessment_identity_is_dedicated_stateless_uuid4_hex():
    generator = ProductionCriticalCostCompletenessIdentityGenerator()
    values = tuple(generator() for _ in range(64))
    assert len(set(values)) == len(values)
    assert all(len(value) == 32 and value == value.lower() for value in values)
    assert all(set(value) <= set("0123456789abcdef") for value in values)
    assert not hasattr(generator, "__dict__")


def test_incomplete_unknown_and_ordered_warning_reasons_round_trip(tmp_path):
    path = tmp_path / "critical-cost.sqlite3"
    composition, verified = seed(path, incomplete=True)
    with SQLiteCriticalCostCompletenessRepository(path) as repository:
        result = owner(repository)[0].execute(persistence_command(composition, verified))
        restored = repository.get_assessment(result.receipt.assessment_id)
    assert restored == result.assessment
    assert restored.state is CriticalCostCompletenessState.INCOMPLETE
    assert tuple(reason.code for reason in restored.blocking_reasons) == (
        CriticalCostReasonCode.SHIPPING_SCOPE_UNKNOWN,
        CriticalCostReasonCode.SHIPPING_SCOPE_UNKNOWN,
    )
    assert tuple(reason.code for reason in restored.warning_reasons) == (
        CriticalCostReasonCode.ADVERTISING_ALLOWANCE_DEFERRED,
        CriticalCostReasonCode.RETURNS_ALLOWANCE_DEFERRED,
    )
    assert not hasattr(restored, "roi")
    assert not hasattr(restored, "net_profit")


def test_restart_exact_replay_preserves_identity_times_and_rows_without_fresh_dependencies(tmp_path):
    path = tmp_path / "critical-cost.sqlite3"
    composition, verified = seed(path)
    command = persistence_command(composition, verified)
    with SQLiteCriticalCostCompletenessRepository(path) as repository:
        first = owner(repository)[0].execute(command)
    with SQLiteCriticalCostCompletenessRepository(path) as repository:
        replay = owner(repository, fail=True)[0].execute(command)
        assert replay.assessment == first.assessment
        assert replay.receipt == first.receipt
        assert replay.replayed is True
        assert counts(repository) == (1, 1)


def test_new_command_appends_history_without_refreshing_prior_assessment(tmp_path):
    path = tmp_path / "critical-cost.sqlite3"
    composition, verified = seed(path)
    with SQLiteCriticalCostCompletenessRepository(path) as repository:
        first = owner(repository)[0].execute(persistence_command(composition, verified))
        second_command = persistence_command(
            composition, verified, command_id="critical-cost-command-2"
        )
        second = owner(
            repository,
            identity=Counter("critical-cost-assessment-2"),
            evaluated_at=NOW + timedelta(minutes=7),
            committed_at=NOW + timedelta(minutes=8),
        )[0].execute(second_command)
        assert second.receipt.assessment_id != first.receipt.assessment_id
        assert repository.get_assessment(first.receipt.assessment_id) == first.assessment
        assert repository.get_assessment(second.receipt.assessment_id) == second.assessment
        assert counts(repository) == (2, 2)


@pytest.mark.parametrize(
    "change",
    (
        {"composition_id": "changed-composition"},
        {"verified_economics_snapshot_at": ECONOMICS_NOW + timedelta(seconds=1)},
        {"policy_version": "2.0.0"},
    ),
)
def test_same_command_changed_exact_source_or_policy_conflicts_before_dependencies(tmp_path, change):
    path = tmp_path / "critical-cost.sqlite3"
    composition, verified = seed(path)
    with SQLiteCriticalCostCompletenessRepository(path) as repository:
        use_case = owner(repository)[0]
        use_case.execute(persistence_command(composition, verified))
        blocked, identity, evaluated, committed = owner(repository, fail=True)
        with pytest.raises(CriticalCostCompletenessReplayConflictError):
            blocked.execute(persistence_command(composition, verified, **change))
        assert identity.calls == evaluated.calls == committed.calls == 0
        assert counts(repository) == (1, 1)


@pytest.mark.parametrize("table", (HISTORY, RECEIPTS))
@pytest.mark.parametrize("operation", ("UPDATE", "DELETE"))
def test_assessment_and_receipt_histories_are_append_only(tmp_path, table, operation):
    path = tmp_path / "critical-cost.sqlite3"
    composition, verified = seed(path)
    with SQLiteCriticalCostCompletenessRepository(path) as repository:
        owner(repository)[0].execute(persistence_command(composition, verified))
        with pytest.raises(sqlite3.IntegrityError):
            if operation == "UPDATE":
                repository._connection.execute(
                    f"UPDATE {table} SET inserted_at=inserted_at"
                )
            else:
                repository._connection.execute(f"DELETE FROM {table}")
        repository._connection.rollback()


@pytest.mark.parametrize(
    ("failure", "error_type"),
    (
        ("history", CriticalCostCompletenessHistoryError),
        ("receipt", CriticalCostCompletenessReceiptError),
        ("commit", CriticalCostCompletenessCommitError),
    ),
)
def test_atomic_failures_rollback_and_allow_retry(tmp_path, monkeypatch, failure, error_type):
    path = tmp_path / "critical-cost.sqlite3"
    composition, verified = seed(path)
    with SQLiteCriticalCostCompletenessRepository(path) as repository:
        original_commit = repository._commit
        table = HISTORY if failure == "history" else RECEIPTS
        if failure != "commit":
            repository._connection.execute(
                f"CREATE TRIGGER force_failure BEFORE INSERT ON {table} "
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
            owner(repository)[0].execute(persistence_command(composition, verified))
        assert counts(repository) == (0, 0)
        assert repository._connection.in_transaction is False
        if failure != "commit":
            repository._connection.execute("DROP TRIGGER force_failure")
            repository._connection.commit()
        else:
            monkeypatch.setattr(repository, "_commit", original_commit)
        assert owner(repository)[0].execute(
            persistence_command(composition, verified)
        ).replayed is False


def test_concurrent_same_command_converges_and_changed_payload_conflicts(tmp_path):
    path = tmp_path / "critical-cost.sqlite3"
    composition, verified = seed(path)

    def run_pair(changes):
        barrier = Barrier(2)

        def run(change):
            with SQLiteCriticalCostCompletenessRepository(path) as repository:
                barrier.wait()
                try:
                    return owner(
                        repository, identity=Counter(lambda: uuid4().hex)
                    )[0].execute(persistence_command(composition, verified, **change))
                except CriticalCostCompletenessReplayConflictError as error:
                    return error

        with ThreadPoolExecutor(max_workers=2) as pool:
            return list(pool.map(run, changes))

    same = run_pair(({}, {}))
    assert same[0].assessment == same[1].assessment
    with SQLiteCriticalCostCompletenessRepository(path) as repository:
        assert counts(repository) == (1, 1)

    conflict_path = tmp_path / "critical-cost-conflict.sqlite3"
    composition, verified = seed(conflict_path)
    path = conflict_path
    changed = run_pair(({}, {"requested_at": NOW + timedelta(seconds=1)}))
    assert sum(isinstance(value, CriticalCostCompletenessReplayConflictError) for value in changed) == 1
    with SQLiteCriticalCostCompletenessRepository(path) as repository:
        assert counts(repository) == (1, 1)


def _rewrite_payload(repository, mutate, *, preserve_fingerprint=True):
    row = repository._connection.execute(f"SELECT payload_json FROM {HISTORY}").fetchone()
    payload = json.loads(row[0])
    mutate(payload)
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    fingerprint = hashlib.sha256(encoded.encode()).hexdigest()
    repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
    repository._connection.execute(
        f"UPDATE {HISTORY} SET payload_json=?, integrity_fingerprint=?",
        (encoded, fingerprint if preserve_fingerprint else "0" * 64),
    )
    repository._connection.commit()


@pytest.mark.parametrize(
    "corruption",
    ("state", "reason", "reason_order", "policy", "schema", "json", "fingerprint"),
)
def test_malformed_assessment_persistence_is_rejected(tmp_path, corruption):
    path = tmp_path / f"{corruption}.sqlite3"
    composition, verified = seed(path, incomplete=True)
    with SQLiteCriticalCostCompletenessRepository(path) as repository:
        saved = owner(repository)[0].execute(persistence_command(composition, verified))
        if corruption == "schema":
            repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
            repository._connection.execute(f"UPDATE {HISTORY} SET schema_version='future'")
            repository._connection.commit()
            error_type = UnsupportedCriticalCostCompletenessVersionError
        elif corruption == "json":
            repository._connection.execute(f"DROP TRIGGER trg_{HISTORY}_no_update")
            repository._connection.execute(f"UPDATE {HISTORY} SET payload_json='{{'")
            repository._connection.commit()
            error_type = MalformedCriticalCostCompletenessPersistenceError
        else:
            def mutate(payload):
                if corruption == "state":
                    payload["state"] = "future"
                elif corruption == "reason":
                    payload["blocking_reasons"][0]["code"] = "future"
                elif corruption == "reason_order":
                    payload["blocking_reasons"][1]["ordinal"] = 0
                elif corruption == "policy":
                    payload["policy_name"] = ""

            _rewrite_payload(
                repository, mutate,
                preserve_fingerprint=corruption != "fingerprint",
            )
            error_type = MalformedCriticalCostCompletenessPersistenceError
        with pytest.raises(error_type):
            repository.get_assessment(saved.receipt.assessment_id)


def test_orphan_receipt_and_missing_or_mismatched_sources_are_rejected(tmp_path):
    orphan_path = tmp_path / "orphan.sqlite3"
    with SQLiteCriticalCostCompletenessRepository(orphan_path) as repository:
        repository._connection.execute("PRAGMA foreign_keys = OFF")
        repository._connection.execute(
            f"INSERT INTO {RECEIPTS} VALUES(?,?,?,?,?,?)",
            ("orphan", "missing", "0" * 64, NOW.isoformat(),
             "critical-cost-completeness-receipt-v1", NOW.isoformat()),
        )
        repository._connection.commit()
        with pytest.raises(MalformedCriticalCostCompletenessPersistenceError):
            repository.validate_replay("orphan", "0" * 64)

    path = tmp_path / "source.sqlite3"
    composition, verified = seed(path)
    with SQLiteCriticalCostCompletenessRepository(path) as repository:
        saved = owner(repository)[0].execute(persistence_command(composition, verified))
        _rewrite_payload(
            repository,
            lambda payload: payload["opportunity_identity"].update(
                opportunity_id="wrong-opportunity"
            ),
        )
        with pytest.raises(MalformedCriticalCostCompletenessPersistenceError):
            repository.get_assessment(saved.receipt.assessment_id)


@pytest.mark.parametrize(
    ("source_table", "trigger"),
    (
        (
            "landed_cost_composition_history",
            "trg_landed_cost_composition_history_no_delete",
        ),
        (
            "verified_economics_snapshots",
            "trg_verified_economics_no_delete",
        ),
    ),
)
def test_missing_exact_source_is_rejected_on_reconstruction(tmp_path, source_table, trigger):
    path = tmp_path / f"missing-{source_table}.sqlite3"
    composition, verified = seed(path)
    with SQLiteCriticalCostCompletenessRepository(path) as repository:
        saved = owner(repository)[0].execute(persistence_command(composition, verified))
        repository._connection.execute(f"DROP TRIGGER {trigger}")
        repository._connection.commit()
        repository._connection.execute("PRAGMA foreign_keys = OFF")
        repository._connection.execute(f"DELETE FROM {source_table}")
        repository._connection.commit()
        with pytest.raises(MalformedCriticalCostCompletenessPersistenceError):
            repository.get_assessment(saved.receipt.assessment_id)


def test_malformed_receipt_fingerprint_is_rejected(tmp_path):
    path = tmp_path / "malformed-receipt.sqlite3"
    composition, verified = seed(path)
    with SQLiteCriticalCostCompletenessRepository(path) as repository:
        saved = owner(repository)[0].execute(persistence_command(composition, verified))
        repository._connection.execute(f"DROP TRIGGER trg_{RECEIPTS}_no_update")
        repository._connection.execute(
            f"UPDATE {RECEIPTS} SET command_fingerprint='not-a-fingerprint'"
        )
        repository._connection.commit()
        with pytest.raises(MalformedCriticalCostCompletenessPersistenceError):
            repository.get_receipt(saved.receipt.command_id)


def test_read_path_is_pure_and_connection_ownership_is_preserved(tmp_path):
    path = tmp_path / "critical-cost.sqlite3"
    composition, verified = seed(path)
    with SQLiteCriticalCostCompletenessRepository(path) as repository:
        saved = owner(repository)[0].execute(persistence_command(composition, verified))
        before = repository._connection.total_changes
        assert repository.get_assessment(saved.receipt.assessment_id) == saved.assessment
        assert repository.get_receipt(saved.receipt.command_id) == saved.receipt
        assert repository._connection.total_changes == before
        assert repository._connection.in_transaction is False

    owned = SQLiteCriticalCostCompletenessRepository(tmp_path / "owned.sqlite3")
    owned.close()
    with pytest.raises(sqlite3.ProgrammingError):
        owned._connection.execute("SELECT 1")

    connection = sqlite3.connect(tmp_path / "injected.sqlite3")
    repository = SQLiteCriticalCostCompletenessRepository(connection=connection)
    repository.close()
    assert connection.execute("SELECT 1").fetchone()[0] == 1
    assert connection.in_transaction is False
    connection.close()
