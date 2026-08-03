from dataclasses import FrozenInstanceError, replace
import sqlite3

import pytest

from app.application.dashboard_api import (
    DashboardCompositionUnavailableError,
    ProductionOpportunityDecisionDashboardProvider,
)
from app.application.production_safety_snapshot import (
    GetProductionSafetySnapshot,
    MalformedProductionSafetySnapshotError,
    ProductionSafetySnapshot,
    ProductionSafetySnapshotIdentityConflictError,
    ProductionSafetySnapshotNotFoundError,
)
from app.domain.opportunity import ProductionSafetyAssessment, ProductionSafetyStatus
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from test_economics_variance import calculation
from test_opportunity_market_identity_binding import service
from test_verified_economics_snapshot_binding import verified_command


ASSESSMENT = ProductionSafetyAssessment(
    status=ProductionSafetyStatus.INSUFFICIENT_DATA,
    missing_fields=("price_history", "shipping_cost"),
    failed_checks=("production_source",),
)


def safety_command():
    return replace(
        verified_command(),
        production_safety=ASSESSMENT,
        production_safety_rule_version="production-safety-v1",
    )


def counts(repository):
    tables = (
        "opportunity_lifecycles",
        "opportunity_lifecycle_transitions",
        "validation_queue_admission_snapshots",
        "opportunity_estimated_economics_snapshots",
        "opportunity_market_identity_bindings",
        "verified_economics_snapshots",
        "production_safety_snapshots",
    )
    return {
        table: repository._connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in tables
    }


def test_safety_snapshot_persists_immutable_tuple_round_trip() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    service(repository).add(safety_command())

    snapshot = repository.get_production_safety_snapshot("opp-bound")
    actual = GetProductionSafetySnapshot(repository).execute("opp-bound")

    assert actual == ASSESSMENT
    assert isinstance(actual.missing_fields, tuple)
    assert isinstance(actual.failed_checks, tuple)
    assert snapshot.snapshot_at == safety_command().captured_at
    assert snapshot.snapshot_at.utcoffset() is not None
    assert snapshot.rule_version == "production-safety-v1"
    assert snapshot.schema_version == "production-safety-snapshot-v1"
    repository.close()


def test_snapshot_object_update_and_delete_are_blocked() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    service(repository).add(safety_command())
    snapshot = repository.get_production_safety_snapshot("opp-bound")

    with pytest.raises(FrozenInstanceError):
        snapshot.rule_version = "changed"
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        repository._connection.execute(
            "UPDATE production_safety_snapshots SET status='READY'"
        )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        repository._connection.execute("DELETE FROM production_safety_snapshots")
    assert repository.get_production_safety_snapshot("opp-bound") == snapshot
    repository.close()


def test_duplicate_safety_snapshot_is_rejected() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    service(repository).add(safety_command())
    snapshot = repository.get_production_safety_snapshot("opp-bound")

    with pytest.raises(sqlite3.IntegrityError):
        repository._insert_production_safety_snapshot(snapshot)

    assert repository.get_production_safety_snapshot("opp-bound") == snapshot
    repository.close()


def test_safety_identity_mismatch_is_rejected_before_writes() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    command = safety_command()
    lifecycle, transition, admission = service(repository)._build_admission(command)
    binding = service(repository)._binding(command, lifecycle)
    economics = service(repository)._verified_economics(command, lifecycle)
    safety = ProductionSafetySnapshot(
        opportunity_id="different",
        assessment=ASSESSMENT,
        snapshot_at=command.captured_at,
        rule_version="production-safety-v1",
    )

    with pytest.raises(
        ProductionSafetySnapshotIdentityConflictError,
        match="opportunity_id",
    ):
        repository.admit_with_decision_sources(
            lifecycle, transition, admission, binding, economics, safety
        )
    assert counts(repository) == {name: 0 for name in counts(repository)}
    repository.close()


def test_safety_insert_failure_rolls_back_every_admission_artifact() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    repository._connection.execute(
        """CREATE TRIGGER fail_safety BEFORE INSERT ON production_safety_snapshots
        BEGIN SELECT RAISE(ABORT, 'safety failure'); END"""
    )

    with pytest.raises(sqlite3.IntegrityError, match="safety failure"):
        service(repository).add_with_economics(safety_command(), calculation())

    assert counts(repository) == {name: 0 for name in counts(repository)}
    repository.close()


def test_legacy_safety_snapshot_missing_is_explicit() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    service(repository).add(verified_command())

    with pytest.raises(ProductionSafetySnapshotNotFoundError):
        GetProductionSafetySnapshot(repository).execute("opp-bound")
    repository.close()


def test_dashboard_provider_loads_safety_without_recomputation() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    service(repository).add(safety_command())

    with pytest.raises(
        DashboardCompositionUnavailableError,
        match="finalized decision composition not found",
    ) as error:
        ProductionOpportunityDecisionDashboardProvider(repository).get("opp-bound")

    assert str(error.value) == "finalized decision composition not found"
    repository.close()


def test_malformed_persisted_safety_snapshot_is_explicit() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    service(repository).add(safety_command())
    repository._connection.execute("DROP TRIGGER trg_production_safety_no_update")
    repository._connection.execute(
        "UPDATE production_safety_snapshots SET missing_fields='not-json'"
    )

    with pytest.raises(MalformedProductionSafetySnapshotError):
        repository.get_production_safety_snapshot("opp-bound")
    repository.close()


def test_repeated_safety_query_is_deterministic_and_read_only() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    service(repository).add(safety_command())
    before = counts(repository)

    first = GetProductionSafetySnapshot(repository).execute("opp-bound")
    second = GetProductionSafetySnapshot(repository).execute("opp-bound")

    assert first == second == ASSESSMENT
    assert counts(repository) == before
    repository.close()


def test_safety_requires_verified_economics_and_rule_version() -> None:
    with pytest.raises(ValueError, match="verified_economics"):
        replace(
            verified_command(),
            verified_economics=None,
            production_safety=ASSESSMENT,
            production_safety_rule_version="production-safety-v1",
        )
    with pytest.raises(ValueError, match="rule version"):
        replace(
            verified_command(),
            production_safety=ASSESSMENT,
            production_safety_rule_version=" ",
        )
