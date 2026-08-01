import sqlite3
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from app.application.opportunity_lifecycle import Archive, LifecycleVersionConflictError, OpportunityLifecycleService
from app.application.opportunity_validation import (
    AddToValidationQueueCommand,
    DuplicateActiveValidationError,
    DuplicateValidationConflictError,
    OpportunityValidationService,
    ValidationActionCommand,
    ValidationQueueQuery,
    canonicalize_discovery_reference,
)
from app.domain.opportunity import FounderDecisionType, OpportunityLifecycleStatus
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository


NOW = datetime(2026, 8, 3, tzinfo=timezone.utc)


def service(repository):
    return OpportunityValidationService(queue_repository=repository, lifecycle_repository=repository)


def admission(reference="ebay:item-1", opportunity_id="opp-1", title="Camera"):
    return AddToValidationQueueCommand(
        discovery_reference=reference,
        marketplace="ebay",
        title=title,
        admission_recommendation="WATCH",
        admission_score=72.5,
        admission_roi=31.25,
        currency="usd",
        admission_safety_status="READY",
        operator_id="founder",
        reason="selected for validation",
        captured_at=NOW,
        opportunity_id=opportunity_id,
    )


def action(opportunity_id="opp-1", version=1, minute=1):
    return ValidationActionCommand(
        opportunity_id=opportunity_id,
        expected_version=version,
        operator_id="founder",
        reason="manual review",
        occurred_at=NOW + timedelta(minutes=minute),
    )


def test_only_selected_opportunity_is_admitted_and_snapshot_is_preserved() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    validation = service(repository)
    selected = validation.add(admission())
    assert selected.opportunity_id == "opp-1"
    assert repository.get("not-selected") is None
    validation.start_review(action())
    after_transition = validation.get("opp-1")
    assert after_transition.recommendation == "WATCH"
    assert after_transition.score == 72.5
    assert after_transition.roi == 31.25
    assert after_transition.safety_status == "READY"
    assert after_transition.lifecycle_status is OpportunityLifecycleStatus.UNDER_REVIEW


def test_duplicate_active_registration_is_rejected() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    validation = service(repository)
    validation.add(admission())
    with pytest.raises(DuplicateActiveValidationError):
        validation.add(admission(opportunity_id="opp-2"))
    assert len(validation.list(ValidationQueueQuery())) == 1


@pytest.mark.parametrize(
    "reference",
    [" EBAY : ITEM-1 ", "eBay/Item-1", "ebay|item-1", "ebay\\item-1"],
)
def test_discovery_reference_is_canonicalized_deterministically(reference) -> None:
    assert canonicalize_discovery_reference(reference) == "ebay:item-1"
    repository = SQLiteValidationQueueRepository(":memory:")
    item = service(repository).add(admission(reference=reference))
    assert item.discovery_reference == "ebay:item-1"
    assert repository.get("opp-1").discovery_reference == "ebay:item-1"
    stored = repository._connection.execute(
        "SELECT discovery_reference FROM validation_queue_admission_snapshots"
    ).fetchone()[0]
    assert stored == "ebay:item-1"


@pytest.mark.parametrize(
    "duplicate_reference",
    [" EBAY : ITEM-1 ", "eBay/Item-1", "ebay|item-1", "ebay\\item-1"],
)
def test_canonical_equivalent_reference_is_rejected_as_duplicate(duplicate_reference) -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    validation = service(repository)
    validation.add(admission(reference="ebay:item-1"))
    with pytest.raises(DuplicateValidationConflictError):
        validation.add(admission(reference=duplicate_reference, opportunity_id="opp-2"))


@pytest.mark.parametrize("terminal_status", ["approved", "rejected"])
def test_non_archived_approved_and_rejected_block_duplicate_registration(terminal_status) -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    validation = service(repository)
    validation.add(admission())
    if terminal_status == "approved":
        validation.start_review(action(version=1, minute=1))
        validation.approve(action(version=2, minute=2))
    else:
        validation.reject(action(version=1, minute=1))
    with pytest.raises(DuplicateValidationConflictError):
        validation.add(admission(opportunity_id="opp-2"))


def test_archived_lifecycle_allows_duplicate_registration_but_restore_is_explicit_conflict() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    validation = service(repository)
    validation.add(admission())
    lifecycle_service = OpportunityLifecycleService(repository)
    lifecycle_service.archive(
        Archive("opp-1", 1, "founder", "archive", NOW + timedelta(minutes=1))
    )
    validation.add(admission(opportunity_id="opp-2"))
    from app.application.opportunity_lifecycle import Restore
    with pytest.raises(DuplicateValidationConflictError):
        lifecycle_service.restore(
            Restore("opp-1", 2, "founder", "restore", NOW + timedelta(minutes=2))
        )
    assert repository.get("opp-1").is_archived


