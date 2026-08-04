from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from app.domain.decision_engine import OpportunityIdentity
from app.domain.discovery_identity import (
    ADMISSION_SNAPSHOT_HANDOFF_SCHEMA_VERSION,
    DISCOVERY_IDENTITY_SCHEMA_VERSION,
    AdmissionSnapshotChainHandoff,
    DiscoveryOpportunityContext,
    OpportunityCandidateIdentity,
)
from app.domain.market_intelligence import (
    MarketObservationIdentity,
    MarketObservationScope,
)


NOW = datetime(2026, 8, 5, 9, tzinfo=timezone.utc)


def market_identity(
    scope: MarketObservationScope = MarketObservationScope.LISTING,
) -> MarketObservationIdentity:
    return MarketObservationIdentity(
        scope=scope,
        market="US",
        marketplace="ebay",
        canonical_product_id=("canonical-1" if scope is MarketObservationScope.CANONICAL_PRODUCT else None),
        marketplace_item_id=("item-1" if scope is MarketObservationScope.LISTING else None),
        normalized_query=("camera" if scope is MarketObservationScope.SEARCH_QUERY else None),
        category=("electronics" if scope is MarketObservationScope.CATEGORY else None),
        variant_identity=None,
        condition="new",
        window_started_at=NOW - timedelta(minutes=1),
        window_ended_at=NOW,
    )


def candidate() -> OpportunityCandidateIdentity:
    return OpportunityCandidateIdentity("candidate-1", "ebay:item-1")


def context() -> DiscoveryOpportunityContext:
    return DiscoveryOpportunityContext(
        candidate(), market_identity(), "execution-1", "command-1", NOW
    )


def handoff() -> AdmissionSnapshotChainHandoff:
    return AdmissionSnapshotChainHandoff(
        discovery_context=context(),
        opportunity_identity=OpportunityIdentity("opportunity-1", "ebay:item-1"),
        product_observation_snapshot_ids=("product-1", "product-2"),
        price_intelligence_snapshot_id="price-1",
        economics_calculation_snapshot_id="economics-1",
        candidate_opportunity_binding_id="binding-1",
        admission_command_id="admit-1",
        handed_off_at=NOW,
    )


def test_candidate_identity_is_distinct_from_authoritative_opportunity_identity() -> None:
    value = candidate()
    assert value.candidate_id == "candidate-1"
    assert not isinstance(value, OpportunityIdentity)
    assert value == OpportunityCandidateIdentity("candidate-1", "ebay:item-1")


def test_context_is_immutable_explicit_and_versioned() -> None:
    value = context()
    assert value.market_observation_identity == market_identity()
    assert value.discovery_execution_id == "execution-1"
    assert value.command_id == "command-1"
    assert value.requested_at == NOW
    assert value.schema_version == DISCOVERY_IDENTITY_SCHEMA_VERSION
    with pytest.raises(FrozenInstanceError):
        value.command_id = "changed"


@pytest.mark.parametrize(
    "scope",
    (MarketObservationScope.SEARCH_QUERY, MarketObservationScope.CATEGORY),
)
def test_context_rejects_non_candidate_market_scope(scope) -> None:
    with pytest.raises(ValueError, match="listing or canonical_product"):
        DiscoveryOpportunityContext(
            candidate(), market_identity(scope), "execution-1", "command-1", NOW
        )


@pytest.mark.parametrize(
    "field",
    ("candidate_id", "discovery_reference", "discovery_execution_id", "command_id"),
)
def test_empty_identity_and_correlation_values_are_rejected(field) -> None:
    if field in {"candidate_id", "discovery_reference"}:
        values = {"candidate_id": "candidate-1", "discovery_reference": "ebay:item-1"}
        values[field] = "  "
        with pytest.raises(ValueError):
            OpportunityCandidateIdentity(**values)
    else:
        values = {
            "candidate_identity": candidate(),
            "market_observation_identity": market_identity(),
            "discovery_execution_id": "execution-1",
            "command_id": "command-1",
            "requested_at": NOW,
        }
        values[field] = "  "
        with pytest.raises(ValueError):
            DiscoveryOpportunityContext(**values)


def test_context_requires_timezone_aware_request_time() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(context(), requested_at=NOW.replace(tzinfo=None))


def test_retry_context_equality_is_value_based_and_deterministic() -> None:
    assert context() == context()
    assert replace(context(), command_id="other") != context()
    assert replace(context(), discovery_execution_id="other") != context()


def test_handoff_explicitly_promotes_candidate_and_preserves_ordered_sources() -> None:
    value = handoff()
    assert value.candidate_identity == candidate()
    assert value.discovery_context == context()
    assert value.market_observation_identity == market_identity()
    assert value.opportunity_identity == OpportunityIdentity(
        "opportunity-1", "ebay:item-1"
    )
    assert value.product_observation_snapshot_ids == ("product-1", "product-2")
    assert value.schema_version == ADMISSION_SNAPSHOT_HANDOFF_SCHEMA_VERSION


def test_handoff_rejects_opportunity_and_candidate_reference_mismatch() -> None:
    with pytest.raises(ValueError, match="discovery references"):
        replace(
            handoff(),
            opportunity_identity=OpportunityIdentity("opportunity-1", "ebay:other"),
        )


def test_handoff_preserves_exact_market_and_retry_correlation_context() -> None:
    changed_market = market_identity(MarketObservationScope.CANONICAL_PRODUCT)
    changed_context = replace(context(), market_observation_identity=changed_market)
    value = replace(handoff(), discovery_context=changed_context)
    assert value.market_observation_identity is changed_market
    assert value.discovery_context.command_id == "command-1"
    assert value.discovery_context.discovery_execution_id == "execution-1"


def test_handoff_rejects_mutable_duplicate_or_missing_source_ids() -> None:
    with pytest.raises(TypeError):
        replace(handoff(), product_observation_snapshot_ids=["product-1"])
    with pytest.raises(ValueError):
        replace(
            handoff(),
            product_observation_snapshot_ids=("product-1", "product-1"),
        )
    with pytest.raises(ValueError):
        replace(handoff(), product_observation_snapshot_ids=())


def test_contract_has_no_identity_generation_or_global_state() -> None:
    assert not hasattr(OpportunityCandidateIdentity, "generate")
    assert not hasattr(DiscoveryOpportunityContext, "current")
    assert not hasattr(AdmissionSnapshotChainHandoff, "save")
