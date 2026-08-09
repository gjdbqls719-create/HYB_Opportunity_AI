"""Immutable exact-source Actual Outcome authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import StrEnum
import json

from .actual_acquisition_settlement import ActualAcquisitionCostCategory
from .actual_sale_settlement import ActualSaleMonetaryCategory
from .owned_inventory import OwnedInventoryProductKey


ACTUAL_OUTCOME_SCHEMA_VERSION = "actual-outcome-v1"
ACTUAL_OUTCOME_SOURCE_MANIFEST_SCHEMA_VERSION = "actual-outcome-source-manifest-v1"
ACTUAL_OUTCOME_COMMAND_SCHEMA_VERSION = "actual-outcome-command-v1"
ACTUAL_OUTCOME_RECEIPT_SCHEMA_VERSION = "actual-outcome-receipt-v1"
ACTUAL_OUTCOME_POLICY_NAME = "actual-outcome"
ACTUAL_OUTCOME_POLICY_VERSION = "1.0.0"
ACTUAL_OUTCOME_DECIMAL_PRECISION = 34
ACTUAL_OUTCOME_ROUNDING = ROUND_HALF_EVEN


class ActualOutcomeState(StrEnum):
    CALCULABLE = "calculable"
    BLOCKED = "blocked"


class ActualOutcomeInventoryResolution(StrEnum):
    PARTIAL = "partial"
    FULLY_RESOLVED = "fully_resolved"


class ActualOutcomeBlockingReason(StrEnum):
    ACQUISITION_NOT_COMPLETE = "acquisition_not_complete"
    SALE_SET_NOT_COMPLETE = "sale_set_not_complete"
    MULTI_PURCHASE_ALLOCATION_UNSUPPORTED = "multi_purchase_allocation_unsupported"
    CURRENCY_MISMATCH = "currency_mismatch"
    CORRECTION_REQUIRED = "correction_required"


def actual_outcome_decimal_context() -> Context:
    return Context(prec=ACTUAL_OUTCOME_DECIMAL_PRECISION, rounding=ACTUAL_OUTCOME_ROUNDING)


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _quantity(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _money(value: Decimal, name: str, *, signed: bool = False) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")
    if not signed and value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _sum(values) -> Decimal:
    with localcontext(actual_outcome_decimal_context()):
        result = Decimal("0")
        for value in values:
            result += value
        return result


def _ids(values: tuple[str, ...], name: str, *, non_empty: bool = True) -> tuple[str, ...]:
    if not isinstance(values, tuple) or (non_empty and not values):
        raise ValueError(f"{name} must be {'a non-empty ' if non_empty else ''}tuple")
    normalized = tuple(_text(value, name) for value in values)
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must contain unique values")
    return normalized


@dataclass(frozen=True, slots=True)
class ActualOutcomeSaleWindow:
    settlement_id: str
    period_start: datetime
    period_end: datetime

    def __post_init__(self) -> None:
        object.__setattr__(self, "settlement_id", _text(self.settlement_id, "settlement_id"))
        object.__setattr__(self, "period_start", _aware(self.period_start, "period_start"))
        object.__setattr__(self, "period_end", _aware(self.period_end, "period_end"))
        if self.period_start >= self.period_end:
            raise ValueError("sale window start must precede end")


@dataclass(frozen=True, slots=True)
class ActualOutcomeSourceManifest:
    product_key: OwnedInventoryProductKey
    purchase_execution_record_id: str
    actual_acquisition_settlement_id: str
    goods_receipt_ids: tuple[str, ...]
    actual_sale_settlement_ids: tuple[str, ...]
    sale_windows: tuple[ActualOutcomeSaleWindow, ...]
    executed_quantity: int
    received_quantity: int
    sellable_received_quantity: int
    damaged_quantity: int
    sold_quantity: int
    remaining_sellable_quantity: int
    returned_quantity: int
    unreceived_quantity: int
    quantity_unit: str
    currency: str
    evaluation_start: datetime
    evaluation_through: datetime
    acquisition_policy_version: str
    acquisition_schema_version: str
    goods_receipt_policy_versions: tuple[str, ...]
    goods_receipt_schema_versions: tuple[str, ...]
    sale_policy_versions: tuple[str, ...]
    sale_schema_versions: tuple[str, ...]
    acquisition_source_snapshot: str
    goods_receipt_source_snapshots: tuple[str, ...]
    sale_source_snapshots: tuple[str, ...]
    schema_version: str = ACTUAL_OUTCOME_SOURCE_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.product_key, OwnedInventoryProductKey):
            raise TypeError("product_key must be OwnedInventoryProductKey")
        for name in (
            "purchase_execution_record_id", "actual_acquisition_settlement_id",
            "quantity_unit", "currency", "acquisition_policy_version",
            "acquisition_schema_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "currency", self.currency.upper())
        object.__setattr__(self, "goods_receipt_ids", _ids(self.goods_receipt_ids, "goods_receipt_ids", non_empty=False))
        object.__setattr__(self, "actual_sale_settlement_ids", _ids(self.actual_sale_settlement_ids, "actual_sale_settlement_ids"))
        if not isinstance(self.sale_windows, tuple) or any(not isinstance(v, ActualOutcomeSaleWindow) for v in self.sale_windows):
            raise TypeError("sale_windows must contain ActualOutcomeSaleWindow")
        if tuple(v.settlement_id for v in self.sale_windows) != self.actual_sale_settlement_ids:
            raise ValueError("sale windows must match exact sale settlement order")
        if tuple(sorted(self.sale_windows, key=lambda v: (v.period_end, v.settlement_id))) != self.sale_windows:
            raise ValueError("sale windows must use deterministic chronological order")
        for name in (
            "executed_quantity", "received_quantity", "sellable_received_quantity",
            "damaged_quantity", "sold_quantity", "remaining_sellable_quantity",
            "returned_quantity", "unreceived_quantity",
        ):
            object.__setattr__(self, name, _quantity(getattr(self, name), name))
        if self.executed_quantity <= 0:
            raise ValueError("executed_quantity must be positive")
        if self.quantity_unit != self.product_key.quantity_unit:
            raise ValueError("quantity unit differs from exact product key")
        if self.sellable_received_quantity + self.damaged_quantity != self.received_quantity:
            raise ValueError("receipt condition quantities are inconsistent")
        if self.sold_quantity > self.sellable_received_quantity:
            raise ValueError("sold quantity exceeds sellable receipts")
        if self.remaining_sellable_quantity != self.sellable_received_quantity - self.sold_quantity:
            raise ValueError("remaining sellable quantity is inconsistent")
        if self.unreceived_quantity != self.executed_quantity - self.received_quantity:
            raise ValueError("unreceived quantity is inconsistent")
        if self.executed_quantity != self.sold_quantity + self.remaining_sellable_quantity + self.damaged_quantity + self.unreceived_quantity:
            raise ValueError("outcome quantity decomposition does not conserve executed quantity")
        object.__setattr__(self, "evaluation_start", _aware(self.evaluation_start, "evaluation_start"))
        object.__setattr__(self, "evaluation_through", _aware(self.evaluation_through, "evaluation_through"))
        if self.evaluation_start != min(v.period_start for v in self.sale_windows) or self.evaluation_through != max(v.period_end for v in self.sale_windows):
            raise ValueError("evaluation boundary differs from selected windows")
        for name in ("goods_receipt_policy_versions", "goods_receipt_schema_versions", "sale_policy_versions", "sale_schema_versions"):
            values = getattr(self, name)
            if not isinstance(values, tuple):
                raise TypeError(f"{name} must be tuple")
            object.__setattr__(self, name, tuple(_text(v, name) for v in values))
        if len(self.goods_receipt_policy_versions) != len(self.goods_receipt_ids) or len(self.goods_receipt_schema_versions) != len(self.goods_receipt_ids):
            raise ValueError("Goods Receipt version manifest cardinality differs")
        if len(self.sale_policy_versions) != len(self.actual_sale_settlement_ids) or len(self.sale_schema_versions) != len(self.actual_sale_settlement_ids):
            raise ValueError("Actual Sale version manifest cardinality differs")
        object.__setattr__(self, "acquisition_source_snapshot", _text(self.acquisition_source_snapshot, "acquisition_source_snapshot"))
        for name, expected in (
            ("goods_receipt_source_snapshots", len(self.goods_receipt_ids)),
            ("sale_source_snapshots", len(self.actual_sale_settlement_ids)),
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or len(values) != expected:
                raise ValueError(f"{name} cardinality differs from exact sources")
            object.__setattr__(self, name, tuple(_text(v, name) for v in values))
        for snapshot in (self.acquisition_source_snapshot, *self.goods_receipt_source_snapshots, *self.sale_source_snapshots):
            if not isinstance(json.loads(snapshot), dict):
                raise ValueError("source snapshot must be a canonical JSON object")
        if self.schema_version != ACTUAL_OUTCOME_SOURCE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported Actual Outcome source manifest schema")


@dataclass(frozen=True, slots=True)
class ActualOutcomeAcquisitionAllocation:
    category: ActualAcquisitionCostCategory
    batch_amount: Decimal
    per_executed_unit: Decimal
    sold_cogs: Decimal
    remaining_sellable_basis: Decimal
    damaged_loss: Decimal
    unreceived_exposure: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "category", ActualAcquisitionCostCategory(self.category))
        for name in ("batch_amount", "per_executed_unit", "sold_cogs", "remaining_sellable_basis", "damaged_loss", "unreceived_exposure"):
            object.__setattr__(self, name, _money(getattr(self, name), name))
        if _sum((self.sold_cogs, self.remaining_sellable_basis, self.damaged_loss, self.unreceived_exposure)) != self.batch_amount:
            raise ValueError("acquisition category allocation does not conserve batch amount")


@dataclass(frozen=True, slots=True)
class ActualOutcomeSaleComponent:
    category: ActualSaleMonetaryCategory
    amount: Decimal

    def __post_init__(self) -> None:
        object.__setattr__(self, "category", ActualSaleMonetaryCategory(self.category))
        object.__setattr__(self, "amount", _money(self.amount, "amount"))


@dataclass(frozen=True, slots=True)
class ActualOutcomeMetric:
    available: bool
    value: Decimal | None

    def __post_init__(self) -> None:
        if not isinstance(self.available, bool):
            raise TypeError("metric available must be bool")
        if self.available != (self.value is not None):
            raise ValueError("metric availability and value differ")
        if self.value is not None:
            object.__setattr__(self, "value", _money(self.value, "metric value", signed=True))


@dataclass(frozen=True, slots=True)
class ActualOutcome:
    outcome_id: str
    source_manifest: ActualOutcomeSourceManifest
    state: ActualOutcomeState
    inventory_resolution: ActualOutcomeInventoryResolution
    blocking_reasons: tuple[ActualOutcomeBlockingReason, ...]
    acquisition_allocations: tuple[ActualOutcomeAcquisitionAllocation, ...]
    sale_components: tuple[ActualOutcomeSaleComponent, ...]
    other_sale_side_costs: Decimal | None
    acquisition_batch_total: Decimal | None
    actual_cogs: Decimal | None
    remaining_sellable_inventory_cost_basis: Decimal | None
    damaged_acquisition_loss: Decimal | None
    unreceived_acquisition_cost_basis: Decimal | None
    gross_realized_merchandise_revenue: Decimal | None
    recognized_sale_credits: Decimal | None
    recognized_sale_side_costs: Decimal | None
    net_realized_sale_contribution: Decimal | None
    actual_realized_profit: Decimal | None
    actual_margin: ActualOutcomeMetric
    actual_acquisition_roi: ActualOutcomeMetric
    known_payout_total: Decimal | None
    payout_reconciliation_states: tuple[str, ...]
    requested_at: datetime
    calculated_at: datetime
    committed_at: datetime
    policy_name: str = ACTUAL_OUTCOME_POLICY_NAME
    policy_version: str = ACTUAL_OUTCOME_POLICY_VERSION
    policy_precision: int = ACTUAL_OUTCOME_DECIMAL_PRECISION
    policy_rounding: str = ACTUAL_OUTCOME_ROUNDING
    schema_version: str = ACTUAL_OUTCOME_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "outcome_id", _text(self.outcome_id, "outcome_id"))
        if not isinstance(self.source_manifest, ActualOutcomeSourceManifest):
            raise TypeError("source_manifest must be ActualOutcomeSourceManifest")
        state = ActualOutcomeState(self.state)
        resolution = ActualOutcomeInventoryResolution(self.inventory_resolution)
        reasons = tuple(ActualOutcomeBlockingReason(v) for v in self.blocking_reasons)
        object.__setattr__(self, "state", state)
        object.__setattr__(self, "inventory_resolution", resolution)
        object.__setattr__(self, "blocking_reasons", reasons)
        expected_resolution = ActualOutcomeInventoryResolution.FULLY_RESOLVED if (
            self.source_manifest.received_quantity == self.source_manifest.executed_quantity
            and self.source_manifest.remaining_sellable_quantity == 0
            and self.source_manifest.returned_quantity == 0
        ) else ActualOutcomeInventoryResolution.PARTIAL
        if resolution is not expected_resolution:
            raise ValueError("inventory resolution differs from exact quantity state")
        if not isinstance(self.actual_margin, ActualOutcomeMetric) or not isinstance(self.actual_acquisition_roi, ActualOutcomeMetric):
            raise TypeError("Actual Outcome ratios must be explicit metrics")
        for name in ("requested_at", "calculated_at", "committed_at"):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if self.calculated_at > self.committed_at:
            raise ValueError("committed_at cannot precede calculated_at")
        if (self.policy_name, self.policy_version, self.policy_precision, self.policy_rounding, self.schema_version) != (
            ACTUAL_OUTCOME_POLICY_NAME, ACTUAL_OUTCOME_POLICY_VERSION,
            ACTUAL_OUTCOME_DECIMAL_PRECISION, ACTUAL_OUTCOME_ROUNDING,
            ACTUAL_OUTCOME_SCHEMA_VERSION,
        ):
            raise ValueError("unsupported Actual Outcome policy or schema")
        if state is ActualOutcomeState.BLOCKED:
            if not reasons:
                raise ValueError("BLOCKED outcome requires reasons")
            if self.acquisition_allocations or self.sale_components:
                raise ValueError("BLOCKED outcome cannot carry derived component results")
            money = (
                self.other_sale_side_costs, self.acquisition_batch_total, self.actual_cogs,
                self.remaining_sellable_inventory_cost_basis, self.damaged_acquisition_loss,
                self.unreceived_acquisition_cost_basis, self.gross_realized_merchandise_revenue,
                self.recognized_sale_credits, self.recognized_sale_side_costs,
                self.net_realized_sale_contribution, self.actual_realized_profit,
                self.known_payout_total,
            )
            if any(value is not None for value in money) or self.actual_margin.available or self.actual_acquisition_roi.available:
                raise ValueError("BLOCKED outcome cannot carry profitability results")
            return
        if reasons:
            raise ValueError("CALCULABLE outcome cannot carry blocking reasons")
        if tuple(v.category for v in self.acquisition_allocations) != tuple(ActualAcquisitionCostCategory):
            raise ValueError("acquisition allocations must preserve canonical category order")
        if tuple(v.category for v in self.sale_components) != tuple(ActualSaleMonetaryCategory):
            raise ValueError("sale components must preserve canonical category order")
        for name in (
            "other_sale_side_costs", "acquisition_batch_total", "actual_cogs",
            "remaining_sellable_inventory_cost_basis", "damaged_acquisition_loss",
            "unreceived_acquisition_cost_basis", "gross_realized_merchandise_revenue",
            "recognized_sale_credits", "recognized_sale_side_costs",
            "net_realized_sale_contribution", "actual_realized_profit",
        ):
            value = getattr(self, name)
            object.__setattr__(self, name, _money(value, name, signed=name in {"net_realized_sale_contribution", "actual_realized_profit"}))  # type: ignore[arg-type]
        allocations = self.acquisition_allocations
        expected = {
            "acquisition_batch_total": _sum(v.batch_amount for v in allocations),
            "actual_cogs": _sum(v.sold_cogs for v in allocations),
            "remaining_sellable_inventory_cost_basis": _sum(v.remaining_sellable_basis for v in allocations),
            "damaged_acquisition_loss": _sum(v.damaged_loss for v in allocations),
            "unreceived_acquisition_cost_basis": _sum(v.unreceived_exposure for v in allocations),
        }
        if any(getattr(self, name) != value for name, value in expected.items()):
            raise ValueError("Actual Outcome acquisition totals differ from category allocations")
        by_category = {v.category: v.amount for v in self.sale_components}
        gross = by_category[ActualSaleMonetaryCategory.GROSS_COMPLETED_MERCHANDISE]
        credits = _sum((gross, by_category[ActualSaleMonetaryCategory.BUYER_SHIPPING], by_category[ActualSaleMonetaryCategory.MARKETPLACE_FUNDED_DISCOUNT_SUPPORT]))
        cost_categories = (
            ActualSaleMonetaryCategory.REFUND, ActualSaleMonetaryCategory.MARKETPLACE_FEE,
            ActualSaleMonetaryCategory.PAYMENT_FEE, ActualSaleMonetaryCategory.FIXED_FEE,
            ActualSaleMonetaryCategory.RETURN_RELATED_FEE, ActualSaleMonetaryCategory.ADVERTISING,
            ActualSaleMonetaryCategory.FULFILLMENT, ActualSaleMonetaryCategory.STORAGE,
            ActualSaleMonetaryCategory.SALE_SIDE_INBOUND_HANDLING,
        )
        costs = _sum((*tuple(by_category[v] for v in cost_categories), self.other_sale_side_costs))  # type: ignore[arg-type]
        contribution = _sum((credits, -costs))
        profit = _sum((contribution, -self.actual_cogs, -self.damaged_acquisition_loss))  # type: ignore[arg-type]
        if (self.gross_realized_merchandise_revenue, self.recognized_sale_credits, self.recognized_sale_side_costs, self.net_realized_sale_contribution, self.actual_realized_profit) != (gross, credits, costs, contribution, profit):
            raise ValueError("Actual Outcome sale/profit formula differs")
        with localcontext(actual_outcome_decimal_context()):
            margin = None if gross == 0 else profit / gross * Decimal("100")
            recognized_basis = self.actual_cogs + self.damaged_acquisition_loss  # type: ignore[operator]
            roi = None if recognized_basis == 0 else profit / recognized_basis * Decimal("100")
        if self.actual_margin != ActualOutcomeMetric(margin is not None, margin):
            raise ValueError("actual margin differs from authoritative formula")
        if self.actual_acquisition_roi != ActualOutcomeMetric(roi is not None, roi):
            raise ValueError("actual acquisition ROI differs from authoritative formula")
        if self.known_payout_total is not None:
            object.__setattr__(self, "known_payout_total", _money(self.known_payout_total, "known_payout_total"))
        if not isinstance(self.payout_reconciliation_states, tuple):
            raise TypeError("payout_reconciliation_states must be tuple")
        object.__setattr__(self, "payout_reconciliation_states", tuple(_text(v, "payout_reconciliation_state") for v in self.payout_reconciliation_states))


__all__ = [name for name in globals() if name.startswith(("ActualOutcome", "ACTUAL_OUTCOME")) or name == "actual_outcome_decimal_context"]
