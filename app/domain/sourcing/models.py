"""Immutable language for Founder-assisted sourcing authority."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.domain.decision_engine import OpportunityIdentity
from app.domain.market_intelligence import (
    ArtifactReference,
    MarketObservationIdentity,
    MarketObservationScope,
)


SOURCING_AUTHORITY_SCHEMA_VERSION = "founder-sourcing-admission-v2"
DOMESTIC_SELLING_SOURCING_AUTHORITY_SCHEMA_VERSION = "founder-sourcing-admission-v3"
DOMESTIC_SELLING_PRODUCT_LINEAGE_SCHEMA_VERSION = "domestic-selling-product-lineage-v1"
SUPPLIER_IDENTITY_SCHEMA_VERSION = "supplier-identity-v1"
SOURCING_PRODUCT_IDENTITY_SCHEMA_VERSION = "sourcing-product-identity-v1"
SUPPLIER_QUOTE_SCHEMA_VERSION = "supplier-quote-revision-v1"
PRODUCT_MATCH_VERIFICATION_SCHEMA_VERSION = "sourcing-product-match-v1"
SOURCING_EVIDENCE_SCHEMA_VERSION = "sourcing-evidence-reference-v1"
SOURCING_ECONOMICS_SOURCE_REFERENCE_SCHEMA_VERSION = "sourcing-economics-source-reference-v1"


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _optional(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text or None")
    return value.strip() or None


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _positive(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


class CommercialFactAvailability(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"


class ShippingScope(StrEnum):
    SUPPLIER_SIDE = "supplier_side"
    INTERNATIONAL_FREIGHT = "international_freight"
    DOMESTIC_INBOUND = "domestic_inbound"


class MatchVerificationStatus(StrEnum):
    VERIFIED_MATCH = "verified_match"
    VERIFIED_MISMATCH = "verified_mismatch"
    NEEDS_REVIEW = "needs_review"


class SourcingEvidenceKind(StrEnum):
    MANUAL_ENTRY = "manual_entry"
    SUPPLIER_PAGE = "supplier_page"
    QUOTE_DOCUMENT = "quote_document"
    ARTIFACT = "artifact"
    OTHER = "other"


@dataclass(frozen=True, slots=True)
class SourcingMoneyFact:
    availability: CommercialFactAvailability
    amount: Decimal | None = None
    currency: str | None = None

    def __post_init__(self) -> None:
        try:
            availability = CommercialFactAvailability(self.availability)
        except ValueError as error:
            raise ValueError("unsupported commercial fact availability") from error
        if availability is CommercialFactAvailability.KNOWN:
            if not isinstance(self.amount, Decimal):
                raise TypeError("known amount must be Decimal")
            if not self.amount.is_finite():
                raise ValueError("amount must be finite")
            if self.amount < 0:
                raise ValueError("amount cannot be negative")
            currency = _required(self.currency, "currency").upper()  # type: ignore[arg-type]
            if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
                raise ValueError("currency must be a three-letter code")
            object.__setattr__(self, "currency", currency)
        elif self.amount is not None or self.currency is not None:
            raise ValueError("unknown/not-applicable money must not carry amount or currency")
        object.__setattr__(self, "availability", availability)


@dataclass(frozen=True, slots=True)
class SourcingQuantityFact:
    availability: CommercialFactAvailability
    quantity: int | None = None

    def __post_init__(self) -> None:
        try:
            availability = CommercialFactAvailability(self.availability)
        except ValueError as error:
            raise ValueError("unsupported commercial fact availability") from error
        if availability is CommercialFactAvailability.KNOWN:
            if self.quantity is None:
                raise ValueError("known quantity requires a value")
            _positive(self.quantity, "quantity")
        elif self.quantity is not None:
            raise ValueError("unknown/not-applicable quantity must not carry a value")
        object.__setattr__(self, "availability", availability)


@dataclass(frozen=True, slots=True)
class ShippingTerm:
    scope: ShippingScope
    cost: SourcingMoneyFact

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "scope", ShippingScope(self.scope))
        except ValueError as error:
            raise ValueError("unsupported shipping scope") from error
        if not isinstance(self.cost, SourcingMoneyFact):
            raise TypeError("cost must be SourcingMoneyFact")


@dataclass(frozen=True, slots=True)
class SourcingEvidenceReference:
    kind: SourcingEvidenceKind
    source_reference: str
    observed_at: datetime
    artifact_reference: ArtifactReference | None = None
    schema_version: str = SOURCING_EVIDENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        try:
            kind = SourcingEvidenceKind(self.kind)
        except ValueError as error:
            raise ValueError("unsupported sourcing evidence kind") from error
        if self.artifact_reference is not None and not isinstance(
            self.artifact_reference, ArtifactReference
        ):
            raise TypeError("artifact_reference must be ArtifactReference or None")
        if kind is SourcingEvidenceKind.ARTIFACT and self.artifact_reference is None:
            raise ValueError("artifact evidence requires artifact_reference")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "source_reference", _required(self.source_reference, "source_reference"))
        _aware(self.observed_at, "observed_at")
        object.__setattr__(self, "schema_version", _required(self.schema_version, "schema_version"))


@dataclass(frozen=True, slots=True)
class SupplierIdentity:
    supplier_id: str
    source_platform: str
    external_supplier_reference: str | None = None
    display_name: str | None = None
    schema_version: str = SUPPLIER_IDENTITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "supplier_id", _required(self.supplier_id, "supplier_id"))
        object.__setattr__(self, "source_platform", _required(self.source_platform, "source_platform").lower())
        object.__setattr__(self, "external_supplier_reference", _optional(self.external_supplier_reference, "external_supplier_reference"))
        object.__setattr__(self, "display_name", _optional(self.display_name, "display_name"))
        object.__setattr__(self, "schema_version", _required(self.schema_version, "schema_version"))


@dataclass(frozen=True, slots=True)
class SourcingProductIdentity:
    sourcing_product_id: str
    supplier_id: str
    external_product_reference: str
    option_reference: str | None
    sku_reference: str | None
    source_url: str | None
    observed_at: datetime
    schema_version: str = SOURCING_PRODUCT_IDENTITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("sourcing_product_id", "supplier_id", "external_product_reference"):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        for name in ("option_reference", "sku_reference", "source_url"):
            object.__setattr__(self, name, _optional(getattr(self, name), name))
        _aware(self.observed_at, "observed_at")
        object.__setattr__(self, "schema_version", _required(self.schema_version, "schema_version"))


@dataclass(frozen=True, slots=True)
class SellingProductLineage:
    opportunity_identity: OpportunityIdentity
    candidate_id: str
    candidate_opportunity_binding_id: str
    product_observation_snapshot_id: str
    market_observation_identity: MarketObservationIdentity

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.market_observation_identity, MarketObservationIdentity):
            raise TypeError("market_observation_identity must be MarketObservationIdentity")
        for name in (
            "candidate_id", "candidate_opportunity_binding_id",
            "product_observation_snapshot_id",
        ):
            object.__setattr__(self, name, _required(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class DomesticSellingProductLineage:
    opportunity_identity: OpportunityIdentity
    domestic_selling_admission_id: str
    source_opportunity_identity: OpportunityIdentity
    source_product_observation_snapshot_id: str
    market_observation_identity: MarketObservationIdentity
    product_equivalence_evidence_reference: str
    schema_version: str = DOMESTIC_SELLING_PRODUCT_LINEAGE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("opportunity_identity", "source_opportunity_identity"):
            if not isinstance(getattr(self, name), OpportunityIdentity):
                raise TypeError(f"{name} must be OpportunityIdentity")
        if self.opportunity_identity == self.source_opportunity_identity:
            raise ValueError("source and domestic Opportunity identities must differ")
        if not isinstance(self.market_observation_identity, MarketObservationIdentity):
            raise TypeError("market_observation_identity must be MarketObservationIdentity")
        if self.market_observation_identity.market.upper() != "KR":
            raise ValueError("domestic selling lineage Market identity must be KR")
        if self.market_observation_identity.scope not in {
            MarketObservationScope.LISTING,
            MarketObservationScope.CANONICAL_PRODUCT,
        }:
            raise ValueError(
                "domestic selling lineage must identify a listing or canonical product"
            )
        for name in (
            "domestic_selling_admission_id",
            "source_product_observation_snapshot_id",
            "product_equivalence_evidence_reference",
        ):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        if self.schema_version != DOMESTIC_SELLING_PRODUCT_LINEAGE_SCHEMA_VERSION:
            raise ValueError("unsupported domestic selling Product lineage version")


SellingProductLineageValue = SellingProductLineage | DomesticSellingProductLineage


def _is_selling_lineage(value: object) -> bool:
    return isinstance(value, (SellingProductLineage, DomesticSellingProductLineage))


@dataclass(frozen=True, slots=True)
class SupplierQuoteRevision:
    quote_id: str
    revision: int
    sourcing_product_id: str
    unit_price: SourcingMoneyFact
    minimum_order_quantity: SourcingQuantityFact
    quoted_quantity: SourcingQuantityFact
    shipping_terms: tuple[ShippingTerm, ...]
    lead_time_availability: CommercialFactAvailability
    lead_time_days: int | None
    observed_at: datetime
    valid_until: datetime | None
    evidence: SourcingEvidenceReference
    schema_version: str = SUPPLIER_QUOTE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "quote_id", _required(self.quote_id, "quote_id"))
        _positive(self.revision, "revision")
        object.__setattr__(self, "sourcing_product_id", _required(self.sourcing_product_id, "sourcing_product_id"))
        if not isinstance(self.unit_price, SourcingMoneyFact):
            raise TypeError("unit_price must be SourcingMoneyFact")
        if not isinstance(self.minimum_order_quantity, SourcingQuantityFact):
            raise TypeError("minimum_order_quantity must be SourcingQuantityFact")
        if not isinstance(self.quoted_quantity, SourcingQuantityFact):
            raise TypeError("quoted_quantity must be SourcingQuantityFact")
        if not isinstance(self.shipping_terms, tuple):
            raise TypeError("shipping_terms must be a tuple")
        if any(not isinstance(value, ShippingTerm) for value in self.shipping_terms):
            raise TypeError("shipping_terms must contain ShippingTerm values")
        scopes = tuple(value.scope for value in self.shipping_terms)
        if len(set(scopes)) != len(scopes):
            raise ValueError("shipping scopes must be unique")
        if set(scopes) != set(ShippingScope):
            raise ValueError("shipping terms must explicitly cover every shipping scope")
        try:
            availability = CommercialFactAvailability(self.lead_time_availability)
        except ValueError as error:
            raise ValueError("unsupported lead time availability") from error
        if availability is CommercialFactAvailability.KNOWN:
            if self.lead_time_days is None:
                raise ValueError("known lead time requires lead_time_days")
            _positive(self.lead_time_days, "lead_time_days")
        elif self.lead_time_days is not None:
            raise ValueError("unknown/not-applicable lead time cannot carry days")
        object.__setattr__(self, "lead_time_availability", availability)
        _aware(self.observed_at, "observed_at")
        if self.valid_until is not None:
            _aware(self.valid_until, "valid_until")
            if self.valid_until < self.observed_at:
                raise ValueError("valid_until cannot precede observed_at")
        if not isinstance(self.evidence, SourcingEvidenceReference):
            raise TypeError("evidence must be SourcingEvidenceReference")
        object.__setattr__(self, "schema_version", _required(self.schema_version, "schema_version"))


@dataclass(frozen=True, slots=True)
class ProductMatchVerification:
    verification_id: str
    selling_product_lineage: SellingProductLineageValue
    sourcing_product_id: str
    status: MatchVerificationStatus
    verifier_id: str
    verified_at: datetime
    evidence: SourcingEvidenceReference
    proposal_score: Decimal | None = None
    proposal_version: str | None = None
    schema_version: str = PRODUCT_MATCH_VERIFICATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "verification_id", _required(self.verification_id, "verification_id"))
        if not _is_selling_lineage(self.selling_product_lineage):
            raise TypeError("selling_product_lineage must be a supported lineage")
        object.__setattr__(self, "sourcing_product_id", _required(self.sourcing_product_id, "sourcing_product_id"))
        try:
            object.__setattr__(self, "status", MatchVerificationStatus(self.status))
        except ValueError as error:
            raise ValueError("unsupported match verification status") from error
        object.__setattr__(self, "verifier_id", _required(self.verifier_id, "verifier_id"))
        _aware(self.verified_at, "verified_at")
        if not isinstance(self.evidence, SourcingEvidenceReference):
            raise TypeError("evidence must be SourcingEvidenceReference")
        if self.proposal_score is not None:
            if not isinstance(self.proposal_score, Decimal):
                raise TypeError("proposal_score must be Decimal or None")
            if not self.proposal_score.is_finite() or not Decimal("0") <= self.proposal_score <= Decimal("100"):
                raise ValueError("proposal_score must be finite and between 0 and 100")
            object.__setattr__(self, "proposal_version", _required(self.proposal_version, "proposal_version"))  # type: ignore[arg-type]
        elif self.proposal_version is not None:
            raise ValueError("proposal_version requires proposal_score")
        object.__setattr__(self, "schema_version", _required(self.schema_version, "schema_version"))


@dataclass(frozen=True, slots=True)
class SourcingEconomicsSourceReference:
    admission_id: str
    admission_revision: int
    quote_id: str
    quote_revision: int
    schema_version: str = SOURCING_ECONOMICS_SOURCE_REFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("admission_id", "quote_id"):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        for name in ("admission_revision", "quote_revision"):
            _positive(getattr(self, name), name)
        if self.admission_revision != self.quote_revision:
            raise ValueError("admission and quote revisions must match")
        object.__setattr__(self, "schema_version", _required(self.schema_version, "schema_version"))


@dataclass(frozen=True, slots=True)
class FounderSourcingAdmission:
    admission_id: str
    revision: int
    selling_product_lineage: SellingProductLineageValue
    supplier_identity: SupplierIdentity
    sourcing_product_identity: SourcingProductIdentity
    quote_revision: SupplierQuoteRevision
    match_verification: ProductMatchVerification
    admitted_by: str
    requested_at: datetime
    admitted_at: datetime
    schema_version: str = SOURCING_AUTHORITY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "admission_id", _required(self.admission_id, "admission_id"))
        _positive(self.revision, "revision")
        if not _is_selling_lineage(self.selling_product_lineage):
            raise TypeError("selling_product_lineage must be a supported lineage")
        if (
            isinstance(self.selling_product_lineage, DomesticSellingProductLineage)
            and self.schema_version
            != DOMESTIC_SELLING_SOURCING_AUTHORITY_SCHEMA_VERSION
        ):
            raise ValueError("Sourcing admission schema does not match lineage kind")
        if not isinstance(self.supplier_identity, SupplierIdentity):
            raise TypeError("supplier_identity must be SupplierIdentity")
        if not isinstance(self.sourcing_product_identity, SourcingProductIdentity):
            raise TypeError("sourcing_product_identity must be SourcingProductIdentity")
        if not isinstance(self.quote_revision, SupplierQuoteRevision):
            raise TypeError("quote_revision must be SupplierQuoteRevision")
        if not isinstance(self.match_verification, ProductMatchVerification):
            raise TypeError("match_verification must be ProductMatchVerification")
        if self.sourcing_product_identity.supplier_id != self.supplier_identity.supplier_id:
            raise ValueError("Sourcing Product must belong to Supplier")
        if self.quote_revision.sourcing_product_id != self.sourcing_product_identity.sourcing_product_id:
            raise ValueError("Quote must belong to Sourcing Product")
        if self.match_verification.sourcing_product_id != self.sourcing_product_identity.sourcing_product_id:
            raise ValueError("Match verification must reference Sourcing Product")
        if self.match_verification.selling_product_lineage != self.selling_product_lineage:
            raise ValueError("Match verification must preserve selling Product lineage")
        if self.match_verification.status is not MatchVerificationStatus.VERIFIED_MATCH:
            raise ValueError("Sourcing admission requires a verified match")
        if self.revision != self.quote_revision.revision:
            raise ValueError("Admission and Quote revisions must match")
        object.__setattr__(self, "admitted_by", _required(self.admitted_by, "admitted_by"))
        _aware(self.requested_at, "requested_at")
        _aware(self.admitted_at, "admitted_at")
        object.__setattr__(self, "schema_version", _required(self.schema_version, "schema_version"))

    def to_economics_source_reference(self) -> SourcingEconomicsSourceReference:
        return SourcingEconomicsSourceReference(
            self.admission_id, self.revision,
            self.quote_revision.quote_id, self.quote_revision.revision,
        )


__all__ = (
    "CommercialFactAvailability",
    "FounderSourcingAdmission",
    "DomesticSellingProductLineage",
    "SellingProductLineageValue",
    "MatchVerificationStatus",
    "ProductMatchVerification",
    "SellingProductLineage",
    "ShippingScope",
    "ShippingTerm",
    "SourcingEvidenceKind",
    "SourcingEvidenceReference",
    "SourcingEconomicsSourceReference",
    "SourcingMoneyFact",
    "SourcingProductIdentity",
    "SourcingQuantityFact",
    "SupplierIdentity",
    "SupplierQuoteRevision",
    "SOURCING_AUTHORITY_SCHEMA_VERSION",
    "DOMESTIC_SELLING_SOURCING_AUTHORITY_SCHEMA_VERSION",
    "DOMESTIC_SELLING_PRODUCT_LINEAGE_SCHEMA_VERSION",
    "SOURCING_EVIDENCE_SCHEMA_VERSION",
    "SOURCING_PRODUCT_IDENTITY_SCHEMA_VERSION",
    "SUPPLIER_IDENTITY_SCHEMA_VERSION",
    "SUPPLIER_QUOTE_SCHEMA_VERSION",
    "PRODUCT_MATCH_VERIFICATION_SCHEMA_VERSION",
    "SOURCING_ECONOMICS_SOURCE_REFERENCE_SCHEMA_VERSION",
)
