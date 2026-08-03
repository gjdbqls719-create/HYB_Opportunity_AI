from dataclasses import FrozenInstanceError, replace
import sqlite3

import pytest

from app.application.dashboard_api import (
    DashboardCompositionUnavailableError,
    MISSING_PRODUCTION_SAFETY,
    ProductionOpportunityDecisionDashboardProvider,
)
from app.application.verified_economics_snapshot import (
    GetVerifiedEconomicsSnapshot,
    VerifiedEconomicsSnapshot,
    VerifiedEconomicsSnapshotIdentityConflictError,
    VerifiedEconomicsSnapshotNotFoundError,
)
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from test_economics_variance import calculation
from test_opportunity_market_identity_binding import command, identity, service
from test_verified_economics import complete_input


def verified_command():
    return replace(
        command(identity()),
        verified_economics=complete_input(),
    )


def counts(repository):
    return {
        table: repository._connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in (
            "opportunity_lifecycles",
            "opportunity_lifecycle_transitions",
            "validation_queue_admission_snapshots",
            "opportunity_market_identity_bindings",
            "verified_economics_snapshots",
            "opportunity_estimated_economics_snapshots",
        )
    }


def test_verified_economics_snapshot_persists_exact_round_trip() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    expected = complete_input()
    service(repository).add(replace(command(identity()), verified_economics=expected))

    snapshot = repository.get_verified_economics_snapshot("opp-bound")
    actual = GetVerifiedEconomicsSnapshot(repository).execute("opp-bound")

    assert snapshot.inputs == expected
    assert actual == expected
    assert actual.marketplace_fee_rate.rate.as_tuple() == expected.marketplace_fee_rate.rate.as_tuple()
    assert snapshot.snapshot_at == command().captured_at
    assert snapshot.schema_version == "verified-economics-snapshot-v1"
    repository.close()


def test_snapshot_is_frozen_and_update_delete_are_blocked() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    service(repository).add(verified_command())
    snapshot = repository.get_verified_economics_snapshot("opp-bound")

    with pytest.raises(FrozenInstanceError):
        snapshot.opportunity_id = "changed"
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        repository._connection.execute(
            "UPDATE verified_economics_snapshots SET currency='KRW'"
        )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        repository._connection.execute("DELETE FROM verified_economics_snapshots")
    assert repository.get_verified_economics_snapshot("opp-bound") == snapshot
    repository.close()


def test_duplicate_snapshot_insert_is_rejected() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    service(repository).add(verified_command())
    snapshot = repository.get_verified_economics_snapshot("opp-bound")

    with pytest.raises(sqlite3.IntegrityError):
        repository._insert_verified_economics_snapshot(snapshot)

    assert repository.get_verified_economics_snapshot("opp-bound") == snapshot
    repository.close()


def test_verified_snapshot_identity_mismatch_is_rejected_before_writes() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    lifecycle, transition, admission = service(repository)._build_admission(
        verified_command()
    )
    binding = service(repository)._binding(verified_command(), lifecycle)
    snapshot = VerifiedEconomicsSnapshot(
        opportunity_id="different",
        inputs=complete_input(),
        snapshot_at=verified_command().captured_at,
    )

    with pytest.raises(
        VerifiedEconomicsSnapshotIdentityConflictError,
        match="opportunity_id",
    ):
        repository.admit_with_decision_sources(
            lifecycle, transition, admission, binding, snapshot
        )
    assert counts(repository) == {name: 0 for name in counts(repository)}
    repository.close()


def test_verified_snapshot_failure_rolls_back_all_admission_artifacts() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    repository._connection.execute(
        """CREATE TRIGGER fail_verified_economics BEFORE INSERT
        ON verified_economics_snapshots
        BEGIN SELECT RAISE(ABORT, 'verified failure'); END"""
    )

    with pytest.raises(sqlite3.IntegrityError, match="verified failure"):
        service(repository).add(verified_command())

    assert counts(repository) == {name: 0 for name in counts(repository)}
    repository.close()


def test_variance_ready_verified_failure_rolls_back_baseline_and_binding() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    repository._connection.execute(
        """CREATE TRIGGER fail_verified_economics BEFORE INSERT
        ON verified_economics_snapshots
        BEGIN SELECT RAISE(ABORT, 'verified failure'); END"""
    )

    with pytest.raises(sqlite3.IntegrityError, match="verified failure"):
        service(repository).add_with_economics(
            verified_command(), calculation()
        )

    assert counts(repository) == {name: 0 for name in counts(repository)}
    repository.close()


def test_legacy_snapshot_missing_is_explicit() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    service(repository).add(command(identity()))

    with pytest.raises(VerifiedEconomicsSnapshotNotFoundError):
        GetVerifiedEconomicsSnapshot(repository).execute("opp-bound")
    repository.close()


def test_dashboard_provider_loads_snapshot_and_advances_to_safety_gap() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    service(repository).add(verified_command())

    with pytest.raises(
        DashboardCompositionUnavailableError,
        match="no authoritative ProductionSafetyAssessment source",
    ) as error:
        ProductionOpportunityDecisionDashboardProvider(repository).get("opp-bound")

    assert str(error.value) == MISSING_PRODUCTION_SAFETY
    repository.close()


def test_repeated_snapshot_query_is_deterministic_and_read_only() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    service(repository).add(verified_command())
    before = counts(repository)

    first = GetVerifiedEconomicsSnapshot(repository).execute("opp-bound")
    second = GetVerifiedEconomicsSnapshot(repository).execute("opp-bound")

    assert first == second == complete_input()
    assert counts(repository) == before
    repository.close()


def test_verified_economics_requires_explicit_market_identity() -> None:
    with pytest.raises(ValueError, match="requires an explicit"):
        replace(command(), verified_economics=complete_input())
