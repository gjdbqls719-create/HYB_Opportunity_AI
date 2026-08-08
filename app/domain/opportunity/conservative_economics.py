"""Immutable Conservative Economics result and Decimal policy."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import StrEnum
from typing import TYPE_CHECKING

from app.domain.opportunity.economics import EvidenceStatus

if TYPE_CHECKING:
    from app.domain.decision_engine import OpportunityIdentity


CONSERVATIVE_ECONOMICS_SCHEMA_VERSION = "conservative-economics-v1"
CONSERVATIVE_ECONOMICS_POLICY_NAME = "conservative-unit-economics"
CONSERVATIVE_ECONOMICS_POLICY_VERSION = "1.0.0"
CONSERVATIVE_ECONOMICS_DECIMAL_PRECISION = 34
CONSERVATIVE_ECONOMICS_ROUNDING = ROUND_HALF_EVEN


class ConservativeEconomicsStatus(StrEnum):
    CALCULABLE = "calculable"
    BLOCKED = "blocked"


class ConservativeEconomicsAssumptionKind(StrEnum):
    SALE_PRICE_FACTOR = "sale_price_factor"


class ConservativeEconomicsBlockingCode(StrEnum):
    SOURCE_COMPOSITION_BLOCKED = "source_composition_blocked"
    SALE_PRICE_NOT_READY = "sale_price_not_ready"
    MARKETPLACE_FEE_NOT_READY = "marketplace_fee_not_ready"
    PAYMENT_FEE_NOT_READY = "payment_fee_not_ready"
    FIXED_FEE_NOT_READY = "fixed_fee_not_ready"
    TAX_NOT_CAPITAL_AUTHORITATIVE = "tax_not_capital_authoritative"
    DUTY_NOT_CAPITAL_AUTHORITATIVE = "duty_not_capital_authoritative"
    OTHER_COST_SCOPE_UNRESOLVED = "other_cost_scope_unresolved"
    ACQUISITION_COST_NON_POSITIVE = "acquisition_cost_non_positive"
    CURRENCY_MISMATCH = "currency_mismatch"


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _currency(value: str, name: str) -> str:
    result = _text(value, name).upper()
    if len(result) != 3 or not result.isascii() or not result.isalpha():
        raise ValueError(f"{name} must be a three-letter currency code")
    return result


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _decimal(value: Decimal, name: str, *, non_negative: bool = False) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal")
    if not value.is_finite() or (non_negative and value < 0):
        qualifier = "finite and non-negative" if non_negative else "finite"
        raise ValueError(f"{name} must be {qualifier}")
    return value


def conservative_decimal_context() -> Context:
    return Context(
        prec=CONSERVATIVE_ECONOMICS_DECIMAL_PRECISION,
        rounding=CONSERVATIVE_ECONOMICS_ROUNDING,
    )


@dataclass(frozen=True, slots=True)
class ConservativeEconomicsAssumption:
    kind: ConservativeEconomicsAssumptionKind
    value: Decimal
    owner: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", ConservativeEconomicsAssumptionKind(self.kind))
        value = _decimal(self.value, "assumption value")
        if self.kind is ConservativeEconomicsAssumptionKind.SALE_PRICE_FACTOR and not (
            Decimal("0") < value <= Decimal("1")
        ):
            raise ValueError("sale price factor must be greater than zero and at most one")
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "owner", _text(self.owner, "assumption owner"))


@dataclass(frozen=True, slots=True)
class ConservativeEconomicsBlockingReason:
    code: ConservativeEconomicsBlockingCode
    category: str
    source_reference: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", ConservativeEconomicsBlockingCode(self.code))
        object.__setattr__(self, "category", _text(self.category, "category"))
        if self.source_reference is not None:
            object.__setattr__(
                self,
                "source_reference",
                _text(self.source_reference, "source_reference"),
            )


def calculate_conservative_unit_values(
    *,
    expected_sale_price: Decimal,
    sale_price_factor: Decimal,
    acquisition_cost_per_unit: Decimal,
    marketplace_fee_rate: Decimal,
    payment_fee_rate: Decimal,
    fixed_fee: Decimal,
    tax_cost: Decimal,
    duty_cost: Decimal,
    other_cost: Decimal,
) -> dict[str, Decimal]:
    values = {
        "expected_sale_price": expected_sale_price,
        "sale_price_factor": sale_price_factor,
        "acquisition_cost_per_unit": acquisition_cost_per_unit,
        "marketplace_fee_rate": marketplace_fee_rate,
        "payment_fee_rate": payment_fee_rate,
        "fixed_fee": fixed_fee,
        "tax_cost": tax_cost,
        "duty_cost": duty_cost,
        "other_cost": other_cost,
    }
    for name, value in values.items():
        _decimal(value, name, non_negative=True)
    if sale_price_factor <= 0 or sale_price_factor > 1:
        raise ValueError("sale_price_factor must be greater than zero and at most one")
    if expected_sale_price <= 0:
        raise ValueError("expected_sale_price must be positive")
    if acquisition_cost_per_unit <= 0:
        raise ValueError("acquisition_cost_per_unit must be positive")
    with localcontext(conservative_decimal_context()):
        sale_price = expected_sale_price * sale_price_factor
        marketplace_fee = sale_price * marketplace_fee_rate
        payment_fee = sale_price * payment_fee_rate
        total_cost = (
            acquisition_cost_per_unit
            + marketplace_fee
            + payment_fee
            + fixed_fee
            + tax_cost
            + duty_cost
            + other_cost
        )
        profit = sale_price - total_cost
        margin = profit / sale_price * Decimal("100")
        acquisition_roi = profit / acquisition_cost_per_unit * Decimal("100")
    return {
        "conservative_sale_price": sale_price,
        "marketplace_fee": marketplace_fee,
        "payment_fee": payment_fee,
        "total_unit_cost": total_cost,
        "conservative_profit_per_unit": profit,
        "conservative_margin": margin,
        "conservative_acquisition_roi": acquisition_roi,
    }


@dataclass(frozen=True, slots=True)
class ConservativeEconomicsResult:
    result_id: str
    opportunity_identity: OpportunityIdentity
    source_composition_id: str
    source_composition_schema_version: str
    economics_currency: str
    authoritative_expected_sale_price: Decimal | None
    expected_sale_price_evidence_status: EvidenceStatus
    expected_sale_price_evidence_reference: str | None
    conservative_sale_price: Decimal | None
    acquisition_cost_per_unit: Decimal
    marketplace_fee: Decimal | None
    payment_fee: Decimal | None
    fixed_fee: Decimal | None
    accepted_tax_cost: Decimal | None
    accepted_duty_cost: Decimal | None
    accepted_other_cost: Decimal | None
    total_unit_cost: Decimal | None
    conservative_profit_per_unit: Decimal | None
    conservative_margin: Decimal | None
    conservative_acquisition_roi: Decimal | None
    assumptions: tuple[ConservativeEconomicsAssumption, ...]
    scenario_name: str
    scenario_version: str
    status: ConservativeEconomicsStatus
    blocking_reasons: tuple[ConservativeEconomicsBlockingReason, ...]
    policy_name: str
    policy_version: str
    policy_precision: int
    policy_rounding: str
    requested_at: datetime
    calculated_at: datetime
    schema_version: str = CONSERVATIVE_ECONOMICS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "result_id",
            "source_composition_id",
            "source_composition_schema_version",
            "scenario_name",
            "scenario_version",
            "policy_name",
            "policy_version",
            "policy_rounding",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        from app.domain.decision_engine import OpportunityIdentity

        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        object.__setattr__(
            self,
            "economics_currency",
            _currency(self.economics_currency, "economics_currency"),
        )
        if self.authoritative_expected_sale_price is not None:
            _decimal(
                self.authoritative_expected_sale_price,
                "authoritative_expected_sale_price",
                non_negative=True,
            )
        object.__setattr__(
            self,
            "expected_sale_price_evidence_status",
            EvidenceStatus(self.expected_sale_price_evidence_status),
        )
        if self.expected_sale_price_evidence_reference is not None:
            object.__setattr__(
                self,
                "expected_sale_price_evidence_reference",
                _text(
                    self.expected_sale_price_evidence_reference,
                    "expected_sale_price_evidence_reference",
                ),
            )
        _decimal(
            self.acquisition_cost_per_unit,
            "acquisition_cost_per_unit",
            non_negative=True,
        )
        if not isinstance(self.assumptions, tuple) or len(self.assumptions) != 1:
            raise ValueError("Conservative Economics v1 requires one assumption")
        if not isinstance(self.assumptions[0], ConservativeEconomicsAssumption):
            raise TypeError("assumptions must contain ConservativeEconomicsAssumption")
        if self.assumptions[0].kind is not ConservativeEconomicsAssumptionKind.SALE_PRICE_FACTOR:
            raise ValueError("Conservative Economics v1 requires sale-price factor")
        status = ConservativeEconomicsStatus(self.status)
        object.__setattr__(self, "status", status)
        if not isinstance(self.blocking_reasons, tuple) or any(
            not isinstance(value, ConservativeEconomicsBlockingReason)
            for value in self.blocking_reasons
        ):
            raise TypeError("blocking_reasons must be reason tuple")
        if len({(reason.code, reason.category) for reason in self.blocking_reasons}) != len(
            self.blocking_reasons
        ):
            raise ValueError("blocking reasons must be unique")
        calculated_names = (
            "conservative_sale_price",
            "marketplace_fee",
            "payment_fee",
            "fixed_fee",
            "accepted_tax_cost",
            "accepted_duty_cost",
            "accepted_other_cost",
            "total_unit_cost",
            "conservative_profit_per_unit",
            "conservative_margin",
            "conservative_acquisition_roi",
        )
        if status is ConservativeEconomicsStatus.BLOCKED:
            if not self.blocking_reasons:
                raise ValueError("BLOCKED result requires blocking reasons")
            if any(getattr(self, name) is not None for name in calculated_names):
                raise ValueError("BLOCKED result cannot carry profitability values")
        else:
            if self.blocking_reasons:
                raise ValueError("CALCULABLE result cannot carry blockers")
            if any(getattr(self, name) is None for name in calculated_names):
                raise ValueError("CALCULABLE result requires complete profitability values")
            for name in calculated_names:
                _decimal(getattr(self, name), name)  # type: ignore[arg-type]
            with localcontext(conservative_decimal_context()):
                sale = (
                    self.authoritative_expected_sale_price
                    * self.assumptions[0].value
                )
                total = (
                    self.acquisition_cost_per_unit
                    + self.marketplace_fee
                    + self.payment_fee
                    + self.fixed_fee
                    + self.accepted_tax_cost
                    + self.accepted_duty_cost
                    + self.accepted_other_cost
                )
                profit = sale - total
                expected = {
                    "conservative_sale_price": sale,
                    "total_unit_cost": total,
                    "conservative_profit_per_unit": profit,
                    "conservative_margin": profit / sale * Decimal("100"),
                    "conservative_acquisition_roi": (
                        profit / self.acquisition_cost_per_unit * Decimal("100")
                    ),
                }
            for name, value in expected.items():
                if getattr(self, name) != value:
                    raise ValueError(f"{name} arithmetic mismatch")
        if (
            self.policy_name != CONSERVATIVE_ECONOMICS_POLICY_NAME
            or self.policy_version != CONSERVATIVE_ECONOMICS_POLICY_VERSION
            or self.policy_precision != CONSERVATIVE_ECONOMICS_DECIMAL_PRECISION
            or self.policy_rounding != CONSERVATIVE_ECONOMICS_ROUNDING
        ):
            raise ValueError("unsupported Conservative Economics policy")
        _aware(self.requested_at, "requested_at")
        _aware(self.calculated_at, "calculated_at")
        if self.schema_version != CONSERVATIVE_ECONOMICS_SCHEMA_VERSION:
            raise ValueError("unsupported Conservative Economics schema")


__all__ = [
    name
    for name in globals()
    if name.startswith("Conservative")
    or name.startswith("CONSERVATIVE_ECONOMICS")
    or name == "calculate_conservative_unit_values"
    or name == "conservative_decimal_context"
]
