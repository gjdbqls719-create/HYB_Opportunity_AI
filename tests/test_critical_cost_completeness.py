from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal

import pytest

from app.application.sourcing import (
    CriticalCostSourceMismatchError,
    DOMESTIC_COMMERCE_CRITICAL_COST_POLICY,
    EvaluateCriticalCostCompleteness,
)
from app.application.verified_economics_snapshot import VerifiedEconomicsSnapshot
from app.domain.opportunity import (
    EconomicEvidence,
    EvidenceStatus,
    MoneyInput,
    RateInput,
    VerifiedEconomicsInput,
)
from app.domain.sourcing import (
    CommercialFactAvailability,
    CostAllocationBasis,
    CriticalCostCompletenessPolicy,
    CriticalCostCompletenessState,
    CriticalCostReasonCode,
    LandedCostComponentKind,
    ShippingTerm,
    SourcingMoneyFact,
)
from engine.opportunity import calculate_verified_economics
from test_landed_cost_composition import composition_command, prepare
from test_sourcing_authority_contract import NOW


class CriticalCostSources:
    def __init__(self, composition, binding, admission, verified):
        self.composition = composition
        self.binding = binding
        self.admission = admission
        self.verified = verified

    def get_composition(self, composition_id):
        return self.composition if composition_id == self.composition.composition_id else None

    def get_binding(self, reference):
        return self.binding

    def get_source_admission(self, reference):
        return self.admission if reference == self.binding.source_reference else None

    def get_verified_economics_snapshot(self, opportunity_id):
        return self.verified if opportunity_id == self.verified.opportunity_id else None


def economic_evidence(status=EvidenceStatus.VERIFIED, reference="economics-source-1"):
    return EconomicEvidence(status, "founder", NOW, reference)


def economics(*, currency="CNY", shipping=Decimal("0"), shipping_status=EvidenceStatus.VERIFIED):
    def money(amount, status=EvidenceStatus.VERIFIED):
        return MoneyInput(amount, currency, economic_evidence(status))

    def rate(amount, status=EvidenceStatus.VERIFIED):
        return RateInput(amount, economic_evidence(status))

    return VerifiedEconomicsInput(
        purchase_cost=money(Decimal("12.34")),
        shipping_cost=money(shipping, shipping_status),
        marketplace_fee_rate=rate(Decimal("0.15")),
        payment_fee_rate=rate(Decimal("0")),
        fixed_fee=money(Decimal("0.40")),
        tax_rate=rate(Decimal("0")),
        duty_cost=money(Decimal("0")),
        other_cost=money(Decimal("3")),
        expected_sale_price=money(Decimal("50"), EvidenceStatus.ESTIMATED),
    )


def scenario(*, shipping=None, unit_price=None, quoted_quantity=None,
             valid_until=timedelta(days=1), evaluated_at=NOW, verified=None):
    admission, binding, repository, compose, *_ = prepare()
    terms = admission.quote_revision.shipping_terms
    shipping = shipping or (
        SourcingMoneyFact(CommercialFactAvailability.KNOWN, Decimal("0"), "CNY"),
        SourcingMoneyFact(CommercialFactAvailability.NOT_APPLICABLE),
        SourcingMoneyFact(CommercialFactAvailability.NOT_APPLICABLE),
    )
    quote = replace(
        admission.quote_revision,
        unit_price=unit_price or admission.quote_revision.unit_price,
        quoted_quantity=quoted_quantity or admission.quote_revision.quoted_quantity,
        shipping_terms=tuple(
            ShippingTerm(term.scope, cost) for term, cost in zip(terms, shipping, strict=True)
        ),
        valid_until=None if valid_until is None else NOW + valid_until,
    )
    admission = replace(admission, quote_revision=quote)
    repository.admission = admission
    composition = compose.execute(composition_command(binding)).composition
    snapshot = VerifiedEconomicsSnapshot("opp-1", verified or economics(), NOW)
    sources = CriticalCostSources(composition, binding, admission, snapshot)
    evaluator = EvaluateCriticalCostCompleteness(
        sources,
        sources,
        policy=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY,
        evaluated_clock=lambda: evaluated_at,
    )
    return evaluator, sources


def codes(result):
    return tuple(reason.code for reason in result.blocking_reasons)


def test_all_required_cost_sources_are_complete_without_claiming_capital_readiness():
    evaluator, sources = scenario()
    result = evaluator.execute(sources.composition.composition_id)
    assert result.state is CriticalCostCompletenessState.COMPLETE
    assert result.blocking_reasons == ()
    assert result.policy_name == "domestic-commerce-critical-cost-completeness"
    assert result.policy_version == "1.0.0"
    assert result.composition_id == sources.composition.composition_id
    assert result.binding_reference == sources.binding.reference
    assert result.source_reference == sources.binding.source_reference
    assert result.verified_economics_snapshot_at == NOW
    assert not hasattr(result, "capital_ready")
    assert not hasattr(result, "roi")
    assert not hasattr(result, "net_profit")
    with pytest.raises(FrozenInstanceError):
        result.policy_version = "2.0.0"


