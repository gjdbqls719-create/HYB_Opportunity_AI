import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.actual_economics import (
    ActualEconomicsSemanticError,
    ActualEconomicsVersionConflictError,
    DuplicateActualEconomicsError,
)
from app.domain.opportunity import (
    ActualEconomics,
    ActualEconomicsAction,
    ActualEconomicsEvent,
    ActualEconomicsStatus,
)
from app.infrastructure.actual_economics import SQLiteActualEconomicsRepository

NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)


def purchased():
    item = ActualEconomics("opp-1", "USD", created_at=NOW)
    event = item.record_purchase(purchase_price=Decimal("100"), shipping_cost=Decimal("10"), occurred_at=NOW)
    return item, event


def sale_recorded(repository):
    item, purchase = purchased()
    repository.create(item, purchase)
    sale = item.record_sale(sale_price=Decimal("180"), occurred_at=NOW + timedelta(hours=1))
    return item, sale


def settlement_recorded(repository):
    item, sale = sale_recorded(repository)
    repository.save_event(item, sale, expected_version=1)
    settlement = item.complete_settlement(
        marketplace_fee=Decimal("18"), payment_fee=Decimal("5"),
        fixed_fee=Decimal("2"), settlement_amount=Decimal("155"),
        occurred_at=NOW + timedelta(hours=2),
    )
    return item, settlement


def assert_semantic_rollback(repository, operation, *, version, event_count):
    with pytest.raises(ActualEconomicsSemanticError):
        operation()
    assert repository.get("opp-1").version == version
    assert len(repository.list_events("opp-1")) == event_count


def test_round_trip_and_append_only_events() -> None:
    repository = SQLiteActualEconomicsRepository(":memory:")
    item, purchase = purchased(); repository.create(item, purchase)
    sale = item.record_sale(sale_price=Decimal("180"), occurred_at=NOW + timedelta(hours=1))
    repository.save_event(item, sale, expected_version=1)
    settlement = item.complete_settlement(marketplace_fee=Decimal("18"), payment_fee=Decimal("5"),
        fixed_fee=Decimal("2"), settlement_amount=Decimal("155"), occurred_at=NOW + timedelta(hours=2))
    repository.save_event(item, settlement, expected_version=2)
    assert repository.get("opp-1") == item
    assert [event.version for event in repository.list_events("opp-1")] == [1, 2, 3]


def test_unique_aggregate_and_optimistic_lock() -> None:
    repository = SQLiteActualEconomicsRepository(":memory:")
    item, event = purchased(); repository.create(item, event)
    duplicate, duplicate_event = purchased()
    with pytest.raises(DuplicateActualEconomicsError): repository.create(duplicate, duplicate_event)
    sale = item.record_sale(sale_price=Decimal("180"), occurred_at=NOW + timedelta(hours=1))
    with pytest.raises(ActualEconomicsVersionConflictError): repository.save_event(item, sale, expected_version=0)
    assert repository.get("opp-1").version == 1
    assert len(repository.list_events("opp-1")) == 1


def test_event_failure_rolls_back_current_state() -> None:
    connection = sqlite3.connect(":memory:")
    repository = SQLiteActualEconomicsRepository(connection=connection)
    item, purchase = purchased(); repository.create(item, purchase)
    sale = item.record_sale(sale_price=Decimal("180"), occurred_at=NOW + timedelta(hours=1))
    object.__setattr__(sale, "event_id", purchase.event_id)
    with pytest.raises(ActualEconomicsVersionConflictError): repository.save_event(item, sale, expected_version=1)
    assert repository.get("opp-1").version == 1
    assert len(repository.list_events("opp-1")) == 1


@pytest.mark.parametrize(
    ("field_name", "wrong_value"),
    [("purchase_price", Decimal("999")), ("shipping_cost", Decimal("999"))],
)
def test_purchase_event_facts_must_match_aggregate(field_name, wrong_value) -> None:
    repository = SQLiteActualEconomicsRepository(":memory:")
    item, event = purchased()
    invalid = replace(event, **{field_name: wrong_value})
    with pytest.raises(ActualEconomicsSemanticError, match=field_name):
        repository.create(item, invalid)
    assert repository.get("opp-1") is None
    assert repository.list_events("opp-1") == ()


def test_sale_event_facts_must_match_aggregate_and_roll_back() -> None:
    repository = SQLiteActualEconomicsRepository(":memory:")
    item, event = sale_recorded(repository)
    invalid = replace(event, sale_price=Decimal("999"))
    assert_semantic_rollback(
        repository,
        lambda: repository.save_event(item, invalid, expected_version=1),
        version=1,
        event_count=1,
    )


@pytest.mark.parametrize(
    "field_name",
    ["marketplace_fee", "payment_fee", "fixed_fee", "settlement_amount"],
)
def test_settlement_event_facts_must_match_aggregate(field_name) -> None:
    repository = SQLiteActualEconomicsRepository(":memory:")
    item, event = settlement_recorded(repository)
    invalid = replace(event, **{field_name: Decimal("999")})
    assert_semantic_rollback(
        repository,
        lambda: repository.save_event(item, invalid, expected_version=2),
        version=2,
        event_count=2,
    )


