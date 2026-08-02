from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.actual_economics import (ActualEconomicsLifecyclePreconditionError,
    ActualEconomicsService, CompleteSettlement, GetActualEconomics, RecordActualPurchase, RecordActualSale)
from app.domain.opportunity import OpportunityLifecycle

NOW = datetime(2026, 8, 2, tzinfo=timezone.utc)


class MemoryRepository:
    def __init__(self): self.item = None; self.events = []
    def create(self, economics, event): self.item = economics; self.events.append(event)
    def get(self, opportunity_id): return self.item if self.item and self.item.opportunity_id == opportunity_id else None
    def save_event(self, economics, event, *, expected_version): self.item = economics; self.events.append(event)
    def list_events(self, opportunity_id): return tuple(self.events)


class LifecycleReader:
    def __init__(self, status="purchased", archived=False):
        item = OpportunityLifecycle("opp-1", "ebay:item-1", created_at=NOW, updated_at=NOW)
        if status in {"purchased", "sold"}:
            item.start_review(occurred_at=NOW, operator_id="f", reason="r")
            item.approve(occurred_at=NOW, operator_id="f", reason="r")
            item.purchase(occurred_at=NOW, operator_id="f", reason="r")
        if status == "sold":
            item.list_for_sale(occurred_at=NOW, operator_id="f", reason="r")
            item.sell(occurred_at=NOW, operator_id="f", reason="r")
        if archived: item.archive(occurred_at=NOW, operator_id="f", reason="r")
        self.item = item
    def get(self, opportunity_id): return self.item if opportunity_id == "opp-1" else None


def purchase(service):
    return service.record_purchase(RecordActualPurchase("opp-1", "USD", Decimal("100"), Decimal("10"), NOW))


def test_purchase_get_sale_and_settlement() -> None:
    repository = MemoryRepository()
    purchase_service = ActualEconomicsService(repository, LifecycleReader())
    assert purchase(purchase_service) == purchase_service.get(GetActualEconomics("opp-1"))
    sold_service = ActualEconomicsService(repository, LifecycleReader("sold"))
    sold_service.record_sale(RecordActualSale("opp-1", Decimal("180"), NOW + timedelta(hours=1), 1))
    result = sold_service.complete_settlement(CompleteSettlement(
        "opp-1", Decimal("18"), Decimal("5"), Decimal("2"), Decimal("155"),
        NOW + timedelta(hours=2), 2))
    assert result.calculate_actual_profit() == Decimal("45")


def test_lifecycle_preconditions_and_independence() -> None:
    command = RecordActualPurchase("opp-1", "USD", Decimal("1"), Decimal("0"), NOW)
    for reader in (LifecycleReader("discovered"), LifecycleReader("purchased", archived=True)):
        with pytest.raises(ActualEconomicsLifecyclePreconditionError):
            ActualEconomicsService(MemoryRepository(), reader).record_purchase(command)
    reader = LifecycleReader()
    version = reader.item.version
    purchase(ActualEconomicsService(MemoryRepository(), reader))
    assert reader.item.version == version
    assert reader.item.status.value == "purchased"
