from dataclasses import FrozenInstanceError, replace

import pytest

from app.application.production_safety_integration import (
    ProductionSafetyEvaluationContext,
    SnapshotCandidateSubjectMismatchError,
    SnapshotMarketIdentityMismatchError,
    SnapshotOpportunityBindingMismatchError,
)
from app.domain.discovery_identity import AdmissionSnapshotChainHandoff
from app.domain.decision_engine import OpportunityIdentity
from test_product_observation_snapshot import snapshot as product_snapshot
from test_price_intelligence_snapshot import snapshot as price_snapshot
from test_economics_calculation_snapshot import snapshot as economics_snapshot
from test_production_safety_integration_foundation import promotion_binding


def chain():
    product=product_snapshot()
    price=replace(price_snapshot(),candidate_identity=product.candidate_identity,
        market_observation_identity=product.market_observation_identity,
        product_observation_snapshot_ids=(product.snapshot_id,"product-2","product-3"))
    economics=replace(economics_snapshot(),market_observation_identity=product.market_observation_identity)
    binding=promotion_binding(product)
    return product,price,economics,binding


def test_product_and_price_are_candidate_scoped_without_opportunity_alias():
    product,price,_,_=chain()
    assert product.candidate_identity==price.candidate_identity
    assert "opportunity_identity" not in product.__dataclass_fields__
    assert "opportunity_identity" not in price.__dataclass_fields__
    assert product.schema_version.endswith("v2") and price.schema_version.endswith("v2")


def test_candidate_market_and_opportunity_binding_are_distinct_lineage_checks():
    product,price,economics,binding=chain()
    with pytest.raises(SnapshotCandidateSubjectMismatchError):
        ProductionSafetyEvaluationContext(product,replace(price,candidate_identity=replace(price.candidate_identity,candidate_id="other")),economics,binding,"opp-1")
    with pytest.raises(SnapshotMarketIdentityMismatchError):
        ProductionSafetyEvaluationContext(product,price,economics,replace(binding,market_observation_identity=replace(product.market_observation_identity,marketplace_item_id="other")),"opp-1")
    with pytest.raises(SnapshotOpportunityBindingMismatchError):
        ProductionSafetyEvaluationContext(product,price,economics,replace(binding,opportunity_id="other"),"opp-1")


def test_post_promotion_economics_is_bridged_without_candidate_id_substitution():
    product,price,economics,binding=chain()
    value=ProductionSafetyEvaluationContext(product,price,economics,binding,"opp-1")
    assert value.product_observation_snapshot.candidate_identity.candidate_id=="candidate-1"
    assert value.economics_calculation_snapshot.opportunity_identity.opportunity_id=="opp-1"
    assert value.candidate_opportunity_binding.candidate_id!="opp-1"


def test_complete_handoff_requires_real_binding_and_snapshot_references():
    product,price,economics,binding=chain()
    handoff=AdmissionSnapshotChainHandoff(
        discovery_context=replace_context(product,binding),
        opportunity_identity=OpportunityIdentity("opp-1","ebay:item-1"),
        product_observation_snapshot_ids=(product.snapshot_id,),
        price_intelligence_snapshot_id=price.snapshot_id,
        economics_calculation_snapshot_id=economics.snapshot_id,
        candidate_opportunity_binding_id=binding.binding_id,
        admission_command_id="promotion-1",handed_off_at=binding.promoted_at)
    assert handoff.candidate_identity==product.candidate_identity
    with pytest.raises(FrozenInstanceError):handoff.admission_command_id="changed"
    with pytest.raises(ValueError):replace(handoff,candidate_opportunity_binding_id=" ")


def replace_context(product,binding):
    from app.domain.discovery_identity import DiscoveryOpportunityContext
    return DiscoveryOpportunityContext(product.candidate_identity,product.market_observation_identity,
        binding.discovery_execution_id,binding.discovery_command_id,binding.promoted_at)
