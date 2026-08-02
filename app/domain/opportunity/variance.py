from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping

from app.domain.opportunity.actual_economics import ActualEconomics, ActualEconomicsStatus
from app.domain.opportunity.economics import EconomicEvidence


class VarianceAvailability(StrEnum):
    COMPARABLE = "comparable"
    BASELINE_MISSING = "baseline_missing"
    ACTUAL_INCOMPLETE = "actual_incomplete"
    CURRENCY_MISMATCH = "currency_mismatch"
    COST_SCOPE_MISMATCH = "cost_scope_mismatch"
    PERCENTAGE_UNDEFINED = "percentage_undefined"


class SnapshotValidationError(ValueError):
    """Raised when an estimated baseline lacks its required evidence contract."""


_REQUIRED_SNAPSHOT_EVIDENCE = frozenset({
    "purchase_price", "shipping_cost", "expected_sale_price",
    "marketplace_fee", "payment_fee", "fixed_fee",
    "expected_profit", "expected_roi", "tax_rate", "tax_cost",
})


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _decimal(value: Decimal | None, name: str, *, non_negative: bool = False) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal or None")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    if non_negative and value < 0:
        raise ValueError(f"{name} cannot be negative")
    return value


@dataclass(frozen=True, slots=True)
class EstimatedEconomicsSnapshot:
    snapshot_id: str
    opportunity_id: str
    baseline_kind: str
    currency: str
    purchase_price: Decimal
    shipping_cost: Decimal
    expected_sale_price: Decimal
    marketplace_fee: Decimal
    payment_fee: Decimal
    fixed_fee: Decimal
    expected_profit: Decimal
    expected_roi: Decimal
    tax_cost: Decimal | None
    other_cost: Decimal | None
    duty_cost: Decimal | None
    evidence_metadata: Mapping[str, EconomicEvidence]
    calculation_version: str
    variance_formula_version: str
    captured_at: datetime

    def __post_init__(self) -> None:
        for name in ("snapshot_id", "opportunity_id", "baseline_kind", "calculation_version", "variance_formula_version"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        object.__setattr__(self, "baseline_kind", self.baseline_kind.lower())
        currency = _required_text(self.currency, "currency").upper()
        if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
            raise ValueError("currency must be a three-letter code")
        object.__setattr__(self, "currency", currency)
        for name in (
            "purchase_price", "shipping_cost", "expected_sale_price",
            "marketplace_fee", "payment_fee", "fixed_fee",
        ):
            _decimal(getattr(self, name), name, non_negative=True)
        _decimal(self.expected_profit, "expected_profit")
        _decimal(self.expected_roi, "expected_roi")
        for name in ("tax_cost", "other_cost", "duty_cost"):
            _decimal(getattr(self, name), name, non_negative=True)
        if not isinstance(self.evidence_metadata, Mapping):
            raise TypeError("evidence_metadata must be a mapping")
        evidence = dict(self.evidence_metadata)
        for name, value in evidence.items():
            _required_text(name, "evidence key")
            if not isinstance(value, EconomicEvidence):
                raise TypeError("evidence metadata values must be EconomicEvidence")
        missing_evidence = sorted(_REQUIRED_SNAPSHOT_EVIDENCE.difference(evidence))
        if missing_evidence:
            raise SnapshotValidationError(
                f"missing required snapshot evidence: {', '.join(missing_evidence)}"
            )
        object.__setattr__(self, "evidence_metadata", MappingProxyType(evidence))
        _aware(self.captured_at, "captured_at")


@dataclass(frozen=True, slots=True)
class MetricVariance:
    metric: str
    estimated: Decimal | None
    actual: Decimal | None
    difference: Decimal | None
    absolute_difference: Decimal | None
    percentage_difference: Decimal | None
    availability: VarianceAvailability
    unit: str
    reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric", _required_text(self.metric, "metric"))
        object.__setattr__(self, "unit", _required_text(self.unit, "unit"))
        if not isinstance(self.availability, VarianceAvailability):
            object.__setattr__(self, "availability", VarianceAvailability(self.availability))
        for name in ("estimated", "actual", "difference", "absolute_difference", "percentage_difference"):
            _decimal(getattr(self, name), name)
        if self.reason is not None:
            object.__setattr__(self, "reason", self.reason.strip() or None)


@dataclass(frozen=True, slots=True)
class EconomicsVariance:
    opportunity_id: str
    estimate_snapshot_id: str
    actual_version: int
    currency: str
    calculation_version: str
    variance_formula_version: str
    calculated_at: datetime
    metrics: tuple[MetricVariance, ...]

    def __post_init__(self) -> None:
        for name in ("opportunity_id", "estimate_snapshot_id", "currency", "calculation_version", "variance_formula_version"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        currency = self.currency.upper()
        if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
            raise ValueError("currency must be a three-letter code")
        object.__setattr__(self, "currency", currency)
        if not isinstance(self.actual_version, int) or isinstance(self.actual_version, bool) or self.actual_version < 0:
            raise ValueError("actual_version must be a non-negative integer")
        _aware(self.calculated_at, "calculated_at")
        metrics = tuple(self.metrics)
        if not metrics or any(not isinstance(metric, MetricVariance) for metric in metrics):
            raise TypeError("metrics must contain MetricVariance values")
        object.__setattr__(self, "metrics", metrics)


def _unavailable(metric: str, availability: VarianceAvailability, reason: str, *, unit: str = "money") -> MetricVariance:
    return MetricVariance(metric, None, None, None, None, None, availability, unit, reason)


def _metric(metric: str, estimated: Decimal, actual: Decimal, *, unit: str = "money") -> MetricVariance:
    difference = actual - estimated
    if unit == "percentage_points":
        return MetricVariance(
            metric, estimated, actual, difference, abs(difference), None,
            VarianceAvailability.COMPARABLE, unit,
        )
    if estimated == 0:
        return MetricVariance(
            metric, estimated, actual, difference, abs(difference), None,
            VarianceAvailability.PERCENTAGE_UNDEFINED, unit,
            "percentage difference is undefined for a zero estimate",
        )
    return MetricVariance(
        metric, estimated, actual, difference, abs(difference),
        difference / abs(estimated),
        VarianceAvailability.COMPARABLE, unit,
    )


def calculate_economics_variance(
    estimated: EstimatedEconomicsSnapshot,
    actual: ActualEconomics,
) -> EconomicsVariance:
    """Pure comparison of an immutable estimate baseline and actual ledger."""
    if estimated.opportunity_id != actual.opportunity_id:
        raise ValueError("estimate and actual opportunity_id must match")

    metric_names = (
        "purchase_price", "shipping_cost", "sale_price", "marketplace_fee",
        "payment_fee", "fixed_fee", "profit", "roi",
    )
    if actual.status is not ActualEconomicsStatus.SETTLED:
        metrics = tuple(
            _unavailable(
                name, VarianceAvailability.ACTUAL_INCOMPLETE,
                "actual economics must be settled",
                unit="percentage_points" if name == "roi" else "money",
            )
            for name in metric_names
        )
    elif estimated.currency != actual.currency:
        metrics = tuple(
            _unavailable(
                name, VarianceAvailability.CURRENCY_MISMATCH,
                "estimate and actual currencies differ",
                unit="percentage_points" if name == "roi" else "money",
            )
            for name in metric_names
        )
    else:
        metrics_list = [
            _metric("purchase_price", estimated.purchase_price, actual.purchase_price),
            _metric("shipping_cost", estimated.shipping_cost, actual.shipping_cost),
            _metric("sale_price", estimated.expected_sale_price, actual.sale_price),
            _metric("marketplace_fee", estimated.marketplace_fee, actual.marketplace_fee),
            _metric("payment_fee", estimated.payment_fee, actual.payment_fee),
            _metric("fixed_fee", estimated.fixed_fee, actual.fixed_fee),
        ]
        comparable_scope = all(
            value == 0
            for value in (estimated.tax_cost, estimated.other_cost, estimated.duty_cost)
        )
        if comparable_scope:
            metrics_list.extend((
                _metric("profit", estimated.expected_profit, actual.calculate_actual_profit()),
                _metric("roi", estimated.expected_roi, actual.calculate_actual_roi(), unit="percentage_points"),
            ))
        else:
            reason = "estimated and actual profit cost scopes differ"
            metrics_list.extend((
                _unavailable("profit", VarianceAvailability.COST_SCOPE_MISMATCH, reason),
                _unavailable("roi", VarianceAvailability.COST_SCOPE_MISMATCH, reason, unit="percentage_points"),
            ))
        metrics = tuple(metrics_list)

    return EconomicsVariance(
        opportunity_id=estimated.opportunity_id,
        estimate_snapshot_id=estimated.snapshot_id,
        actual_version=actual.version,
        currency=estimated.currency,
        calculation_version=estimated.calculation_version,
        variance_formula_version=estimated.variance_formula_version,
        calculated_at=actual.updated_at,
        metrics=metrics,
    )
