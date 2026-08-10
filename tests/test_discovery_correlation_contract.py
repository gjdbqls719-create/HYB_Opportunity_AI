from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.discovery_identity import (
    CANDIDATE_HANDOFF_COLLECTOR_OBSERVATION_SCHEMA_VERSION,
    CANDIDATE_HANDOFF_POLICY_NAME,
    CANDIDATE_HANDOFF_POLICY_VERSION,
    CandidateIssuanceReplayKey,
    CollectedProductObservation,
    DiscoveryCommand,
    DiscoveryCommandParameters,
    DiscoveryExecutionResult,
    DiscoveryGroupMembershipConflictError,
    DiscoveryMarketIdentityResolutionError,
    DiscoveryObservationIdentityConflictError,
    FinalizedProductGroup,
    MalformedCollectorObservationError,
    MalformedDiscoveryCommandError,
    UnsupportedDiscoveryCommandVersionError,
)
from app.domain.market_intelligence import (
    MarketObservationIdentity,
    MarketObservationScope,
)
from app.domain.product_observation import CollectorProvenance
from test_product_observation_snapshot import observed_product


NOW = datetime(2026, 8, 5, 10, tzinfo=timezone.utc)


def provenance() -> CollectorProvenance:
    return CollectorProvenance("ebay_search", "v1", "ebay:item-1")


def parameters(**changes) -> DiscoveryCommandParameters:
    values = {
        "query": "camera",
        "selling_price_multiplier": Decimal("1.5"),
        "shipping_cost": None,
        "marketplace_fee_rate": Decimal("0.15"),
        "payment_fee_rate": Decimal("0"),
        "fixed_fee": None,
        "marketplace_fee_known": False,
        "payment_fee_known": False,
        "fixed_fee_known": False,
        "tax_rate": Decimal("0"),
        "other_cost": Decimal("0"),
        "minimum_net_profit": Decimal("10"),
        "minimum_roi": Decimal("20"),
        "estimated_monthly_sales": 100,
        "competitor_count": 20,
        "risk_level": "medium",
        "limit": 10,
        "match_threshold": Decimal("75"),
        "target_currency": None,
        "policy_references": (
            ("economics", "verified-economics-v1"),
            ("grouping", "title-similarity-v1"),
        ),
        "source_references": (),
    }
    values.update(changes)
    return DiscoveryCommandParameters(**values)


def command(**changes) -> DiscoveryCommand:
    values = {
        "command_id": "command-1",
        "discovery_execution_id": "execution-1",
        "parameters": parameters(),
        "requested_at": NOW,
    }
    values.update(changes)
    return DiscoveryCommand(**values)


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


def observation(**changes) -> CollectedProductObservation:
    product = observed_product()
    values = {
        "observation_id": "observation-1",
        "discovery_execution_id": "execution-1",
        "source_marketplace": product.marketplace,
        "source_item_id": product.item_id,
        "product": product,
        "collector_provenance": provenance(),
        "observed_at": NOW,
    }
    values.update(changes)
    return CollectedProductObservation(**values)


def group(**changes) -> FinalizedProductGroup:
    values = {
        "finalized_group_id": "group-opaque-1",
        "discovery_execution_id": "execution-1",
        "observation_ids": ("observation-1", "observation-2"),
        "grouping_policy_version": "title-similarity-v1",
        "representative_observation_id": "observation-1",
        "finalized_at": NOW,
    }
    values.update(changes)
    return FinalizedProductGroup(**values)


def test_command_is_immutable_versioned_and_fingerprinted() -> None:
    value = command()
    assert value == command()
    assert value.fingerprint == command().fingerprint
    assert len(value.fingerprint) == 64
    with pytest.raises(FrozenInstanceError):
        value.command_id = "changed"


def test_command_payload_is_deterministic_and_decimal_preserving() -> None:
    first = command()
    second = command(
        parameters=parameters(
            policy_references=(
                ("grouping", "title-similarity-v1"),
                ("economics", "verified-economics-v1"),
            )
        )
    )
    assert first.fingerprint == second.fingerprint
    assert isinstance(first.parameters.minimum_roi, Decimal)
    assert first.parameters.minimum_roi == Decimal("20")


def test_changed_payload_changes_fingerprint_but_command_id_is_independent() -> None:
    original = command()
    changed = command(parameters=parameters(limit=20))
    new_command = command(command_id="command-2")
    assert original.fingerprint != changed.fingerprint
    assert original.fingerprint == new_command.fingerprint


def test_bool_int_and_arbitrary_mutable_context_cannot_be_confused() -> None:
    with pytest.raises(MalformedDiscoveryCommandError):
        parameters(estimated_monthly_sales=True)
    with pytest.raises(MalformedDiscoveryCommandError):
        parameters(marketplace_fee_known=1)
    with pytest.raises(MalformedDiscoveryCommandError):
        parameters(source_references=(("context", object()),))
    with pytest.raises(MalformedDiscoveryCommandError):
        parameters(policy_references=[("grouping", "v1")])


def test_command_validates_timezone_and_exact_version() -> None:
    with pytest.raises(MalformedDiscoveryCommandError, match="timezone-aware"):
        command(requested_at=NOW.replace(tzinfo=None))
    with pytest.raises(UnsupportedDiscoveryCommandVersionError):
        command(schema_version="future")


