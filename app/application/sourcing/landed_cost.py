"""Application owner for exact Sourcing landed-cost composition."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import json
from typing import Callable, Protocol

from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing import (
    CostAllocationBasis,
    FounderSourcingAdmission,
    LandedCostComponent,
    LandedCostComponentKind,
    LandedCostComposition,
    ShippingScope,
    SourcingEconomicsBinding,
    SourcingEconomicsBindingReference,
    SourcingEconomicsSourceReference,
)


LANDED_COST_COMPOSITION_COMMAND_SCHEMA_VERSION = "landed-cost-composition-command-v1"
LANDED_COST_COMPOSITION_RECEIPT_SCHEMA_VERSION = "landed-cost-composition-receipt-v1"


class LandedCostCompositionError(RuntimeError): pass
class SourcingEconomicsBindingNotFoundError(LandedCostCompositionError): pass
class LandedCostCompositionSourceNotFoundError(LandedCostCompositionError): pass
class LandedCostCompositionOpportunityMismatchError(LandedCostCompositionError): pass
class LandedCostCompositionExactSourceError(LandedCostCompositionError): pass
class LandedCostCompositionReplayConflictError(LandedCostCompositionError): pass


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class ComposeLandedCostCommand:
    command_id: str
    opportunity_identity: OpportunityIdentity
    binding_reference: SourcingEconomicsBindingReference
    requested_at: datetime
    schema_version: str = LANDED_COST_COMPOSITION_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.binding_reference, SourcingEconomicsBindingReference):
            raise TypeError("binding_reference must be SourcingEconomicsBindingReference")
        _aware(self.requested_at, "requested_at")
        if self.schema_version != LANDED_COST_COMPOSITION_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported composition command version")

    @property
    def fingerprint(self) -> str:
        payload = {
            "command_id": self.command_id,
            "opportunity_identity": {
                "opportunity_id": self.opportunity_identity.opportunity_id,
                "discovery_reference": self.opportunity_identity.discovery_reference,
            },
            "binding_reference": {
                "binding_id": self.binding_reference.binding_id,
                "schema_version": self.binding_reference.schema_version,
            },
            "requested_at": self.requested_at.astimezone(timezone.utc).isoformat(),
            "schema_version": self.schema_version,
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class LandedCostCompositionReceipt:
    command_id: str
    composition_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = LANDED_COST_COMPOSITION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "composition_id", _text(self.composition_id, "composition_id"))
        if len(self.command_fingerprint) != 64:
            raise ValueError("command_fingerprint must be SHA-256 text")
        _aware(self.committed_at, "committed_at")
        if self.schema_version != LANDED_COST_COMPOSITION_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported composition receipt version")


@dataclass(frozen=True, slots=True)
class LandedCostCompositionResult:
    composition: LandedCostComposition
    receipt: LandedCostCompositionReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if self.receipt.composition_id != self.composition.composition_id:
            raise ValueError("receipt must reference composition")


class LandedCostCompositionRepository(Protocol):
    def validate_replay(self, command_id: str, fingerprint: str) -> LandedCostCompositionResult | None: ...
    def get_binding(self, reference: SourcingEconomicsBindingReference) -> SourcingEconomicsBinding | None: ...
    def get_source_admission(self, reference: SourcingEconomicsSourceReference) -> FounderSourcingAdmission | None: ...
    def save_composition(self, command: ComposeLandedCostCommand, composition: LandedCostComposition, receipt: LandedCostCompositionReceipt) -> LandedCostCompositionResult: ...


class ComposeLandedCost:
    def __init__(self, repository: LandedCostCompositionRepository, *,
                 composition_id_generator: Callable[[], str],
                 composed_clock: Callable[[], datetime],
                 committed_clock: Callable[[], datetime]) -> None:
        if not all(callable(value) for value in (composition_id_generator, composed_clock, committed_clock)):
            raise TypeError("composition dependencies must be callable")
        self._repository = repository
        self._identity = composition_id_generator
        self._composed = composed_clock
        self._committed = committed_clock

    def execute(self, command: ComposeLandedCostCommand) -> LandedCostCompositionResult:
        if not isinstance(command, ComposeLandedCostCommand):
            raise TypeError("command must be ComposeLandedCostCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        binding = self._repository.get_binding(command.binding_reference)
        if binding is None:
            raise SourcingEconomicsBindingNotFoundError("exact binding is missing")
        if binding.opportunity_identity != command.opportunity_identity:
            raise LandedCostCompositionOpportunityMismatchError("binding Opportunity differs")
        admission = self._repository.get_source_admission(binding.source_reference)
        if admission is None:
            raise LandedCostCompositionSourceNotFoundError("exact Sourcing source is missing")
        if admission.to_economics_source_reference() != binding.source_reference:
            raise LandedCostCompositionExactSourceError("binding source differs from Admission")
        if admission.selling_product_lineage.opportunity_identity != command.opportunity_identity:
            raise LandedCostCompositionOpportunityMismatchError("Admission Opportunity differs")
        quote = admission.quote_revision
        shipping = {value.scope: value.cost for value in quote.shipping_terms}
        components = (
            LandedCostComponent(LandedCostComponentKind.UNIT_PURCHASE,
                                quote.unit_price.availability, quote.unit_price.amount,
                                quote.unit_price.currency, CostAllocationBasis.PER_UNIT),
            *tuple(LandedCostComponent(kind, shipping[scope].availability,
                                       shipping[scope].amount, shipping[scope].currency,
                                       CostAllocationBasis.UNSPECIFIED)
                   for kind, scope in (
                       (LandedCostComponentKind.SUPPLIER_SIDE_SHIPPING, ShippingScope.SUPPLIER_SIDE),
                       (LandedCostComponentKind.INTERNATIONAL_FREIGHT, ShippingScope.INTERNATIONAL_FREIGHT),
                       (LandedCostComponentKind.DOMESTIC_INBOUND, ShippingScope.DOMESTIC_INBOUND),
                   )),
        )
        composition_id = _text(self._identity(), "composition_id")
        composition = LandedCostComposition(
            composition_id, command.opportunity_identity, command.binding_reference,
            components, quote.minimum_order_quantity, quote.quoted_quantity,
            quote.evidence, command.requested_at, _aware(self._composed(), "composed_at"),
        )
        receipt = LandedCostCompositionReceipt(
            command.command_id, composition_id, command.fingerprint,
            _aware(self._committed(), "committed_at"),
        )
        return self._repository.save_composition(command, composition, receipt)


__all__ = [name for name in globals() if name.startswith("Landed") or name.startswith("Compose") or name.startswith("SourcingEconomicsBindingNot")]