def test_return_to_review_reports_duplicate_conflict_for_legacy_collision() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    validation = service(repository)
    validation.add(admission())
    validation.start_review(action(version=1, minute=1))
    validation.approve(action(version=2, minute=2))
    repository._connection.execute("DROP INDEX uq_active_validation_discovery_reference")
    repository._connection.execute(
        """INSERT INTO opportunity_lifecycles
        (opportunity_id, discovery_reference, status, version, created_at, updated_at,
         archived_at, archived_by, archive_reason)
        VALUES ('legacy-duplicate', 'ebay:item-1', 'discovered', 1, ?, ?, NULL, NULL, NULL)""",
        (NOW.isoformat(), NOW.isoformat()),
    )
    repository._connection.commit()
    with pytest.raises(DuplicateValidationConflictError):
        validation.return_to_review(action(version=3, minute=3))
    assert repository.get("opp-1").status is OpportunityLifecycleStatus.APPROVED


def test_concurrent_duplicate_registration_allows_exactly_one(tmp_path) -> None:
    database = tmp_path / "validation.db"
    SQLiteValidationQueueRepository(database).close()

    def add(opportunity_id):
        repository = SQLiteValidationQueueRepository(database)
        try:
            return service(repository).add(admission(opportunity_id=opportunity_id)).opportunity_id
        finally:
            repository.close()

    outcomes = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(add, "opp-a"), executor.submit(add, "opp-b")]
        for future in futures:
            try:
                outcomes.append(("created", future.result()))
            except DuplicateActiveValidationError:
                outcomes.append(("duplicate", None))
    assert sorted(outcome for outcome, _ in outcomes) == ["created", "duplicate"]


def test_snapshot_failure_rolls_back_lifecycle_and_history() -> None:
    connection = sqlite3.connect(":memory:")
    repository = SQLiteValidationQueueRepository(connection=connection)
    connection.execute(
        """CREATE TRIGGER fail_validation_snapshot BEFORE INSERT
        ON validation_queue_admission_snapshots BEGIN
        SELECT RAISE(ABORT, 'snapshot failure'); END"""
    )
    with pytest.raises(sqlite3.IntegrityError, match="snapshot failure"):
        service(repository).add(admission())
    assert repository.get("opp-1") is None
    assert repository.list_transitions("opp-1") == ()


def test_queue_query_filters_status_and_excludes_archived() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    validation = service(repository)
    validation.add(admission())
    validation.add(admission("ebay:item-2", "opp-2", "Lens"))
    validation.reject(action("opp-2", 1, 1))
    assert [item.opportunity_id for item in validation.list(ValidationQueueQuery())] == ["opp-1"]
    rejected = validation.list(ValidationQueueQuery(statuses=(OpportunityLifecycleStatus.REJECTED,)))
    assert [item.opportunity_id for item in rejected] == ["opp-2"]
    OpportunityLifecycleService(repository).archive(
        Archive("opp-1", 1, "founder", "not now", NOW + timedelta(minutes=2))
    )
    assert validation.list(ValidationQueueQuery()) == ()
    assert validation.get("opp-1") is None


def test_review_approve_and_return_to_review_flow() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    validation = service(repository)
    validation.add(admission())
    reviewed = validation.start_review(action(version=1, minute=1))
    assert reviewed.lifecycle.status is OpportunityLifecycleStatus.UNDER_REVIEW
    approved = validation.approve(action(version=2, minute=2))
    assert approved.lifecycle.status is OpportunityLifecycleStatus.APPROVED
    assert approved.founder_decision.decision is FounderDecisionType.APPROVE
    assert validation.get("opp-1").recommendation == "WATCH"
    returned = validation.return_to_review(action(version=3, minute=3))
    assert returned.lifecycle.status is OpportunityLifecycleStatus.UNDER_REVIEW
    assert returned.transition.action.value == "return_to_review"


def test_reject_and_founder_decision_are_independent_from_admission_recommendation() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    validation = service(repository)
    validation.add(admission())
    rejected = validation.reject(action(version=1, minute=1))
    assert rejected.founder_decision.decision is FounderDecisionType.REJECT
    assert rejected.lifecycle.status is OpportunityLifecycleStatus.REJECTED
    stored = validation.get("opp-1")
    assert stored.recommendation == "WATCH"
    assert stored.score == 72.5


def test_optimistic_version_is_enforced() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    validation = service(repository)
    validation.add(admission())
    with pytest.raises(LifecycleVersionConflictError):
        validation.start_review(action(version=99, minute=1))
    assert repository.get("opp-1").version == 1
    assert len(repository.list_transitions("opp-1")) == 1