def test_collector_observation_preserves_exact_source_without_market_inference() -> None:
    value = observation()
    assert value.source_marketplace == value.product.marketplace
    assert value.source_item_id == value.product.item_id
    assert value.collector_provenance == provenance()
    assert value.candidate_market_identity is None


def test_collector_observation_accepts_only_exact_explicit_candidate_market_identity() -> None:
    value = observation(candidate_market_identity=market_identity())
    assert value.candidate_market_identity == market_identity()
    with pytest.raises(DiscoveryObservationIdentityConflictError):
        observation(source_item_id="other")
    with pytest.raises(DiscoveryMarketIdentityResolutionError):
        observation(candidate_market_identity=market_identity(MarketObservationScope.SEARCH_QUERY))


def candidate_ready_observation(**changes) -> CollectedProductObservation:
    source = observation()
    values = {
        "collector_provenance": replace(
            source.collector_provenance,
            collector_name="ebay",
        ),
        "candidate_market_identity": replace(
            market_identity(),
            condition=source.product.condition,
            window_started_at=source.observed_at,
            window_ended_at=source.observed_at,
        ),
        "candidate_discovery_reference": "collector:ebay:item-1",
        "candidate_handoff_policy_name": CANDIDATE_HANDOFF_POLICY_NAME,
        "candidate_handoff_policy_version": CANDIDATE_HANDOFF_POLICY_VERSION,
        "schema_version": CANDIDATE_HANDOFF_COLLECTOR_OBSERVATION_SCHEMA_VERSION,
    }
    values.update(changes)
    return replace(source, **values)


def test_candidate_handoff_is_all_or_none_and_policy_exact() -> None:
    value = candidate_ready_observation()
    assert value.is_candidate_eligible is True
    with pytest.raises(MalformedCollectorObservationError):
        candidate_ready_observation(candidate_discovery_reference=None)
    with pytest.raises(MalformedCollectorObservationError, match="unsupported"):
        candidate_ready_observation(candidate_handoff_policy_version="future")
    with pytest.raises(DiscoveryObservationIdentityConflictError):
        candidate_ready_observation(
            candidate_market_identity=replace(
                value.candidate_market_identity,
                market="KR",
            )
        )


def test_historical_observation_remains_non_candidate_eligible() -> None:
    assert observation().is_candidate_eligible is False
    assert (
        observation(candidate_market_identity=market_identity()).is_candidate_eligible
        is False
    )


def test_finalized_group_preserves_order_and_has_separate_stable_id_and_fingerprint() -> None:
    value = group()
    assert value.observation_ids == ("observation-1", "observation-2")
    assert value.finalized_group_id == "group-opaque-1"
    assert value.membership_fingerprint == group().membership_fingerprint
    assert value.finalized_group_id not in value.membership_fingerprint


def test_group_membership_order_policy_and_representative_affect_fingerprint() -> None:
    original = group()
    assert original.membership_fingerprint != replace(
        original,
        observation_ids=("observation-2", "observation-1"),
    ).membership_fingerprint
    assert original.membership_fingerprint != replace(
        original, grouping_policy_version="future-grouping"
    ).membership_fingerprint
    assert original.membership_fingerprint != replace(
        original, representative_observation_id="observation-2"
    ).membership_fingerprint


def test_group_rejects_duplicate_or_external_representative() -> None:
    with pytest.raises(DiscoveryGroupMembershipConflictError):
        group(observation_ids=("observation-1", "observation-1"))
    with pytest.raises(DiscoveryGroupMembershipConflictError):
        group(representative_observation_id="other")


def test_command_result_represents_ordered_and_successful_zero_results() -> None:
    result = DiscoveryExecutionResult(
        "command-1", "execution-1", ("group-2", "group-1"), NOW
    )
    zero = DiscoveryExecutionResult("command-1", "execution-1", (), NOW)
    assert result.finalized_group_ids == ("group-2", "group-1")
    assert result.is_zero_result is False
    assert zero.is_zero_result is True
    assert zero.fingerprint == DiscoveryExecutionResult(
        "command-1", "execution-1", (), NOW
    ).fingerprint


def test_candidate_issuance_replay_key_is_derivable_without_candidate_id() -> None:
    key = CandidateIssuanceReplayKey(
        command_id=command().command_id,
        finalized_group_id=group().finalized_group_id,
        command_fingerprint=command().fingerprint,
        membership_fingerprint=group().membership_fingerprint,
        market_observation_identity=market_identity(),
    )
    assert len(key.fingerprint) == 64
    assert "candidate" not in key.__dataclass_fields__
    assert key == CandidateIssuanceReplayKey(
        "command-1",
        "group-opaque-1",
        command().fingerprint,
        group().membership_fingerprint,
        market_identity(),
    )


def test_contract_has_no_group_index_generator_registry_or_persistence() -> None:
    assert "group_index" not in FinalizedProductGroup.__dataclass_fields__
    assert not hasattr(FinalizedProductGroup, "generate")
    assert not hasattr(DiscoveryCommand, "current")
    assert not hasattr(DiscoveryExecutionResult, "save")
