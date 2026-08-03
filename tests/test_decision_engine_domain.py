from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.decision_engine import (
    DecisionConfidence,
    DecisionDimension,
    DecisionDimensionResult,
    DecisionEvidenceAvailability,
    DecisionEvidenceMetadata,
    DecisionFreshness,
    DecisionInput,
    DecisionOutcome,
    DecisionReasonCode,
    DecisionResult,
    OpportunityIdentity,
)
from app.domain.market_intelligence import (
    ExternalMarketSignal,
    ExternalSignalDirection,
    ExternalSignalSourceType,
    MarketEvidence,
    MarketEvidenceStatus,
    MarketObservationIdentity,
    MarketObservationScope,
)
from app.domain.opportunity import (
    EconomicEvidence,
    EvidenceStatus,
    MoneyInput,
    RateInput,
    VerifiedEconomicsInput,
)
from engine.production_safety import ProductionSafetyAssessment, ProductionSafetyStatus


NOW = datetime(2026, 8, 3, 12, tzinfo=timezone.utc)


def identity() -> MarketObservationIdentity:
    return MarketObservationIdentity(
        scope=MarketObservationScope.CANONICAL_PRODUCT,
        market="US",
        marketplace="ebay",
        canonical_product_id="product-1",
        marketplace_item_id=None,
        normalized_query=None,
        category=None,
        variant_identity=None,
        condition=None,
        window_started_at=NOW,
        window_ended_at=NOW,
    )


def opportunity_identity() -> OpportunityIdentity:
    return OpportunityIdentity(
        opportunity_id="opportunity-1",
        discovery_reference="ebay:item-1",
    )


def evidence(status: EvidenceStatus = EvidenceStatus.VERIFIED) -> EconomicEvidence:
    return EconomicEvidence(status=status, source="test")


def money(amount: str | None, status: EvidenceStatus = EvidenceStatus.VERIFIED) -> MoneyInput:
    return MoneyInput(
        amount=None if amount is None else Decimal(amount),
        currency="USD",
        evidence=evidence(status),
    )


def rate(value: str | None, status: EvidenceStatus = EvidenceStatus.VERIFIED) -> RateInput:
    return RateInput(
        rate=None if value is None else Decimal(value),
        evidence=evidence(status),
    )


def economics() -> VerifiedEconomicsInput:
    return VerifiedEconomicsInput(
        purchase_cost=money("50"),
        shipping_cost=money("5"),
        marketplace_fee_rate=rate("0.1"),
        payment_fee_rate=rate("0.03"),
        fixed_fee=money("0.3"),
        tax_rate=rate("0"),
        duty_cost=money(None, EvidenceStatus.UNSUPPORTED),
        other_cost=money("0"),
        expected_sale_price=money("100"),
    )


def metadata() -> tuple[DecisionEvidenceMetadata, ...]:
    return tuple(
        DecisionEvidenceMetadata(
            dimension=dimension,
            availability=(
                DecisionEvidenceAvailability.COMPLETE
                if dimension in {DecisionDimension.ECONOMICS, DecisionDimension.SAFETY}
                else DecisionEvidenceAvailability.UNAVAILABLE
            ),
            freshness=(
                DecisionFreshness.FRESH
                if dimension in {DecisionDimension.ECONOMICS, DecisionDimension.SAFETY}
                else DecisionFreshness.UNKNOWN
            ),
        )
        for dimension in DecisionDimension
    )


def dimension_result(
    dimension: DecisionDimension = DecisionDimension.ECONOMICS,
    **overrides: object,
) -> DecisionDimensionResult:
    values: dict[str, object] = {
        "dimension": dimension,
        "availability": DecisionEvidenceAvailability.COMPLETE,
        "confidence": Decimal("1"),
        "freshness": DecisionFreshness.FRESH,
        "assessment_reference": "economics:product-1",
        "reason_codes": (DecisionReasonCode.ECONOMICS_READY,),
        "generated_at": NOW,
        "schema_version": "decision-dimension-v1",
        "policy_version": "decision-policy-v1",
    }
    values.update(overrides)
    return DecisionDimensionResult(**values)


def decision_input(**overrides: object) -> DecisionInput:
    values: dict[str, object] = {
        "opportunity_identity": opportunity_identity(),
        "market_observation_identity": identity(),
        "verified_economics": economics(),
        "production_safety": ProductionSafetyAssessment(ProductionSafetyStatus.READY),
        "competition_assessment": None,
        "demand_assessment": None,
        "external_signals": (),
        "evidence_metadata": metadata(),
        "generated_at": NOW,
        "schema_version": "decision-input-v1",
        "policy_version": "decision-policy-v1",
    }
    values.update(overrides)
    return DecisionInput(**values)


