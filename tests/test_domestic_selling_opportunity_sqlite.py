from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import sqlite3

import pytest

from app.application.candidate_promotion import CandidatePromotionProductionEntry
from app.application.domestic_selling_opportunity import (
    AdmitDomesticSellingOpportunity,
    DomesticSellingOpportunityCardinalityConflictError,
    DomesticSellingOpportunityReplayConflictError,
)
from app.domain.discovery_identity import OpportunityCandidateIdentity
from app.domain.opportunity import OpportunityLifecycleStatus
from app.domain.product_observation import (
    CollectorProvenance,
    ProductObservationSnapshot,
)
from app.infrastructure.domestic_selling_opportunity import (
    DomesticSellingOpportunityCommitError,
    DomesticSellingOpportunityHistoryError,
    DomesticSellingOpportunityReceiptError,
    MalformedDomesticSellingOpportunityPersistenceError,
    SQLiteDomesticSellingOpportunityAdmissionRepository,
)
from app.infrastructure.opportunity_validation import SQLiteCandidatePromotionRepository
from app.infrastructure.product_observation import SQLiteProductObservationSnapshotRepository
from test_candidate_issuance_foundation import Counter, ISSUED_AT
from test_candidate_opportunity_promotion import command as promotion_command
from test_domestic_selling_opportunity_admission import (
    Calls,
    command,
    observed_product,
)
from test_product_snapshot_capture_production_entry import close_all, prepare


def seed(path):
    sources, candidates, issuance, _, _ = prepare(path)
    promotions = SQLiteCandidatePromotionRepository(path)
    promoted = CandidatePromotionProductionEntry(
        candidate_repository=candidates,
        promotion_repository=promotions,
        opportunity_id_generator=Counter("source-opportunity-1"),
        binding_id_generator=Counter("candidate-opportunity-binding-1"),
        clock=Counter(ISSUED_AT + timedelta(minutes=1)),
    ).execute(promotion_command())
    products = SQLiteProductObservationSnapshotRepository(database_path=path)
    context = candidates.get_context(issuance.candidate_identity.candidate_id)
    snapshot = ProductObservationSnapshot(
        snapshot_id="product-snapshot-1",
        candidate_identity=OpportunityCandidateIdentity(
            issuance.candidate_identity.candidate_id,
            issuance.candidate_identity.discovery_reference,
        ),
        market_observation_identity=context.market_observation_identity,
        product=observed_product(context.market_observation_identity.marketplace),
        collector_provenance=CollectorProvenance(
            "ebay-collector", "1.0.0", "ebay:item:source-listing-1"
        ),
        observed_at=ISSUED_AT,
    )
    products.save_snapshot(snapshot)
    products.close()
    promotions.close()
    candidates.close()
    close_all(*sources)
    return promoted


def make_owner(repository, *, opportunity=None, admission=None, admitted=None, committed=None):
    requested_at = command().requested_at
    return AdmitDomesticSellingOpportunity(
        repository,
        opportunity_id_generator=opportunity or Calls("domestic-opportunity-1"),
        admission_id_generator=admission or Calls("domestic-admission-1"),
        admitted_clock=admitted or Calls(requested_at + timedelta(minutes=1)),
        committed_clock=committed or Calls(requested_at + timedelta(minutes=2)),
    )


def counts(repository):
    return tuple(
        repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "opportunity_lifecycles",
            "opportunity_lifecycle_transitions",
            "opportunity_market_identity_bindings",
            "domestic_selling_opportunity_admission_history",
            "domestic_selling_opportunity_admission_receipts",
        )
    )


def test_fresh_atomic_persistence_and_exact_round_trip(tmp_path):
    path = tmp_path / "fresh.db"
    seed(path)
    repository = SQLiteDomesticSellingOpportunityAdmissionRepository(path)
    result = make_owner(repository).execute(command())

    assert result.replayed is False
    assert result.lifecycle.status is OpportunityLifecycleStatus.DISCOVERED
    assert result.lifecycle.version == 1
    assert repository.get_source_lifecycle("source-opportunity-1").status is OpportunityLifecycleStatus.DISCOVERED
    assert repository.get_market_identity_binding("domestic-opportunity-1") == result.market_binding
    assert repository.get_admission_by_source("source-opportunity-1") == result
    assert counts(repository) == (2, 2, 2, 1, 1)
    assert repository._connection.in_transaction is False
    repository.close()


def test_exact_and_restart_replay_skip_sources_identities_and_clocks(tmp_path):
    path = tmp_path / "restart.db"
    seed(path)
    repository = SQLiteDomesticSellingOpportunityAdmissionRepository(path)
    first = make_owner(repository).execute(command())
    repository.close()

    repository = SQLiteDomesticSellingOpportunityAdmissionRepository(path)
    fail = Calls(AssertionError("must not run"))
    source_reads = repository.source_read_count
    replay = make_owner(
        repository, opportunity=fail, admission=fail, admitted=fail, committed=fail
    ).execute(command())
    assert replay == replace(first, replayed=True)
    assert repository.source_read_count == source_reads
    assert fail.calls == 0
    assert counts(repository) == (2, 2, 2, 1, 1)
    repository.close()


def test_changed_command_and_existing_subject_conflict_without_new_rows(tmp_path):
    path = tmp_path / "conflicts.db"
    seed(path)
    repository = SQLiteDomesticSellingOpportunityAdmissionRepository(path)
    make_owner(repository).execute(command())
    with pytest.raises(DomesticSellingOpportunityReplayConflictError):
        make_owner(repository).execute(command(evidence_reference="changed"))
    with pytest.raises(DomesticSellingOpportunityCardinalityConflictError):
        make_owner(repository).execute(command(command_id="other-command"))
    assert counts(repository) == (2, 2, 2, 1, 1)
    repository.close()


