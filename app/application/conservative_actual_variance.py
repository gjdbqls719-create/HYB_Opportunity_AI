"""Application owner for immutable Conservative-to-Actual variance v2."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from enum import Enum
import hashlib
import json
from typing import Callable, Protocol

from app.domain.capital import (
    ACTUAL_OUTCOME_POLICY_NAME,
    ACTUAL_OUTCOME_POLICY_VERSION,
    ActualAcquisitionCostCategory,
    ActualOutcome,
    ActualOutcomeInventoryResolution,
    ActualOutcomeState,
    ActualSaleMonetaryCategory,
    PlannedAcquisitionCapitalRequirement,
)
from app.domain.opportunity.conservative_actual_variance import (
    ACQUISITION_COMPONENT_ORDER,
    CONSERVATIVE_ACTUAL_VARIANCE_POLICY_NAME,
    CONSERVATIVE_ACTUAL_VARIANCE_POLICY_VERSION,
    CONSERVATIVE_ACTUAL_VARIANCE_SCHEMA_VERSION,
    ConservativeActualExposureContext,
    ConservativeActualPredictedContext,
    ConservativeActualScenarioContext,
    ConservativeActualScopeContext,
    ConservativeActualVariance,
    ConservativeActualVarianceContributor,
    ConservativeActualVarianceMetric,
    ConservativeActualVarianceSourceManifest,
    VarianceCalibrationEligibility,
    VarianceCalibrationReason,
    VarianceComparisonState,
    VarianceFavorability,
    VarianceMetricComparability,
    VarianceMetricDirection,
    VarianceMetricName,
    expected_favorability,
    variance_decimal_context,
)
from app.domain.opportunity.conservative_economics import (
    CONSERVATIVE_ECONOMICS_POLICY_NAME,
    CONSERVATIVE_ECONOMICS_POLICY_VERSION,
    ConservativeEconomicsResult,
    ConservativeEconomicsStatus,
)
from app.domain.opportunity.economics_source_composition import EconomicsSourceComposition
from app.domain.sourcing import (
    AcquisitionCostNormalization,
    FounderSourcingAdmission,
    LandedCostComponentKind,
    LandedCostComposition,
    SourcingEconomicsBinding,
)


CONSERVATIVE_ACTUAL_VARIANCE_COMMAND_SCHEMA_VERSION = (
    "conservative-actual-variance-command-v2"
)
CONSERVATIVE_ACTUAL_VARIANCE_RECEIPT_SCHEMA_VERSION = (
    "conservative-actual-variance-receipt-v2"
)


class ConservativeActualVarianceError(RuntimeError): pass
class ConservativeActualVarianceSourceNotFoundError(ConservativeActualVarianceError): pass
class ConservativeActualVarianceSourceConflictError(ConservativeActualVarianceError): pass
class ConservativeActualVarianceOpportunityConflictError(ConservativeActualVarianceError): pass
class ConservativeActualVariancePolicyError(ConservativeActualVarianceError): pass
class ConservativeActualVarianceReplayConflictError(ConservativeActualVarianceError): pass
class ConservativeActualVarianceSourceIntegrityError(ConservativeActualVarianceError): pass


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


def _canonical(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _canonical(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _snapshot(value: object) -> str:
    return json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _fingerprint(value: object) -> str:
    return _hash(_snapshot(value))


def _fingerprint_text(value: str) -> str:
    result = _text(value, "fingerprint").lower()
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise ValueError("fingerprint must be SHA-256 text")
    return result


@dataclass(frozen=True, slots=True)
class CalculateConservativeActualVarianceCommand:
    command_id: str
    opportunity_id: str
    conservative_economics_result_id: str
    actual_outcome_id: str
    requested_at: datetime
    policy_name: str = CONSERVATIVE_ACTUAL_VARIANCE_POLICY_NAME
    policy_version: str = CONSERVATIVE_ACTUAL_VARIANCE_POLICY_VERSION
    schema_version: str = CONSERVATIVE_ACTUAL_VARIANCE_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "command_id", "opportunity_id", "conservative_economics_result_id",
            "actual_outcome_id", "policy_name", "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        if (
            self.policy_name,
            self.policy_version,
            self.schema_version,
        ) != (
            CONSERVATIVE_ACTUAL_VARIANCE_POLICY_NAME,
            CONSERVATIVE_ACTUAL_VARIANCE_POLICY_VERSION,
            CONSERVATIVE_ACTUAL_VARIANCE_COMMAND_SCHEMA_VERSION,
        ):
            raise ValueError("unsupported Variance v2 command policy or schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class ConservativeActualVarianceReceipt:
    command_id: str
    variance_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = CONSERVATIVE_ACTUAL_VARIANCE_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "variance_id", _text(self.variance_id, "variance_id"))
        object.__setattr__(
            self,
            "command_fingerprint",
            _fingerprint_text(self.command_fingerprint),
        )
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version != CONSERVATIVE_ACTUAL_VARIANCE_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported Variance v2 receipt schema")


@dataclass(frozen=True, slots=True)
class ConservativeActualVariancePublication:
    variance: ConservativeActualVariance
    receipt: ConservativeActualVarianceReceipt
    replayed: bool
    aliased: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.variance, ConservativeActualVariance):
            raise TypeError("variance has unsupported type")
        if not isinstance(self.receipt, ConservativeActualVarianceReceipt):
            raise TypeError("receipt has unsupported type")
        if self.variance.variance_id != self.receipt.variance_id:
            raise ValueError("receipt must reference Variance v2")
        if not isinstance(self.replayed, bool) or not isinstance(self.aliased, bool):
            raise TypeError("publication flags must be bool")


class ConservativeActualVarianceRepository(Protocol):
    def validate_replay(self, command_id: str, fingerprint: str) -> ConservativeActualVariancePublication | None: ...
    def get_conservative_result(self, result_id: str) -> ConservativeEconomicsResult | None: ...
    def get_actual_outcome(self, outcome_id: str) -> ActualOutcome | None: ...
    def get_source_composition(self, composition_id: str) -> EconomicsSourceComposition | None: ...
    def get_acquisition_normalization(self, normalization_id: str) -> AcquisitionCostNormalization | None: ...
    def get_landed_cost_composition(self, composition_id: str) -> LandedCostComposition | None: ...
    def get_sourcing_binding(self, binding_id: str) -> SourcingEconomicsBinding | None: ...
    def get_sourcing_admission(self, admission_id: str, revision: int) -> FounderSourcingAdmission | None: ...
    def get_capital_requirement(self, requirement_id: str) -> PlannedAcquisitionCapitalRequirement | None: ...
    def find_by_scope(self, scope_fingerprint: str) -> ConservativeActualVariance | None: ...
    def save(self, command, variance, receipt, scope_fingerprint: str) -> ConservativeActualVariancePublication: ...


def conservative_actual_variance_scope_fingerprint(
    conservative_result_id: str,
    actual_outcome_id: str,
) -> str:
    return _fingerprint({
        "conservative_result_id": _text(conservative_result_id, "conservative_result_id"),
        "actual_outcome_id": _text(actual_outcome_id, "actual_outcome_id"),
        "policy_name": CONSERVATIVE_ACTUAL_VARIANCE_POLICY_NAME,
        "policy_version": CONSERVATIVE_ACTUAL_VARIANCE_POLICY_VERSION,
    })


def _json_object(snapshot: str, name: str) -> dict[str, object]:
    try:
        value = json.loads(snapshot)
    except (TypeError, json.JSONDecodeError) as error:
        raise ConservativeActualVarianceSourceIntegrityError(f"{name} is malformed") from error
    if not isinstance(value, dict):
        raise ConservativeActualVarianceSourceIntegrityError(f"{name} must be an object")
    return value


def _required_object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ConservativeActualVarianceSourceIntegrityError(f"{name} must be an object")
    return value


def _required_list(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ConservativeActualVarianceSourceIntegrityError(f"{name} must be a list")
    return value


def _required_snapshot_text(value: object, name: str) -> str:
    try:
        return _text(value, name)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise ConservativeActualVarianceSourceIntegrityError(f"{name} is malformed") from error


def _purchase_source(outcome: ActualOutcome) -> dict[str, object]:
    acquisition = _json_object(
        outcome.source_manifest.acquisition_source_snapshot,
        "Actual Outcome acquisition snapshot",
    )
    return _required_object(acquisition.get("source_manifest"), "acquisition source manifest")


def _sale_availability(outcome: ActualOutcome, category: ActualSaleMonetaryCategory) -> tuple[str, ...]:
    values: list[str] = []
    for snapshot in outcome.source_manifest.sale_source_snapshots:
        sale = _json_object(snapshot, "Actual Outcome sale snapshot")
        facts = _required_list(sale.get("fixed_monetary_facts"), "sale monetary facts")
        matches = [
            _required_object(value, "sale monetary fact")
            for value in facts
            if isinstance(value, dict) and value.get("category") == category.value
        ]
        if len(matches) != 1:
            raise ConservativeActualVarianceSourceIntegrityError(
                f"sale category {category.value} cardinality differs"
            )
        availability = _required_snapshot_text(
            matches[0].get("availability"), "sale fact availability"
        )
        if availability not in {"known", "not_applicable"}:
            raise ConservativeActualVarianceSourceIntegrityError(
                "CALCULABLE Actual Outcome contains unresolved sale availability"
            )
        values.append(availability)
    return tuple(values)


def _comparable_metric(
    metric_name: str,
    direction: VarianceMetricDirection,
    predicted: Decimal,
    actual: Decimal,
    *,
    unit: str,
    currency: str | None,
    reason_codes: tuple[str, ...] = (),
    predicted_scope_total: Decimal | None = None,
    actual_scope_total: Decimal | None = None,
) -> ConservativeActualVarianceMetric:
    with localcontext(variance_decimal_context()):
        difference = actual - predicted
        relative = (
            None
            if unit == "percentage_points" or predicted == 0
            else difference / abs(predicted) * Decimal("100")
        )
        total_difference = (
            None
            if predicted_scope_total is None or actual_scope_total is None
            else actual_scope_total - predicted_scope_total
        )
    return ConservativeActualVarianceMetric(
        metric_name=metric_name,
        direction=direction,
        comparability=VarianceMetricComparability.COMPARABLE,
        predicted_value=predicted,
        actual_value=actual,
        variance=difference,
        relative_variance_percent=relative,
        variance_percentage_points=(difference if unit == "percentage_points" else None),
        favorability=expected_favorability(direction, difference),
        unit=unit,
        currency=currency,
        reason_codes=reason_codes,
        predicted_scope_total=predicted_scope_total,
        actual_scope_total=actual_scope_total,
        scope_total_variance=total_difference,
    )


def _non_comparable_metric(
    metric_name: str,
    direction: VarianceMetricDirection,
    comparability: VarianceMetricComparability,
    *,
    predicted: Decimal | None,
    actual: Decimal | None,
    unit: str,
    currency: str | None,
    reason: str,
) -> ConservativeActualVarianceMetric:
    return ConservativeActualVarianceMetric(
        metric_name=metric_name,
        direction=direction,
        comparability=comparability,
        predicted_value=predicted,
        actual_value=actual,
        variance=None,
        relative_variance_percent=None,
        variance_percentage_points=None,
        favorability=VarianceFavorability.UNAVAILABLE,
        unit=unit,
        currency=currency,
        reason_codes=(reason,),
    )


_ALIGNED_ACQUISITION = (
    ActualAcquisitionCostCategory.UNIT_PURCHASE,
    ActualAcquisitionCostCategory.SUPPLIER_SIDE_SHIPPING,
    ActualAcquisitionCostCategory.INTERNATIONAL_FREIGHT,
    ActualAcquisitionCostCategory.DOMESTIC_INBOUND,
)


class CalculateConservativeActualVariance:
    def __init__(
        self,
        repository: ConservativeActualVarianceRepository,
        *,
        variance_id_generator: Callable[[], str],
        calculated_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        if not all(callable(value) for value in (
            variance_id_generator, calculated_clock, committed_clock
        )):
            raise TypeError("Variance v2 dependencies must be callable")
        self._repository = repository
        self._identity = variance_id_generator
        self._calculated = calculated_clock
        self._committed = committed_clock

    def execute(
        self,
        command: CalculateConservativeActualVarianceCommand,
    ) -> ConservativeActualVariancePublication:
        if not isinstance(command, CalculateConservativeActualVarianceCommand):
            raise TypeError("command must be CalculateConservativeActualVarianceCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        self._validate_policy(command)
        conservative = self._repository.get_conservative_result(
            command.conservative_economics_result_id
        )
        if conservative is None:
            raise ConservativeActualVarianceSourceNotFoundError(
                "exact Conservative Economics result is missing"
            )
        outcome = self._repository.get_actual_outcome(command.actual_outcome_id)
        if outcome is None:
            raise ConservativeActualVarianceSourceNotFoundError(
                "exact Actual Outcome is missing"
            )
        if conservative.status is not ConservativeEconomicsStatus.CALCULABLE:
            raise ConservativeActualVarianceSourceConflictError(
                "Conservative Economics result must be CALCULABLE"
            )
        if outcome.state is not ActualOutcomeState.CALCULABLE:
            raise ConservativeActualVarianceSourceConflictError(
                "Actual Outcome must be CALCULABLE"
            )
        if (
            conservative.policy_name,
            conservative.policy_version,
        ) != (
            CONSERVATIVE_ECONOMICS_POLICY_NAME,
            CONSERVATIVE_ECONOMICS_POLICY_VERSION,
        ) or (outcome.policy_name, outcome.policy_version) != (
            ACTUAL_OUTCOME_POLICY_NAME,
            ACTUAL_OUTCOME_POLICY_VERSION,
        ):
            raise ConservativeActualVariancePolicyError(
                "unsupported Conservative or Actual source policy"
            )
        actual_identity = outcome.source_manifest.product_key.opportunity_identity
        if conservative.opportunity_identity.opportunity_id != command.opportunity_id or (
            actual_identity.opportunity_id != command.opportunity_id
        ):
            raise ConservativeActualVarianceOpportunityConflictError(
                "Variance source differs from route Opportunity"
            )
        if conservative.opportunity_identity != actual_identity:
            raise ConservativeActualVarianceSourceConflictError(
                "Conservative and Actual O2 identity differs"
            )
        if conservative.economics_currency != outcome.source_manifest.currency:
            raise ConservativeActualVarianceSourceConflictError(
                "Conservative and Actual currency differs"
            )
        source = self._required(
            self._repository.get_source_composition(conservative.source_composition_id),
            "exact Economics Source Composition is missing",
        )
        normalization = self._required(
            self._repository.get_acquisition_normalization(source.acquisition_normalization_id),
            "exact Acquisition Cost Normalization is missing",
        )
        landed = self._required(
            self._repository.get_landed_cost_composition(normalization.composition_id),
            "exact Landed Cost Composition is missing",
        )
        binding = self._required(
            self._repository.get_sourcing_binding(landed.binding_reference.binding_id),
            "exact Sourcing Economics Binding is missing",
        )
        reference = binding.source_reference
        admission = self._required(
            self._repository.get_sourcing_admission(
                reference.admission_id, reference.admission_revision
            ),
            "exact Sourcing Admission revision is missing",
        )
        purchase = _purchase_source(outcome)
        requirement_id = _required_snapshot_text(
            purchase.get("capital_requirement_id"), "capital_requirement_id"
        )
        requirement = self._required(
            self._repository.get_capital_requirement(requirement_id),
            "exact Capital Requirement is missing",
        )
        purchase_executed_at = self._snapshot_datetime(
            purchase.get("purchase_executed_at"), "purchase_executed_at"
        )
        self._validate_lineage(
            conservative, outcome, source, normalization, landed, binding,
            admission, requirement, purchase,
        )
        scope_fingerprint = conservative_actual_variance_scope_fingerprint(
            conservative.result_id, outcome.outcome_id
        )
        alias = self._repository.find_by_scope(scope_fingerprint)
        if alias is not None:
            receipt = ConservativeActualVarianceReceipt(
                command.command_id,
                alias.variance_id,
                command.fingerprint,
                _aware(self._committed(), "committed_at"),
            )
            return self._repository.save(command, alias, receipt, scope_fingerprint)
        variance = self._calculate(
            command, conservative, outcome, source, normalization, landed,
            binding, admission, purchase_executed_at, scope_fingerprint,
        )
        receipt = ConservativeActualVarianceReceipt(
            command.command_id,
            variance.variance_id,
            command.fingerprint,
            variance.committed_at,
        )
        return self._repository.save(command, variance, receipt, scope_fingerprint)

    @staticmethod
    def _required(value, message: str):
        if value is None:
            raise ConservativeActualVarianceSourceNotFoundError(message)
        return value

    @staticmethod
    def _snapshot_datetime(value: object, name: str) -> datetime:
        if not isinstance(value, str):
            raise ConservativeActualVarianceSourceIntegrityError(f"{name} is malformed")
        try:
            return _aware(datetime.fromisoformat(value), name)
        except (TypeError, ValueError) as error:
            raise ConservativeActualVarianceSourceIntegrityError(f"{name} is malformed") from error

    @staticmethod
    def _validate_policy(command: CalculateConservativeActualVarianceCommand) -> None:
        if (command.policy_name, command.policy_version) != (
            CONSERVATIVE_ACTUAL_VARIANCE_POLICY_NAME,
            CONSERVATIVE_ACTUAL_VARIANCE_POLICY_VERSION,
        ):
            raise ConservativeActualVariancePolicyError("unsupported Variance v2 policy")

    @staticmethod
    def _validate_lineage(
        conservative,
        outcome,
        source,
        normalization,
        landed,
        binding,
        admission,
        requirement,
        purchase,
    ) -> None:
        identity = conservative.opportunity_identity
        key = outcome.source_manifest.product_key
        admission_identity = admission.selling_product_lineage.opportunity_identity
        product = admission.sourcing_product_identity
        supplier = admission.supplier_identity
        expected_reference = admission.to_economics_source_reference()
        checks = (
            source.opportunity_identity == identity,
            source.composition_id == conservative.source_composition_id,
            source.acquisition_normalization_id == normalization.normalization_id,
            normalization.opportunity_identity == identity,
            normalization.total_per_unit_acquisition_cost == conservative.acquisition_cost_per_unit,
            normalization.target_currency == conservative.economics_currency,
            normalization.composition_id == landed.composition_id,
            landed.opportunity_identity == identity,
            landed.binding_reference == binding.reference,
            binding.opportunity_identity == identity,
            binding.source_reference == expected_reference,
            admission_identity == identity,
            requirement.opportunity_identity == identity,
            requirement.acquisition_normalization_id == normalization.normalization_id,
            requirement.sourcing_binding_id == binding.binding_id,
            requirement.sourcing_admission_id == admission.admission_id,
            requirement.sourcing_admission_revision == admission.revision,
            requirement.quote_id == admission.quote_revision.quote_id,
            requirement.quote_revision == admission.quote_revision.revision,
            requirement.quantity_unit == key.quantity_unit,
            requirement.currency == outcome.source_manifest.currency,
            purchase.get("sourcing_admission_id") == admission.admission_id,
            purchase.get("sourcing_admission_revision") == admission.revision,
            purchase.get("quote_id") == admission.quote_revision.quote_id,
            purchase.get("quote_revision") == admission.quote_revision.revision,
            purchase.get("supplier_id") == supplier.supplier_id,
            purchase.get("source_platform") == supplier.source_platform,
            purchase.get("sourcing_product_id") == product.sourcing_product_id,
            purchase.get("external_product_reference") == product.external_product_reference,
            purchase.get("option_reference") == product.option_reference,
            purchase.get("sku_reference") == product.sku_reference,
            purchase.get("executed_quantity_unit") == key.quantity_unit,
            key.supplier_id == supplier.supplier_id,
            key.source_platform == supplier.source_platform,
            key.sourcing_product_id == product.sourcing_product_id,
            key.external_product_reference == product.external_product_reference,
            key.option_reference == product.option_reference,
            key.sku_reference == product.sku_reference,
        )
        if not all(checks):
            raise ConservativeActualVarianceSourceConflictError(
                "Conservative and Actual exact product/economic lineage differs"
            )

    def _calculate(
        self,
        command,
        conservative,
        outcome,
        source,
        normalization,
        landed,
        binding,
        admission,
        purchase_executed_at,
        scope_fingerprint,
    ) -> ConservativeActualVariance:
        currency = conservative.economics_currency
        sold = outcome.source_manifest.sold_quantity
        actual_allocations = {value.category: value for value in outcome.acquisition_allocations}
        predicted_components = {value.kind: value for value in normalization.components}
        with localcontext(variance_decimal_context()):
            actual_aligned_acquisition = sum(
                (actual_allocations[value].per_executed_unit for value in _ALIGNED_ACQUISITION),
                Decimal("0"),
            )
        acquisition_metric = _comparable_metric(
            VarianceMetricName.ACQUISITION_COST_PER_UNIT.value,
            VarianceMetricDirection.COST,
            conservative.acquisition_cost_per_unit,
            actual_aligned_acquisition,
            unit="money_per_unit",
            currency=currency,
        )
        component_metrics = tuple(
            _comparable_metric(
                name,
                VarianceMetricDirection.COST,
                predicted_components[predicted_kind].normalized_per_unit_amount,
                actual_allocations[actual_kind].per_executed_unit,
                unit="money_per_unit",
                currency=currency,
            )
            for name, predicted_kind, actual_kind in zip(
                ACQUISITION_COMPONENT_ORDER,
                tuple(LandedCostComponentKind),
                _ALIGNED_ACQUISITION,
                strict=True,
            )
        )
        if sold > 0:
            divisor = Decimal(sold)
            sale_components = {value.category: value.amount for value in outcome.sale_components}
            with localcontext(variance_decimal_context()):
                sale_price = outcome.gross_realized_merchandise_revenue / divisor
                marketplace = sale_components[ActualSaleMonetaryCategory.MARKETPLACE_FEE] / divisor
                payment = sale_components[ActualSaleMonetaryCategory.PAYMENT_FEE] / divisor
                fixed = sale_components[ActualSaleMonetaryCategory.FIXED_FEE] / divisor
                actual_profit_unit = outcome.actual_realized_profit / divisor
                predicted_profit_total = conservative.conservative_profit_per_unit * divisor
            payment_availability = _sale_availability(
                outcome, ActualSaleMonetaryCategory.PAYMENT_FEE
            )
            fixed_availability = _sale_availability(
                outcome, ActualSaleMonetaryCategory.FIXED_FEE
            )
            sale_metric = _comparable_metric(
                VarianceMetricName.GROSS_SALE_PRICE_PER_SOLD_UNIT.value,
                VarianceMetricDirection.BENEFIT,
                conservative.conservative_sale_price,
                sale_price,
                unit="money_per_unit",
                currency=currency,
            )
            marketplace_metric = _comparable_metric(
                VarianceMetricName.MARKETPLACE_FEE_PER_SOLD_UNIT.value,
                VarianceMetricDirection.COST,
                conservative.marketplace_fee,
                marketplace,
                unit="money_per_unit",
                currency=currency,
            )
            payment_metric = _comparable_metric(
                VarianceMetricName.PAYMENT_FEE_PER_SOLD_UNIT.value,
                VarianceMetricDirection.COST,
                conservative.payment_fee,
                payment,
                unit="money_per_unit",
                currency=currency,
                reason_codes=("actual_source_not_applicable",)
                if all(value == "not_applicable" for value in payment_availability)
                else (),
            )
            fixed_metric = _comparable_metric(
                VarianceMetricName.FIXED_FEE_PER_SOLD_UNIT.value,
                VarianceMetricDirection.COST,
                conservative.fixed_fee,
                fixed,
                unit="money_per_unit",
                currency=currency,
                reason_codes=("actual_source_not_applicable",)
                if all(value == "not_applicable" for value in fixed_availability)
                else (),
            )
            profit_metric = _comparable_metric(
                VarianceMetricName.PROFIT.value,
                VarianceMetricDirection.BENEFIT,
                conservative.conservative_profit_per_unit,
                actual_profit_unit,
                unit="money_per_unit",
                currency=currency,
                predicted_scope_total=predicted_profit_total,
                actual_scope_total=outcome.actual_realized_profit,
            )
            margin_metric = (
                _comparable_metric(
                    VarianceMetricName.MARGIN.value,
                    VarianceMetricDirection.BENEFIT,
                    conservative.conservative_margin,
                    outcome.actual_margin.value,
                    unit="percentage_points",
                    currency=None,
                )
                if outcome.actual_margin.available
                else _non_comparable_metric(
                    VarianceMetricName.MARGIN.value,
                    VarianceMetricDirection.BENEFIT,
                    VarianceMetricComparability.UNAVAILABLE,
                    predicted=conservative.conservative_margin,
                    actual=None,
                    unit="percentage_points",
                    currency=None,
                    reason="actual_margin_unavailable",
                )
            )
            unmatched = any(
                actual_allocations[category].batch_amount != 0
                for category in (
                    ActualAcquisitionCostCategory.DUTY_CUSTOMS,
                    ActualAcquisitionCostCategory.OTHER_MANDATORY_ACQUISITION,
                )
            )
            roi_scope_mismatch = outcome.damaged_acquisition_loss != 0 or unmatched
            if roi_scope_mismatch:
                roi_metric = _non_comparable_metric(
                    VarianceMetricName.ACQUISITION_ROI.value,
                    VarianceMetricDirection.BENEFIT,
                    VarianceMetricComparability.SCOPE_MISMATCH,
                    predicted=conservative.conservative_acquisition_roi,
                    actual=outcome.actual_acquisition_roi.value,
                    unit="percentage_points",
                    currency=None,
                    reason="actual_acquisition_denominator_scope_differs",
                )
            elif outcome.actual_acquisition_roi.available:
                roi_metric = _comparable_metric(
                    VarianceMetricName.ACQUISITION_ROI.value,
                    VarianceMetricDirection.BENEFIT,
                    conservative.conservative_acquisition_roi,
                    outcome.actual_acquisition_roi.value,
                    unit="percentage_points",
                    currency=None,
                )
            else:
                roi_metric = _non_comparable_metric(
                    VarianceMetricName.ACQUISITION_ROI.value,
                    VarianceMetricDirection.BENEFIT,
                    VarianceMetricComparability.UNAVAILABLE,
                    predicted=conservative.conservative_acquisition_roi,
                    actual=None,
                    unit="percentage_points",
                    currency=None,
                    reason="actual_acquisition_roi_unavailable",
                )
        else:
            unavailable = lambda name, direction, predicted, unit: _non_comparable_metric(
                name,
                direction,
                VarianceMetricComparability.UNAVAILABLE,
                predicted=predicted,
                actual=None,
                unit=unit,
                currency=None if unit == "percentage_points" else currency,
                reason="sold_quantity_zero",
            )
            sale_metric = unavailable(
                VarianceMetricName.GROSS_SALE_PRICE_PER_SOLD_UNIT.value,
                VarianceMetricDirection.BENEFIT,
                conservative.conservative_sale_price,
                "money_per_unit",
            )
            marketplace_metric = unavailable(
                VarianceMetricName.MARKETPLACE_FEE_PER_SOLD_UNIT.value,
                VarianceMetricDirection.COST,
                conservative.marketplace_fee,
                "money_per_unit",
            )
            payment_metric = unavailable(
                VarianceMetricName.PAYMENT_FEE_PER_SOLD_UNIT.value,
                VarianceMetricDirection.COST,
                conservative.payment_fee,
                "money_per_unit",
            )
            fixed_metric = unavailable(
                VarianceMetricName.FIXED_FEE_PER_SOLD_UNIT.value,
                VarianceMetricDirection.COST,
                conservative.fixed_fee,
                "money_per_unit",
            )
            profit_metric = unavailable(
                VarianceMetricName.PROFIT.value,
                VarianceMetricDirection.BENEFIT,
                conservative.conservative_profit_per_unit,
                "money_per_unit",
            )
            margin_metric = unavailable(
                VarianceMetricName.MARGIN.value,
                VarianceMetricDirection.BENEFIT,
                conservative.conservative_margin,
                "percentage_points",
            )
            roi_metric = unavailable(
                VarianceMetricName.ACQUISITION_ROI.value,
                VarianceMetricDirection.BENEFIT,
                conservative.conservative_acquisition_roi,
                "percentage_points",
            )
        core = (
            acquisition_metric,
            sale_metric,
            marketplace_metric,
            payment_metric,
            fixed_metric,
            profit_metric,
            margin_metric,
            roi_metric,
        )
        comparable_count = sum(
            value.comparability is VarianceMetricComparability.COMPARABLE
            for value in core
        )
        state = (
            VarianceComparisonState.COMPARABLE
            if comparable_count == len(core)
            else VarianceComparisonState.PARTIALLY_COMPARABLE
            if comparable_count
            else VarianceComparisonState.NOT_COMPARABLE
        )
        eligibility = (
            VarianceCalibrationEligibility.INELIGIBLE
            if conservative.calculated_at >= purchase_executed_at
            or state is VarianceComparisonState.NOT_COMPARABLE
            else VarianceCalibrationEligibility.PROVISIONAL
            if outcome.inventory_resolution is ActualOutcomeInventoryResolution.PARTIAL
            else VarianceCalibrationEligibility.ELIGIBLE
        )
        contributors = self._contributors(outcome, currency)
        reasons = self._calibration_reasons(
            outcome, conservative, purchase_executed_at, core, contributors
        )
        conservative_snapshot = _snapshot(conservative)
        actual_snapshot = _snapshot(outcome)
        manifest = ConservativeActualVarianceSourceManifest(
            opportunity_identity=conservative.opportunity_identity,
            product_key=outcome.source_manifest.product_key,
            conservative_result_id=conservative.result_id,
            source_composition_id=source.composition_id,
            acquisition_normalization_id=normalization.normalization_id,
            landed_cost_composition_id=landed.composition_id,
            sourcing_binding_id=binding.binding_id,
            sourcing_admission_id=admission.admission_id,
            sourcing_admission_revision=admission.revision,
            quote_id=admission.quote_revision.quote_id,
            quote_revision=admission.quote_revision.revision,
            actual_outcome_id=outcome.outcome_id,
            purchase_execution_record_id=outcome.source_manifest.purchase_execution_record_id,
            actual_acquisition_settlement_id=outcome.source_manifest.actual_acquisition_settlement_id,
            actual_sale_settlement_ids=outcome.source_manifest.actual_sale_settlement_ids,
            currency=currency,
            conservative_policy_name=conservative.policy_name,
            conservative_policy_version=conservative.policy_version,
            conservative_schema_version=conservative.schema_version,
            actual_policy_name=outcome.policy_name,
            actual_policy_version=outcome.policy_version,
            actual_schema_version=outcome.schema_version,
            conservative_calculated_at=conservative.calculated_at,
            purchase_executed_at=purchase_executed_at,
            conservative_source_snapshot=conservative_snapshot,
            actual_source_snapshot=actual_snapshot,
            conservative_source_fingerprint=_hash(conservative_snapshot),
            actual_source_fingerprint=_hash(actual_snapshot),
            source_pair_fingerprint=scope_fingerprint,
        )
        calculated_at = _aware(self._calculated(), "calculated_at")
        committed_at = _aware(self._committed(), "committed_at")
        assumption = conservative.assumptions[0]
        return ConservativeActualVariance(
            variance_id=_text(self._identity(), "variance_id"),
            source_manifest=manifest,
            comparison_state=state,
            calibration_eligibility=eligibility,
            calibration_reasons=reasons,
            core_metrics=core,
            acquisition_component_metrics=component_metrics,
            actual_only_contributors=contributors,
            predicted_only_context=(
                ConservativeActualPredictedContext(
                    "generic_tax", conservative.accepted_tax_cost, currency,
                    VarianceMetricComparability.NO_ACTUAL_EQUIVALENT,
                    conservative.result_id,
                ),
                ConservativeActualPredictedContext(
                    "generic_duty", conservative.accepted_duty_cost, currency,
                    VarianceMetricComparability.NO_ACTUAL_EQUIVALENT,
                    conservative.result_id,
                ),
                ConservativeActualPredictedContext(
                    "generic_other_cost", conservative.accepted_other_cost, currency,
                    VarianceMetricComparability.NO_ACTUAL_EQUIVALENT,
                    conservative.result_id,
                ),
            ),
            exposure_context=ConservativeActualExposureContext(
                outcome.source_manifest.remaining_sellable_quantity,
                outcome.remaining_sellable_inventory_cost_basis,
                outcome.source_manifest.unreceived_quantity,
                outcome.unreceived_acquisition_cost_basis,
                outcome.source_manifest.damaged_quantity,
                outcome.damaged_acquisition_loss,
                outcome.source_manifest.returned_quantity,
                outcome.inventory_resolution,
                outcome.source_manifest.quantity_unit,
                currency,
            ),
            scenario_context=ConservativeActualScenarioContext(
                conservative.scenario_name,
                conservative.scenario_version,
                assumption.value,
                assumption.owner,
                conservative.policy_name,
                conservative.policy_version,
            ),
            actual_scope_context=ConservativeActualScopeContext(
                sold,
                outcome.source_manifest.executed_quantity,
                outcome.inventory_resolution,
                outcome.source_manifest.sale_windows,
                outcome.source_manifest.remaining_sellable_quantity,
                outcome.source_manifest.damaged_quantity,
                outcome.source_manifest.returned_quantity,
                outcome.source_manifest.unreceived_quantity,
                outcome.source_manifest.quantity_unit,
            ),
            requested_at=command.requested_at,
            calculated_at=calculated_at,
            committed_at=committed_at,
            policy_name=command.policy_name,
            policy_version=command.policy_version,
            schema_version=CONSERVATIVE_ACTUAL_VARIANCE_SCHEMA_VERSION,
        )

    @staticmethod
    def _contributors(outcome: ActualOutcome, currency: str):
        sale = {value.category: value.amount for value in outcome.sale_components}
        sale_refs = outcome.source_manifest.actual_sale_settlement_ids
        acquisition_ref = (outcome.source_manifest.actual_acquisition_settlement_id,)
        allocations = {value.category: value for value in outcome.acquisition_allocations}
        values = (
            ("buyer_shipping_credit", sale[ActualSaleMonetaryCategory.BUYER_SHIPPING], sale_refs),
            ("marketplace_funded_support_credit", sale[ActualSaleMonetaryCategory.MARKETPLACE_FUNDED_DISCOUNT_SUPPORT], sale_refs),
            ("refund", sale[ActualSaleMonetaryCategory.REFUND], sale_refs),
            ("return_related_fee", sale[ActualSaleMonetaryCategory.RETURN_RELATED_FEE], sale_refs),
            ("advertising", sale[ActualSaleMonetaryCategory.ADVERTISING], sale_refs),
            ("fulfillment", sale[ActualSaleMonetaryCategory.FULFILLMENT], sale_refs),
            ("storage", sale[ActualSaleMonetaryCategory.STORAGE], sale_refs),
            ("sale_side_inbound_handling", sale[ActualSaleMonetaryCategory.SALE_SIDE_INBOUND_HANDLING], sale_refs),
            ("other_sale_side_costs", outcome.other_sale_side_costs, sale_refs),
            ("actual_duty_customs", allocations[ActualAcquisitionCostCategory.DUTY_CUSTOMS].batch_amount, acquisition_ref),
            ("actual_other_mandatory_acquisition", allocations[ActualAcquisitionCostCategory.OTHER_MANDATORY_ACQUISITION].batch_amount, acquisition_ref),
            ("damaged_acquisition_loss", outcome.damaged_acquisition_loss, acquisition_ref),
        )
        return tuple(
            ConservativeActualVarianceContributor(
                category,
                amount,
                currency,
                VarianceMetricComparability.UNMODELED_IN_PREDICTION,
                tuple(references),
            )
            for category, amount, references in values
        )

    @staticmethod
    def _calibration_reasons(outcome, conservative, purchase_executed_at, core, contributors):
        reasons = set()
        manifest = outcome.source_manifest
        if outcome.inventory_resolution is ActualOutcomeInventoryResolution.PARTIAL:
            reasons.add(VarianceCalibrationReason.ACTUAL_OUTCOME_PARTIAL)
        if manifest.sold_quantity == 0:
            reasons.add(VarianceCalibrationReason.ZERO_SALES_SCOPE)
        if conservative.calculated_at >= purchase_executed_at:
            reasons.add(VarianceCalibrationReason.PREDICTION_AFTER_EXECUTION)
        if any(value.comparability is not VarianceMetricComparability.COMPARABLE for value in core):
            reasons.add(VarianceCalibrationReason.CORE_METRIC_UNAVAILABLE)
        cost_categories = {
            "refund", "return_related_fee", "advertising", "fulfillment", "storage",
            "sale_side_inbound_handling", "other_sale_side_costs",
            "actual_duty_customs", "actual_other_mandatory_acquisition",
            "damaged_acquisition_loss",
        }
        if any(value.category in cost_categories and value.amount != 0 for value in contributors):
            reasons.add(VarianceCalibrationReason.ACTUAL_ONLY_COSTS_PRESENT)
        if manifest.remaining_sellable_quantity > 0:
            reasons.add(VarianceCalibrationReason.REMAINING_INVENTORY_EXPOSURE)
        if manifest.unreceived_quantity > 0:
            reasons.add(VarianceCalibrationReason.UNRECEIVED_EXPOSURE)
        if any(value.comparability is VarianceMetricComparability.SCOPE_MISMATCH for value in core):
            reasons.add(VarianceCalibrationReason.SOURCE_SCOPE_MISMATCH)
        return tuple(value for value in VarianceCalibrationReason if value in reasons)


@dataclass(frozen=True, slots=True)
class ConservativeActualVarianceProductionRequest:
    command_id: str
    opportunity_id: str
    conservative_economics_result_id: str
    actual_outcome_id: str
    requested_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "command_id", "opportunity_id", "conservative_economics_result_id",
            "actual_outcome_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))


class ConservativeActualVarianceProductionEntry:
    def __init__(self, owner: CalculateConservativeActualVariance) -> None:
        if not isinstance(owner, CalculateConservativeActualVariance):
            raise TypeError("owner must be CalculateConservativeActualVariance")
        self._owner = owner

    def execute(self, request: ConservativeActualVarianceProductionRequest):
        if not isinstance(request, ConservativeActualVarianceProductionRequest):
            raise TypeError("request must be ConservativeActualVarianceProductionRequest")
        return self._owner.execute(CalculateConservativeActualVarianceCommand(
            command_id=request.command_id,
            opportunity_id=request.opportunity_id,
            conservative_economics_result_id=request.conservative_economics_result_id,
            actual_outcome_id=request.actual_outcome_id,
            requested_at=request.requested_at,
        ))


__all__ = [
    name
    for name in globals()
    if name.startswith(("ConservativeActual", "CalculateConservative", "CONSERVATIVE_ACTUAL"))
    or name == "conservative_actual_variance_scope_fingerprint"
]