def decision_result(**overrides: object) -> DecisionResult:
    values: dict[str, object] = {
        "opportunity_identity": opportunity_identity(),
        "outcome": DecisionOutcome.REVIEW,
        "confidence": DecisionConfidence(
            confidence=Decimal("0.8"),
            availability=DecisionEvidenceAvailability.PARTIAL,
            missing_dimensions=(DecisionDimension.COMPETITION, DecisionDimension.DEMAND),
        ),
        "dimension_results": tuple(dimension_result(value) for value in DecisionDimension),
        "blocking_reasons": (),
        "supporting_reasons": (DecisionReasonCode.ECONOMICS_READY,),
        "uncertainty_reasons": (DecisionReasonCode.INSUFFICIENT_EVIDENCE,),
        "generated_at": NOW,
        "schema_version": "decision-result-v1",
        "policy_version": "decision-policy-v1",
    }
    values.update(overrides)
    return DecisionResult(**values)


def test_decision_enums_have_stable_values() -> None:
    assert tuple(value.value for value in DecisionOutcome) == (
        "invest", "review", "reject", "insufficient_evidence"
    )
    assert tuple(value.value for value in DecisionDimension) == (
        "economics", "safety", "competition", "demand", "external_reference"
    )
    assert DecisionReasonCode.EXTERNAL_SIGNAL_DISAGREES.value == "external_signal_disagrees"


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-0.01"), Decimal("1.01")])
def test_decision_confidence_rejects_non_finite_and_out_of_range(value: Decimal) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        DecisionConfidence(value, DecisionEvidenceAvailability.PARTIAL, ())


def test_decision_confidence_requires_decimal_and_immutable_dimensions() -> None:
    with pytest.raises(TypeError, match="Decimal"):
        DecisionConfidence(0.5, DecisionEvidenceAvailability.COMPLETE, ())
    with pytest.raises(TypeError, match="tuple"):
        DecisionConfidence(Decimal("0.5"), DecisionEvidenceAvailability.PARTIAL, [])
    with pytest.raises(ValueError, match="duplicates"):
        DecisionConfidence(
            Decimal("0.5"),
            DecisionEvidenceAvailability.PARTIAL,
            (DecisionDimension.DEMAND, DecisionDimension.DEMAND),
        )


def test_decision_confidence_enforces_availability_semantics() -> None:
    complete = DecisionConfidence(
        Decimal("1"), DecisionEvidenceAvailability.COMPLETE, ()
    )
    partial = DecisionConfidence(
        Decimal("0.5"),
        DecisionEvidenceAvailability.PARTIAL,
        (DecisionDimension.DEMAND,),
    )
    unavailable = DecisionConfidence(
        Decimal("0"),
        DecisionEvidenceAvailability.UNAVAILABLE,
        (
            DecisionDimension.ECONOMICS,
            DecisionDimension.SAFETY,
            DecisionDimension.COMPETITION,
            DecisionDimension.DEMAND,
        ),
    )

    assert complete.missing_dimensions == ()
    assert partial.missing_dimensions == (DecisionDimension.DEMAND,)
    assert len(unavailable.missing_dimensions) == 4

    with pytest.raises(ValueError, match="complete"):
        DecisionConfidence(
            Decimal("1"),
            DecisionEvidenceAvailability.COMPLETE,
            (DecisionDimension.DEMAND,),
        )
    with pytest.raises(ValueError, match="partial"):
        DecisionConfidence(
            Decimal("0.5"), DecisionEvidenceAvailability.PARTIAL, ()
        )
    with pytest.raises(ValueError, match="every core dimension"):
        DecisionConfidence(
            Decimal("0.5"),
            DecisionEvidenceAvailability.PARTIAL,
            (
                DecisionDimension.ECONOMICS,
                DecisionDimension.SAFETY,
                DecisionDimension.COMPETITION,
                DecisionDimension.DEMAND,
            ),
        )
    with pytest.raises(ValueError, match="every core dimension"):
        DecisionConfidence(
            Decimal("0"),
            DecisionEvidenceAvailability.UNAVAILABLE,
            (DecisionDimension.DEMAND,),
        )


def test_decision_input_preserves_domain_contract_and_versions() -> None:
    value = decision_input()

    assert value.opportunity_identity == opportunity_identity()
    assert value.market_observation_identity == identity()
    assert value.verified_economics == economics()
    assert value.production_safety.status is ProductionSafetyStatus.READY
    assert value.external_signals == ()
    assert {item.dimension for item in value.evidence_metadata} == set(DecisionDimension)
    assert value.schema_version == "decision-input-v1"
    assert value.policy_version == "decision-policy-v1"


def test_opportunity_identity_is_distinct_immutable_value() -> None:
    value = opportunity_identity()
    assert value.opportunity_id == "opportunity-1"
    assert value.discovery_reference == "ebay:item-1"
    assert value == opportunity_identity()
    with pytest.raises(FrozenInstanceError):
        value.opportunity_id = "changed"


@pytest.mark.parametrize(
    ("scope", "overrides"),
    (
        (
            MarketObservationScope.SEARCH_QUERY,
            {"canonical_product_id": None, "normalized_query": "wireless mouse"},
        ),
        (
            MarketObservationScope.CATEGORY,
            {"canonical_product_id": None, "category": "electronics"},
        ),
    ),
)
def test_decision_input_rejects_non_opportunity_market_scope(
    scope: MarketObservationScope,
    overrides: dict[str, object],
) -> None:
    market_identity = replace(identity(), scope=scope, **overrides)
    with pytest.raises(ValueError, match="listing or canonical_product"):
        decision_input(market_observation_identity=market_identity)