def test_history_and_receipt_are_append_only(tmp_path):
    path = tmp_path / "append-only.db"
    seed(path)
    repository = SQLiteDomesticSellingOpportunityAdmissionRepository(path)
    make_owner(repository).execute(command())
    for table in (
        "domestic_selling_opportunity_admission_history",
        "domestic_selling_opportunity_admission_receipts",
    ):
        for statement in (
            f"UPDATE {table} SET rowid=rowid",
            f"DELETE FROM {table}",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                repository._connection.execute(statement)
            repository._connection.rollback()
    repository.close()


@pytest.mark.parametrize(
    "phase,error",
    (
        ("lifecycle", DomesticSellingOpportunityHistoryError),
        ("transition", DomesticSellingOpportunityHistoryError),
        ("market", DomesticSellingOpportunityHistoryError),
        ("admission", DomesticSellingOpportunityHistoryError),
        ("receipt", DomesticSellingOpportunityReceiptError),
        ("commit", DomesticSellingOpportunityCommitError),
    ),
)
def test_each_write_failure_rolls_back_every_authoritative_fact(tmp_path, phase, error):
    path = tmp_path / f"rollback-{phase}.db"
    seed(path)
    repository = SQLiteDomesticSellingOpportunityAdmissionRepository(path)
    targets = {
        "lifecycle": (repository._lifecycles, "_insert_current"),
        "transition": (repository._lifecycles, "_insert_transition"),
        "market": (repository, "_insert_market_identity_binding"),
        "admission": (repository, "_insert_admission"),
        "receipt": (repository, "_insert_domestic_receipt"),
        "commit": (repository, "_commit"),
    }
    target, name = targets[phase]
    original = getattr(target, name)
    setattr(
        target,
        name,
        lambda *_: (_ for _ in ()).throw(sqlite3.OperationalError("forced failure")),
    )
    with pytest.raises(error):
        make_owner(repository).execute(command())
    assert counts(repository) == (1, 1, 1, 0, 0)
    assert repository._connection.in_transaction is False
    setattr(target, name, original)
    assert make_owner(repository).execute(command()).replayed is False
    repository.close()


def test_same_command_concurrency_converges_and_competing_subject_conflicts(tmp_path):
    path = tmp_path / "concurrency.db"
    seed(path)

    def execute(command_id, suffix):
        repository = SQLiteDomesticSellingOpportunityAdmissionRepository(path)
        try:
            return make_owner(
                repository,
                opportunity=Calls(f"domestic-opportunity-{suffix}"),
                admission=Calls(f"domestic-admission-{suffix}"),
            ).execute(command(command_id=command_id))
        finally:
            repository.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        same = list(pool.map(lambda value: execute("same-command", value), ("a", "b")))
    assert {item.admission.admission_id for item in same} == {same[0].admission.admission_id}
    assert sorted(item.replayed for item in same) == [False, True]

    path2 = tmp_path / "cardinality-race.db"
    seed(path2)

    def compete(value):
        repository = SQLiteDomesticSellingOpportunityAdmissionRepository(path2)
        try:
            return make_owner(
                repository,
                opportunity=Calls(f"domestic-opportunity-{value}"),
                admission=Calls(f"domestic-admission-{value}"),
            ).execute(command(command_id=f"command-{value}"))
        finally:
            repository.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(compete, value) for value in ("a", "b")]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except DomesticSellingOpportunityCardinalityConflictError:
                outcomes.append("conflict")
    assert sum(item == "conflict" for item in outcomes) == 1
    repository = SQLiteDomesticSellingOpportunityAdmissionRepository(path2)
    assert counts(repository) == (2, 2, 2, 1, 1)
    repository.close()


@pytest.mark.parametrize(
    "table,column,value",
    (
        ("domestic_selling_opportunity_admission_history", "payload_json", "{"),
        ("domestic_selling_opportunity_admission_history", "integrity_fingerprint", "0" * 64),
        ("domestic_selling_opportunity_admission_history", "schema_version", "future"),
        ("domestic_selling_opportunity_admission_receipts", "command_fingerprint", "0" * 64),
    ),
)
def test_malformed_persistence_is_rejected(tmp_path, table, column, value):
    path = tmp_path / f"malformed-{column}.db"
    seed(path)
    repository = SQLiteDomesticSellingOpportunityAdmissionRepository(path)
    make_owner(repository).execute(command())
    repository._connection.execute(f"DROP TRIGGER trg_{table}_no_update")
    repository._connection.execute(f"UPDATE {table} SET {column}=?", (value,))
    repository._connection.commit()
    with pytest.raises(MalformedDomesticSellingOpportunityPersistenceError):
        repository.validate_replay(command().command_id, command().fingerprint)
    repository.close()


def test_read_path_does_not_mutate_and_connection_ownership_is_explicit(tmp_path):
    path = tmp_path / "reads.db"
    seed(path)
    connection = sqlite3.connect(path, check_same_thread=False)
    repository = SQLiteDomesticSellingOpportunityAdmissionRepository(connection=connection)
    make_owner(repository).execute(command())
    before = connection.total_changes
    assert repository.get_admission_by_source("source-opportunity-1") is not None
    assert repository.validate_replay(command().command_id, command().fingerprint) is not None
    assert connection.total_changes == before
    repository.close()
    assert connection.execute("SELECT 1").fetchone()[0] == 1
    connection.close()

    owned = SQLiteDomesticSellingOpportunityAdmissionRepository(path)
    owned.close()
    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        owned._connection.execute("SELECT 1")
