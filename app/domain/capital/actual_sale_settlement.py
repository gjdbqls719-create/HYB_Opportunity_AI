"""Immutable actual marketplace-sale settlement revisions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import StrEnum

from .owned_inventory import OwnedInventoryProductKey


ACTUAL_SALE_SETTLEMENT_SCHEMA_VERSION = "actual-sale-settlement-v1"
ACTUAL_SALE_SOURCE_MANIFEST_SCHEMA_VERSION = "actual-sale-settlement-source-manifest-v1"
ACTUAL_SALE_EVIDENCE_SCHEMA_VERSION = "actual-sale-evidence-v1"
ACTUAL_SALE_MONETARY_FACT_SCHEMA_VERSION = "actual-sale-monetary-fact-v1"
ACTUAL_SALE_OTHER_COSTS_SCHEMA_VERSION = "actual-sale-other-costs-v1"
ACTUAL_SALE_PAYOUT_SCHEMA_VERSION = "actual-sale-payout-v1"
ACTUAL_SALE_FINALITY_SCHEMA_VERSION = "actual-sale-finality-v1"
ACTUAL_SALE_POLICY_NAME = "actual-sale-settlement"
ACTUAL_SALE_POLICY_VERSION = "1.0.0"
ACTUAL_SALE_DECIMAL_PRECISION = 34
ACTUAL_SALE_ROUNDING = ROUND_HALF_EVEN


class ActualSaleSettlementState(StrEnum):
    BLOCKED = "blocked"
    COMPLETE = "complete"


class ActualSaleFactAvailability(StrEnum):
    KNOWN = "known"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class ActualSaleMonetaryCategory(StrEnum):
    GROSS_COMPLETED_MERCHANDISE = "gross_completed_merchandise"
    BUYER_SHIPPING = "buyer_shipping"
    MARKETPLACE_FUNDED_DISCOUNT_SUPPORT = "marketplace_funded_discount_support"
    SELLER_FUNDED_DISCOUNT = "seller_funded_discount"
    TAX_COLLECTED = "tax_collected"
    MARKETPLACE_FEE = "marketplace_fee"
    PAYMENT_FEE = "payment_fee"
    FIXED_FEE = "fixed_fee"
    REFUND = "refund"
    CANCELLATION_REVERSAL = "cancellation_reversal"
    RETURN_RELATED_FEE = "return_related_fee"
    ADVERTISING = "advertising"
    FULFILLMENT = "fulfillment"
    STORAGE = "storage"
    SALE_SIDE_INBOUND_HANDLING = "sale_side_inbound_handling"


FIXED_ACTUAL_SALE_CATEGORIES = tuple(ActualSaleMonetaryCategory)


class ActualSalePayoutReconciliationState(StrEnum):
    RECONCILED = "reconciled"
    NOT_SCOPE_COMPARABLE = "not_scope_comparable"
    UNRESOLVED = "unresolved"


class ActualSaleBlockingReason(StrEnum):
    GROSS_SALES_UNKNOWN = "gross_sales_unknown"
    BUYER_SHIPPING_UNKNOWN = "buyer_shipping_unknown"
    MARKETPLACE_FUNDED_SUPPORT_UNKNOWN = "marketplace_funded_support_unknown"
    SELLER_FUNDED_DISCOUNT_UNKNOWN = "seller_funded_discount_unknown"
    TAX_SCOPE_UNKNOWN = "tax_scope_unknown"
    MARKETPLACE_FEE_UNKNOWN = "marketplace_fee_unknown"
    PAYMENT_FEE_UNKNOWN = "payment_fee_unknown"
    FIXED_FEE_UNKNOWN = "fixed_fee_unknown"
    REFUND_SCOPE_UNRESOLVED = "refund_scope_unresolved"
    CANCELLATION_SCOPE_UNRESOLVED = "cancellation_scope_unresolved"
    RETURN_RELATED_FEE_UNKNOWN = "return_related_fee_unknown"
    RETURN_FINALITY_UNRESOLVED = "return_finality_unresolved"
    ADVERTISING_UNKNOWN = "advertising_unknown"
    FULFILLMENT_UNKNOWN = "fulfillment_unknown"
    STORAGE_UNKNOWN = "storage_unknown"
    HANDLING_UNKNOWN = "handling_unknown"
    OTHER_SALE_SIDE_COST_SCOPE_UNRESOLVED = "other_sale_side_cost_scope_unresolved"
    PAYOUT_UNRESOLVED = "payout_unresolved"
    PAYOUT_RECONCILIATION_UNRESOLVED = "payout_reconciliation_unresolved"
    CROSS_CURRENCY_ACTUAL_FX_UNSUPPORTED = "cross_currency_actual_fx_unsupported"


_UNKNOWN_REASON = {
    ActualSaleMonetaryCategory.GROSS_COMPLETED_MERCHANDISE: ActualSaleBlockingReason.GROSS_SALES_UNKNOWN,
    ActualSaleMonetaryCategory.BUYER_SHIPPING: ActualSaleBlockingReason.BUYER_SHIPPING_UNKNOWN,
    ActualSaleMonetaryCategory.MARKETPLACE_FUNDED_DISCOUNT_SUPPORT: ActualSaleBlockingReason.MARKETPLACE_FUNDED_SUPPORT_UNKNOWN,
    ActualSaleMonetaryCategory.SELLER_FUNDED_DISCOUNT: ActualSaleBlockingReason.SELLER_FUNDED_DISCOUNT_UNKNOWN,
    ActualSaleMonetaryCategory.TAX_COLLECTED: ActualSaleBlockingReason.TAX_SCOPE_UNKNOWN,
    ActualSaleMonetaryCategory.MARKETPLACE_FEE: ActualSaleBlockingReason.MARKETPLACE_FEE_UNKNOWN,
    ActualSaleMonetaryCategory.PAYMENT_FEE: ActualSaleBlockingReason.PAYMENT_FEE_UNKNOWN,
    ActualSaleMonetaryCategory.FIXED_FEE: ActualSaleBlockingReason.FIXED_FEE_UNKNOWN,
    ActualSaleMonetaryCategory.REFUND: ActualSaleBlockingReason.REFUND_SCOPE_UNRESOLVED,
    ActualSaleMonetaryCategory.CANCELLATION_REVERSAL: ActualSaleBlockingReason.CANCELLATION_SCOPE_UNRESOLVED,
    ActualSaleMonetaryCategory.RETURN_RELATED_FEE: ActualSaleBlockingReason.RETURN_RELATED_FEE_UNKNOWN,
    ActualSaleMonetaryCategory.ADVERTISING: ActualSaleBlockingReason.ADVERTISING_UNKNOWN,
    ActualSaleMonetaryCategory.FULFILLMENT: ActualSaleBlockingReason.FULFILLMENT_UNKNOWN,
    ActualSaleMonetaryCategory.STORAGE: ActualSaleBlockingReason.STORAGE_UNKNOWN,
    ActualSaleMonetaryCategory.SALE_SIDE_INBOUND_HANDLING: ActualSaleBlockingReason.HANDLING_UNKNOWN,
}


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _optional_text(value: str | None, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _currency(value: str, name: str = "currency") -> str:
    result = _text(value, name).upper()
    if len(result) != 3 or not result.isascii() or not result.isalpha():
        raise ValueError(f"{name} must be a three-letter currency code")
    return result


def _money(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal")
    if not value.is_finite() or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")
    return value


def _quantity(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def actual_sale_decimal_context() -> Context:
    return Context(prec=ACTUAL_SALE_DECIMAL_PRECISION, rounding=ACTUAL_SALE_ROUNDING)


@dataclass(frozen=True, slots=True)
class ActualSaleEvidenceReference:
    reference: str
    observed_at: datetime
    operator_id: str
    collection_method: str
    schema_version: str = ACTUAL_SALE_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("reference", "operator_id", "collection_method"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        if self.schema_version != ACTUAL_SALE_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported actual sale evidence schema")


@dataclass(frozen=True, slots=True)
class ActualSaleMonetaryFact:
    category: ActualSaleMonetaryCategory
    availability: ActualSaleFactAvailability
    amount: Decimal | None
    currency: str | None
    occurred_at: datetime | None
    evidence: ActualSaleEvidenceReference | None
    unresolved_reason: str | None
    schema_version: str = ACTUAL_SALE_MONETARY_FACT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "category", ActualSaleMonetaryCategory(self.category))
        availability = ActualSaleFactAvailability(self.availability)
        object.__setattr__(self, "availability", availability)
        object.__setattr__(self, "unresolved_reason", _optional_text(self.unresolved_reason, "unresolved_reason"))
        if availability is ActualSaleFactAvailability.KNOWN:
            object.__setattr__(self, "amount", _money(self.amount, "amount"))  # type: ignore[arg-type]
            object.__setattr__(self, "currency", _currency(self.currency))  # type: ignore[arg-type]
            object.__setattr__(self, "occurred_at", _aware(self.occurred_at, "occurred_at"))  # type: ignore[arg-type]
            if not isinstance(self.evidence, ActualSaleEvidenceReference):
                raise TypeError("KNOWN actual sale fact requires evidence")
            if self.unresolved_reason is not None:
                raise ValueError("KNOWN actual sale fact cannot be unresolved")
        elif availability is ActualSaleFactAvailability.NOT_APPLICABLE:
            if any(value is not None for value in (self.amount, self.currency, self.occurred_at, self.unresolved_reason)):
                raise ValueError("NOT_APPLICABLE actual sale fact cannot carry value or unresolved reason")
            if not isinstance(self.evidence, ActualSaleEvidenceReference):
                raise TypeError("NOT_APPLICABLE actual sale fact requires evidence")
        else:
            if any(value is not None for value in (self.amount, self.currency, self.occurred_at)):
                raise ValueError("UNKNOWN actual sale fact cannot carry monetary value")
            object.__setattr__(self, "unresolved_reason", _text(self.unresolved_reason, "unresolved_reason"))  # type: ignore[arg-type]
            if self.evidence is not None and not isinstance(self.evidence, ActualSaleEvidenceReference):
                raise TypeError("evidence must be ActualSaleEvidenceReference or None")
        if self.schema_version != ACTUAL_SALE_MONETARY_FACT_SCHEMA_VERSION:
            raise ValueError("unsupported actual sale monetary fact schema")


@dataclass(frozen=True, slots=True)
class OtherActualSaleCostItem:
    scope: str
    amount: Decimal
    currency: str
    occurred_at: datetime
    evidence: ActualSaleEvidenceReference

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", _text(self.scope, "scope"))
        object.__setattr__(self, "amount", _money(self.amount, "amount"))
        object.__setattr__(self, "currency", _currency(self.currency))
        object.__setattr__(self, "occurred_at", _aware(self.occurred_at, "occurred_at"))
        if not isinstance(self.evidence, ActualSaleEvidenceReference):
            raise TypeError("other actual sale cost requires evidence")


@dataclass(frozen=True, slots=True)
class OtherActualSaleCosts:
    availability: ActualSaleFactAvailability
    items: tuple[OtherActualSaleCostItem, ...]
    scope_evidence: ActualSaleEvidenceReference | None
    unresolved_reason: str | None
    schema_version: str = ACTUAL_SALE_OTHER_COSTS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        availability = ActualSaleFactAvailability(self.availability)
        object.__setattr__(self, "availability", availability)
        if not isinstance(self.items, tuple) or any(not isinstance(v, OtherActualSaleCostItem) for v in self.items):
            raise TypeError("items must be a tuple of OtherActualSaleCostItem")
        object.__setattr__(self, "unresolved_reason", _optional_text(self.unresolved_reason, "unresolved_reason"))
        if availability is ActualSaleFactAvailability.KNOWN:
            if not isinstance(self.scope_evidence, ActualSaleEvidenceReference):
                raise TypeError("KNOWN other sale cost scope requires evidence")
            if self.unresolved_reason is not None:
                raise ValueError("KNOWN other sale cost scope cannot be unresolved")
        elif availability is ActualSaleFactAvailability.NOT_APPLICABLE:
            if self.items or self.unresolved_reason is not None:
                raise ValueError("NOT_APPLICABLE other sale cost scope cannot carry items")
            if not isinstance(self.scope_evidence, ActualSaleEvidenceReference):
                raise TypeError("NOT_APPLICABLE other sale cost scope requires evidence")
        else:
            if self.items:
                raise ValueError("UNKNOWN other sale cost scope cannot carry items")
            object.__setattr__(self, "unresolved_reason", _text(self.unresolved_reason, "unresolved_reason"))  # type: ignore[arg-type]
            if self.scope_evidence is not None and not isinstance(self.scope_evidence, ActualSaleEvidenceReference):
                raise TypeError("scope_evidence must be evidence or None")
        if self.schema_version != ACTUAL_SALE_OTHER_COSTS_SCHEMA_VERSION:
            raise ValueError("unsupported other actual sale costs schema")


@dataclass(frozen=True, slots=True)
class ActualSalePayoutFact:
    availability: ActualSaleFactAvailability
    amount: Decimal | None
    currency: str | None
    external_reference: str | None
    paid_at: datetime | None
    evidence: ActualSaleEvidenceReference | None
    unresolved_reason: str | None
    reconciliation_state: ActualSalePayoutReconciliationState
    reconciliation_explanation: str | None
    reconciliation_evidence: ActualSaleEvidenceReference | None
    schema_version: str = ACTUAL_SALE_PAYOUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        availability = ActualSaleFactAvailability(self.availability)
        reconciliation = ActualSalePayoutReconciliationState(self.reconciliation_state)
        object.__setattr__(self, "availability", availability)
        object.__setattr__(self, "reconciliation_state", reconciliation)
        object.__setattr__(self, "external_reference", _optional_text(self.external_reference, "external_reference"))
        object.__setattr__(self, "unresolved_reason", _optional_text(self.unresolved_reason, "unresolved_reason"))
        object.__setattr__(self, "reconciliation_explanation", _optional_text(self.reconciliation_explanation, "reconciliation_explanation"))
        if availability is ActualSaleFactAvailability.KNOWN:
            object.__setattr__(self, "amount", _money(self.amount, "amount"))  # type: ignore[arg-type]
            object.__setattr__(self, "currency", _currency(self.currency))  # type: ignore[arg-type]
            object.__setattr__(self, "external_reference", _text(self.external_reference, "external_reference"))  # type: ignore[arg-type]
            object.__setattr__(self, "paid_at", _aware(self.paid_at, "paid_at"))  # type: ignore[arg-type]
            if not isinstance(self.evidence, ActualSaleEvidenceReference):
                raise TypeError("KNOWN payout requires evidence")
            if self.unresolved_reason is not None:
                raise ValueError("KNOWN payout cannot carry unresolved reason")
        elif availability is ActualSaleFactAvailability.NOT_APPLICABLE:
            if any(v is not None for v in (self.amount, self.currency, self.external_reference, self.paid_at, self.unresolved_reason)):
                raise ValueError("NOT_APPLICABLE payout cannot carry payout value")
            if not isinstance(self.evidence, ActualSaleEvidenceReference):
                raise TypeError("NOT_APPLICABLE payout requires evidence")
            if reconciliation is not ActualSalePayoutReconciliationState.NOT_SCOPE_COMPARABLE:
                raise ValueError("NOT_APPLICABLE payout must be NOT_SCOPE_COMPARABLE")
        else:
            if any(v is not None for v in (self.amount, self.currency, self.external_reference, self.paid_at)):
                raise ValueError("UNKNOWN payout cannot carry payout value")
            object.__setattr__(self, "unresolved_reason", _text(self.unresolved_reason, "unresolved_reason"))  # type: ignore[arg-type]
            if reconciliation is not ActualSalePayoutReconciliationState.UNRESOLVED:
                raise ValueError("UNKNOWN payout reconciliation must be UNRESOLVED")
        if reconciliation is ActualSalePayoutReconciliationState.UNRESOLVED:
            if not self.reconciliation_explanation:
                raise ValueError("UNRESOLVED payout reconciliation requires explanation")
        else:
            if not self.reconciliation_explanation or not isinstance(self.reconciliation_evidence, ActualSaleEvidenceReference):
                raise ValueError("resolved payout reconciliation requires explanation and evidence")
        if self.schema_version != ACTUAL_SALE_PAYOUT_SCHEMA_VERSION:
            raise ValueError("unsupported actual sale payout schema")


@dataclass(frozen=True, slots=True)
class ActualSaleFinalityFact:
    confirmed: bool
    observed_at: datetime | None
    evidence: ActualSaleEvidenceReference | None
    unresolved_reason: str | None
    schema_version: str = ACTUAL_SALE_FINALITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.confirmed, bool):
            raise TypeError("confirmed must be bool")
        object.__setattr__(self, "unresolved_reason", _optional_text(self.unresolved_reason, "unresolved_reason"))
        if self.confirmed:
            object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))  # type: ignore[arg-type]
            if not isinstance(self.evidence, ActualSaleEvidenceReference):
                raise TypeError("confirmed finality requires evidence")
            if self.unresolved_reason is not None:
                raise ValueError("confirmed finality cannot be unresolved")
        else:
            if self.observed_at is not None:
                object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
            object.__setattr__(self, "unresolved_reason", _text(self.unresolved_reason, "unresolved_reason"))  # type: ignore[arg-type]
        if self.schema_version != ACTUAL_SALE_FINALITY_SCHEMA_VERSION:
            raise ValueError("unsupported actual sale finality schema")


@dataclass(frozen=True, slots=True)
class ActualSaleSettlementSourceManifest:
    product_key: OwnedInventoryProductKey
    anchor_goods_receipt_id: str
    eligible_goods_receipt_ids: tuple[str, ...]
    contributing_purchase_execution_ids: tuple[str, ...]
    marketplace: str
    seller_account_reference: str
    marketplace_product_reference: str
    marketplace_option_reference: str | None
    marketplace_sku_reference: str | None
    external_report_reference: str
    transaction_references: tuple[str, ...]
    schema_version: str = ACTUAL_SALE_SOURCE_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.product_key, OwnedInventoryProductKey):
            raise TypeError("product_key must be OwnedInventoryProductKey")
        for name in ("anchor_goods_receipt_id", "seller_account_reference", "marketplace_product_reference", "external_report_reference"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "marketplace", _text(self.marketplace, "marketplace").upper())
        for name in ("marketplace_option_reference", "marketplace_sku_reference"):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))
        for name in ("eligible_goods_receipt_ids", "contributing_purchase_execution_ids"):
            values = getattr(self, name)
            if not isinstance(values, tuple) or not values:
                raise ValueError(f"{name} must be a non-empty tuple")
            normalized = tuple(_text(v, name) for v in values)
            if len(set(normalized)) != len(normalized):
                raise ValueError(f"{name} must contain unique values")
            object.__setattr__(self, name, normalized)
        if self.anchor_goods_receipt_id not in self.eligible_goods_receipt_ids:
            raise ValueError("anchor Goods Receipt must be eligible")
        if not isinstance(self.transaction_references, tuple):
            raise TypeError("transaction_references must be tuple")
        transactions = tuple(_text(v, "transaction_reference") for v in self.transaction_references)
        if len(set(transactions)) != len(transactions):
            raise ValueError("transaction references must be unique")
        object.__setattr__(self, "transaction_references", transactions)
        if self.schema_version != ACTUAL_SALE_SOURCE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported actual sale source manifest schema")


def evaluate_actual_sale_settlement(
    fixed_facts: tuple[ActualSaleMonetaryFact, ...],
    other_costs: OtherActualSaleCosts,
    payout: ActualSalePayoutFact,
    finality: ActualSaleFinalityFact,
    settlement_currency: str,
) -> tuple[ActualSaleBlockingReason, ...]:
    if not isinstance(fixed_facts, tuple) or tuple(v.category for v in fixed_facts) != FIXED_ACTUAL_SALE_CATEGORIES:
        raise ValueError("fixed actual sale facts must preserve canonical category order")
    settlement_currency = _currency(settlement_currency, "settlement_currency")
    reasons: list[ActualSaleBlockingReason] = []
    for fact in fixed_facts:
        if fact.category is ActualSaleMonetaryCategory.GROSS_COMPLETED_MERCHANDISE and fact.availability is not ActualSaleFactAvailability.KNOWN:
            reasons.append(ActualSaleBlockingReason.GROSS_SALES_UNKNOWN)
        elif fact.availability is ActualSaleFactAvailability.UNKNOWN:
            reasons.append(_UNKNOWN_REASON[fact.category])
        if fact.availability is ActualSaleFactAvailability.KNOWN and fact.currency != settlement_currency:
            if ActualSaleBlockingReason.CROSS_CURRENCY_ACTUAL_FX_UNSUPPORTED not in reasons:
                reasons.append(ActualSaleBlockingReason.CROSS_CURRENCY_ACTUAL_FX_UNSUPPORTED)
    if other_costs.availability is ActualSaleFactAvailability.UNKNOWN:
        reasons.append(ActualSaleBlockingReason.OTHER_SALE_SIDE_COST_SCOPE_UNRESOLVED)
    elif any(item.currency != settlement_currency for item in other_costs.items):
        reasons.append(ActualSaleBlockingReason.CROSS_CURRENCY_ACTUAL_FX_UNSUPPORTED)
    if payout.availability is ActualSaleFactAvailability.UNKNOWN:
        reasons.append(ActualSaleBlockingReason.PAYOUT_UNRESOLVED)
    elif payout.availability is ActualSaleFactAvailability.KNOWN and payout.currency != settlement_currency:
        reasons.append(ActualSaleBlockingReason.CROSS_CURRENCY_ACTUAL_FX_UNSUPPORTED)
    if payout.reconciliation_state is ActualSalePayoutReconciliationState.UNRESOLVED:
        reasons.append(ActualSaleBlockingReason.PAYOUT_RECONCILIATION_UNRESOLVED)
    elif payout.reconciliation_state is ActualSalePayoutReconciliationState.RECONCILED:
        if payout.availability is not ActualSaleFactAvailability.KNOWN:
            raise ValueError("RECONCILED payout must be KNOWN")
        if not reasons:
            by_category = {value.category: value for value in fixed_facts}

            def amount(category: ActualSaleMonetaryCategory) -> Decimal:
                fact = by_category[category]
                if fact.availability is ActualSaleFactAvailability.NOT_APPLICABLE:
                    return Decimal("0")
                if fact.amount is None:
                    raise ValueError("RECONCILED payout has unresolved component")
                return fact.amount

            with localcontext(actual_sale_decimal_context()):
                component_net = (
                    amount(ActualSaleMonetaryCategory.GROSS_COMPLETED_MERCHANDISE)
                    + amount(ActualSaleMonetaryCategory.BUYER_SHIPPING)
                    + amount(ActualSaleMonetaryCategory.MARKETPLACE_FUNDED_DISCOUNT_SUPPORT)
                    - amount(ActualSaleMonetaryCategory.REFUND)
                    - amount(ActualSaleMonetaryCategory.MARKETPLACE_FEE)
                    - amount(ActualSaleMonetaryCategory.PAYMENT_FEE)
                    - amount(ActualSaleMonetaryCategory.FIXED_FEE)
                    - amount(ActualSaleMonetaryCategory.RETURN_RELATED_FEE)
                    - amount(ActualSaleMonetaryCategory.ADVERTISING)
                    - amount(ActualSaleMonetaryCategory.FULFILLMENT)
                    - amount(ActualSaleMonetaryCategory.STORAGE)
                    - amount(ActualSaleMonetaryCategory.SALE_SIDE_INBOUND_HANDLING)
                )
                for item in other_costs.items:
                    component_net -= item.amount
            if component_net != payout.amount:
                raise ValueError("RECONCILED payout differs from canonical components")
    if not finality.confirmed:
        reasons.append(ActualSaleBlockingReason.RETURN_FINALITY_UNRESOLVED)
    return tuple(dict.fromkeys(reasons))


@dataclass(frozen=True, slots=True)
class ActualSaleSettlement:
    settlement_id: str
    source_manifest: ActualSaleSettlementSourceManifest
    revision: int
    predecessor_settlement_id: str | None
    period_start: datetime
    period_end: datetime
    fulfilled_outbound_quantity: int
    cancelled_quantity: int
    refunded_quantity: int
    returned_quantity: int
    quantity_unit: str
    settlement_currency: str
    fixed_monetary_facts: tuple[ActualSaleMonetaryFact, ...]
    other_sale_side_costs: OtherActualSaleCosts
    payout: ActualSalePayoutFact
    finality: ActualSaleFinalityFact
    state: ActualSaleSettlementState
    blocking_reasons: tuple[ActualSaleBlockingReason, ...]
    operator_id: str
    requested_at: datetime
    admitted_at: datetime
    policy_name: str = ACTUAL_SALE_POLICY_NAME
    policy_version: str = ACTUAL_SALE_POLICY_VERSION
    policy_precision: int = ACTUAL_SALE_DECIMAL_PRECISION
    policy_rounding: str = ACTUAL_SALE_ROUNDING
    schema_version: str = ACTUAL_SALE_SETTLEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "settlement_id", _text(self.settlement_id, "settlement_id"))
        if not isinstance(self.source_manifest, ActualSaleSettlementSourceManifest):
            raise TypeError("source_manifest must be ActualSaleSettlementSourceManifest")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision <= 0:
            raise ValueError("revision must be a positive integer")
        object.__setattr__(self, "predecessor_settlement_id", _optional_text(self.predecessor_settlement_id, "predecessor_settlement_id"))
        if (self.revision == 1) != (self.predecessor_settlement_id is None):
            raise ValueError("revision 1 alone has no predecessor")
        for name in ("period_start", "period_end", "requested_at", "admitted_at"):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if self.period_start >= self.period_end:
            raise ValueError("period_start must precede period_end")
        if self.requested_at < self.period_end or self.admitted_at < self.requested_at:
            raise ValueError("sale settlement must be requested after its closed window")
        for name in ("fulfilled_outbound_quantity", "cancelled_quantity", "refunded_quantity", "returned_quantity"):
            object.__setattr__(self, name, _quantity(getattr(self, name), name))
        if self.refunded_quantity > self.fulfilled_outbound_quantity or self.returned_quantity > self.fulfilled_outbound_quantity:
            raise ValueError("refunded/returned quantity cannot exceed fulfilled outbound")
        object.__setattr__(self, "quantity_unit", _text(self.quantity_unit, "quantity_unit"))
        if self.quantity_unit != self.source_manifest.product_key.quantity_unit:
            raise ValueError("quantity unit differs from exact product key")
        object.__setattr__(self, "settlement_currency", _currency(self.settlement_currency, "settlement_currency"))
        if not isinstance(self.other_sale_side_costs, OtherActualSaleCosts):
            raise TypeError("other_sale_side_costs must be OtherActualSaleCosts")
        if not isinstance(self.payout, ActualSalePayoutFact) or not isinstance(self.finality, ActualSaleFinalityFact):
            raise TypeError("payout/finality has unsupported type")
        reasons = evaluate_actual_sale_settlement(self.fixed_monetary_facts, self.other_sale_side_costs, self.payout, self.finality, self.settlement_currency)
        if tuple(self.blocking_reasons) != reasons:
            raise ValueError("blocking reasons differ from authoritative evaluation")
        object.__setattr__(self, "blocking_reasons", reasons)
        expected_state = ActualSaleSettlementState.BLOCKED if reasons else ActualSaleSettlementState.COMPLETE
        object.__setattr__(self, "state", ActualSaleSettlementState(self.state))
        if self.state is not expected_state:
            raise ValueError("state differs from authoritative completeness")
        object.__setattr__(self, "operator_id", _text(self.operator_id, "operator_id"))
        evidence = [v.evidence for v in self.fixed_monetary_facts if v.evidence]
        evidence.extend(v.evidence for v in self.other_sale_side_costs.items)
        evidence.extend(v for v in (self.other_sale_side_costs.scope_evidence, self.payout.evidence, self.payout.reconciliation_evidence, self.finality.evidence) if v)
        if any(v.operator_id != self.operator_id for v in evidence):
            raise ValueError("all actual sale evidence must belong to command operator")
        if self.finality.confirmed and self.finality.observed_at < self.period_end:  # type: ignore[operator]
            raise ValueError("finality cannot precede evaluation window end")
        if (self.policy_name, self.policy_version, self.policy_precision, self.policy_rounding) != (ACTUAL_SALE_POLICY_NAME, ACTUAL_SALE_POLICY_VERSION, ACTUAL_SALE_DECIMAL_PRECISION, ACTUAL_SALE_ROUNDING):
            raise ValueError("unsupported actual sale settlement policy")
        if self.schema_version != ACTUAL_SALE_SETTLEMENT_SCHEMA_VERSION:
            raise ValueError("unsupported actual sale settlement schema")


__all__ = [name for name in globals() if name.startswith(("ActualSale", "OtherActualSale", "ACTUAL_SALE", "FIXED_ACTUAL_SALE")) or name in {"actual_sale_decimal_context", "evaluate_actual_sale_settlement"}]
