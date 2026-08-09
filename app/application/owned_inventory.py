"""Read-only projection of committed Goods Receipt events into owned inventory."""

from __future__ import annotations

from datetime import timezone
from typing import Protocol

from app.domain.capital import (
    ActualSaleSettlement,
    ActualSaleSettlementState,
    GoodsReceiptRecord,
    OwnedInventoryPosition,
    OwnedInventoryPositionV2,
    OwnedInventoryProductKey,
)
from app.domain.decision_engine import OpportunityIdentity


class OwnedInventoryError(RuntimeError):
    pass


class OwnedInventoryOpportunityNotFoundError(OwnedInventoryError):
    pass


class OwnedInventorySourceConflictError(OwnedInventoryError):
    pass


class OwnedInventoryRepository(Protocol):
    def get_opportunity_identity(
        self, opportunity_id: str
    ) -> OpportunityIdentity | None: ...

    def list_goods_receipts_for_opportunity(
        self, opportunity_id: str
    ) -> tuple[GoodsReceiptRecord, ...]: ...


class OwnedInventoryV2Repository(OwnedInventoryRepository, Protocol):
    def list_complete_actual_sale_settlements_for_opportunity(
        self, opportunity_id: str
    ) -> tuple[ActualSaleSettlement, ...]: ...


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _product_key(record: GoodsReceiptRecord) -> OwnedInventoryProductKey:
    source = record.source_manifest
    return OwnedInventoryProductKey(
        opportunity_identity=source.opportunity_identity,
        source_platform=source.source_platform,
        supplier_id=source.supplier_id,
        sourcing_product_id=source.sourcing_product_id,
        external_product_reference=source.external_product_reference,
        option_reference=source.option_reference,
        sku_reference=source.sku_reference,
        quantity_unit=record.quantity_unit,
    )


def _event_order(record: GoodsReceiptRecord) -> tuple[object, ...]:
    return (record.received_at.astimezone(timezone.utc), record.record_id)


def _sale_event_order(value: ActualSaleSettlement) -> tuple[object, ...]:
    return (value.period_end.astimezone(timezone.utc), value.settlement_id)


class GetOwnedInventoryPositions:
    def __init__(self, repository: OwnedInventoryRepository) -> None:
        self._repository = repository

    def execute(self, opportunity_id: str) -> tuple[OwnedInventoryPosition, ...]:
        opportunity_id = _text(opportunity_id, "opportunity_id")
        identity = self._repository.get_opportunity_identity(opportunity_id)
        if identity is None:
            raise OwnedInventoryOpportunityNotFoundError("opportunity not found")
        if not isinstance(identity, OpportunityIdentity):
            raise OwnedInventorySourceConflictError("opportunity identity is malformed")

        records = tuple(
            self._repository.list_goods_receipts_for_opportunity(opportunity_id)
        )
        if any(not isinstance(record, GoodsReceiptRecord) for record in records):
            raise OwnedInventorySourceConflictError(
                "Goods Receipt source contains an unsupported value"
            )
        record_ids = tuple(record.record_id for record in records)
        if len(set(record_ids)) != len(record_ids):
            raise OwnedInventorySourceConflictError("Goods Receipt source IDs are not unique")

        groups: dict[OwnedInventoryProductKey, list[GoodsReceiptRecord]] = {}
        for record in sorted(records, key=_event_order):
            if record.source_manifest.opportunity_identity != identity:
                raise OwnedInventorySourceConflictError(
                    "Goods Receipt differs from exact Opportunity identity"
                )
            key = _product_key(record)
            groups.setdefault(key, []).append(record)

        positions = tuple(
            self._position(key, tuple(groups[key]))
            for key in sorted(groups, key=lambda value: value.sort_key)
        )
        return positions

    @staticmethod
    def _position(
        key: OwnedInventoryProductKey,
        records: tuple[GoodsReceiptRecord, ...],
    ) -> OwnedInventoryPosition:
        purchase_ids: list[str] = []
        for record in records:
            purchase_id = record.source_manifest.purchase_execution_record_id
            if purchase_id not in purchase_ids:
                purchase_ids.append(purchase_id)
        total_sellable = sum(record.sellable_quantity for record in records)
        total_outbound = 0
        return OwnedInventoryPosition(
            product_key=key,
            total_received=sum(record.received_quantity for record in records),
            total_sellable_received=total_sellable,
            total_damaged_received=sum(record.damaged_quantity for record in records),
            total_outbound_quantity=total_outbound,
            sellable_on_hand=total_sellable - total_outbound,
            contributing_purchase_execution_ids=tuple(purchase_ids),
            contributing_goods_receipt_ids=tuple(record.record_id for record in records),
            source_event_count=len(records),
        )


