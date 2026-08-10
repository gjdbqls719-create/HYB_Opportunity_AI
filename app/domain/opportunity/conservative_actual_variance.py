"""Immutable Conservative-to-Actual economics variance v2 authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Context, Decimal, ROUND_HALF_EVEN, localcontext
from enum import StrEnum
import hashlib
import json

from app.domain.capital import (
    ActualOutcomeInventoryResolution,
    ActualOutcomeSaleWindow,
    OwnedInventoryProductKey,
)
from app.domain.decision_engine import OpportunityIdentity


CONSERVATIVE_ACTUAL_VARIANCE_SCHEMA_VERSION = "conservative-actual-variance-v2"
CONSERVATIVE_ACTUAL_VARIANCE_SOURCE_MANIFEST_SCHEMA_VERSION = (
    "conservative-actual-variance-source-manifest-v2"
)
CONSERVATIVE_ACTUAL_VARIANCE_POLICY_NAME = "conservative-actual-variance"
CONSERVATIVE_ACTUAL_VARIANCE_POLICY_VERSION = "2.0.0"
CONSERVATIVE_ACTUAL_VARIANCE_DECIMAL_PRECISION = 34
CONSERVATIVE_ACTUAL_VARIANCE_ROUNDING = ROUND_HALF_EVEN


class VarianceComparisonState(StrEnum):
    COMPARABLE = "comparable"
    PARTIALLY_COMPARABLE = "partially_comparable"
    NOT_COMPARABLE = "not_comparable"


class VarianceCalibrationEligibility(StrEnum):
    ELIGIBLE = "eligible"
    PROVISIONAL = "provisional"
    INELIGIBLE = "ineligible"


class VarianceMetricComparability(StrEnum):
    COMPARABLE = "comparable"
    UNAVAILABLE = "unavailable"
    UNMODELED_IN_PREDICTION = "unmodeled_in_prediction"
    NO_ACTUAL_EQUIVALENT = "no_actual_equivalent"
    SCOPE_MISMATCH = "scope_mismatch"
    NOT_APPLICABLE = "not_applicable"


class VarianceFavorability(StrEnum):
    FAVORABLE = "favorable"
    UNFAVORABLE = "unfavorable"
    NEUTRAL = "neutral"
    UNAVAILABLE = "unavailable"


class VarianceMetricDirection(StrEnum):
    COST = "cost"
    BENEFIT = "benefit"


class VarianceMetricName(StrEnum):
    ACQUISITION_COST_PER_UNIT = "acquisition_cost_per_unit"
    GROSS_SALE_PRICE_PER_SOLD_UNIT = "gross_sale_price_per_sold_unit"
    MARKETPLACE_FEE_PER_SOLD_UNIT = "marketplace_fee_per_sold_unit"
    PAYMENT_FEE_PER_SOLD_UNIT = "payment_fee_per_sold_unit"
    FIXED_FEE_PER_SOLD_UNIT = "fixed_fee_per_sold_unit"
    PROFIT = "profit"
    MARGIN = "margin"
    ACQUISITION_ROI = "acquisition_roi"


class VarianceCalibrationReason(StrEnum):
    ACTUAL_OUTCOME_PARTIAL = "actual_outcome_partial"
    ZERO_SALES_SCOPE = "zero_sales_scope"
    PREDICTION_AFTER_EXECUTION = "prediction_after_execution"
    CORE_METRIC_UNAVAILABLE = "core_metric_unavailable"
    ACTUAL_ONLY_COSTS_PRESENT = "actual_only_costs_present"
    REMAINING_INVENTORY_EXPOSURE = "remaining_inventory_exposure"
    UNRECEIVED_EXPOSURE = "unreceived_exposure"
    SOURCE_SCOPE_MISMATCH = "source_scope_mismatch"


CALIBRATION_REASON_ORDER = tuple(VarianceCalibrationReason)
CORE_METRIC_ORDER = tuple(VarianceMetricName)
ACQUISITION_COMPONENT_ORDER = (
    "acquisition_unit_purchase",
    "acquisition_supplier_side_shipping",
    "acquisition_international_freight",
    "acquisition_domestic_inbound",
)


def variance_decimal_context() -> Context:
    return Context(
        prec=CONSERVATIVE_ACTUAL_VARIANCE_DECIMAL_PRECISION,
        rounding=CONSERVATIVE_ACTUAL_VARIANCE_ROUNDING,
    )


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


def _decimal(
    value: Decimal | None,
    name: str,
    *,
    non_negative: bool = False,
) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal or None")
    if non_negative and value < 0:
        raise ValueError(f"{name} must be non-negative")
    return value


def _fingerprint(value: str, name: str) -> str:
    result = _text(value, name).lower()
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise ValueError(f"{name} must be SHA-256 text")
    return result


def _string_tuple(value: tuple[str, ...], name: str, *, non_empty: bool = False) -> tuple[str, ...]:
    if not isinstance(value, tuple) or (non_empty and not value):
        raise ValueError(f"{name} must be {'a non-empty ' if non_empty else ''}tuple")
    result = tuple(_text(item, name) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must be unique")
    return result


def expected_favorability(
    direction: VarianceMetricDirection,
    variance: Decimal,
) -> VarianceFavorability:
    direction = VarianceMetricDirection(direction)
    _decimal(variance, "variance")
    if variance == 0:
        return VarianceFavorability.NEUTRAL
    favorable = variance < 0 if direction is VarianceMetricDirection.COST else variance > 0
    return VarianceFavorability.FAVORABLE if favorable else VarianceFavorability.UNFAVORABLE


@dataclass(frozen=True, slots=True)
class ConservativeActualVarianceMetric:
    metric_name: str
    direction: VarianceMetricDirection
    comparability: VarianceMetricComparability
    predicted_value: Decimal | None
    actual_value: Decimal | None
    variance: Decimal | None
    relative_variance_percent: Decimal | None
    variance_percentage_points: Decimal | None
    favorability: VarianceFavorability
    unit: str
    currency: str | None
    reason_codes: tuple[str, ...] = ()
    predicted_scope_total: Decimal | None = None
    actual_scope_total: Decimal | None = None
    scope_total_variance: Decimal | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "metric_name", _text(self.metric_name, "metric_name"))
        direction = VarianceMetricDirection(self.direction)
        comparability = VarianceMetricComparability(self.comparability)
        favorability = VarianceFavorability(self.favorability)
        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "comparability", comparability)
        object.__setattr__(self, "favorability", favorability)
        object.__setattr__(self, "unit", _text(self.unit, "unit"))
        if self.currency is not None:
            currency = _text(self.currency, "currency").upper()
            if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
                raise ValueError("currency must be a three-letter code")
            object.__setattr__(self, "currency", currency)
        for name in (
            "predicted_value", "actual_value", "variance",
            "relative_variance_percent", "variance_percentage_points",
            "predicted_scope_total", "actual_scope_total", "scope_total_variance",
        ):
            _decimal(getattr(self, name), name)
        reasons = _string_tuple(self.reason_codes, "reason_codes")
        object.__setattr__(self, "reason_codes", reasons)
        is_ratio = self.unit == "percentage_points"
        is_profit = self.metric_name == VarianceMetricName.PROFIT.value
        if comparability is VarianceMetricComparability.COMPARABLE:
            if self.predicted_value is None or self.actual_value is None or self.variance is None:
                raise ValueError("COMPARABLE metric requires predicted, actual, and variance")
            with localcontext(variance_decimal_context()):
                expected = self.actual_value - self.predicted_value
                relative = (
                    None
                    if is_ratio or self.predicted_value == 0
                    else expected / abs(self.predicted_value) * Decimal("100")
                )
            if self.variance != expected:
                raise ValueError("metric variance arithmetic mismatch")
            if is_ratio:
                if self.variance_percentage_points != expected or self.relative_variance_percent is not None:
                    raise ValueError("ratio metric percentage-point contract differs")
            elif self.variance_percentage_points is not None or self.relative_variance_percent != relative:
                raise ValueError("money metric relative variance contract differs")
            if favorability is not expected_favorability(direction, expected):
                raise ValueError("metric favorability differs from direction")
            if is_profit:
                if any(value is None for value in (
                    self.predicted_scope_total,
                    self.actual_scope_total,
                    self.scope_total_variance,
                )):
                    raise ValueError("comparable profit requires sold-scope totals")
                if self.scope_total_variance != self.actual_scope_total - self.predicted_scope_total:  # type: ignore[operator]
                    raise ValueError("profit scope-total variance mismatch")
            elif any(value is not None for value in (
                self.predicted_scope_total,
                self.actual_scope_total,
                self.scope_total_variance,
            )):
                raise ValueError("only profit metric may carry sold-scope totals")
        else:
            if any(value is not None for value in (
                self.variance,
                self.relative_variance_percent,
                self.variance_percentage_points,
                self.predicted_scope_total,
                self.actual_scope_total,
                self.scope_total_variance,
            )):
                raise ValueError("non-comparable metric cannot carry derived variance")
            if favorability is not VarianceFavorability.UNAVAILABLE:
                raise ValueError("non-comparable metric favorability must be unavailable")
            if not reasons:
                raise ValueError("non-comparable metric requires reason codes")


@dataclass(frozen=True, slots=True)
class ConservativeActualVarianceContributor:
    category: str
    amount: Decimal
    currency: str
    classification: VarianceMetricComparability
    source_references: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "category", _text(self.category, "category"))
        _decimal(self.amount, "amount", non_negative=True)
        currency = _text(self.currency, "currency").upper()
        if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
            raise ValueError("currency must be a three-letter code")
        object.__setattr__(self, "currency", currency)
        classification = VarianceMetricComparability(self.classification)
        if classification is not VarianceMetricComparability.UNMODELED_IN_PREDICTION:
            raise ValueError("actual-only contributor classification differs")
        object.__setattr__(self, "classification", classification)
        object.__setattr__(
            self,
            "source_references",
            _string_tuple(self.source_references, "source_references", non_empty=True),
        )


@dataclass(frozen=True, slots=True)
class ConservativeActualPredictedContext:
    category: str
    predicted_value: Decimal
    currency: str
    classification: VarianceMetricComparability
    source_reference: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "category", _text(self.category, "category"))
        _decimal(self.predicted_value, "predicted_value", non_negative=True)
        currency = _text(self.currency, "currency").upper()
        if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
            raise ValueError("currency must be a three-letter code")
        object.__setattr__(self, "currency", currency)
        classification = VarianceMetricComparability(self.classification)
        if classification is not VarianceMetricComparability.NO_ACTUAL_EQUIVALENT:
            raise ValueError("predicted-only context classification differs")
        object.__setattr__(self, "classification", classification)
        object.__setattr__(self, "source_reference", _text(self.source_reference, "source_reference"))


@dataclass(frozen=True, slots=True)
class ConservativeActualExposureContext:
    remaining_sellable_quantity: int
    remaining_inventory_cost_basis: Decimal
    unreceived_quantity: int
    unreceived_acquisition_basis: Decimal
    damaged_quantity: int
    damaged_acquisition_loss: Decimal
    returned_quantity: int
    inventory_resolution: ActualOutcomeInventoryResolution
    quantity_unit: str
    currency: str

    def __post_init__(self) -> None:
        for name in (
            "remaining_sellable_quantity", "unreceived_quantity",
            "damaged_quantity", "returned_quantity",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        for name in (
            "remaining_inventory_cost_basis",
            "unreceived_acquisition_basis",
            "damaged_acquisition_loss",
        ):
            _decimal(getattr(self, name), name, non_negative=True)
        object.__setattr__(
            self,
            "inventory_resolution",
            ActualOutcomeInventoryResolution(self.inventory_resolution),
        )
        object.__setattr__(self, "quantity_unit", _text(self.quantity_unit, "quantity_unit"))
        currency = _text(self.currency, "currency").upper()
        if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
            raise ValueError("currency must be a three-letter code")
        object.__setattr__(self, "currency", currency)


@dataclass(frozen=True, slots=True)
class ConservativeActualScenarioContext:
    scenario_name: str
    scenario_version: str
    sale_price_factor: Decimal
    assumption_owner: str
    conservative_policy_name: str
    conservative_policy_version: str

    def __post_init__(self) -> None:
        for name in (
            "scenario_name", "scenario_version", "assumption_owner",
            "conservative_policy_name", "conservative_policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        factor = _decimal(self.sale_price_factor, "sale_price_factor")
        if factor is None or not Decimal("0") < factor <= Decimal("1"):
            raise ValueError("sale_price_factor must be greater than zero and at most one")


@dataclass(frozen=True, slots=True)
class ConservativeActualScopeContext:
    sold_quantity: int
    executed_quantity: int
    inventory_resolution: ActualOutcomeInventoryResolution
    sale_windows: tuple[ActualOutcomeSaleWindow, ...]
    remaining_sellable_quantity: int
    damaged_quantity: int
    returned_quantity: int
    unreceived_quantity: int
    quantity_unit: str

    def __post_init__(self) -> None:
        for name in (
            "sold_quantity", "executed_quantity", "remaining_sellable_quantity",
            "damaged_quantity", "returned_quantity", "unreceived_quantity",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.executed_quantity <= 0:
            raise ValueError("executed_quantity must be positive")
        object.__setattr__(
            self,
            "inventory_resolution",
            ActualOutcomeInventoryResolution(self.inventory_resolution),
        )
        if not isinstance(self.sale_windows, tuple) or not self.sale_windows or any(
            not isinstance(value, ActualOutcomeSaleWindow) for value in self.sale_windows
        ):
            raise ValueError("sale_windows must be a non-empty window tuple")
        object.__setattr__(self, "quantity_unit", _text(self.quantity_unit, "quantity_unit"))


@dataclass(frozen=True, slots=True)
class ConservativeActualVarianceSourceManifest:
    opportunity_identity: OpportunityIdentity
    product_key: OwnedInventoryProductKey
    conservative_result_id: str
    source_composition_id: str
    acquisition_normalization_id: str
    landed_cost_composition_id: str
    sourcing_binding_id: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    quote_id: str
    quote_revision: int
    actual_outcome_id: str
    purchase_execution_record_id: str
    actual_acquisition_settlement_id: str
    actual_sale_settlement_ids: tuple[str, ...]
    currency: str
    conservative_policy_name: str
    conservative_policy_version: str
    conservative_schema_version: str
    actual_policy_name: str
    actual_policy_version: str
    actual_schema_version: str
    conservative_calculated_at: datetime
    purchase_executed_at: datetime
    conservative_source_snapshot: str
    actual_source_snapshot: str
    conservative_source_fingerprint: str
    actual_source_fingerprint: str
    source_pair_fingerprint: str
    schema_version: str = CONSERVATIVE_ACTUAL_VARIANCE_SOURCE_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.product_key, OwnedInventoryProductKey):
            raise TypeError("product_key must be OwnedInventoryProductKey")
        if self.product_key.opportunity_identity != self.opportunity_identity:
            raise ValueError("product key Opportunity differs")
        for name in (
            "conservative_result_id", "source_composition_id",
            "acquisition_normalization_id", "landed_cost_composition_id",
            "sourcing_binding_id", "sourcing_admission_id", "quote_id",
            "actual_outcome_id", "purchase_execution_record_id",
            "actual_acquisition_settlement_id", "conservative_policy_name",
            "conservative_policy_version", "conservative_schema_version",
            "actual_policy_name", "actual_policy_version", "actual_schema_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("sourcing_admission_revision", "quote_revision"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")
        object.__setattr__(
            self,
            "actual_sale_settlement_ids",
            _string_tuple(
                self.actual_sale_settlement_ids,
                "actual_sale_settlement_ids",
                non_empty=True,
            ),
        )
        currency = _text(self.currency, "currency").upper()
        if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
            raise ValueError("currency must be a three-letter code")
        object.__setattr__(self, "currency", currency)
        object.__setattr__(
            self,
            "conservative_calculated_at",
            _aware(self.conservative_calculated_at, "conservative_calculated_at"),
        )
        object.__setattr__(
            self,
            "purchase_executed_at",
            _aware(self.purchase_executed_at, "purchase_executed_at"),
        )
        for name in ("conservative_source_snapshot", "actual_source_snapshot"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in (
            "conservative_source_fingerprint",
            "actual_source_fingerprint",
            "source_pair_fingerprint",
        ):
            object.__setattr__(self, name, _fingerprint(getattr(self, name), name))
        if hashlib.sha256(self.conservative_source_snapshot.encode("utf-8")).hexdigest() != (
            self.conservative_source_fingerprint
        ):
            raise ValueError("Conservative source snapshot fingerprint differs")
        if hashlib.sha256(self.actual_source_snapshot.encode("utf-8")).hexdigest() != (
            self.actual_source_fingerprint
        ):
            raise ValueError("Actual source snapshot fingerprint differs")
        expected_pair = hashlib.sha256(
            json.dumps(
                {
                    "actual_outcome_id": self.actual_outcome_id,
                    "conservative_result_id": self.conservative_result_id,
                    "policy_name": CONSERVATIVE_ACTUAL_VARIANCE_POLICY_NAME,
                    "policy_version": CONSERVATIVE_ACTUAL_VARIANCE_POLICY_VERSION,
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()
        if self.source_pair_fingerprint != expected_pair:
            raise ValueError("Variance source-pair fingerprint differs")
        if self.schema_version != CONSERVATIVE_ACTUAL_VARIANCE_SOURCE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported Variance v2 source manifest schema")


@dataclass(frozen=True, slots=True)
class ConservativeActualVariance:
    variance_id: str
    source_manifest: ConservativeActualVarianceSourceManifest
    comparison_state: VarianceComparisonState
    calibration_eligibility: VarianceCalibrationEligibility
    calibration_reasons: tuple[VarianceCalibrationReason, ...]
    core_metrics: tuple[ConservativeActualVarianceMetric, ...]
    acquisition_component_metrics: tuple[ConservativeActualVarianceMetric, ...]
    actual_only_contributors: tuple[ConservativeActualVarianceContributor, ...]
    predicted_only_context: tuple[ConservativeActualPredictedContext, ...]
    exposure_context: ConservativeActualExposureContext
    scenario_context: ConservativeActualScenarioContext
    actual_scope_context: ConservativeActualScopeContext
    requested_at: datetime
    calculated_at: datetime
    committed_at: datetime
    policy_name: str = CONSERVATIVE_ACTUAL_VARIANCE_POLICY_NAME
    policy_version: str = CONSERVATIVE_ACTUAL_VARIANCE_POLICY_VERSION
    policy_precision: int = CONSERVATIVE_ACTUAL_VARIANCE_DECIMAL_PRECISION
    policy_rounding: str = CONSERVATIVE_ACTUAL_VARIANCE_ROUNDING
    schema_version: str = CONSERVATIVE_ACTUAL_VARIANCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "variance_id", _text(self.variance_id, "variance_id"))
        if not isinstance(self.source_manifest, ConservativeActualVarianceSourceManifest):
            raise TypeError("source_manifest must be ConservativeActualVarianceSourceManifest")
        state = VarianceComparisonState(self.comparison_state)
        eligibility = VarianceCalibrationEligibility(self.calibration_eligibility)
        object.__setattr__(self, "comparison_state", state)
        object.__setattr__(self, "calibration_eligibility", eligibility)
        reasons = tuple(VarianceCalibrationReason(value) for value in self.calibration_reasons)
        if len(set(reasons)) != len(reasons) or tuple(
            sorted(reasons, key=CALIBRATION_REASON_ORDER.index)
        ) != reasons:
            raise ValueError("calibration reasons must be unique and ordered")
        object.__setattr__(self, "calibration_reasons", reasons)
        if not isinstance(self.core_metrics, tuple) or any(
            not isinstance(value, ConservativeActualVarianceMetric) for value in self.core_metrics
        ):
            raise TypeError("core_metrics must contain variance metrics")
        if tuple(value.metric_name for value in self.core_metrics) != tuple(
            value.value for value in CORE_METRIC_ORDER
        ):
            raise ValueError("core metrics must preserve exact v2 order")
        if not isinstance(self.acquisition_component_metrics, tuple) or any(
            not isinstance(value, ConservativeActualVarianceMetric)
            for value in self.acquisition_component_metrics
        ):
            raise TypeError("acquisition component metrics must contain variance metrics")
        if tuple(value.metric_name for value in self.acquisition_component_metrics) != ACQUISITION_COMPONENT_ORDER:
            raise ValueError("acquisition component metrics must preserve exact order")
        for name, expected in (
            ("actual_only_contributors", ConservativeActualVarianceContributor),
            ("predicted_only_context", ConservativeActualPredictedContext),
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple) or any(not isinstance(value, expected) for value in values):
                raise TypeError(f"{name} has unsupported values")
            categories = tuple(value.category for value in values)
            if len(set(categories)) != len(categories):
                raise ValueError(f"{name} categories must be unique")
        if not isinstance(self.exposure_context, ConservativeActualExposureContext):
            raise TypeError("exposure_context has unsupported type")
        if not isinstance(self.scenario_context, ConservativeActualScenarioContext):
            raise TypeError("scenario_context has unsupported type")
        if not isinstance(self.actual_scope_context, ConservativeActualScopeContext):
            raise TypeError("actual_scope_context has unsupported type")
        comparable_count = sum(
            value.comparability is VarianceMetricComparability.COMPARABLE
            for value in self.core_metrics
        )
        expected_state = (
            VarianceComparisonState.COMPARABLE
            if comparable_count == len(self.core_metrics)
            else VarianceComparisonState.PARTIALLY_COMPARABLE
            if comparable_count
            else VarianceComparisonState.NOT_COMPARABLE
        )
        if state is not expected_state:
            raise ValueError("comparison state differs from core metrics")
        manifest = self.source_manifest
        expected_eligibility = (
            VarianceCalibrationEligibility.INELIGIBLE
            if manifest.conservative_calculated_at >= manifest.purchase_executed_at
            or state is VarianceComparisonState.NOT_COMPARABLE
            else VarianceCalibrationEligibility.PROVISIONAL
            if self.actual_scope_context.inventory_resolution
            is ActualOutcomeInventoryResolution.PARTIAL
            else VarianceCalibrationEligibility.ELIGIBLE
        )
        if eligibility is not expected_eligibility:
            raise ValueError("calibration eligibility differs from source state")
        for name in ("requested_at", "calculated_at", "committed_at"):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if self.calculated_at > self.committed_at:
            raise ValueError("committed_at cannot precede calculated_at")
        if (
            self.policy_name,
            self.policy_version,
            self.policy_precision,
            self.policy_rounding,
            self.schema_version,
        ) != (
            CONSERVATIVE_ACTUAL_VARIANCE_POLICY_NAME,
            CONSERVATIVE_ACTUAL_VARIANCE_POLICY_VERSION,
            CONSERVATIVE_ACTUAL_VARIANCE_DECIMAL_PRECISION,
            CONSERVATIVE_ACTUAL_VARIANCE_ROUNDING,
            CONSERVATIVE_ACTUAL_VARIANCE_SCHEMA_VERSION,
        ):
            raise ValueError("unsupported Variance v2 policy or schema")


__all__ = [
    name
    for name in globals()
    if name.startswith(("ConservativeActual", "Variance", "CONSERVATIVE_ACTUAL"))
    or name in {
        "ACQUISITION_COMPONENT_ORDER",
        "CALIBRATION_REASON_ORDER",
        "CORE_METRIC_ORDER",
        "expected_favorability",
        "variance_decimal_context",
    }
]
