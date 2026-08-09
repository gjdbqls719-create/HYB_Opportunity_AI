"""Immutable event-derived owned-inventory read model."""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.decision_engine import OpportunityIdentity


OWNED_INVENTORY_POLICY_NAME = "receipt-derived-owned-inventory"
OWNED_INVENTORY_POLICY_VERSION = "1.0.0"
OWNED_INVENTORY_POSITION_SCHEMA_VERSION = "owned-inventory-position-v1"
OWNED_INVENTORY_V2_POLICY_NAME = "receipt-and-complete-sale-derived-owned-inventory"
OWNED_INVENTORY_V2_POLICY_VERSION = "2.0.0"
OWNED_INVENTORY_V2_POSITION_SCHEMA_VERSION = "owned-inventory-position-v2"


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _optional_text(value: str | None, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _non_negative_integer(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _source_ids(values: tuple[str, ...], name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple) or not values:
        raise ValueError(f"{name} must be a non-empty tuple")
    normalized = tuple(_text(value, name) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must be unique")
    return normalized


@dataclass(frozen=True, slots=True)
class OwnedInventoryProductKey:
    opportunity_identity: OpportunityIdentity
    source_platform: str
    supplier_id: str
    sourcing_product_id: str
    external_product_reference: str
    option_reference: str | None
    sku_reference: str | None
    quantity_unit: str

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        for name in (
            "source_platform",
            "supplier_id",
            "sourcing_product_id",
            "external_product_reference",
            "quantity_unit",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("option_reference", "sku_reference"):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))

    @property
    def sort_key(self) -> tuple[object, ...]:
        return (
            self.opportunity_identity.opportunity_id,
            self.opportunity_identity.discovery_reference,
            self.source_platform,
            self.supplier_id,
            self.sourcing_product_id,
            self.external_product_reference,
            self.option_reference is not None,
            self.option_reference or "",
            self.sku_reference is not None,
            self.sku_reference or "",
            self.quantity_unit,
        )


@dataclass(frozen=True, slots=True)
class OwnedInventoryPosition:
    product_key: OwnedInventoryProductKey
    total_received: int
    total_sellable_received: int
    total_damaged_received: int
    total_outbound_quantity: int
    sellable_on_hand: int
    contributing_purchase_execution_ids: tuple[str, ...]
    contributing_goods_receipt_ids: tuple[str, ...]
    source_event_count: int
    policy_name: str = OWNED_INVENTORY_POLICY_NAME
    policy_version: str = OWNED_INVENTORY_POLICY_VERSION
    schema_version: str = OWNED_INVENTORY_POSITION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.product_key, OwnedInventoryProductKey):
            raise TypeError("product_key must be OwnedInventoryProductKey")
        for name in (
            "total_received",
            "total_sellable_received",
            "total_damaged_received",
            "total_outbound_quantity",
            "sellable_on_hand",
            "source_event_count",
        ):
            object.__setattr__(
                self, name, _non_negative_integer(getattr(self, name), name)
            )
        object.__setattr__(
            self,
            "contributing_purchase_execution_ids",
            _source_ids(
                self.contributing_purchase_execution_ids,
                "contributing_purchase_execution_ids",
            ),
        )
        object.__setattr__(
            self,
            "contributing_goods_receipt_ids",
            _source_ids(
                self.contributing_goods_receipt_ids,
                "contributing_goods_receipt_ids",
            ),
        )
        if self.source_event_count != len(self.contributing_goods_receipt_ids):
            raise ValueError("source_event_count must equal Goods Receipt source count")
        if self.source_event_count == 0 or self.total_received == 0:
            raise ValueError("Owned Inventory Position requires receipt events")
        if self.total_sellable_received + self.total_damaged_received != self.total_received:
            raise ValueError("sellable plus damaged received must equal total received")
        if self.total_outbound_quantity != 0:
            raise ValueError("owned inventory v1 has no authoritative outbound events")
        if self.sellable_on_hand != (
            self.total_sellable_received - self.total_outbound_quantity
        ):
            raise ValueError("sellable_on_hand differs from authoritative calculation")
        if (
            self.policy_name != OWNED_INVENTORY_POLICY_NAME
            or self.policy_version != OWNED_INVENTORY_POLICY_VERSION
        ):
            raise ValueError("unsupported Owned Inventory policy")
        if self.schema_version != OWNED_INVENTORY_POSITION_SCHEMA_VERSION:
            raise ValueError("unsupported Owned Inventory Position schema")

    @property
    def opportunity_identity(self) -> OpportunityIdentity:
        return self.product_key.opportunity_identity

    @property
    def quantity_unit(self) -> str:
        return self.product_key.quantity_unit


@dataclass(frozen=True, slots=True)
class OwnedInventoryPositionV2:
    product_key: OwnedInventoryProductKey
    total_received: int
    total_sellable_received: int
    total_damaged_received: int
    total_outbound_quantity: int
    sellable_on_hand: int
    contributing_purchase_execution_ids: tuple[str, ...]
    contributing_goods_receipt_ids: tuple[str, ...]
    contributing_actual_sale_settlement_ids: tuple[str, ...]
    inbound_source_event_count: int
    outbound_source_event_count: int
    policy_name: str = OWNED_INVENTORY_V2_POLICY_NAME
    policy_version: str = OWNED_INVENTORY_V2_POLICY_VERSION
    schema_version: str = OWNED_INVENTORY_V2_POSITION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.product_key, OwnedInventoryProductKey):
            raise TypeError("product_key must be OwnedInventoryProductKey")
        for name in (
            "total_received",
            "total_sellable_received",
            "total_damaged_received",
            "total_outbound_quantity",
            "sellable_on_hand",
            "inbound_source_event_count",
            "outbound_source_event_count",
        ):
            object.__setattr__(
                self, name, _non_negative_integer(getattr(self, name), name)
            )
        for name in (
            "contributing_purchase_execution_ids",
            "contributing_goods_receipt_ids",
        ):
            object.__setattr__(self, name, _source_ids(getattr(self, name), name))
        sale_ids = self.contributing_actual_sale_settlement_ids
        if not isinstance(sale_ids, tuple):
            raise ValueError(
                "contributing_actual_sale_settlement_ids must be a tuple"
            )
        normalized_sale_ids = tuple(
            _text(value, "contributing_actual_sale_settlement_ids")
            for value in sale_ids
        )
        if len(set(normalized_sale_ids)) != len(normalized_sale_ids):
            raise ValueError(
                "contributing_actual_sale_settlement_ids must be unique"
            )
        object.__setattr__(
            self, "contributing_actual_sale_settlement_ids", normalized_sale_ids
        )
        if self.inbound_source_event_count != len(
            self.contributing_goods_receipt_ids
        ):
            raise ValueError("inbound count must equal Goods Receipt source count")
        if self.outbound_source_event_count != len(normalized_sale_ids):
            raise ValueError("outbound count must equal Actual Sale source count")
        if self.inbound_source_event_count == 0 or self.total_received == 0:
            raise ValueError("Owned Inventory Position v2 requires receipt events")
        if self.total_sellable_received + self.total_damaged_received != self.total_received:
            raise ValueError("sellable plus damaged received must equal total received")
        if self.total_outbound_quantity > self.total_sellable_received:
            raise ValueError("Owned Inventory Position v2 source history is negative")
        if self.sellable_on_hand != (
            self.total_sellable_received - self.total_outbound_quantity
        ):
            raise ValueError("sellable_on_hand differs from authoritative calculation")
        if (
            self.policy_name != OWNED_INVENTORY_V2_POLICY_NAME
            or self.policy_version != OWNED_INVENTORY_V2_POLICY_VERSION
        ):
            raise ValueError("unsupported Owned Inventory v2 policy")
        if self.schema_version != OWNED_INVENTORY_V2_POSITION_SCHEMA_VERSION:
            raise ValueError("unsupported Owned Inventory Position v2 schema")

    @property
    def opportunity_identity(self) -> OpportunityIdentity:
        return self.product_key.opportunity_identity

    @property
    def quantity_unit(self) -> str:
        return self.product_key.quantity_unit


__all__ = [
    name
    for name in globals()
    if name.startswith(("OwnedInventory", "OWNED_INVENTORY"))
]