@pytest.mark.parametrize(
    ("stage", "field_name"),
    [
        ("purchase", "purchase_price"),
        ("sale", "sale_price"),
        ("settlement", "marketplace_fee"),
    ],
)
def test_action_required_fact_cannot_be_missing(stage, field_name) -> None:
    repository = SQLiteActualEconomicsRepository(":memory:")
    if stage == "purchase":
        item, event = purchased()
        invalid = replace(event, **{field_name: None})
        with pytest.raises(ActualEconomicsSemanticError, match=field_name):
            repository.create(item, invalid)
        assert repository.get("opp-1") is None
        return
    if stage == "sale":
        item, event = sale_recorded(repository)
        expected_version = 1
    else:
        item, event = settlement_recorded(repository)
        expected_version = 2
    invalid = replace(event, **{field_name: None})
    assert_semantic_rollback(
        repository,
        lambda: repository.save_event(item, invalid, expected_version=expected_version),
        version=expected_version,
        event_count=expected_version,
    )


@pytest.mark.parametrize(
    ("stage", "field_name"),
    [("purchase", "sale_price"), ("sale", "marketplace_fee")],
)
def test_action_cannot_contain_future_fact(stage, field_name) -> None:
    repository = SQLiteActualEconomicsRepository(":memory:")
    if stage == "purchase":
        item, event = purchased()
        invalid = replace(event, **{field_name: Decimal("0")})
        with pytest.raises(ActualEconomicsSemanticError, match=field_name):
            repository.create(item, invalid)
        assert repository.get("opp-1") is None
        return
    item, event = sale_recorded(repository)
    invalid = replace(event, **{field_name: Decimal("0")})
    assert_semantic_rollback(
        repository,
        lambda: repository.save_event(item, invalid, expected_version=1),
        version=1,
        event_count=1,
    )


def test_decimal_zero_is_a_complete_actual_fact() -> None:
    repository = SQLiteActualEconomicsRepository(":memory:")
    item = ActualEconomics("opp-1", "USD", created_at=NOW)
    purchase = item.record_purchase(
        purchase_price=Decimal("0"), shipping_cost=Decimal("0"), occurred_at=NOW,
    )
    repository.create(item, purchase)
    sale = item.record_sale(sale_price=Decimal("0"), occurred_at=NOW + timedelta(hours=1))
    repository.save_event(item, sale, expected_version=1)
    settlement = item.complete_settlement(
        marketplace_fee=Decimal("0"), payment_fee=Decimal("0"),
        fixed_fee=Decimal("0"), settlement_amount=Decimal("0"),
        occurred_at=NOW + timedelta(hours=2),
    )
    repository.save_event(item, settlement, expected_version=2)
    assert repository.get("opp-1") == item
    assert len(repository.list_events("opp-1")) == 3


def test_empty_is_transient_and_first_persisted_event_is_purchase() -> None:
    repository = SQLiteActualEconomicsRepository(":memory:")
    item = ActualEconomics("opp-1", "USD", created_at=NOW)
    invalid = ActualEconomicsEvent(
        opportunity_id="opp-1", action=ActualEconomicsAction.RECORD_PURCHASE,
        previous_status=ActualEconomicsStatus.EMPTY,
        new_status=ActualEconomicsStatus.EMPTY, version=1, occurred_at=NOW,
    )
    with pytest.raises(ActualEconomicsSemanticError):
        repository.create(item, invalid)
    assert repository.get("opp-1") is None

    purchase = item.record_purchase(
        purchase_price=Decimal("100"), shipping_cost=Decimal("10"), occurred_at=NOW,
    )
    repository.create(item, purchase)
    restored = repository.get("opp-1")
    events = repository.list_events("opp-1")
    assert restored == item
    assert restored.status is ActualEconomicsStatus.PURCHASE_RECORDED
    assert restored.version == 1
    assert events[0].version == 1
    assert events[0].action is ActualEconomicsAction.RECORD_PURCHASE


def test_first_purchase_event_binds_and_round_trips_currency() -> None:
    repository = SQLiteActualEconomicsRepository(":memory:")
    item, event = purchased()
    assert event.currency == item.currency == "USD"
    repository.create(item, event)
    restored = repository.get("opp-1")
    restored_event = repository.list_events("opp-1")[0]
    assert restored.currency == "USD"
    assert restored_event.currency == "USD"
    assert restored_event.currency == restored.currency


def test_purchase_event_currency_mismatch_is_rejected_without_rows() -> None:
    repository = SQLiteActualEconomicsRepository(":memory:")
    item, event = purchased()
    invalid = replace(event, currency="KRW")
    with pytest.raises(ActualEconomicsSemanticError, match="currency"):
        repository.create(item, invalid)
    assert repository.get("opp-1") is None
    assert repository.list_events("opp-1") == ()


def test_tampered_purchase_aggregate_currency_is_rejected_without_rows() -> None:
    repository = SQLiteActualEconomicsRepository(":memory:")
    item, event = purchased()
    object.__setattr__(item, "_currency", "KRW")
    with pytest.raises(ActualEconomicsSemanticError, match="currency"):
        repository.create(item, event)
    assert repository.get("opp-1") is None
    assert repository.list_events("opp-1") == ()


def test_malformed_event_version_is_semantic_not_optimistic_conflict() -> None:
    repository = SQLiteActualEconomicsRepository(":memory:")
    item, event = sale_recorded(repository)
    malformed = replace(event, version=event.version + 1)
    with pytest.raises(ActualEconomicsSemanticError, match="event version"):
        repository.save_event(item, malformed, expected_version=1)
    assert repository.get("opp-1").version == 1
    assert len(repository.list_events("opp-1")) == 1


def test_stale_expected_version_remains_optimistic_conflict() -> None:
    repository = SQLiteActualEconomicsRepository(":memory:")
    item, event = sale_recorded(repository)
    with pytest.raises(ActualEconomicsVersionConflictError):
        repository.save_event(item, event, expected_version=0)
    assert repository.get("opp-1").version == 1
    assert len(repository.list_events("opp-1")) == 1
