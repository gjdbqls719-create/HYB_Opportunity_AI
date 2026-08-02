from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.opportunity import ActualEconomics, ActualEconomicsStatus, InvalidActualEconomicsTransitionError

NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)


def settled() -> ActualEconomics:
    item = ActualEconomics("opp-1", "usd", created_at=NOW)
    item.record_purchase(purchase_price=Decimal("100"), shipping_cost=Decimal("10"), occurred_at=NOW)
    item.record_sale(sale_price=Decimal("180"), occurred_at=NOW + timedelta(hours=1))
    item.complete_settlement(marketplace_fee=Decimal("18"), payment_fee=Decimal("5"),
                             fixed_fee=Decimal("2"), settlement_amount=Decimal("155"),
                             occurred_at=NOW + timedelta(hours=2))
    return item


def test_purchase_sale_settlement_version_profit_and_roi() -> None:
    item = settled()
    assert item.status is ActualEconomicsStatus.SETTLED
    assert item.version == 3
    assert item.currency == "USD"
    assert item.calculate_actual_profit() == Decimal("45")
    assert item.calculate_actual_roi() == Decimal("45")
    assert not hasattr(item, "actual_profit")


def test_negative_actual_profit_is_valid_calculated_outcome() -> None:
    item = ActualEconomics("opp", "USD", created_at=NOW)
    item.record_purchase(purchase_price=Decimal("100"), shipping_cost=Decimal("10"), occurred_at=NOW)
    item.record_sale(sale_price=Decimal("80"), occurred_at=NOW + timedelta(hours=1))
    item.complete_settlement(marketplace_fee=Decimal("8"), payment_fee=Decimal("2"),
                             fixed_fee=Decimal("1"), settlement_amount=Decimal("69"),
                             occurred_at=NOW + timedelta(hours=2))
    assert item.calculate_actual_profit() == Decimal("-41")
    assert item.calculate_actual_roi() == Decimal("-41")


@pytest.mark.parametrize("value", [-1, 1.2, "1"])
def test_money_requires_non_negative_decimal(value) -> None:
    item = ActualEconomics("opp", "USD", created_at=NOW)
    with pytest.raises((TypeError, ValueError)):
        item.record_purchase(purchase_price=value, shipping_cost=Decimal("0"), occurred_at=NOW)


def test_negative_sale_timezone_currency_and_stage_are_rejected() -> None:
    with pytest.raises(ValueError, match="three-letter"):
        ActualEconomics("opp", "US", created_at=NOW)
    with pytest.raises(ValueError, match="timezone-aware"):
        ActualEconomics("opp", "USD", created_at=NOW.replace(tzinfo=None))
    item = ActualEconomics("opp", "USD", created_at=NOW)
    with pytest.raises(InvalidActualEconomicsTransitionError):
        item.record_sale(sale_price=Decimal("2"), occurred_at=NOW)
    item.record_purchase(purchase_price=Decimal("1"), shipping_cost=Decimal("0"), occurred_at=NOW)
    with pytest.raises(ValueError, match="negative"):
        item.record_sale(sale_price=Decimal("-1"), occurred_at=NOW + timedelta(minutes=1))


def test_core_state_is_read_only() -> None:
    item = ActualEconomics("opp", "USD", created_at=NOW)
    for name, value in (("opportunity_id", "changed"), ("currency", "KRW"),
                        ("status", ActualEconomicsStatus.SETTLED), ("version", 99)):
        with pytest.raises(AttributeError):
            setattr(item, name, value)