class GetOwnedInventoryPositionsV2:
    def __init__(self, repository: OwnedInventoryV2Repository) -> None:
        self._repository = repository

    def execute(self, opportunity_id: str) -> tuple[OwnedInventoryPositionV2, ...]:
        opportunity_id = _text(opportunity_id, "opportunity_id")
        identity = self._repository.get_opportunity_identity(opportunity_id)
        if identity is None:
            raise OwnedInventoryOpportunityNotFoundError("opportunity not found")
        if not isinstance(identity, OpportunityIdentity):
            raise OwnedInventorySourceConflictError("opportunity identity is malformed")

        records = tuple(
            self._repository.list_goods_receipts_for_opportunity(opportunity_id)
        )
        sales = tuple(
            self._repository.list_complete_actual_sale_settlements_for_opportunity(
                opportunity_id
            )
        )
        if any(not isinstance(record, GoodsReceiptRecord) for record in records):
            raise OwnedInventorySourceConflictError(
                "Goods Receipt source contains an unsupported value"
            )
        if any(not isinstance(value, ActualSaleSettlement) for value in sales):
            raise OwnedInventorySourceConflictError(
                "Actual Sale source contains an unsupported value"
            )
        record_ids = tuple(record.record_id for record in records)
        sale_ids = tuple(value.settlement_id for value in sales)
        if len(set(record_ids)) != len(record_ids):
            raise OwnedInventorySourceConflictError(
                "Goods Receipt source IDs are not unique"
            )
        if len(set(sale_ids)) != len(sale_ids):
            raise OwnedInventorySourceConflictError(
                "Actual Sale source IDs are not unique"
            )

        receipt_groups: dict[OwnedInventoryProductKey, list[GoodsReceiptRecord]] = {}
        for record in sorted(records, key=_event_order):
            if record.source_manifest.opportunity_identity != identity:
                raise OwnedInventorySourceConflictError(
                    "Goods Receipt differs from exact Opportunity identity"
                )
            key = _product_key(record)
            receipt_groups.setdefault(key, []).append(record)

        sale_groups: dict[OwnedInventoryProductKey, list[ActualSaleSettlement]] = {}
        for value in sorted(sales, key=_sale_event_order):
            if value.state is not ActualSaleSettlementState.COMPLETE:
                raise OwnedInventorySourceConflictError(
                    "Actual Sale enumeration contains a non-COMPLETE revision"
                )
            key = value.source_manifest.product_key
            if key.opportunity_identity != identity:
                raise OwnedInventorySourceConflictError(
                    "Actual Sale differs from exact Opportunity identity"
                )
            if key not in receipt_groups:
                raise OwnedInventorySourceConflictError(
                    "Actual Sale has no matching Goods Receipt product key"
                )
            sale_groups.setdefault(key, []).append(value)

        return tuple(
            self._position(
                key,
                tuple(receipt_groups[key]),
                tuple(sale_groups.get(key, ())),
            )
            for key in sorted(receipt_groups, key=lambda value: value.sort_key)
        )

    @staticmethod
    def _position(
        key: OwnedInventoryProductKey,
        records: tuple[GoodsReceiptRecord, ...],
        sales: tuple[ActualSaleSettlement, ...],
    ) -> OwnedInventoryPositionV2:
        purchase_ids: list[str] = []
        for record in records:
            purchase_id = record.source_manifest.purchase_execution_record_id
            if purchase_id not in purchase_ids:
                purchase_ids.append(purchase_id)
        total_sellable = sum(record.sellable_quantity for record in records)
        total_outbound = sum(value.fulfilled_outbound_quantity for value in sales)
        if total_outbound > total_sellable:
            raise OwnedInventorySourceConflictError(
                "Actual Sale outbound reconstructs negative owned inventory"
            )
        return OwnedInventoryPositionV2(
            product_key=key,
            total_received=sum(record.received_quantity for record in records),
            total_sellable_received=total_sellable,
            total_damaged_received=sum(record.damaged_quantity for record in records),
            total_outbound_quantity=total_outbound,
            sellable_on_hand=total_sellable - total_outbound,
            contributing_purchase_execution_ids=tuple(purchase_ids),
            contributing_goods_receipt_ids=tuple(record.record_id for record in records),
            contributing_actual_sale_settlement_ids=tuple(
                value.settlement_id for value in sales
            ),
            inbound_source_event_count=len(records),
            outbound_source_event_count=len(sales),
        )


__all__ = [
    name
    for name in globals()
    if name.startswith(("OwnedInventory", "GetOwnedInventory"))
]
