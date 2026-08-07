"""Application owner for exact critical-cost completeness evaluation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Callable, Protocol

from app.application.verified_economics_snapshot import VerifiedEconomicsSnapshot
from app.domain.opportunity import EvidenceStatus, MoneyInput
from app.domain.sourcing import (
    CommercialFactAvailability,
    CostAllocationBasis,
    CriticalCostCompleteness,
    CriticalCostCompletenessPolicy,
    CriticalCostCompletenessReason,
    CriticalCostCompletenessState,
    CriticalCostReasonCode,
    CriticalCostReasonSeverity,
    FounderSourcingAdmission,
    LandedCostComposition,
    SourcingEconomicsBinding,
    SourcingEconomicsBindingReference,
    SourcingEconomicsSourceReference,
)


class CriticalCostCompletenessError(RuntimeError):
    pass


class CriticalCostSourceNotFoundError(CriticalCostCompletenessError):
    pass


class CriticalCostSourceMismatchError(CriticalCostCompletenessError):
    pass


class CriticalCostCompletenessRepository(Protocol):
    def get_composition(self, composition_id: str) -> LandedCostComposition | None: ...
    def get_binding(self, reference: SourcingEconomicsBindingReference) -> SourcingEconomicsBinding | None: ...
    def get_source_admission(self, reference: SourcingEconomicsSourceReference) -> FounderSourcingAdmission | None: ...


class CriticalCostVerifiedEconomicsRepository(Protocol):
    def get_verified_economics_snapshot(self, opportunity_id: str) -> VerifiedEconomicsSnapshot | None: ...


DOMESTIC_COMMERCE_CRITICAL_COST_POLICY = CriticalCostCompletenessPolicy(
    name="domestic-commerce-critical-cost-completeness",
    version="1.0.0",
    expected_sale_evidence_statuses=("verified", "estimated"),
    required_evidence_statuses=("verified",),
    require_evidence_reference=True,
    require_quote_valid_until=True,
)


class EvaluateCriticalCostCompleteness:
    def __init__(self, repository: CriticalCostCompletenessRepository,
                 verified_economics_repository: CriticalCostVerifiedEconomicsRepository, *,
                 policy: CriticalCostCompletenessPolicy,
                 evaluated_clock: Callable[[], datetime]) -> None:
        if not isinstance(policy, CriticalCostCompletenessPolicy):
            raise TypeError("policy must be CriticalCostCompletenessPolicy")
        if not callable(evaluated_clock):
            raise TypeError("evaluated_clock must be callable")
        self._repository = repository
        self._verified_repository = verified_economics_repository
        self._policy = policy
        self._clock = evaluated_clock

    def execute(self, composition_id: str) -> CriticalCostCompleteness:
        if not isinstance(composition_id, str) or not composition_id.strip():
            raise ValueError("composition_id must be non-empty text")
        composition = self._repository.get_composition(composition_id.strip())
        if composition is None:
            raise CriticalCostSourceNotFoundError("exact Landed Cost Composition is missing")
        binding = self._repository.get_binding(composition.binding_reference)
        if binding is None:
            raise CriticalCostSourceNotFoundError("exact Sourcing Economics Binding is missing")
        if binding.reference != composition.binding_reference:
            raise CriticalCostSourceMismatchError("binding reference differs from composition")
        if binding.opportunity_identity != composition.opportunity_identity:
            raise CriticalCostSourceMismatchError("binding Opportunity differs from composition")
        admission = self._repository.get_source_admission(binding.source_reference)
        if admission is None:
            raise CriticalCostSourceNotFoundError("exact Sourcing Admission revision is missing")
        if admission.to_economics_source_reference() != binding.source_reference:
            raise CriticalCostSourceMismatchError("Admission source differs from binding")
        if admission.selling_product_lineage.opportunity_identity != composition.opportunity_identity:
            raise CriticalCostSourceMismatchError("Admission Opportunity differs from composition")
        if admission.quote_revision.evidence != composition.evidence_reference:
            raise CriticalCostSourceMismatchError("quote evidence differs from composition")
        self._validate_composition_source(composition, admission)
        opportunity_id = composition.opportunity_identity.opportunity_id
        verified = self._verified_repository.get_verified_economics_snapshot(opportunity_id)
        if verified is None:
            raise CriticalCostSourceNotFoundError("Verified Economics Snapshot is missing")
        if verified.opportunity_id != opportunity_id:
            raise CriticalCostSourceMismatchError("Verified Economics Opportunity differs")
        evaluated_at = self._aware(self._clock(), "evaluated_at")
        blockers = self._blocking_reasons(composition, admission, verified, evaluated_at)
        warnings = (
            self._warning(CriticalCostReasonCode.ADVERTISING_ALLOWANCE_DEFERRED, "advertising"),
            self._warning(CriticalCostReasonCode.RETURNS_ALLOWANCE_DEFERRED, "returns"),
        )
        return CriticalCostCompleteness(
            opportunity_identity=composition.opportunity_identity,
            composition_id=composition.composition_id,
            binding_reference=composition.binding_reference,
            source_reference=binding.source_reference,
            verified_economics_opportunity_id=verified.opportunity_id,
            verified_economics_snapshot_at=verified.snapshot_at,
            verified_economics_schema_version=verified.schema_version,
            policy_name=self._policy.name,
            policy_version=self._policy.version,
            evaluated_at=evaluated_at,
            state=CriticalCostCompletenessState.INCOMPLETE if blockers else CriticalCostCompletenessState.COMPLETE,
            blocking_reasons=tuple(blockers),
            warning_reasons=warnings,
        )

    @staticmethod
    def _aware(value: datetime, name: str) -> datetime:
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")
        return value

    @staticmethod
    def _blocking(code: CriticalCostReasonCode, category: str, reference: str | None = None):
        return CriticalCostCompletenessReason(code, CriticalCostReasonSeverity.BLOCKING, category, reference)

    @staticmethod
    def _warning(code: CriticalCostReasonCode, category: str):
        return CriticalCostCompletenessReason(code, CriticalCostReasonSeverity.WARNING, category)

    @staticmethod
    def _validate_composition_source(composition, admission) -> None:
        quote = admission.quote_revision
        shipping = {term.scope.value: term.cost for term in quote.shipping_terms}
        expected = (
            (quote.unit_price.availability, quote.unit_price.amount, quote.unit_price.currency),
            *((shipping[scope].availability, shipping[scope].amount, shipping[scope].currency)
              for scope in ("supplier_side", "international_freight", "domestic_inbound")),
        )
        actual = tuple((value.availability, value.amount, value.currency) for value in composition.components)
        if actual != expected:
            raise CriticalCostSourceMismatchError("composition facts differ from exact quote")
        if composition.minimum_order_quantity != quote.minimum_order_quantity:
            raise CriticalCostSourceMismatchError("composition MOQ differs from exact quote")
        if composition.quoted_quantity != quote.quoted_quantity:
            raise CriticalCostSourceMismatchError("composition quoted quantity differs from exact quote")

    def _blocking_reasons(self, composition, admission, verified, evaluated_at):
        reasons: list[CriticalCostCompletenessReason] = []
        purchase = composition.components[0]
        if purchase.availability is not CommercialFactAvailability.KNOWN:
            reasons.append(self._blocking(CriticalCostReasonCode.PURCHASE_COST_UNKNOWN, purchase.kind.value))

        for component in composition.components[1:]:
            if component.availability is CommercialFactAvailability.UNKNOWN:
                reasons.append(self._blocking(CriticalCostReasonCode.SHIPPING_SCOPE_UNKNOWN, component.kind.value))
                continue
            if component.availability is CommercialFactAvailability.NOT_APPLICABLE:
                continue
            if component.amount == Decimal("0") or component.allocation_basis is CostAllocationBasis.PER_UNIT:
                continue
            if component.allocation_basis is CostAllocationBasis.PER_QUOTED_QUANTITY:
                quantity = composition.quoted_quantity
                if quantity.availability is not CommercialFactAvailability.KNOWN or quantity.quantity is None:
                    reasons.append(self._blocking(
                        CriticalCostReasonCode.SHIPPING_ALLOCATION_DENOMINATOR_MISSING,
                        component.kind.value,
                    ))
                continue
            reasons.append(self._blocking(CriticalCostReasonCode.SHIPPING_ALLOCATION_UNKNOWN, component.kind.value))

        inputs = verified.inputs
        required = (
            ("expected_sale_price", inputs.expected_sale_price,
             CriticalCostReasonCode.EXPECTED_SALE_PRICE_MISSING, self._policy.expected_sale_evidence_statuses),
            ("marketplace_fee", inputs.marketplace_fee_rate,
             CriticalCostReasonCode.MARKETPLACE_FEE_MISSING, self._policy.required_evidence_statuses),
            ("payment_fee", inputs.payment_fee_rate,
             CriticalCostReasonCode.PAYMENT_FEE_MISSING, self._policy.required_evidence_statuses),
            ("fixed_fee", inputs.fixed_fee,
             CriticalCostReasonCode.FIXED_FEE_MISSING, self._policy.required_evidence_statuses),
            ("tax", inputs.tax_rate,
             CriticalCostReasonCode.TAX_MISSING, self._policy.required_evidence_statuses),
            ("duty", inputs.duty_cost,
             CriticalCostReasonCode.DUTY_MISSING, self._policy.required_evidence_statuses),
            ("other_cost", inputs.other_cost,
             CriticalCostReasonCode.OTHER_COST_MISSING, self._policy.required_evidence_statuses),
        )
        for category, value, missing_code, allowed_statuses in required:
            numeric = value.amount if isinstance(value, MoneyInput) else value.rate
            evidence = value.evidence
            if numeric is None or evidence.status in {EvidenceStatus.MISSING, EvidenceStatus.UNSUPPORTED}:
                reasons.append(self._blocking(missing_code, category, evidence.reference))
            elif evidence.status.value not in allowed_statuses:
                reasons.append(self._blocking(CriticalCostReasonCode.EVIDENCE_NOT_VERIFIED, category, evidence.reference))
            elif self._policy.require_evidence_reference and evidence.reference is None:
                reasons.append(self._blocking(CriticalCostReasonCode.EVIDENCE_REFERENCE_MISSING, category))

        currencies = list(composition.known_currencies)
        if inputs.currency not in currencies:
            currencies.append(inputs.currency)
        if len(currencies) > 1:
            reasons.append(self._blocking(CriticalCostReasonCode.CROSS_CURRENCY_FX_MISSING, "fx"))

        valid_until = admission.quote_revision.valid_until
        if self._policy.require_quote_valid_until and valid_until is None:
            reasons.append(self._blocking(CriticalCostReasonCode.QUOTE_VALIDITY_UNKNOWN, "quote"))
        elif valid_until is not None and valid_until <= evaluated_at:
            reasons.append(self._blocking(CriticalCostReasonCode.QUOTE_EXPIRED, "quote"))
        return reasons


__all__ = [
    name for name in globals()
    if name.startswith("CriticalCost") or name.startswith("Evaluate") or name.startswith("DOMESTIC")
]
