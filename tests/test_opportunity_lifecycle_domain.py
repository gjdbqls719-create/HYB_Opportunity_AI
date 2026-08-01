from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from app.domain.opportunity import (
    ArchivedLifecycleError,
    FounderDecision,
    FounderDecisionType,
    InvalidLifecycleTransitionError,
    OpportunityLifecycle,
    OpportunityLifecycleStatus,
)


NOW = datetime(2026, 8, 2, 1, 0, tzinfo=timezone.utc)


def lifecycle() -> OpportunityLifecycle:
    return OpportunityLifecycle("opp-1", "ebay:item-1", created_at=NOW, updated_at=NOW)


def args(minutes: int = 1):
    return dict(occurred_at=NOW + timedelta(minutes=minutes), operator_id="founder-1", reason="validated")


def test_valid_lifecycle_path_and_version_increments() -> None:
    item = lifecycle()
    item.start_review(**args(1))
    item.approve(**args(2))
    item.purchase(**args(3))
    item.list_for_sale(**args(4))
    event = item.sell(**args(5))
    assert item.status is OpportunityLifecycleStatus.SOLD
    assert item.version == 6
    assert event.version == 6


@pytest.mark.parametrize(
    "operation",
    ["approve", "purchase", "list_for_sale", "sell"],
)
def test_invalid_transitions_are_blocked(operation: str) -> None:
    with pytest.raises(InvalidLifecycleTransitionError):
        getattr(lifecycle(), operation)(**args())


def test_rejection_review_and_listing_withdrawal_paths() -> None:
    item = lifecycle()
    item.reject(**args(1))
    item.start_review(**args(2))
    item.approve(**args(3))
    item.return_to_review(**args(4))
    item.approve(**args(5))
    item.purchase(**args(6))
    item.list_for_sale(**args(7))
    item.withdraw_listing(**args(8))
    assert item.status is OpportunityLifecycleStatus.PURCHASED


def test_archive_restore_is_metadata_and_blocks_transitions() -> None:
    item = lifecycle()
    item.archive(**args(1))
    assert item.status is OpportunityLifecycleStatus.DISCOVERED
    assert item.archived_at is not None
    with pytest.raises(ArchivedLifecycleError):
        item.start_review(**args(2))
    item.restore(**args(3))
    assert not item.is_archived
    item.start_review(**args(4))


def test_sold_is_terminal() -> None:
    item = lifecycle()
    item.start_review(**args(1)); item.approve(**args(2)); item.purchase(**args(3))
    item.list_for_sale(**args(4)); item.sell(**args(5))
    with pytest.raises(InvalidLifecycleTransitionError):
        item.start_review(**args(6))


def test_timezone_and_monotonic_timestamp_validation() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        OpportunityLifecycle("opp", "ref", created_at=NOW.replace(tzinfo=None), updated_at=NOW)
    with pytest.raises(ValueError, match="precede"):
        lifecycle().start_review(**args(-1))


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("status", OpportunityLifecycleStatus.SOLD),
        ("version", 99),
        ("opportunity_id", "changed"),
        ("discovery_reference", "changed"),
        ("created_at", NOW + timedelta(days=1)),
        ("updated_at", NOW + timedelta(days=1)),
    ],
)
def test_lifecycle_state_cannot_be_assigned_directly(field_name: str, value: object) -> None:
    item = lifecycle()
    with pytest.raises(AttributeError):
        setattr(item, field_name, value)


def test_founder_decision_is_validated_and_immutable() -> None:
    decision = FounderDecision(
        opportunity_id="opp-1", decision=FounderDecisionType.APPROVE,
        reason="supplier confirmed", note="sample order", decided_at=NOW, operator_id="founder-1",
    )
    assert decision.operator_id == "founder-1"
    with pytest.raises(FrozenInstanceError):
        decision.reason = "changed"  # type: ignore[misc]
    with pytest.raises(ValueError):
        FounderDecision("opp", FounderDecisionType.REJECT, "", NOW, "founder")
    with pytest.raises(ValueError, match="timezone-aware"):
        FounderDecision("opp", FounderDecisionType.REJECT, "risk", NOW.replace(tzinfo=None), "founder")
