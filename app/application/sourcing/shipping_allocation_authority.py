"""Durable application owner for explicit shipping-allocation authority."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Callable, Protocol

from app.domain.sourcing.landed_cost import (
    CostAllocationBasis,
    LandedCostComponent,
    LandedCostComponentKind,
    LandedCostComposition,
)
from app.domain.sourcing.models import CommercialFactAvailability
from app.domain.sourcing.shipping_allocation import (
    ShippingAllocationAuthority,
    ShippingAllocationAuthorityCode,
    ShippingAllocationAuthorityCommand,
    ShippingAllocationAuthorityDenominatorSource,
    ShippingAllocationAuthorityStatus,
    ShippingAllocationBasisAuthoritySource,
    ShippingAllocationDenominator,
)


SHIPPING_ALLOCATION_AUTHORITY_RECEIPT_SCHEMA_VERSION = (
    "shipping-allocation-authority-receipt-v1"
)


class ShippingAllocationAuthorityError(RuntimeError):
    pass


class ShippingAllocationSourceNotFoundError(ShippingAllocationAuthorityError):
    pass


class ShippingAllocationOpportunityMismatchError(ShippingAllocationAuthorityError):
    pass


class ShippingAllocationComponentNotFoundError(ShippingAllocationAuthorityError):
    pass


class ShippingAllocationBasisConflictError(ShippingAllocationAuthorityError):
    pass


class ShippingAllocationProvenanceError(ShippingAllocationAuthorityError):
    pass


class ShippingAllocationAuthorityReplayConflictError(
    ShippingAllocationAuthorityError
):
    pass


class ShippingAllocationAuthorityReceiptIntegrityError(
    ShippingAllocationAuthorityError
):
    pass


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class ShippingAllocationAuthorityReceipt:
    command_id: str
    authority_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = SHIPPING_ALLOCATION_AUTHORITY_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(
            self,
            "authority_id",
            _text(self.authority_id, "authority_id"),
        )
        fingerprint = _text(self.command_fingerprint, "command_fingerprint").lower()
        if len(fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in fingerprint
        ):
            raise ValueError("command_fingerprint must be SHA-256 text")
        object.__setattr__(self, "command_fingerprint", fingerprint)
        object.__setattr__(
            self,
            "committed_at",
            _aware(self.committed_at, "committed_at"),
        )
        if self.schema_version != SHIPPING_ALLOCATION_AUTHORITY_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported shipping allocation receipt version")


@dataclass(frozen=True, slots=True)
class ShippingAllocationAuthorityResult:
    authority: ShippingAllocationAuthority
    receipt: ShippingAllocationAuthorityReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.authority, ShippingAllocationAuthority):
            raise TypeError("authority must be ShippingAllocationAuthority")
        if not isinstance(self.receipt, ShippingAllocationAuthorityReceipt):
            raise TypeError("receipt must be ShippingAllocationAuthorityReceipt")
        if self.authority.authority_id != self.receipt.authority_id:
            raise ValueError("receipt must reference authority")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class ShippingAllocationAuthorityRepository(Protocol):
    def get_composition(
        self,
        composition_id: str,
    ) -> LandedCostComposition | None: ...

    def validate_replay(
        self,
        command_id: str,
        fingerprint: str,
    ) -> ShippingAllocationAuthorityResult | None: ...

    def save_authority(
        self,
        command: ShippingAllocationAuthorityCommand,
        authority: ShippingAllocationAuthority,
        receipt: ShippingAllocationAuthorityReceipt,
    ) -> ShippingAllocationAuthorityResult: ...


def _source_component(
    composition: LandedCostComposition,
    component_kind: LandedCostComponentKind,
) -> LandedCostComponent:
    if component_kind is LandedCostComponentKind.UNIT_PURCHASE:
        raise ShippingAllocationComponentNotFoundError(
            "shipping allocation cannot target unit purchase"
        )
    for value in composition.components:
        if value.kind is component_kind:
            return value
    raise ShippingAllocationComponentNotFoundError("component is missing")


class AdmitShippingAllocationAuthority:
    def __init__(
        self,
        repository: ShippingAllocationAuthorityRepository,
        *,
        authority_id_generator: Callable[[], str],
        admitted_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        if not all(
            callable(value)
            for value in (authority_id_generator, admitted_clock, committed_clock)
        ):
            raise TypeError("shipping allocation authority dependencies must be callable")
        self._repository = repository
        self._identity = authority_id_generator
        self._admitted = admitted_clock
        self._committed = committed_clock

    def execute(
        self,
        command: ShippingAllocationAuthorityCommand,
    ) -> ShippingAllocationAuthorityResult:
        if not isinstance(command, ShippingAllocationAuthorityCommand):
            raise TypeError("command must be ShippingAllocationAuthorityCommand")

        replay = self._repository.validate_replay(
            command.command_id,
            command.fingerprint,
        )
        if replay is not None:
            return replace(replay, replayed=True)

        composition = self._repository.get_composition(command.composition_id)
        if composition is None:
            raise ShippingAllocationSourceNotFoundError("composition is missing")
        if composition.opportunity_identity != command.opportunity_identity:
            raise ShippingAllocationOpportunityMismatchError(
                "composition opportunity differs from command"
            )

        component = _source_component(composition, command.component_kind)
        basis, basis_source, operator_id, verified_at, evidence = self._basis(
            command,
            composition,
            component,
        )
        authority = self._admit(
            command,
            composition,
            component,
            basis,
            basis_source,
            operator_id,
            verified_at,
            evidence,
            authority_id=_text(self._identity(), "authority_id"),
            admitted_at=_aware(self._admitted(), "admitted_at"),
        )
        receipt = ShippingAllocationAuthorityReceipt(
            command_id=command.command_id,
            authority_id=authority.authority_id,
            command_fingerprint=command.fingerprint,
            committed_at=_aware(self._committed(), "committed_at"),
        )
        return self._repository.save_authority(command, authority, receipt)

    @staticmethod
    def _basis(command, composition, component):
        original = component.allocation_basis
        requested = command.effective_allocation_basis
        if original is not CostAllocationBasis.UNSPECIFIED:
            if requested is not None and requested is not original:
                raise ShippingAllocationBasisConflictError(
                    "explicit source allocation basis cannot be overridden"
                )
            if command.per_order_denominator is not None and original is not CostAllocationBasis.PER_ORDER:
                raise ShippingAllocationProvenanceError(
                    "per-order denominator requires PER_ORDER basis"
                )
            return (
                original,
                ShippingAllocationBasisAuthoritySource.SOURCE_DECLARED,
                None,
                None,
                composition.evidence_reference,
            )

        effective = requested or CostAllocationBasis.UNSPECIFIED
        if effective is CostAllocationBasis.UNSPECIFIED:
            if command.per_order_denominator is not None:
                raise ShippingAllocationProvenanceError(
                    "denominator cannot infer an allocation basis"
                )
            return (
                effective,
                ShippingAllocationBasisAuthoritySource.SOURCE_DECLARED,
                None,
                None,
                composition.evidence_reference,
            )

        if (
            command.operator_id is None
            or command.verified_at is None
            or command.evidence_reference is None
        ):
            raise ShippingAllocationProvenanceError(
                "explicit allocation basis requires operator, verified_at, and evidence"
            )
        if (
            command.per_order_denominator is not None
            and effective is not CostAllocationBasis.PER_ORDER
        ):
            raise ShippingAllocationProvenanceError(
                "per-order denominator requires PER_ORDER basis"
            )
        return (
            effective,
            ShippingAllocationBasisAuthoritySource.OPERATOR_ADMITTED,
            command.operator_id,
            command.verified_at,
            command.evidence_reference,
        )

    @staticmethod
    def _admit(
        command,
        composition,
        component,
        basis,
        basis_source,
        operator_id,
        verified_at,
        evidence,
        *,
        authority_id,
        admitted_at,
    ):
        common = dict(
            authority_id=authority_id,
            composition_id=composition.composition_id,
            opportunity_identity=composition.opportunity_identity,
            component_kind=component.kind,
            original_allocation_basis=component.allocation_basis,
            allocation_basis=basis,
            basis_authority_source=basis_source,
            evidence_reference=evidence,
            requested_at=command.requested_at,
            admitted_at=admitted_at,
            operator_id=operator_id,
            verified_at=verified_at,
        )

        if basis is CostAllocationBasis.PER_UNIT:
            return ShippingAllocationAuthority(
                status=ShippingAllocationAuthorityStatus.RESOLVED,
                **common,
            )

        if basis is CostAllocationBasis.PER_QUOTED_QUANTITY:
            quantity = composition.quoted_quantity
            if (
                quantity.availability is not CommercialFactAvailability.KNOWN
                or quantity.quantity is None
            ):
                return ShippingAllocationAuthority(
                    status=ShippingAllocationAuthorityStatus.UNRESOLVED,
                    unresolved_code=(
                        ShippingAllocationAuthorityCode
                        .PER_QUOTED_QUANTITY_DENOMINATOR_MISSING
                    ),
                    **common,
                )
            return ShippingAllocationAuthority(
                status=ShippingAllocationAuthorityStatus.RESOLVED,
                denominator=ShippingAllocationDenominator(
                    quantity=quantity.quantity,
                    source=(
                        ShippingAllocationAuthorityDenominatorSource.SOURCE_DERIVED
                    ),
                    source_reference=(
                        f"composition:{composition.composition_id}:quoted_quantity"
                    ),
                    quantity_unit="unit",
                ),
                **common,
            )

        if basis is CostAllocationBasis.PER_ORDER:
            if command.per_order_denominator is None:
                return ShippingAllocationAuthority(
                    status=ShippingAllocationAuthorityStatus.UNRESOLVED,
                    unresolved_code=(
                        ShippingAllocationAuthorityCode.PER_ORDER_DENOMINATOR_MISSING
                    ),
                    **common,
                )
            if command.per_order_denominator <= 0:
                return ShippingAllocationAuthority(
                    status=ShippingAllocationAuthorityStatus.UNRESOLVED,
                    unresolved_code=(
                        ShippingAllocationAuthorityCode.PER_ORDER_DENOMINATOR_INVALID
                    ),
                    **common,
                )
            return ShippingAllocationAuthority(
                status=ShippingAllocationAuthorityStatus.RESOLVED,
                denominator=ShippingAllocationDenominator(
                    quantity=command.per_order_denominator,
                    source=(
                        ShippingAllocationAuthorityDenominatorSource.FOUNDER_ADMITTED
                    ),
                    source_reference=evidence.source_reference,
                    quantity_unit=command.per_order_denominator_unit,
                ),
                **common,
            )

        if basis is CostAllocationBasis.PER_WEIGHT:
            return ShippingAllocationAuthority(
                status=ShippingAllocationAuthorityStatus.UNRESOLVED,
                unresolved_code=ShippingAllocationAuthorityCode.PER_WEIGHT_UNSUPPORTED,
                **common,
            )

        return ShippingAllocationAuthority(
            status=ShippingAllocationAuthorityStatus.UNRESOLVED,
            unresolved_code=ShippingAllocationAuthorityCode.UNSPECIFIED_UNRESOLVED,
            **common,
        )


__all__ = [
    name
    for name in globals()
    if name.startswith("Shipping")
    or name.startswith("SHIPPING")
    or name.startswith("Admit")
]