def test_unknown_purchase_and_shipping_are_blocking_but_explicit_zero_and_na_are_not():
    unknown = SourcingMoneyFact(CommercialFactAvailability.UNKNOWN)
    evaluator, sources = scenario(unit_price=unknown, shipping=(unknown, unknown, unknown))
    result = evaluator.execute(sources.composition.composition_id)
    assert result.state is CriticalCostCompletenessState.INCOMPLETE
    assert codes(result) == (
        CriticalCostReasonCode.PURCHASE_COST_UNKNOWN,
        CriticalCostReasonCode.SHIPPING_SCOPE_UNKNOWN,
        CriticalCostReasonCode.SHIPPING_SCOPE_UNKNOWN,
        CriticalCostReasonCode.SHIPPING_SCOPE_UNKNOWN,
    )

    ready, ready_sources = scenario()
    assert ready.execute(ready_sources.composition.composition_id).is_complete


def test_positive_shipping_without_allocation_authority_blocks_and_never_divides_by_moq():
    shipping = (
        SourcingMoneyFact(CommercialFactAvailability.KNOWN, Decimal("120"), "CNY"),
        SourcingMoneyFact(CommercialFactAvailability.NOT_APPLICABLE),
        SourcingMoneyFact(CommercialFactAvailability.NOT_APPLICABLE),
    )
    evaluator, sources = scenario(shipping=shipping)
    before = sources.composition.components
    result = evaluator.execute(sources.composition.composition_id)
    assert codes(result) == (CriticalCostReasonCode.SHIPPING_ALLOCATION_UNKNOWN,)
    assert sources.composition.components == before
    assert sources.composition.components[1].amount == Decimal("120")
    assert sources.composition.components[1].allocation_basis is CostAllocationBasis.UNSPECIFIED


def test_same_currency_needs_no_fx_but_mixed_currency_blocks_without_inventing_a_rate():
    evaluator, sources = scenario()
    assert CriticalCostReasonCode.CROSS_CURRENCY_FX_MISSING not in codes(
        evaluator.execute(sources.composition.composition_id)
    )
    mixed = (
        SourcingMoneyFact(CommercialFactAvailability.KNOWN, Decimal("0"), "USD"),
        SourcingMoneyFact(CommercialFactAvailability.NOT_APPLICABLE),
        SourcingMoneyFact(CommercialFactAvailability.NOT_APPLICABLE),
    )
    evaluator, sources = scenario(shipping=mixed)
    result = evaluator.execute(sources.composition.composition_id)
    assert CriticalCostReasonCode.CROSS_CURRENCY_FX_MISSING in codes(result)
    assert not hasattr(result, "fx_rate")


@pytest.mark.parametrize(
    ("valid_until", "evaluated_at"),
    ((None, NOW), (timedelta(days=1), NOW + timedelta(days=2))),
)
def test_missing_or_expired_exact_quote_blocks_new_evaluation(valid_until, evaluated_at):
    evaluator, sources = scenario(valid_until=valid_until, evaluated_at=evaluated_at)
    assert codes(evaluator.execute(sources.composition.composition_id))[-1] in {
        CriticalCostReasonCode.QUOTE_VALIDITY_UNKNOWN,
        CriticalCostReasonCode.QUOTE_EXPIRED,
    }


def test_weak_required_evidence_blocks_but_estimated_sale_price_is_allowed():
    value = economics()
    weak = replace(
        value,
        marketplace_fee_rate=RateInput(
            Decimal("0.15"), economic_evidence(EvidenceStatus.ESTIMATED)
        ),
    )
    evaluator, sources = scenario(verified=weak)
    result = evaluator.execute(sources.composition.composition_id)
    assert CriticalCostReasonCode.EVIDENCE_NOT_VERIFIED in codes(result)


