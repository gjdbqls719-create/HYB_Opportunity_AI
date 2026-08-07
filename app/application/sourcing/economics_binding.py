from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from typing import Callable, Protocol

from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing import (
    FounderSourcingAdmission,
    SourcingEconomicsBinding,
    SourcingEconomicsBindingReference,
    SourcingEconomicsSourceReference,
)


SOURCING_ECONOMICS_BINDING_COMMAND_SCHEMA_VERSION = "sourcing-economics-binding-command-v1"
SOURCING_ECONOMICS_BINDING_RECEIPT_SCHEMA_VERSION = "sourcing-economics-binding-receipt-v1"


class SourcingEconomicsBindingError(RuntimeError): pass
class SourcingEconomicsSourceNotFoundError(SourcingEconomicsBindingError): pass
class SourcingEconomicsBindingOpportunityMismatchError(SourcingEconomicsBindingError): pass
class SourcingEconomicsExactRevisionError(SourcingEconomicsBindingError): pass
class SourcingEconomicsBindingReplayConflictError(SourcingEconomicsBindingError): pass
class SourcingEconomicsBindingIdentityError(SourcingEconomicsBindingError): pass
class MalformedSourcingEconomicsBindingError(SourcingEconomicsBindingError): pass
class UnsupportedSourcingEconomicsBindingVersionError(MalformedSourcingEconomicsBindingError): pass


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class BindSourcingEconomicsSourceCommand:
    command_id: str
    opportunity_identity: OpportunityIdentity
    source_reference: SourcingEconomicsSourceReference
    requested_at: datetime
    schema_version: str = SOURCING_ECONOMICS_BINDING_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.source_reference, SourcingEconomicsSourceReference):
            raise TypeError("source_reference must be SourcingEconomicsSourceReference")
        _aware(self.requested_at, "requested_at")
        if self.schema_version != SOURCING_ECONOMICS_BINDING_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported Sourcing Economics Binding command version")

    @property
    def fingerprint(self) -> str:
        source = self.source_reference
        payload = {
            "command_id": self.command_id,
            "opportunity_identity": {
                "opportunity_id": self.opportunity_identity.opportunity_id,
                "discovery_reference": self.opportunity_identity.discovery_reference,
            },
            "source_reference": {
                "admission_id": source.admission_id,
                "admission_revision": source.admission_revision,
                "quote_id": source.quote_id,
                "quote_revision": source.quote_revision,
                "schema_version": source.schema_version,
            },
            "requested_at": self.requested_at.astimezone(timezone.utc).isoformat(),
            "schema_version": self.schema_version,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class SourcingEconomicsBindingReceipt:
    command_id: str
    binding_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = SOURCING_ECONOMICS_BINDING_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("command_id", "binding_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if len(self.command_fingerprint) != 64 or any(
            value not in "0123456789abcdef" for value in self.command_fingerprint
        ):
            raise ValueError("command_fingerprint must be SHA-256 text")
        _aware(self.committed_at, "committed_at")
        if self.schema_version != SOURCING_ECONOMICS_BINDING_RECEIPT_SCHEMA_VERSION:
            raise UnsupportedSourcingEconomicsBindingVersionError(
                "unsupported Sourcing Economics Binding receipt version"
            )


@dataclass(frozen=True, slots=True)
class SourcingEconomicsBindingResult:
    binding: SourcingEconomicsBinding
    receipt: SourcingEconomicsBindingReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if self.receipt.binding_id != self.binding.binding_id:
            raise ValueError("receipt must reference binding")

    @property
    def reference(self) -> SourcingEconomicsBindingReference:
        return self.binding.reference


class SourcingEconomicsBindingRepository(Protocol):
    def validate_replay(self, command_id: str, fingerprint: str) -> SourcingEconomicsBindingResult | None: ...
    def get_source_admission(self, reference: SourcingEconomicsSourceReference) -> FounderSourcingAdmission | None: ...
    def save_binding(self, command: BindSourcingEconomicsSourceCommand, binding: SourcingEconomicsBinding, receipt: SourcingEconomicsBindingReceipt) -> SourcingEconomicsBindingResult: ...
    def get_binding(self, binding_id: str) -> SourcingEconomicsBinding | None: ...
    def get_receipt(self, command_id: str) -> SourcingEconomicsBindingReceipt | None: ...


class BindSourcingEconomicsSource:
    def __init__(self, repository: SourcingEconomicsBindingRepository, *,
                 binding_id_generator: Callable[[], str],
                 bound_clock: Callable[[], datetime],
                 committed_clock: Callable[[], datetime]) -> None:
        if not all(callable(value) for value in (binding_id_generator, bound_clock, committed_clock)):
            raise TypeError("binding dependencies must be callable")
        self._repository = repository
        self._identity = binding_id_generator
        self._bound = bound_clock
        self._committed = committed_clock

    def execute(self, command: BindSourcingEconomicsSourceCommand) -> SourcingEconomicsBindingResult:
        if not isinstance(command, BindSourcingEconomicsSourceCommand):
            raise TypeError("command must be BindSourcingEconomicsSourceCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        admission = self._repository.get_source_admission(command.source_reference)
        if admission is None:
            raise SourcingEconomicsSourceNotFoundError("exact Sourcing Admission revision is missing")
        if admission.selling_product_lineage.opportunity_identity != command.opportunity_identity:
            raise SourcingEconomicsBindingOpportunityMismatchError(
                "Sourcing Admission Opportunity lineage differs"
            )
        if admission.to_economics_source_reference() != command.source_reference:
            raise SourcingEconomicsExactRevisionError(
                "Sourcing Admission and Quote revision reference differs"
            )
        binding_id = _text(self._identity(), "binding_id")
        binding = SourcingEconomicsBinding(
            binding_id, command.opportunity_identity, command.source_reference,
            command.requested_at, _aware(self._bound(), "bound_at"),
        )
        receipt = SourcingEconomicsBindingReceipt(
            command.command_id, binding_id, command.fingerprint,
            _aware(self._committed(), "committed_at"),
        )
        return self._repository.save_binding(command, binding, receipt)


__all__ = [name for name in globals() if name.startswith("Sourcing") or name.startswith("Bind") or name.startswith("Malformed") or name.startswith("Unsupported")]
