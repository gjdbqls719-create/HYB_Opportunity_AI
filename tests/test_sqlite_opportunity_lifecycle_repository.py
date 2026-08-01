import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from app.application.opportunity_lifecycle import (
    DuplicateLifecycleError,
    LifecycleSemanticError,
    LifecycleVersionConflictError,
)
from app.domain.opportunity import OpportunityLifecycle, OpportunityLifecycleStatus
from app.infrastructure.opportunity_lifecycle import SQLiteOpportunityLifecycleRepository


NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)


def created(opportunity_id="opp-1"):
    item = OpportunityLifecycle(opportunity_id, "ebay:item-1", created_at=NOW, updated_at=NOW)
    event = item.creation_transition(operator_id="founder", reason="queue save")
    return item, event


def test_current_state_history_round_trip_and_append_only() -> None:
    repository = SQLiteOpportunityLifecycleRepository(":memory:")
    item, event = created()
    repository.create(item, event)
    transition = item.start_review(
        occurred_at=NOW + timedelta(minutes=1), operator_id="founder", reason="review"
    )
    repository.save_transition(item, transition, expected_version=1)
    restored = repository.get("opp-1")
    assert restored == item
    assert [event.version for event in repository.list_transitions("opp-1")] == [1, 2]


def test_lifecycle_id_is_unique() -> None:
    repository = SQLiteOpportunityLifecycleRepository(":memory:")
    item, event = created()
    repository.create(item, event)
    duplicate, duplicate_event = created()
    with pytest.raises(DuplicateLifecycleError):
        repository.create(duplicate, duplicate_event)


def test_optimistic_version_conflict_does_not_append_history() -> None:
    repository = SQLiteOpportunityLifecycleRepository(":memory:")
    item, event = created()
    repository.create(item, event)
    transition = item.start_review(
        occurred_at=NOW + timedelta(minutes=1), operator_id="founder", reason="review"
    )
    with pytest.raises(LifecycleVersionConflictError):
        repository.save_transition(item, transition, expected_version=0)
    assert repository.get("opp-1").version == 1
    assert len(repository.list_transitions("opp-1")) == 1


def test_history_insert_failure_rolls_back_current_update() -> None:
    connection = sqlite3.connect(":memory:")
    repository = SQLiteOpportunityLifecycleRepository(connection=connection)
    item, event = created()
    repository.create(item, event)
    transition = item.start_review(
        occurred_at=NOW + timedelta(minutes=1), operator_id="founder", reason="review"
    )
    object.__setattr__(transition, "transition_id", event.transition_id)
    with pytest.raises(LifecycleVersionConflictError):
        repository.save_transition(item, transition, expected_version=1)
    assert repository.get("opp-1").version == 1
    assert len(repository.list_transitions("opp-1")) == 1


def test_mismatched_previous_status_is_rejected_without_writes() -> None:
    repository = SQLiteOpportunityLifecycleRepository(":memory:")
    item, event = created()
    repository.create(item, event)
    transition = item.start_review(
        occurred_at=NOW + timedelta(minutes=1), operator_id="founder", reason="review"
    )
    invalid = replace(transition, previous_status=OpportunityLifecycleStatus.REJECTED)
    with pytest.raises(LifecycleSemanticError, match="previous_status"):
        repository.save_transition(item, invalid, expected_version=1)
    assert repository.get("opp-1").version == 1
    assert len(repository.list_transitions("opp-1")) == 1


def test_mismatched_new_status_is_rejected_without_writes() -> None:
    repository = SQLiteOpportunityLifecycleRepository(":memory:")
    item, event = created()
    repository.create(item, event)
    transition = item.start_review(
        occurred_at=NOW + timedelta(minutes=1), operator_id="founder", reason="review"
    )
    invalid = replace(transition, new_status=OpportunityLifecycleStatus.REJECTED)
    with pytest.raises(LifecycleSemanticError, match="new_status"):
        repository.save_transition(item, invalid, expected_version=1)
    assert repository.get("opp-1").status is OpportunityLifecycleStatus.DISCOVERED
    assert len(repository.list_transitions("opp-1")) == 1


def test_incomplete_event_is_rejected_without_writes() -> None:
    repository = SQLiteOpportunityLifecycleRepository(":memory:")
    item, event = created()
    repository.create(item, event)
    transition = item.start_review(
        occurred_at=NOW + timedelta(minutes=1), operator_id="founder", reason="review"
    )
    object.__setattr__(transition, "reason", "")
    with pytest.raises(LifecycleSemanticError, match="reason"):
        repository.save_transition(item, transition, expected_version=1)
    assert repository.get("opp-1").version == 1
    assert len(repository.list_transitions("opp-1")) == 1


def test_timestamp_mismatch_is_rejected_semantically_and_rolls_back() -> None:
    repository = SQLiteOpportunityLifecycleRepository(":memory:")
    item, event = created()
    repository.create(item, event)
    transition = item.start_review(
        occurred_at=NOW + timedelta(minutes=1), operator_id="founder", reason="review"
    )
    invalid = replace(transition, occurred_at=NOW + timedelta(minutes=2))
    with pytest.raises(LifecycleSemanticError, match="timestamp"):
        repository.save_transition(item, invalid, expected_version=1)
    persisted = repository.get("opp-1")
    assert persisted.version == 1
    assert persisted.updated_at == NOW
    assert len(repository.list_transitions("opp-1")) == 1
