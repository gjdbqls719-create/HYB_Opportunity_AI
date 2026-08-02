from __future__ import annotations

from app.application.actual_economics.models import (
    CompleteSettlement,
    GetActualEconomics,
    RecordActualPurchase,
    RecordActualSale,
)
from app.application.actual_economics.ports import (
    ActualEconomicsLifecyclePreconditionError,
    ActualEconomicsNotFoundError,
    ActualEconomicsRepository,
    ActualEconomicsVersionConflictError,
    LifecycleReader,
)
from app.domain.opportunity import ActualEconomics, OpportunityLifecycleStatus


class ActualEconomicsService:
    def __init__(self, repository: ActualEconomicsRepository, lifecycle_reader: LifecycleReader) -> None:
        self._repository = repository
        self._lifecycles = lifecycle_reader

    def record_purchase(self, command: RecordActualPurchase) -> ActualEconomics:
        self._require_lifecycle(command.opportunity_id, {
            OpportunityLifecycleStatus.PURCHASED,
            OpportunityLifecycleStatus.LISTED,
            OpportunityLifecycleStatus.SOLD,
        })
        existing = self._repository.get(command.opportunity_id)
        if existing is not None:
            raise ActualEconomicsVersionConflictError("actual economics already exists")
        if command.expected_version != 0:
            raise ActualEconomicsVersionConflictError("new actual economics must expect version 0")
        economics = ActualEconomics(command.opportunity_id, command.currency, created_at=command.occurred_at)
        event = economics.record_purchase(
            purchase_price=command.purchase_price,
            shipping_cost=command.shipping_cost,
            occurred_at=command.occurred_at,
        )
        self._repository.create(economics, event)
        return economics

    def record_sale(self, command: RecordActualSale) -> ActualEconomics:
        self._require_lifecycle(command.opportunity_id, {OpportunityLifecycleStatus.SOLD})
        economics = self._load(command.opportunity_id, command.expected_version)
        event = economics.record_sale(sale_price=command.sale_price, occurred_at=command.occurred_at)
        self._repository.save_event(economics, event, expected_version=command.expected_version)
        return economics

    def complete_settlement(self, command: CompleteSettlement) -> ActualEconomics:
        self._require_lifecycle(command.opportunity_id, {OpportunityLifecycleStatus.SOLD})
        economics = self._load(command.opportunity_id, command.expected_version)
        event = economics.complete_settlement(
            marketplace_fee=command.marketplace_fee,
            payment_fee=command.payment_fee,
            fixed_fee=command.fixed_fee,
            settlement_amount=command.settlement_amount,
            occurred_at=command.occurred_at,
        )
        self._repository.save_event(economics, event, expected_version=command.expected_version)
        return economics

    def get(self, query: GetActualEconomics) -> ActualEconomics:
        economics = self._repository.get(query.opportunity_id)
        if economics is None:
            raise ActualEconomicsNotFoundError(query.opportunity_id)
        return economics

    def _load(self, opportunity_id: str, expected_version: int) -> ActualEconomics:
        economics = self._repository.get(opportunity_id)
        if economics is None:
            raise ActualEconomicsNotFoundError(opportunity_id)
        if economics.version != expected_version:
            raise ActualEconomicsVersionConflictError(
                f"expected version {expected_version}, found {economics.version}"
            )
        return economics

    def _require_lifecycle(self, opportunity_id: str, allowed: set[OpportunityLifecycleStatus]) -> None:
        lifecycle = self._lifecycles.get(opportunity_id)
        if lifecycle is None:
            raise ActualEconomicsLifecyclePreconditionError("opportunity lifecycle does not exist")
        if lifecycle.is_archived:
            raise ActualEconomicsLifecyclePreconditionError("archived lifecycle cannot record actual economics")
        if lifecycle.status not in allowed:
            expected = ", ".join(sorted(status.value for status in allowed))
            raise ActualEconomicsLifecyclePreconditionError(
                f"lifecycle status {lifecycle.status.value} is not one of: {expected}"
            )
