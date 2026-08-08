from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from app.application.capital_readiness import (
    CAPITAL_READINESS_POLICY_NAME,
    CAPITAL_READINESS_POLICY_VERSION,
    CapitalReadinessPublication,
    CapitalReadinessReplayConflictError,
    EvaluateCapitalReadiness,
    EvaluateCapitalReadinessCommand,
)
from app.application.conservative_economics import EvaluateConservativeEconomics
from app.application.domestic_market_validation import ValidateDomesticMarketForCapital
from app.application.economics_source_composition import ComposeEconomicsSources
from app.application.sourcing import (
    DOMESTIC_COMMERCE_CRITICAL_COST_POLICY,
    ComposeLandedCost,
    NormalizeAcquisitionCosts,
    EvaluateCriticalCostCompleteness,
)
from app.application.verified_economics_snapshot import VerifiedEconomicsSnapshot
from app.domain.capital import (
    CapitalReadinessReasonCode,
    CapitalReadinessState,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.market_intelligence import (
    DomesticMarketValidationReason,
    DomesticMarketValidationReasonCode,
    DomesticMarketValidationState,
)
from app.domain.opportunity import (
    CONSERVATIVE_ECONOMICS_POLICY_NAME,
    CONSERVATIVE_ECONOMICS_POLICY_VERSION,
    ConservativeEconomicsStatus,
    EconomicEvidence,
    EvidenceStatus,
    MoneyInput,
    RateInput,
    VerifiedEconomicsInput,
)
from app.domain.sourcing import (
    CommercialFactAvailability,
    CriticalCostCompletenessReason,
    CriticalCostCompletenessState,
    CriticalCostReasonCode,
    CriticalCostReasonSeverity,
    MatchVerificationStatus,
    ShippingTerm,
    SourcingEconomicsBinding,
    SourcingMoneyFact,
)
from app.infrastructure.capital_readiness import ProductionCapitalReadinessIdentityGenerator
from test_acquisition_cost_normalization import Calls, command as normalization_command
from test_domestic_market_validation import (
    FakeRepository as MarketRepository,
    execute as validate_market,
    identity as domestic_identity,
)
from test_economics_source_composition import (
    MemoryEconomicsSourceRepository,
    command as economics_source_command,
)
from test_landed_cost_composition import MemoryCompositions, composition_command
from test_sourcing_authority_contract import NOW, command as sourcing_command, service


def verified_economics(
    *, expected_sale_price: str = "100", other_cost: str = "0"
) -> VerifiedEconomicsInput:
    evidence = lambda name: EconomicEvidence(
        EvidenceStatus.VERIFIED, "founder", NOW, f"economics:{name}"
    )
    money = lambda amount, name: MoneyInput(Decimal(amount), "CNY", evidence(name))
    rate = lambda amount, name: RateInput(Decimal(amount), evidence(name))
    return VerifiedEconomicsInput(
        purchase_cost=money("12.34", "purchase"),
        shipping_cost=money("0", "shipping"),
        marketplace_fee_rate=rate("0.15", "marketplace"),
        payment_fee_rate=rate("0", "payment"),
        fixed_fee=money("0.40", "fixed"),
        tax_rate=rate("0", "tax"),
        duty_cost=money("0", "duty"),
        other_cost=money(other_cost, "other"),
        expected_sale_price=money(expected_sale_price, "expected-sale"),
    )


class MemoryCapitalReadinessRepository:
    def __init__(self, *, conservative, source, normalization, critical, market, binding, admission):
        self.conservative = conservative
        self.source = source
        self.normalization = normalization
        self.critical = critical
        self.market = market
        self.binding = binding
        self.admission = admission
        self.saved = None
        self.source_reads = 0

    def validate_replay(self, command_id, fingerprint):
        if self.saved is None or self.saved.receipt.command_id != command_id:
            return None
        if self.saved.receipt.command_fingerprint != fingerprint:
            raise CapitalReadinessReplayConflictError("conflict")
        return replace(self.saved, replayed=True)

    def get_conservative_economics_result(self, result_id):
        self.source_reads += 1
        return self.conservative if self.conservative.result_id == result_id else None

    def get_economics_source_composition(self, composition_id):
        return self.source if self.source.composition_id == composition_id else None

    def get_acquisition_normalization(self, normalization_id):
        return self.normalization if self.normalization.normalization_id == normalization_id else None

    def get_critical_cost_assessment(self, assessment_id):
        return self.critical if assessment_id == "critical-assessment-1" else None

    def get_domestic_market_validation(self, assessment_id):
        return self.market if self.market.assessment_id == assessment_id else None

    def get_sourcing_binding(self, reference):
        return self.binding if self.binding.reference == reference else None

    def get_sourcing_admission(self, reference):
        return self.admission if self.admission.to_economics_source_reference() == reference else None

    def save_assessment(self, command, assessment, receipt):
        replay = self.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replay
        self.saved = CapitalReadinessPublication(assessment, receipt, False)
        return self.saved


def ready_sources(*, expected_sale_price="100", other_cost="0", quote_valid_until=None):
    opportunity = OpportunityIdentity("opp-1", "discovery:1")
    market_identity = domestic_identity()
    base = sourcing_command()
    lineage = replace(
        base.selling_product_lineage,
        opportunity_identity=opportunity,
        market_observation_identity=market_identity,
    )
    shipping = tuple(
        ShippingTerm(term.scope, SourcingMoneyFact(CommercialFactAvailability.NOT_APPLICABLE))
        for term in base.shipping_terms
    )
    request = sourcing_command(
        selling_product_lineage=lineage,
        shipping_terms=shipping,
        quote_valid_until=quote_valid_until or NOW + timedelta(days=30),
    )
    admission = service()[0].execute(request).admission
    binding = SourcingEconomicsBinding(
        "binding-1", opportunity, admission.to_economics_source_reference(), NOW, NOW
    )
    landed_repository = MemoryCompositions(binding, admission)
    landed = ComposeLandedCost(
        landed_repository,
        composition_id_generator=lambda: "landed-composition-1",
        composed_clock=lambda: NOW,
        committed_clock=lambda: NOW,
    ).execute(composition_command(binding, opportunity_identity=opportunity)).composition
    normalization_repository = type("NormalizationRepository", (), {
        "get_composition": lambda self, value: landed if value == landed.composition_id else None,
        "get_allocation_authority": lambda self, value: None,
        "get_fx_observation": lambda self, value: None,
        "validate_replay": lambda self, command_id, fingerprint: None,
        "save_normalization": lambda self, command, normalization, receipt: __import__(
            "app.application.sourcing.acquisition_cost_normalization",
            fromlist=["AcquisitionCostNormalizationResult"],
        ).AcquisitionCostNormalizationResult(normalization, receipt, False),
    })()
    normalize_request = normalization_command(
        landed,
        (),
        (),
        target_currency="CNY",
        allocation_authority_ids=(),
        fx_observation_ids=(),
    )
    normalization = NormalizeAcquisitionCosts(
        normalization_repository,
        normalization_id_generator=lambda: "normalization-1",
        normalized_clock=lambda: NOW,
        committed_clock=lambda: NOW,
    ).execute(normalize_request).normalization
    verified = VerifiedEconomicsSnapshot(
        opportunity.opportunity_id,
        verified_economics(
            expected_sale_price=expected_sale_price,
            other_cost=other_cost,
        ),
        NOW,
    )
    source_repository = MemoryEconomicsSourceRepository(normalization, verified)
    source = ComposeEconomicsSources(
        source_repository,
        composition_id_generator=lambda: "economics-source-1",
        composed_clock=lambda: NOW,
        committed_clock=lambda: NOW,
    ).execute(economics_source_command(normalization, verified)).composition
    conservative_repository = type("ConservativeRepository", (), {
        "get_source_composition": lambda self, value: source if value == source.composition_id else None,
        "validate_replay": lambda self, command_id, fingerprint: None,
        "save_result": lambda self, command, result, receipt: __import__(
            "app.application.conservative_economics",
            fromlist=["ConservativeEconomicsPublication"],
        ).ConservativeEconomicsPublication(result, receipt, False),
    })()
    from app.application.conservative_economics import (
        ConservativeEconomicsScenario,
        EvaluateConservativeEconomicsCommand,
    )
    conservative = EvaluateConservativeEconomics(
        conservative_repository,
        result_id_generator=lambda: "conservative-result-1",
        calculated_clock=lambda: NOW,
        committed_clock=lambda: NOW,
    ).execute(EvaluateConservativeEconomicsCommand(
        "conservative-command-1",
        opportunity,
        source.composition_id,
        ConservativeEconomicsScenario("capital", "1.0.0", Decimal("1"), "founder"),
        NOW,
        CONSERVATIVE_ECONOMICS_POLICY_NAME,
        CONSERVATIVE_ECONOMICS_POLICY_VERSION,
    )).result
    critical_repository = type("CriticalRepository", (), {
        "get_composition": lambda self, value: landed if value == landed.composition_id else None,
        "get_binding": lambda self, reference: binding if reference == binding.reference else None,
        "get_source_admission": lambda self, reference: admission if reference == binding.source_reference else None,
        "get_verified_economics_snapshot": lambda self, value: verified if value == opportunity.opportunity_id else None,
    })()
    critical = EvaluateCriticalCostCompleteness(
        critical_repository,
        critical_repository,
        policy=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY,
        evaluated_clock=lambda: NOW,
    ).execute(landed.composition_id)
    market = validate_market(MarketRepository(market_identity))[0].assessment
    market = replace(
        market,
        assessment_id="market-validation-1",
        source_manifest=replace(
            market.source_manifest,
            opportunity_id=opportunity.opportunity_id,
            discovery_reference=opportunity.discovery_reference,
            market_identity=market_identity,
        ),
    )
    repository = MemoryCapitalReadinessRepository(
        conservative=conservative,
        source=source,
        normalization=normalization,
        critical=critical,
        market=market,
        binding=binding,
        admission=admission,
    )
    return repository, opportunity


def command(repository, opportunity, **changes):
    values = dict(
        command_id="capital-readiness-command-1",
        opportunity_identity=opportunity,
        conservative_economics_result_id=repository.conservative.result_id,
        domestic_market_validation_assessment_id=repository.market.assessment_id,
        critical_cost_assessment_id="critical-assessment-1",
        requested_at=NOW,
        policy_name=CAPITAL_READINESS_POLICY_NAME,
        policy_version=CAPITAL_READINESS_POLICY_VERSION,
    )
    values.update(changes)
    return EvaluateCapitalReadinessCommand(**values)


def evaluate(repository=None, opportunity=None, *, evaluated_at=None, identity=None, committed=None):
    if repository is None:
        repository, opportunity = ready_sources()
    identity = identity or Calls("capital-readiness-1")
    evaluated = Calls(evaluated_at or NOW + timedelta(days=1))
    committed = committed or Calls(NOW + timedelta(days=1, minutes=1))
    publication = EvaluateCapitalReadiness(
        repository,
        assessment_id_generator=identity,
        evaluated_clock=evaluated,
        committed_clock=committed,
    ).execute(command(repository, opportunity))
    return publication, repository, opportunity, identity, evaluated, committed


def reason_codes(publication):
    return publication.assessment.reason_codes


def test_exact_safe_source_set_is_ready_for_capital_review() -> None:
    publication, *_ = evaluate()
    assessment = publication.assessment
    assert assessment.state is CapitalReadinessState.READY_FOR_CAPITAL_REVIEW
    assert assessment.blocking_reasons == ()
    assert assessment.source_manifest.conservative_economics_result_id == "conservative-result-1"
    assert assessment.source_manifest.domestic_market_validation_assessment_id == "market-validation-1"
    assert assessment.source_manifest.critical_cost_assessment_id == "critical-assessment-1"
    assert assessment.source_manifest.sourcing_binding_id == "binding-1"
    assert assessment.source_manifest.product_match_verification_id


def test_blocked_prerequisites_are_preserved_as_readiness_reasons() -> None:
    repository, opportunity = ready_sources(other_cost="1")
    assert repository.conservative.status is ConservativeEconomicsStatus.BLOCKED
    result = evaluate(repository, opportunity)[0]
    assert CapitalReadinessReasonCode.CONSERVATIVE_ECONOMICS_BLOCKED in reason_codes(result)

    repository, opportunity = ready_sources()
    repository.market = replace(
        repository.market,
        state=DomesticMarketValidationState.BLOCKED,
        blocking_reasons=(DomesticMarketValidationReason(
            DomesticMarketValidationReasonCode.CURRENT_USE_VERIFICATION_MISSING
        ),),
    )
    result = evaluate(repository, opportunity)[0]
    assert CapitalReadinessReasonCode.DOMESTIC_MARKET_NOT_VALIDATED in reason_codes(result)

    repository, opportunity = ready_sources()
    repository.critical = replace(
        repository.critical,
        state=CriticalCostCompletenessState.INCOMPLETE,
        blocking_reasons=(CriticalCostCompletenessReason(
            CriticalCostReasonCode.QUOTE_VALIDITY_UNKNOWN,
            CriticalCostReasonSeverity.BLOCKING,
            "quote",
        ),),
    )
    result = evaluate(repository, opportunity)[0]
    assert CapitalReadinessReasonCode.CRITICAL_COST_INCOMPLETE in reason_codes(result)


def test_negative_calculable_economics_can_remain_ready_without_thresholds() -> None:
    repository, opportunity = ready_sources(expected_sale_price="14")
    assert repository.conservative.status is ConservativeEconomicsStatus.CALCULABLE
    assert repository.conservative.conservative_profit_per_unit < 0
    publication = evaluate(repository, opportunity)[0]
    assert publication.assessment.state is CapitalReadinessState.READY_FOR_CAPITAL_REVIEW
    for forbidden in (
        "minimum_roi", "minimum_margin", "minimum_profit", "required_capital",
        "available_capital", "buy", "invest", "founder_approved",
    ):
        assert not hasattr(publication.assessment, forbidden)


def test_opportunity_and_sourcing_lineage_mismatches_block() -> None:
    repository, opportunity = ready_sources()
    repository.market = replace(
        repository.market,
        source_manifest=replace(repository.market.source_manifest, opportunity_id="other"),
    )
    publication = evaluate(repository, opportunity)[0]
    assert CapitalReadinessReasonCode.SOURCE_OPPORTUNITY_MISMATCH in reason_codes(publication)

    repository, opportunity = ready_sources()
    repository.normalization = replace(repository.normalization, composition_id="other")
    publication = evaluate(repository, opportunity)[0]
    assert CapitalReadinessReasonCode.SOURCING_LINEAGE_MISMATCH in reason_codes(publication)


def test_verified_product_match_is_required_without_using_proposal_score() -> None:
    repository, opportunity = ready_sources()
    match = object.__new__(type(repository.admission.match_verification))
    for name in repository.admission.match_verification.__dataclass_fields__:
        object.__setattr__(match, name, getattr(repository.admission.match_verification, name))
    object.__setattr__(match, "status", MatchVerificationStatus.VERIFIED_MISMATCH)
    admission = object.__new__(type(repository.admission))
    for name in repository.admission.__dataclass_fields__:
        object.__setattr__(admission, name, getattr(repository.admission, name))
    object.__setattr__(admission, "match_verification", match)
    repository.admission = admission
    publication = evaluate(repository, opportunity)[0]
    assert CapitalReadinessReasonCode.PRODUCT_MATCH_NOT_VERIFIED in reason_codes(publication)
    assert not hasattr(publication.assessment, "proposal_score")


def test_quote_validity_is_evaluated_only_for_fresh_command() -> None:
    repository, opportunity = ready_sources(quote_valid_until=NOW + timedelta(days=2))
    ready = evaluate(repository, opportunity, evaluated_at=NOW + timedelta(days=1))[0]
    assert ready.assessment.state is CapitalReadinessState.READY_FOR_CAPITAL_REVIEW
    assert ready.assessment.source_manifest.quote_valid_until == NOW + timedelta(days=2)

    repository, opportunity = ready_sources()
    repository.admission = replace(
        repository.admission,
        quote_revision=replace(repository.admission.quote_revision, valid_until=None),
    )
    missing = evaluate(repository, opportunity)[0]
    assert CapitalReadinessReasonCode.QUOTE_VALIDITY_MISSING in reason_codes(missing)

    repository, opportunity = ready_sources(quote_valid_until=NOW + timedelta(days=2))
    expired = evaluate(repository, opportunity, evaluated_at=NOW + timedelta(days=3))[0]
    assert CapitalReadinessReasonCode.QUOTE_EXPIRED in reason_codes(expired)


def test_replay_precedes_source_reads_identity_clocks_and_quote_recheck() -> None:
    publication, repository, opportunity, identity, evaluated, committed = evaluate()
    calls = (repository.source_reads, identity.count, evaluated.count, committed.count)
    repository.admission = replace(
        repository.admission,
        quote_revision=replace(repository.admission.quote_revision, valid_until=NOW),
    )
    replay = EvaluateCapitalReadiness(
        repository,
        assessment_id_generator=identity,
        evaluated_clock=evaluated,
        committed_clock=committed,
    ).execute(command(repository, opportunity))
    assert replay.replayed is True
    assert replay.assessment == publication.assessment
    assert (repository.source_reads, identity.count, evaluated.count, committed.count) == calls


def test_new_command_after_quote_expiry_is_blocked_and_changed_source_conflicts() -> None:
    publication, repository, opportunity, *_ = evaluate()
    with pytest.raises(CapitalReadinessReplayConflictError):
        EvaluateCapitalReadiness(
            repository,
            assessment_id_generator=lambda: "never",
            evaluated_clock=lambda: NOW,
            committed_clock=lambda: NOW,
        ).execute(command(
            repository,
            opportunity,
            domestic_market_validation_assessment_id="changed",
        ))
    later = EvaluateCapitalReadiness(
        repository,
        assessment_id_generator=lambda: "later-assessment",
        evaluated_clock=lambda: NOW + timedelta(days=31),
        committed_clock=lambda: NOW + timedelta(days=31, minutes=1),
    ).execute(command(repository, opportunity, command_id="later-command"))
    assert CapitalReadinessReasonCode.QUOTE_EXPIRED in reason_codes(later)
    assert publication.assessment.assessment_id != later.assessment.assessment_id


def test_exact_manifest_reason_order_and_immutability() -> None:
    repository, opportunity = ready_sources(quote_valid_until=NOW + timedelta(days=1))
    repository.market = replace(
        repository.market,
        state=DomesticMarketValidationState.BLOCKED,
        blocking_reasons=(DomesticMarketValidationReason(
            DomesticMarketValidationReasonCode.CURRENT_USE_VERIFICATION_MISSING
        ),),
    )
    publication = evaluate(repository, opportunity, evaluated_at=NOW + timedelta(days=2))[0]
    assert publication.assessment.reason_codes == tuple(sorted(
        publication.assessment.reason_codes, key=lambda value: value.order
    ))
    with pytest.raises(FrozenInstanceError):
        publication.assessment.state = CapitalReadinessState.READY_FOR_CAPITAL_REVIEW


def test_production_identity_supplier_is_stateless_concurrent_uuid4() -> None:
    supplier = ProductionCapitalReadinessIdentityGenerator()
    with ThreadPoolExecutor(max_workers=16) as pool:
        values = tuple(pool.map(lambda _: supplier(), range(512)))
    assert type(supplier).__slots__ == ()
    assert not hasattr(supplier, "__dict__")
    assert len(values) == len(set(values))
    assert all(len(value) == 32 and UUID(hex=value).version == 4 for value in values)
