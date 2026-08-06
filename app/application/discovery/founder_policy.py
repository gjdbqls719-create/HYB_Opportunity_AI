"""Application-owned Founder Discovery policy profiles."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from app.domain.discovery_identity import (
    DiscoveryCommand,
    DiscoveryCommandParameters,
)


class FounderDiscoveryPolicyError(ValueError):
    """Base error for invalid Founder Discovery policy usage."""


class FounderDiscoveryPolicyNotFoundError(FounderDiscoveryPolicyError):
    """Raised when an exact profile name and version are unsupported."""


class FounderDiscoveryPolicyConflictError(FounderDiscoveryPolicyError):
    """Raised when one profile identity is assigned more than one value set."""


class FounderDiscoveryCommandProfileMismatchError(FounderDiscoveryPolicyError):
    """Raised when a complete command does not match its referenced profile."""


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FounderDiscoveryPolicyError(f"{name} must be non-empty text")
    if value != value.strip():
        raise FounderDiscoveryPolicyError(
            f"{name} must not contain surrounding whitespace"
        )
    return value


def _decimal_in_range(
    value: Decimal,
    name: str,
    *,
    minimum: Decimal,
    maximum: Decimal | None = None,
) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise FounderDiscoveryPolicyError(f"{name} must be a finite Decimal")
    if value < minimum:
        raise FounderDiscoveryPolicyError(
            f"{name} must be non-negative"
            if minimum == Decimal("0")
            else f"{name} must be at least {minimum}"
        )
    if maximum is not None and value > maximum:
        raise FounderDiscoveryPolicyError(
            f"{name} must be between {minimum} and {maximum}"
        )


@dataclass(frozen=True, slots=True)
class FounderDiscoveryPolicyProfile:
    """Immutable execution policy copied into one Founder Discovery command."""

    profile_name: str
    profile_version: str
    purpose: str
    marketplace: str
    marketplace_source_reference: str
    selling_price_multiplier: Decimal
    shipping_cost: Decimal | None
    marketplace_fee_rate: Decimal
    payment_fee_rate: Decimal
    fixed_fee: Decimal | None
    marketplace_fee_known: bool
    payment_fee_known: bool
    fixed_fee_known: bool
    tax_rate: Decimal
    other_cost: Decimal
    minimum_net_profit: Decimal
    minimum_roi: Decimal
    estimated_monthly_sales: int
    competitor_count: int
    risk_level: str
    match_threshold: Decimal
    target_currency: str | None
    founder_manual_review_required: bool
    automatic_purchase_or_investment_allowed: bool
    guaranteed_profitability_claim_allowed: bool

    def __post_init__(self) -> None:
        for name in (
            "profile_name",
            "profile_version",
            "purpose",
            "marketplace",
            "marketplace_source_reference",
            "risk_level",
        ):
            _required_text(getattr(self, name), name)
        for name in (
            "founder_manual_review_required",
            "automatic_purchase_or_investment_allowed",
            "guaranteed_profitability_claim_allowed",
        ):
            if not isinstance(getattr(self, name), bool):
                raise FounderDiscoveryPolicyError(f"{name} must be bool")
        if self.marketplace != self.marketplace.lower():
            raise FounderDiscoveryPolicyError(
                "marketplace must be canonical lowercase"
            )
        if self.risk_level not in {"low", "medium", "high"}:
            raise FounderDiscoveryPolicyError(
                "risk_level must be one of low, medium, high"
            )
        if self.target_currency is not None:
            _required_text(self.target_currency, "target_currency")
            if self.target_currency != self.target_currency.upper():
                raise FounderDiscoveryPolicyError(
                    "target_currency must be canonical uppercase"
                )
        for name in (
            "shipping_cost",
            "fixed_fee",
        ):
            value = getattr(self, name)
            if value is not None:
                _decimal_in_range(
                    value,
                    name,
                    minimum=Decimal("0"),
                )
        for name in (
            "other_cost",
            "minimum_net_profit",
            "minimum_roi",
        ):
            _decimal_in_range(
                getattr(self, name),
                name,
                minimum=Decimal("0"),
            )
        for name in (
            "marketplace_fee_rate",
            "payment_fee_rate",
            "tax_rate",
        ):
            _decimal_in_range(
                getattr(self, name),
                name,
                minimum=Decimal("0"),
                maximum=Decimal("1"),
            )

        # The Domain contract remains the authority for its execution-value
        # types and ranges. Neutral visible values exercise that validation
        # without importing Engine or CLI defaults.
        self.build_parameters(query="profile-validation", limit=1)

    @property
    def required_policy_references(self) -> tuple[tuple[str, str], ...]:
        return (
            ("founder_discovery_profile", self.profile_name),
            ("founder_discovery_profile_version", self.profile_version),
        )

    @property
    def required_source_references(self) -> tuple[tuple[str, str], ...]:
        return (("marketplace", self.marketplace_source_reference),)

    def build_parameters(
        self,
        *,
        query: str,
        limit: int,
    ) -> DiscoveryCommandParameters:
        """Copy this profile and Founder-adjustable input into Domain values."""

        return DiscoveryCommandParameters(
            query=query,
            selling_price_multiplier=self.selling_price_multiplier,
            shipping_cost=self.shipping_cost,
            marketplace_fee_rate=self.marketplace_fee_rate,
            payment_fee_rate=self.payment_fee_rate,
            fixed_fee=self.fixed_fee,
            marketplace_fee_known=self.marketplace_fee_known,
            payment_fee_known=self.payment_fee_known,
            fixed_fee_known=self.fixed_fee_known,
            tax_rate=self.tax_rate,
            other_cost=self.other_cost,
            minimum_net_profit=self.minimum_net_profit,
            minimum_roi=self.minimum_roi,
            estimated_monthly_sales=self.estimated_monthly_sales,
            competitor_count=self.competitor_count,
            risk_level=self.risk_level,
            limit=limit,
            match_threshold=self.match_threshold,
            target_currency=self.target_currency,
            policy_references=self.required_policy_references,
            source_references=self.required_source_references,
        )

    def validate_command(self, command: DiscoveryCommand) -> DiscoveryCommand:
        """Require every profile-owned command value to match exactly."""

        if not isinstance(command, DiscoveryCommand):
            raise TypeError("command must be DiscoveryCommand")
        expected = self.build_parameters(
            query=command.parameters.query,
            limit=command.parameters.limit,
        )
        if command.parameters != expected:
            raise FounderDiscoveryCommandProfileMismatchError(
                "DiscoveryCommand does not match founder discovery profile "
                f"{self.profile_name}/{self.profile_version}"
            )
        return command


@dataclass(frozen=True, slots=True)
class FounderDiscoveryPolicyResolver:
    """Resolve an immutable profile by its exact versioned identity."""

    profiles: tuple[FounderDiscoveryPolicyProfile, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.profiles, tuple):
            raise TypeError("profiles must be a tuple")
        identities: set[tuple[str, str]] = set()
        for profile in self.profiles:
            if not isinstance(profile, FounderDiscoveryPolicyProfile):
                raise TypeError(
                    "profiles must contain FounderDiscoveryPolicyProfile values"
                )
            identity = (profile.profile_name, profile.profile_version)
            if identity in identities:
                raise FounderDiscoveryPolicyConflictError(
                    "same profile name and version cannot contain multiple values: "
                    f"{profile.profile_name}/{profile.profile_version}"
                )
            identities.add(identity)

    def resolve(
        self,
        profile_name: str,
        profile_version: str,
    ) -> FounderDiscoveryPolicyProfile:
        for profile in self.profiles:
            if (
                profile.profile_name == profile_name
                and profile.profile_version == profile_version
            ):
                return profile
        raise FounderDiscoveryPolicyNotFoundError(
            "unsupported founder discovery profile: "
            f"{profile_name}/{profile_version}"
        )


FOUNDER_CONSERVATIVE_EBAY_US_V1 = FounderDiscoveryPolicyProfile(
    profile_name="founder-conservative-ebay-us",
    profile_version="1.0.0",
    purpose="Founder Validation",
    marketplace="ebay",
    marketplace_source_reference="EBAY_US",
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
    match_threshold=Decimal("90"),
    target_currency="USD",
    founder_manual_review_required=True,
    automatic_purchase_or_investment_allowed=False,
    guaranteed_profitability_claim_allowed=False,
)


PRODUCTION_FOUNDER_DISCOVERY_POLICY_RESOLVER = FounderDiscoveryPolicyResolver(
    (FOUNDER_CONSERVATIVE_EBAY_US_V1,)
)


def resolve_founder_discovery_policy_profile(
    profile_name: str,
    profile_version: str,
) -> FounderDiscoveryPolicyProfile:
    """Stable production lookup for an exact Founder policy version."""

    return PRODUCTION_FOUNDER_DISCOVERY_POLICY_RESOLVER.resolve(
        profile_name,
        profile_version,
    )


__all__ = [
    "FOUNDER_CONSERVATIVE_EBAY_US_V1",
    "PRODUCTION_FOUNDER_DISCOVERY_POLICY_RESOLVER",
    "FounderDiscoveryCommandProfileMismatchError",
    "FounderDiscoveryPolicyConflictError",
    "FounderDiscoveryPolicyError",
    "FounderDiscoveryPolicyNotFoundError",
    "FounderDiscoveryPolicyProfile",
    "FounderDiscoveryPolicyResolver",
    "resolve_founder_discovery_policy_profile",
]
