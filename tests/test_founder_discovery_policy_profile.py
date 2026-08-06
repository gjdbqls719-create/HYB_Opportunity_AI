from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application.discovery import (
    FOUNDER_CONSERVATIVE_EBAY_US_V1,
    FounderDiscoveryCommandProfileMismatchError,
    FounderDiscoveryPolicyConflictError,
    FounderDiscoveryPolicyError,
    FounderDiscoveryPolicyNotFoundError,
    FounderDiscoveryPolicyResolver,
    resolve_founder_discovery_policy_profile,
)
from app.domain.discovery_identity import (
    DiscoveryCommand,
    DiscoveryCommandParameters,
)


EXPECTED_POLICY_REFERENCES = (
    ("founder_discovery_profile", "founder-conservative-ebay-us"),
    ("founder_discovery_profile_version", "1.0.0"),
)
EXPECTED_SOURCE_REFERENCES = (("marketplace", "EBAY_US"),)


def test_production_profile_is_immutable_and_preserves_approved_governance() -> None:
    profile = FOUNDER_CONSERVATIVE_EBAY_US_V1

    assert profile.profile_name == "founder-conservative-ebay-us"
    assert profile.profile_version == "1.0.0"
    assert profile.purpose == "Founder Validation"
    assert profile.marketplace == "ebay"
    assert profile.marketplace_source_reference == "EBAY_US"
    assert profile.founder_manual_review_required is True
    assert profile.automatic_purchase_or_investment_allowed is False
    assert profile.guaranteed_profitability_claim_allowed is False
    assert not hasattr(profile, "__dict__")

    with pytest.raises(FrozenInstanceError):
        profile.profile_version = "1.0.1"  # type: ignore[misc]


def test_profile_builds_complete_domain_parameters_with_approved_values() -> None:
    parameters = FOUNDER_CONSERVATIVE_EBAY_US_V1.build_parameters(
        query="mirrorless camera",
        limit=25,
    )

    assert parameters == DiscoveryCommandParameters(
        query="mirrorless camera",
        selling_price_multiplier=Decimal("1.50"),
        shipping_cost=Decimal("12.00"),
        marketplace_fee_rate=Decimal("0.153"),
        payment_fee_rate=Decimal("0.00"),
        fixed_fee=Decimal("0.40"),
        marketplace_fee_known=False,
        payment_fee_known=True,
        fixed_fee_known=True,
        tax_rate=Decimal("0.00"),
        other_cost=Decimal("3.00"),
        minimum_net_profit=Decimal("10.00"),
        minimum_roi=Decimal("30"),
        estimated_monthly_sales=5,
        competitor_count=20,
        risk_level="low",
        limit=25,
        match_threshold=Decimal("90"),
        target_currency="USD",
        policy_references=EXPECTED_POLICY_REFERENCES,
        source_references=EXPECTED_SOURCE_REFERENCES,
    )
    assert parameters.minimum_net_profit == Decimal("10.00")
    assert parameters.minimum_roi == Decimal("30")
    assert parameters.match_threshold == Decimal("90")


def test_required_references_use_domain_canonical_ordering() -> None:
    profile = FOUNDER_CONSERVATIVE_EBAY_US_V1
    parameters = profile.build_parameters(query="camera", limit=10)

    assert profile.required_policy_references == EXPECTED_POLICY_REFERENCES
    assert profile.required_source_references == EXPECTED_SOURCE_REFERENCES
    assert parameters.policy_references == EXPECTED_POLICY_REFERENCES
    assert parameters.source_references == EXPECTED_SOURCE_REFERENCES


def test_production_resolver_uses_exact_name_and_version() -> None:
    resolved = resolve_founder_discovery_policy_profile(
        "founder-conservative-ebay-us",
        "1.0.0",
    )

    assert resolved is FOUNDER_CONSERVATIVE_EBAY_US_V1

    for name, version in (
        ("missing-profile", "1.0.0"),
        ("founder-conservative-ebay-us", "2.0.0"),
        ("", "1.0.0"),
        ("founder-conservative-ebay-us", ""),
    ):
        with pytest.raises(FounderDiscoveryPolicyNotFoundError):
            resolve_founder_discovery_policy_profile(name, version)


def test_resolver_rejects_changed_values_under_the_same_version() -> None:
    changed = replace(
        FOUNDER_CONSERVATIVE_EBAY_US_V1,
        shipping_cost=Decimal("13.00"),
    )

    with pytest.raises(
        FounderDiscoveryPolicyConflictError,
        match="same profile name and version",
    ):
        FounderDiscoveryPolicyResolver(
            (FOUNDER_CONSERVATIVE_EBAY_US_V1, changed)
        )


def test_profile_validates_exact_submitted_command_without_owning_visible_input() -> None:
    profile = FOUNDER_CONSERVATIVE_EBAY_US_V1
    command = DiscoveryCommand(
        command_id="command-1",
        discovery_execution_id="execution-1",
        parameters=profile.build_parameters(query="camera", limit=50),
        requested_at=datetime(2026, 8, 6, tzinfo=timezone.utc),
    )

    assert profile.validate_command(command) is command

    mismatched = replace(
        command,
        parameters=replace(
            command.parameters,
            marketplace_fee_rate=Decimal("0.13"),
        ),
    )
    with pytest.raises(
        FounderDiscoveryCommandProfileMismatchError,
        match="does not match founder discovery profile",
    ):
        profile.validate_command(mismatched)


def test_profile_validation_does_not_depend_on_engine_or_cli_defaults() -> None:
    parameters = FOUNDER_CONSERVATIVE_EBAY_US_V1.build_parameters(
        query="camera",
        limit=10,
    )

    assert parameters.selling_price_multiplier == Decimal("1.50")
    assert parameters.shipping_cost == Decimal("12.00")
    assert parameters.fixed_fee == Decimal("0.40")
    assert parameters.estimated_monthly_sales == 5
    assert parameters.match_threshold == Decimal("90")


@pytest.mark.parametrize(
    ("change", "message"),
    (
        ({"profile_name": ""}, "profile_name"),
        ({"marketplace": "EBAY"}, "marketplace must be canonical lowercase"),
        ({"risk_level": "LOW"}, "risk_level must be one of"),
        (
            {"target_currency": "usd"},
            "target_currency must be canonical uppercase",
        ),
        ({"shipping_cost": Decimal("-1")}, "shipping_cost must be non-negative"),
        (
            {"marketplace_fee_rate": Decimal("1.1")},
            "marketplace_fee_rate must be between",
        ),
    ),
)
def test_profile_rejects_invalid_or_noncanonical_policy_values(
    change: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(FounderDiscoveryPolicyError, match=message):
        replace(FOUNDER_CONSERVATIVE_EBAY_US_V1, **change)
