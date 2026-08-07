"""Application command and receipt contracts for sourcing admission."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json

from app.domain.sourcing import (
    CommercialFactAvailability,
    FounderSourcingAdmission,
    MatchVerificationStatus,
    SellingProductLineage,
    ShippingTerm,
    SourcingEvidenceReference,
    SourcingMoneyFact,
    SourcingQuantityFact,
)


SOURCING_ADMISSION_COMMAND_SCHEMA_VERSION = "founder-sourcing-command-v1"
SOURCING_ADMISSION_RECEIPT_SCHEMA_VERSION = "founder-sourcing-receipt-v1"
SOURCING_QUOTE_REVISION_COMMAND_SCHEMA_VERSION = "sourcing-quote-revision-command-v1"


class SourcingAuthorityError(RuntimeError):
    pass


class InvalidSourcingCommandError(ValueError):
    pass


class UnknownSupplierIdentityError(SourcingAuthorityError):
    pass


class UnknownSourcingProductIdentityError(SourcingAuthorityError):
    pass


class SourcingProductMatchNotVerifiedError(SourcingAuthorityError):
    pass


class SourcingAdmissionNotFoundError(SourcingAuthorityError):
    pass


class SourcingAdmissionReplayConflictError(SourcingAuthorityError):
    pass


class SourcingQuoteRevisionConflictError(SourcingAuthorityError):
    pass


class SourcingIdentityGenerationError(SourcingAuthorityError):
    pass


class MalformedSourcingPersistenceError(SourcingAuthorityError):
    pass


class UnsupportedSourcingPersistenceVersionError(MalformedSourcingPersistenceError):
    pass


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidSourcingCommandError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise InvalidSourcingCommandError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvalidSourcingCommandError(f"{name} must be timezone-aware")
    return value


def _canonical(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Decimal):
        return {"kind": "decimal", "value": str(value)}
    if isinstance(value, datetime):
        return {"kind": "datetime", "value": value.astimezone(timezone.utc).isoformat()}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("sourcing command mappings require text keys")
        return {key: _canonical(value[key]) for key in sorted(value)}
    if is_dataclass(value):
        return {
            key: _canonical(item)
            for key, item in sorted(asdict(value).items())
        }
    raise TypeError(f"unsupported sourcing command value: {type(value).__name__}")


def _fingerprint(value: object) -> str:
    payload = json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class AdmitFounderSourcingCommand:
    command_id: str
    selling_product_lineage: SellingProductLineage
    supplier_platform: str
    external_supplier_reference: str | None
    supplier_display_name: str | None
    external_product_reference: str
    option_reference: str | None
    sku_reference: str | None
    source_url: str | None
    product_observed_at: datetime
    quoted_unit_price: SourcingMoneyFact
    minimum_order_quantity: SourcingQuantityFact
    quoted_quantity: SourcingQuantityFact
    shipping_terms: tuple[ShippingTerm, ...]
    lead_time_availability: CommercialFactAvailability
    lead_time_days: int | None
    quote_observed_at: datetime
    quote_valid_until: datetime | None
    quote_evidence: SourcingEvidenceReference
    match_status: MatchVerificationStatus
    match_evidence: SourcingEvidenceReference
    proposal_score: Decimal | None
    proposal_version: str | None
    operator_id: str
    requested_at: datetime
    schema_version: str = SOURCING_ADMISSION_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("command_id", "supplier_platform", "external_product_reference", "operator_id"):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        if not isinstance(self.selling_product_lineage, SellingProductLineage):
            raise InvalidSourcingCommandError(
                "selling_product_lineage must be SellingProductLineage"
            )
        if not isinstance(self.quoted_unit_price, SourcingMoneyFact):
            raise InvalidSourcingCommandError("quoted_unit_price must be SourcingMoneyFact")
        if not isinstance(self.shipping_terms, tuple):
            raise InvalidSourcingCommandError("shipping_terms must be a tuple")
        if not isinstance(self.quote_evidence, SourcingEvidenceReference):
            raise InvalidSourcingCommandError("quote_evidence must be SourcingEvidenceReference")
        if not isinstance(self.match_evidence, SourcingEvidenceReference):
            raise InvalidSourcingCommandError("match_evidence must be SourcingEvidenceReference")
        for name in ("product_observed_at", "quote_observed_at", "requested_at"):
            _aware(getattr(self, name), name)
        if self.quote_valid_until is not None:
            _aware(self.quote_valid_until, "quote_valid_until")
        if self.schema_version != SOURCING_ADMISSION_COMMAND_SCHEMA_VERSION:
            raise InvalidSourcingCommandError("unsupported sourcing admission command version")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class ReviseFounderSourcingQuoteCommand:
    command_id: str
    admission_id: str
    expected_revision: int
    quoted_unit_price: SourcingMoneyFact
    minimum_order_quantity: SourcingQuantityFact
    quoted_quantity: SourcingQuantityFact
    shipping_terms: tuple[ShippingTerm, ...]
    lead_time_availability: CommercialFactAvailability
    lead_time_days: int | None
    quote_observed_at: datetime
    quote_valid_until: datetime | None
    quote_evidence: SourcingEvidenceReference
    operator_id: str
    requested_at: datetime
    schema_version: str = SOURCING_QUOTE_REVISION_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("command_id", "admission_id", "operator_id"):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        if isinstance(self.expected_revision, bool) or not isinstance(self.expected_revision, int) or self.expected_revision < 1:
            raise InvalidSourcingCommandError("expected_revision must be positive")
        if not isinstance(self.quoted_unit_price, SourcingMoneyFact):
            raise InvalidSourcingCommandError("quoted_unit_price must be SourcingMoneyFact")
        if not isinstance(self.shipping_terms, tuple):
            raise InvalidSourcingCommandError("shipping_terms must be a tuple")
        if not isinstance(self.quote_evidence, SourcingEvidenceReference):
            raise InvalidSourcingCommandError("quote_evidence must be SourcingEvidenceReference")
        for name in ("quote_observed_at", "requested_at"):
            _aware(getattr(self, name), name)
        if self.quote_valid_until is not None:
            _aware(self.quote_valid_until, "quote_valid_until")
        if self.schema_version != SOURCING_QUOTE_REVISION_COMMAND_SCHEMA_VERSION:
            raise InvalidSourcingCommandError("unsupported quote revision command version")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class SourcingAdmissionReceipt:
    command_id: str
    admission_id: str
    resulting_revision: int
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = SOURCING_ADMISSION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("command_id", "admission_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
            object.__setattr__(self, name, value.strip())
        if isinstance(self.resulting_revision, bool) or not isinstance(self.resulting_revision, int) or self.resulting_revision < 1:
            raise ValueError("resulting_revision must be positive")
        fingerprint = self.command_fingerprint
        if not isinstance(fingerprint, str) or len(fingerprint) != 64 or any(
            char not in "0123456789abcdef" for char in fingerprint
        ):
            raise ValueError("command_fingerprint must be lowercase SHA-256 text")
        if not isinstance(self.committed_at, datetime) or self.committed_at.tzinfo is None or self.committed_at.utcoffset() is None:
            raise ValueError("committed_at must be timezone-aware")
        if self.schema_version != SOURCING_ADMISSION_RECEIPT_SCHEMA_VERSION:
            raise UnsupportedSourcingPersistenceVersionError(
                "unsupported sourcing admission receipt version"
            )


@dataclass(frozen=True, slots=True)
class SourcingAdmissionResult:
    admission: FounderSourcingAdmission
    receipt: SourcingAdmissionReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.admission, FounderSourcingAdmission):
            raise TypeError("admission must be FounderSourcingAdmission")
        if not isinstance(self.receipt, SourcingAdmissionReceipt):
            raise TypeError("receipt must be SourcingAdmissionReceipt")
        if self.receipt.admission_id != self.admission.admission_id:
            raise ValueError("receipt must reference admission")
        if self.receipt.resulting_revision != self.admission.revision:
            raise ValueError("receipt must preserve resulting revision")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


@dataclass(frozen=True, slots=True)
class SourcingEconomicsSourceReference:
    admission_id: str
    admission_revision: int
    quote_id: str
    quote_revision: int

    def __post_init__(self) -> None:
        for name in ("admission_id", "quote_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
            object.__setattr__(self, name, value.strip())
        for name in ("admission_revision", "quote_revision"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name} must be positive")
        if self.admission_revision != self.quote_revision:
            raise ValueError("admission and quote revisions must match")
