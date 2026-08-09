"""Immutable actual acquisition settlement revisions owned by HYB."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import StrEnum

from app.domain.decision_engine import OpportunityIdentity


ACTUAL_ACQUISITION_SETTLEMENT_SCHEMA_VERSION = "actual-acquisition-settlement-v1"
ACTUAL_ACQUISITION_SOURCE_MANIFEST_SCHEMA_VERSION = (
    "actual-acquisition-settlement-source-manifest-v1"
)
ACTUAL_ACQUISITION_EVIDENCE_SCHEMA_VERSION = "actual-acquisition-evidence-v1"
ACTUAL_ACQUISITION_FX_SCHEMA_VERSION = "actual-acquisition-fx-settlement-v1"
ACTUAL_ACQUISITION_POLICY_NAME = "actual-acquisition-settlement"
ACTUAL_ACQUISITION_POLICY_VERSION = "1.0.0"
ACTUAL_ACQUISITION_DECIMAL_PRECISION = 34
ACTUAL_ACQUISITION_ROUNDING = ROUND_HALF_EVEN


class ActualAcquisitionSettlementState(StrEnum):
    BLOCKED = "blocked"
    COMPLETE = "complete"


class ActualAcquisitionFactAvailability(StrEnum):
    KNOWN = "known"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


class ActualAcquisitionCostCategory(StrEnum):
    UNIT_PURCHASE = "unit_purchase"
    SUPPLIER_SIDE_SHIPPING = "supplier_side_shipping"
    INTERNATIONAL_FREIGHT = "international_freight"
    DOMESTIC_INBOUND = "domestic_inbound"
    DUTY_CUSTOMS = "duty_customs"
    OTHER_MANDATORY_ACQUISITION = "other_mandatory_acquisition"


FIXED_ACTUAL_ACQUISITION_CATEGORIES = tuple(ActualAcquisitionCostCategory)[:-1]


class ActualAcquisitionBlockingReason(StrEnum):
    UNIT_PURCHASE_UNKNOWN = "unit_purchase_unknown"
    SUPPLIER_SIDE_SHIPPING_UNKNOWN = "supplier_side_shipping_unknown"
    INTERNATIONAL_FREIGHT_UNKNOWN = "international_freight_unknown"
    DOMESTIC_INBOUND_UNKNOWN = "domestic_inbound_unknown"
    DUTY_CUSTOMS_UNKNOWN = "duty_customs_unknown"
    OTHER_MANDATORY_COST_SCOPE_UNRESOLVED = (
        "other_mandatory_cost_scope_unresolved"
    )
    ACTUAL_FX_MISSING = "actual_fx_missing"
    ACTUAL_FX_MISMATCH = "actual_fx_mismatch"


_UNKNOWN_REASON_BY_CATEGORY = {
    ActualAcquisitionCostCategory.UNIT_PURCHASE: (
        ActualAcquisitionBlockingReason.UNIT_PURCHASE_UNKNOWN
    ),
    ActualAcquisitionCostCategory.SUPPLIER_SIDE_SHIPPING: (
        ActualAcquisitionBlockingReason.SUPPLIER_SIDE_SHIPPING_UNKNOWN
    ),
    ActualAcquisitionCostCategory.INTERNATIONAL_FREIGHT: (
        ActualAcquisitionBlockingReason.INTERNATIONAL_FREIGHT_UNKNOWN
    ),
    ActualAcquisitionCostCategory.DOMESTIC_INBOUND: (
        ActualAcquisitionBlockingReason.DOMESTIC_INBOUND_UNKNOWN
    ),
    ActualAcquisitionCostCategory.DUTY_CUSTOMS: (
        ActualAcquisitionBlockingReason.DUTY_CUSTOMS_UNKNOWN
    ),
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


def _rate(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal")
    if not value.is_finite() or value <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return value


def actual_acquisition_decimal_context() -> Context:
    return Context(
        prec=ACTUAL_ACQUISITION_DECIMAL_PRECISION,
        rounding=ACTUAL_ACQUISITION_ROUNDING,
    )


def _sum(values: tuple[Decimal, ...]) -> Decimal:
    with localcontext(actual_acquisition_decimal_context()):
        result = Decimal("0")
        for value in values:
            result += value
        return result


@dataclass(frozen=True, slots=True)
class ActualAcquisitionEvidenceReference:
    reference: str
    observed_at: datetime
    operator_id: str
    collection_method: str
    schema_version: str = ACTUAL_ACQUISITION_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("reference", "operator_id", "collection_method"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        if self.schema_version != ACTUAL_ACQUISITION_EVIDENCE_SCHEMA_VERSION:
            raise ValueError("unsupported actual acquisition evidence schema")


@dataclass(frozen=True, slots=True)
class ActualAcquisitionFXSettlement:
    source_currency: str
    target_currency: str
    original_amount: Decimal
    target_amount: Decimal | None
    applied_rate: Decimal | None
    provider: str | None
    payment_channel: str | None
    external_reference: str
    settled_at: datetime
    evidence: ActualAcquisitionEvidenceReference
    schema_version: str = ACTUAL_ACQUISITION_FX_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_currency", _currency(self.source_currency, "source_currency"))
        object.__setattr__(self, "target_currency", _currency(self.target_currency, "target_currency"))
        if self.source_currency == self.target_currency:
            raise ValueError("actual FX source and target currencies must differ")
        object.__setattr__(self, "original_amount", _money(self.original_amount, "original_amount"))
        if self.target_amount is not None:
            object.__setattr__(self, "target_amount", _money(self.target_amount, "target_amount"))
        if self.applied_rate is not None:
            object.__setattr__(self, "applied_rate", _rate(self.applied_rate, "applied_rate"))
        if self.target_amount is None and self.applied_rate is None:
            raise ValueError("actual FX requires target_amount or applied_rate")
        object.__setattr__(self, "provider", _optional_text(self.provider, "provider"))
        object.__setattr__(self, "payment_channel", _optional_text(self.payment_channel, "payment_channel"))
        if self.provider is None and self.payment_channel is None:
            raise ValueError("actual FX requires provider or payment_channel")
        object.__setattr__(self, "external_reference", _text(self.external_reference, "external_reference"))
        object.__setattr__(self, "settled_at", _aware(self.settled_at, "settled_at"))
        if not isinstance(self.evidence, ActualAcquisitionEvidenceReference):
            raise TypeError("evidence must be ActualAcquisitionEvidenceReference")
        if self.target_amount is not None and self.applied_rate is not None:
            with localcontext(actual_acquisition_decimal_context()):
                expected = self.original_amount * self.applied_rate
            if self.target_amount != expected:
                raise ValueError("actual FX target amount contradicts applied rate")
        if self.schema_version != ACTUAL_ACQUISITION_FX_SCHEMA_VERSION:
            raise ValueError("unsupported actual acquisition FX schema")

    @property
    def normalized_target_amount(self) -> Decimal:
        if self.target_amount is not None:
            return self.target_amount
        with localcontext(actual_acquisition_decimal_context()):
            return self.original_amount * self.applied_rate  # type: ignore[operator]


@dataclass(frozen=True, slots=True)
class ActualAcquisitionCostFact:
    category: ActualAcquisitionCostCategory
    availability: ActualAcquisitionFactAvailability
    amount: Decimal | None = None
    currency: str | None = None
    settled_at: datetime | None = None
    evidence: ActualAcquisitionEvidenceReference | None = None
    unresolved_reason: str | None = None
    actual_fx: ActualAcquisitionFXSettlement | None = None

    def __post_init__(self) -> None:
        category = ActualAcquisitionCostCategory(self.category)
        availability = ActualAcquisitionFactAvailability(self.availability)
        if category not in FIXED_ACTUAL_ACQUISITION_CATEGORIES:
            raise ValueError("fixed cost fact has unsupported category")
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "availability", availability)
        if availability is ActualAcquisitionFactAvailability.KNOWN:
            if self.amount is None or self.currency is None or self.settled_at is None:
                raise ValueError("KNOWN cost fact requires amount, currency, and settled_at")
            object.__setattr__(self, "amount", _money(self.amount, "amount"))
            object.__setattr__(self, "currency", _currency(self.currency))
            object.__setattr__(self, "settled_at", _aware(self.settled_at, "settled_at"))
            if not isinstance(self.evidence, ActualAcquisitionEvidenceReference):
                raise TypeError("KNOWN cost fact requires evidence")
            if self.unresolved_reason is not None:
                raise ValueError("KNOWN cost fact cannot carry unresolved_reason")
        elif availability is ActualAcquisitionFactAvailability.NOT_APPLICABLE:
            if any(value is not None for value in (self.amount, self.currency, self.settled_at, self.actual_fx, self.unresolved_reason)):
                raise ValueError("NOT_APPLICABLE cost fact cannot carry money, FX, or unresolved reason")
            if not isinstance(self.evidence, ActualAcquisitionEvidenceReference):
                raise TypeError("NOT_APPLICABLE cost fact requires evidence")
        else:
            if any(value is not None for value in (self.amount, self.currency, self.settled_at, self.actual_fx)):
                raise ValueError("UNKNOWN cost fact cannot carry money or FX")
            object.__setattr__(self, "unresolved_reason", _text(self.unresolved_reason, "unresolved_reason"))  # type: ignore[arg-type]
            if self.evidence is not None and not isinstance(self.evidence, ActualAcquisitionEvidenceReference):
                raise TypeError("evidence must be ActualAcquisitionEvidenceReference or None")
        if self.actual_fx is not None and not isinstance(self.actual_fx, ActualAcquisitionFXSettlement):
            raise TypeError("actual_fx must be ActualAcquisitionFXSettlement or None")


@dataclass(frozen=True, slots=True)
class OtherMandatoryAcquisitionCostItem:
    scope: str
    amount: Decimal
    currency: str
    settled_at: datetime
    evidence: ActualAcquisitionEvidenceReference
    actual_fx: ActualAcquisitionFXSettlement | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "scope", _text(self.scope, "scope"))
        object.__setattr__(self, "amount", _money(self.amount, "amount"))
        object.__setattr__(self, "currency", _currency(self.currency))
        object.__setattr__(self, "settled_at", _aware(self.settled_at, "settled_at"))
        if not isinstance(self.evidence, ActualAcquisitionEvidenceReference):
            raise TypeError("evidence must be ActualAcquisitionEvidenceReference")
        if self.actual_fx is not None and not isinstance(self.actual_fx, ActualAcquisitionFXSettlement):
            raise TypeError("actual_fx must be ActualAcquisitionFXSettlement or None")


@dataclass(frozen=True, slots=True)
class OtherMandatoryAcquisitionCosts:
    availability: ActualAcquisitionFactAvailability
    items: tuple[OtherMandatoryAcquisitionCostItem, ...]
    scope_evidence: ActualAcquisitionEvidenceReference | None
    unresolved_reason: str | None = None

    def __post_init__(self) -> None:
        availability = ActualAcquisitionFactAvailability(self.availability)
        object.__setattr__(self, "availability", availability)
        if not isinstance(self.items, tuple) or any(
            not isinstance(value, OtherMandatoryAcquisitionCostItem) for value in self.items
        ):
            raise TypeError("items must be a tuple of OtherMandatoryAcquisitionCostItem")
        scopes = tuple(value.scope for value in self.items)
        if len(set(scopes)) != len(scopes):
            raise ValueError("other mandatory cost scopes must be unique")
        if availability is ActualAcquisitionFactAvailability.KNOWN:
            if not self.items:
                raise ValueError("KNOWN other mandatory costs require scoped items")
            if not isinstance(self.scope_evidence, ActualAcquisitionEvidenceReference):
                raise TypeError("KNOWN other mandatory scope requires evidence")
            if self.unresolved_reason is not None:
                raise ValueError("KNOWN other mandatory scope cannot be unresolved")
        elif availability is ActualAcquisitionFactAvailability.NOT_APPLICABLE:
            if self.items or self.unresolved_reason is not None:
                raise ValueError("NOT_APPLICABLE other mandatory scope cannot carry items or unresolved reason")
            if not isinstance(self.scope_evidence, ActualAcquisitionEvidenceReference):
                raise TypeError("NOT_APPLICABLE other mandatory scope requires evidence")
        else:
            object.__setattr__(self, "unresolved_reason", _text(self.unresolved_reason, "unresolved_reason"))  # type: ignore[arg-type]
            if self.scope_evidence is not None and not isinstance(self.scope_evidence, ActualAcquisitionEvidenceReference):
                raise TypeError("scope_evidence must be evidence or None")


@dataclass(frozen=True, slots=True)
class ActualAcquisitionSettlementSourceManifest:
    opportunity_identity: OpportunityIdentity
    purchase_execution_record_id: str
    real_money_execution_intent_id: str
    founder_capital_approval_id: str
    capital_gate_id: str
    capital_requirement_id: str
    intended_order_quantity_id: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    supplier_id: str
    source_platform: str
    external_supplier_reference: str | None
    sourcing_product_id: str
    external_product_reference: str
    option_reference: str | None
    sku_reference: str | None
    quote_id: str
    quote_revision: int
    executed_quantity: int
    executed_quantity_unit: str
    external_order_reference: str
    purchase_executed_at: datetime
    purchase_policy_name: str
    purchase_policy_version: str
    purchase_record_schema_version: str
    schema_version: str = ACTUAL_ACQUISITION_SOURCE_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        for name in (
            "purchase_execution_record_id", "real_money_execution_intent_id",
            "founder_capital_approval_id", "capital_gate_id", "capital_requirement_id",
            "intended_order_quantity_id", "sourcing_admission_id", "supplier_id",
            "source_platform", "sourcing_product_id", "external_product_reference",
            "quote_id", "executed_quantity_unit", "external_order_reference",
            "purchase_policy_name", "purchase_policy_version", "purchase_record_schema_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("external_supplier_reference", "option_reference", "sku_reference"):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))
        for name in ("sourcing_admission_revision", "quote_revision", "executed_quantity"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        object.__setattr__(self, "purchase_executed_at", _aware(self.purchase_executed_at, "purchase_executed_at"))
        if self.schema_version != ACTUAL_ACQUISITION_SOURCE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported actual acquisition source manifest schema")


@dataclass(frozen=True, slots=True)
class NormalizedActualAcquisitionCategory:
    category: ActualAcquisitionCostCategory
    target_currency: str
    target_batch_amount: Decimal | None

    def __post_init__(self) -> None:
        object.__setattr__(self, "category", ActualAcquisitionCostCategory(self.category))
        object.__setattr__(self, "target_currency", _currency(self.target_currency, "target_currency"))
        if self.target_batch_amount is not None:
            object.__setattr__(self, "target_batch_amount", _money(self.target_batch_amount, "target_batch_amount"))


def _normalize_money(
    amount: Decimal,
    currency: str,
    actual_fx: ActualAcquisitionFXSettlement | None,
    target_currency: str,
) -> tuple[Decimal | None, ActualAcquisitionBlockingReason | None]:
    if currency == target_currency:
        if actual_fx is not None:
            raise ValueError("same-currency actual cost cannot carry FX settlement")
        return amount, None
    if actual_fx is None:
        return None, ActualAcquisitionBlockingReason.ACTUAL_FX_MISSING
    if (
        actual_fx.source_currency != currency
        or actual_fx.target_currency != target_currency
        or actual_fx.original_amount != amount
    ):
        return None, ActualAcquisitionBlockingReason.ACTUAL_FX_MISMATCH
    return actual_fx.normalized_target_amount, None


def evaluate_actual_acquisition_settlement(
    fixed_cost_facts: tuple[ActualAcquisitionCostFact, ...],
    other_costs: OtherMandatoryAcquisitionCosts,
    target_currency: str,
    executed_quantity: int,
) -> tuple[
    tuple[ActualAcquisitionBlockingReason, ...],
    tuple[NormalizedActualAcquisitionCategory, ...],
    Decimal | None,
    Decimal | None,
]:
    target_currency = _currency(target_currency, "target_currency")
    if isinstance(executed_quantity, bool) or not isinstance(executed_quantity, int) or executed_quantity <= 0:
        raise ValueError("executed_quantity must be a positive integer")
    if not isinstance(fixed_cost_facts, tuple) or tuple(
        value.category for value in fixed_cost_facts
    ) != FIXED_ACTUAL_ACQUISITION_CATEGORIES:
        raise ValueError("fixed cost facts must preserve canonical category order")
    if not isinstance(other_costs, OtherMandatoryAcquisitionCosts):
        raise TypeError("other_costs must be OtherMandatoryAcquisitionCosts")

    reasons: list[ActualAcquisitionBlockingReason] = []
    normalized: list[NormalizedActualAcquisitionCategory] = []
    fx_reasons: list[ActualAcquisitionBlockingReason] = []
    for fact in fixed_cost_facts:
        amount: Decimal | None
        if fact.availability is ActualAcquisitionFactAvailability.UNKNOWN:
            reasons.append(_UNKNOWN_REASON_BY_CATEGORY[fact.category])
            amount = None
        elif fact.availability is ActualAcquisitionFactAvailability.NOT_APPLICABLE:
            amount = Decimal("0")
        else:
            amount, fx_reason = _normalize_money(
                fact.amount, fact.currency, fact.actual_fx, target_currency  # type: ignore[arg-type]
            )
            if fx_reason is not None:
                fx_reasons.append(fx_reason)
        normalized.append(NormalizedActualAcquisitionCategory(fact.category, target_currency, amount))

    other_amount: Decimal | None
    if other_costs.availability is ActualAcquisitionFactAvailability.UNKNOWN:
        reasons.append(ActualAcquisitionBlockingReason.OTHER_MANDATORY_COST_SCOPE_UNRESOLVED)
        other_amount = None
    elif other_costs.availability is ActualAcquisitionFactAvailability.NOT_APPLICABLE:
        other_amount = Decimal("0")
    else:
        amounts: list[Decimal] = []
        for item in other_costs.items:
            amount, fx_reason = _normalize_money(
                item.amount, item.currency, item.actual_fx, target_currency
            )
            if fx_reason is not None:
                fx_reasons.append(fx_reason)
            elif amount is not None:
                amounts.append(amount)
        other_amount = None if len(amounts) != len(other_costs.items) else _sum(tuple(amounts))
    normalized.append(
        NormalizedActualAcquisitionCategory(
            ActualAcquisitionCostCategory.OTHER_MANDATORY_ACQUISITION,
            target_currency,
            other_amount,
        )
    )
    for reason in (
        ActualAcquisitionBlockingReason.ACTUAL_FX_MISSING,
        ActualAcquisitionBlockingReason.ACTUAL_FX_MISMATCH,
    ):
        if reason in fx_reasons:
            reasons.append(reason)
    if reasons:
        return tuple(reasons), tuple(normalized), None, None
    values = tuple(value.target_batch_amount for value in normalized)
    if any(value is None for value in values):
        raise ValueError("complete settlement calculation has missing normalized amount")
    batch_total = _sum(values)  # type: ignore[arg-type]
    with localcontext(actual_acquisition_decimal_context()):
        per_unit = batch_total / Decimal(executed_quantity)
    return (), tuple(normalized), batch_total, per_unit


@dataclass(frozen=True, slots=True)
class ActualAcquisitionSettlement:
    settlement_id: str
    source_manifest: ActualAcquisitionSettlementSourceManifest
    revision: int
    predecessor_settlement_id: str | None
    target_currency: str
    fixed_cost_facts: tuple[ActualAcquisitionCostFact, ...]
    other_mandatory_costs: OtherMandatoryAcquisitionCosts
    normalized_categories: tuple[NormalizedActualAcquisitionCategory, ...]
    state: ActualAcquisitionSettlementState
    blocking_reasons: tuple[ActualAcquisitionBlockingReason, ...]
    acquisition_batch_total: Decimal | None
    acquisition_per_unit: Decimal | None
    operator_id: str
    requested_at: datetime
    admitted_at: datetime
    policy_name: str = ACTUAL_ACQUISITION_POLICY_NAME
    policy_version: str = ACTUAL_ACQUISITION_POLICY_VERSION
    policy_precision: int = ACTUAL_ACQUISITION_DECIMAL_PRECISION
    policy_rounding: str = ACTUAL_ACQUISITION_ROUNDING
    schema_version: str = ACTUAL_ACQUISITION_SETTLEMENT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "settlement_id", _text(self.settlement_id, "settlement_id"))
        if not isinstance(self.source_manifest, ActualAcquisitionSettlementSourceManifest):
            raise TypeError("source_manifest must be ActualAcquisitionSettlementSourceManifest")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision <= 0:
            raise ValueError("revision must be a positive integer")
        object.__setattr__(self, "predecessor_settlement_id", _optional_text(self.predecessor_settlement_id, "predecessor_settlement_id"))
        if (self.revision == 1) != (self.predecessor_settlement_id is None):
            raise ValueError("revision 1 alone has no predecessor")
        object.__setattr__(self, "target_currency", _currency(self.target_currency, "target_currency"))
        expected = evaluate_actual_acquisition_settlement(
            self.fixed_cost_facts,
            self.other_mandatory_costs,
            self.target_currency,
            self.source_manifest.executed_quantity,
        )
        reasons, normalized, batch_total, per_unit = expected
        state = ActualAcquisitionSettlementState(self.state)
        object.__setattr__(self, "state", state)
        if tuple(self.blocking_reasons) != reasons:
            raise ValueError("settlement blocking reasons differ from authoritative evaluation")
        object.__setattr__(self, "blocking_reasons", reasons)
        if tuple(self.normalized_categories) != normalized:
            raise ValueError("normalized categories differ from authoritative calculation")
        object.__setattr__(self, "normalized_categories", normalized)
        expected_state = (
            ActualAcquisitionSettlementState.BLOCKED
            if reasons
            else ActualAcquisitionSettlementState.COMPLETE
        )
        if state is not expected_state:
            raise ValueError("settlement state differs from authoritative completeness")
        if self.acquisition_batch_total != batch_total or self.acquisition_per_unit != per_unit:
            raise ValueError("settlement totals differ from authoritative calculation")
        object.__setattr__(self, "operator_id", _text(self.operator_id, "operator_id"))
        evidence_values = [fact.evidence for fact in self.fixed_cost_facts if fact.evidence]
        evidence_values.extend(item.evidence for item in self.other_mandatory_costs.items)
        if self.other_mandatory_costs.scope_evidence:
            evidence_values.append(self.other_mandatory_costs.scope_evidence)
        evidence_values.extend(
            value.actual_fx.evidence
            for value in (*self.fixed_cost_facts, *self.other_mandatory_costs.items)
            if value.actual_fx is not None
        )
        if any(value.operator_id != self.operator_id for value in evidence_values):
            raise ValueError("all settlement evidence must belong to command operator")
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        object.__setattr__(self, "admitted_at", _aware(self.admitted_at, "admitted_at"))
        if (
            self.policy_name != ACTUAL_ACQUISITION_POLICY_NAME
            or self.policy_version != ACTUAL_ACQUISITION_POLICY_VERSION
            or self.policy_precision != ACTUAL_ACQUISITION_DECIMAL_PRECISION
            or self.policy_rounding != ACTUAL_ACQUISITION_ROUNDING
        ):
            raise ValueError("unsupported actual acquisition settlement policy")
        if self.schema_version != ACTUAL_ACQUISITION_SETTLEMENT_SCHEMA_VERSION:
            raise ValueError("unsupported actual acquisition settlement schema")


__all__ = [
    name
    for name in globals()
    if name.startswith(("ActualAcquisition", "OtherMandatory", "NormalizedActual", "ACTUAL_ACQUISITION", "FIXED_ACTUAL"))
    or name in {"actual_acquisition_decimal_context", "evaluate_actual_acquisition_settlement"}
]