def test_missing_non_sourcing_costs_have_deterministic_field_specific_blockers():
    missing = economic_evidence(EvidenceStatus.MISSING)
    value = replace(
        economics(),
        expected_sale_price=MoneyInput(None, "CNY", missing),
        marketplace_fee_rate=RateInput(None, missing),
        payment_fee_rate=RateInput(None, missing),
        fixed_fee=MoneyInput(None, "CNY", missing),
        tax_rate=RateInput(None, missing),
        duty_cost=MoneyInput(None, "CNY", missing),
        other_cost=MoneyInput(None, "CNY", missing),
    )
    evaluator, sources = scenario(verified=value)
    assert codes(evaluator.execute(sources.composition.composition_id)) == (
        CriticalCostReasonCode.EXPECTED_SALE_PRICE_MISSING,
        CriticalCostReasonCode.MARKETPLACE_FEE_MISSING,
        CriticalCostReasonCode.PAYMENT_FEE_MISSING,
        CriticalCostReasonCode.FIXED_FEE_MISSING,
        CriticalCostReasonCode.TAX_MISSING,
        CriticalCostReasonCode.DUTY_MISSING,
        CriticalCostReasonCode.OTHER_COST_MISSING,
    )


def test_policy_is_immutable_and_rejects_unknown_evidence_status():
    with pytest.raises(FrozenInstanceError):
        DOMESTIC_COMMERCE_CRITICAL_COST_POLICY.version = "2.0.0"
    with pytest.raises(ValueError, match="unsupported"):
        CriticalCostCompletenessPolicy(
            "policy", "1.0.0", ("invented",), ("verified",), True, True
        )


def test_exact_lineage_mismatch_is_rejected_instead_of_falling_back_to_latest():
    evaluator, sources = scenario()
    sources.binding = replace(sources.binding, binding_id="different-binding")
    with pytest.raises(CriticalCostSourceMismatchError):
        evaluator.execute(sources.composition.composition_id)


def test_legacy_calculator_fallback_cannot_make_capital_completeness_authoritative():
    missing = replace(
        economics(),
        shipping_cost=MoneyInput(
            None, "CNY", economic_evidence(EvidenceStatus.MISSING)
        ),
    )
    legacy = calculate_verified_economics(marketplace="ebay", economics=missing)
    assert legacy.inputs.shipping_cost.amount is None

    unknown = SourcingMoneyFact(CommercialFactAvailability.UNKNOWN)
    evaluator, sources = scenario(shipping=(unknown, unknown, unknown), verified=missing)
    assessment = evaluator.execute(sources.composition.composition_id)
    assert not assessment.is_complete
    assert CriticalCostReasonCode.SHIPPING_SCOPE_UNKNOWN in codes(assessment)
    assert CriticalCostReasonCode.EVIDENCE_NOT_VERIFIED not in codes(assessment)
    assert not hasattr(assessment, "roi")
    assert not hasattr(assessment, "net_profit")

    explicit_zero = calculate_verified_economics(
        marketplace="ebay", economics=economics(shipping=Decimal("0"))
    )
    assert explicit_zero.inputs.shipping_cost.amount == Decimal("0")


def test_reason_order_is_deterministic_and_warnings_defer_allowances():
    unknown = SourcingMoneyFact(CommercialFactAvailability.UNKNOWN)
    evaluator, sources = scenario(unit_price=unknown, shipping=(unknown, unknown, unknown))
    first = evaluator.execute(sources.composition.composition_id)
    second = evaluator.execute(sources.composition.composition_id)
    assert first == second
    assert tuple(reason.code for reason in first.warning_reasons) == (
        CriticalCostReasonCode.ADVERTISING_ALLOWANCE_DEFERRED,
        CriticalCostReasonCode.RETURNS_ALLOWANCE_DEFERRED,
    )


def test_allocation_policy_accepts_per_quoted_quantity_only_with_denominator():
    shipping = (
        SourcingMoneyFact(CommercialFactAvailability.KNOWN, Decimal("10"), "CNY"),
        SourcingMoneyFact(CommercialFactAvailability.NOT_APPLICABLE),
        SourcingMoneyFact(CommercialFactAvailability.NOT_APPLICABLE),
    )
    evaluator, sources = scenario(shipping=shipping)
    component = replace(
        sources.composition.components[1],
        amount=Decimal("10"),
        currency="CNY",
        allocation_basis=CostAllocationBasis.PER_QUOTED_QUANTITY,
    )
    sources.composition = replace(
        sources.composition,
        components=(sources.composition.components[0], component, *sources.composition.components[2:]),
    )
    assert evaluator.execute(sources.composition.composition_id).is_complete

    missing_quantity = replace(
        sources.composition.quoted_quantity,
        availability=CommercialFactAvailability.UNKNOWN,
        quantity=None,
    )
    evaluator, sources = scenario(shipping=shipping, quoted_quantity=missing_quantity)
    sources.composition = replace(
        sources.composition,
        components=(sources.composition.components[0], component, *sources.composition.components[2:]),
    )
    assert CriticalCostReasonCode.SHIPPING_ALLOCATION_DENOMINATOR_MISSING in codes(
        evaluator.execute(sources.composition.composition_id)
    )