def test_decision_input_requires_complete_unique_evidence_metadata() -> None:
    with pytest.raises(ValueError, match="every decision dimension"):
        decision_input(evidence_metadata=metadata()[:-1])
    with pytest.raises(ValueError, match="duplicate dimensions"):
        decision_input(evidence_metadata=metadata() + (metadata()[0],))

    inconsistent = list(metadata())
    inconsistent[2] = DecisionEvidenceMetadata(
        DecisionDimension.COMPETITION,
        DecisionEvidenceAvailability.COMPLETE,
        DecisionFreshness.FRESH,
    )
    with pytest.raises(ValueError, match="competition availability"):
        decision_input(evidence_metadata=tuple(inconsistent))


def test_dimension_result_validates_time_reasons_decimal_and_versions() -> None:
    value = dimension_result()
    assert value.confidence == Decimal("1")
    assert value.reason_codes == (DecisionReasonCode.ECONOMICS_READY,)
    assert value.schema_version == "decision-dimension-v1"
    assert value.policy_version == "decision-policy-v1"

    with pytest.raises(TypeError, match="Decimal"):
        dimension_result(confidence=1)
    with pytest.raises(ValueError, match="must be None"):
        dimension_result(
            availability=DecisionEvidenceAvailability.UNAVAILABLE,
            confidence=Decimal("0"),
        )
    unavailable = dimension_result(
        availability=DecisionEvidenceAvailability.UNAVAILABLE,
        confidence=None,
    )
    assert unavailable.confidence is None


@pytest.mark.parametrize("factory", [decision_input, dimension_result, decision_result])
def test_contracts_require_timezone_aware_generated_at(factory) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        factory(generated_at=datetime(2026, 8, 3, 12))


def test_decision_result_uses_reason_codes_and_rejects_duplicate_dimensions() -> None:
    value = decision_result()
    assert value.outcome is DecisionOutcome.REVIEW
    assert value.supporting_reasons == (DecisionReasonCode.ECONOMICS_READY,)

    with pytest.raises(TypeError, match="DecisionReasonCode"):
        decision_result(blocking_reasons=("safety_blocked",))
    with pytest.raises(ValueError, match="duplicate dimensions"):
        decision_result(dimension_results=(dimension_result(), dimension_result()))
    with pytest.raises(ValueError, match="every decision dimension"):
        decision_result(dimension_results=(dimension_result(),))
    with pytest.raises(ValueError, match="multiple result categories"):
        decision_result(
            blocking_reasons=(DecisionReasonCode.INSUFFICIENT_EVIDENCE,),
            uncertainty_reasons=(DecisionReasonCode.INSUFFICIENT_EVIDENCE,),
        )


def test_contracts_are_immutable_and_have_value_equality() -> None:
    first = decision_result()
    second = decision_result()
    assert first == second

    with pytest.raises(FrozenInstanceError):
        first.outcome = DecisionOutcome.INVEST

    for value in (
        DecisionConfidence(
            Decimal("1"), DecisionEvidenceAvailability.COMPLETE, ()
        ),
        metadata()[0],
        dimension_result(),
        decision_input(),
    ):
        with pytest.raises(FrozenInstanceError):
            value.generated_at = NOW


def test_production_safety_rejects_mutable_collections() -> None:
    for values in ([], set()):
        with pytest.raises(TypeError, match="tuple"):
            ProductionSafetyAssessment(
                ProductionSafetyStatus.INSUFFICIENT_DATA,
                missing_fields=values,
            )

    source = ("shipping_cost",)
    value = ProductionSafetyAssessment(
        ProductionSafetyStatus.INSUFFICIENT_DATA,
        missing_fields=source,
    )
    assert value.missing_fields is source


def test_decision_input_rejects_mutable_external_signal_value() -> None:
    mutable_value = {"search_volume": 1200}
    market_identity = identity()
    signal = ExternalMarketSignal(
        signal_id="signal-1",
        identity=market_identity,
        source_type=ExternalSignalSourceType.MANUAL_INPUT,
        signal_name="search_volume",
        signal_direction=ExternalSignalDirection.POSITIVE,
        evidence=MarketEvidence(
            value=mutable_value,
            source="founder",
            reference="manual:1",
            observed_at=NOW,
            status=MarketEvidenceStatus.HUMAN_VERIFIED,
            confidence=Decimal("1"),
            market=market_identity.market,
            marketplace=market_identity.marketplace,
            collection_method="manual",
            schema_version="market-evidence-v1",
        ),
        captured_at=NOW,
        schema_version="external-signal-v1",
        verified_at=NOW,
        operator_id="founder-1",
    )
    evidence = list(metadata())
    evidence[-1] = DecisionEvidenceMetadata(
        DecisionDimension.EXTERNAL_REFERENCE,
        DecisionEvidenceAvailability.COMPLETE,
        DecisionFreshness.FRESH,
    )

    with pytest.raises(ValueError, match="immutable"):
        decision_input(
            external_signals=(signal,),
            evidence_metadata=tuple(evidence),
        )
