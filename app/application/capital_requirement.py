"""Application owner for exact-source planned acquisition capital requirements."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Callable, Protocol

from app.domain.capital import (
    PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_DECIMAL_PRECISION,
    PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_POLICY_NAME,
    PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_POLICY_VERSION,
    PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_ROUNDING,
    IntendedOrderQuantity,
    PlannedAcquisitionCapitalRequirement,
    PlannedAcquisitionCapitalRequirementBlockingReason,
    PlannedAcquisitionCapitalRequirementState,
    UpfrontCostScopeStatus,
    UpfrontCostScopeVerification,
    planned_acquisition_capital_amount,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing import (
    AcquisitionCostNormalization,
    LandedCostComposition,
    SourcingEconomicsBinding,
    SourcingEconomicsBindingReference,
)


PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_COMMAND_SCHEMA_VERSION = (
    "planned-acquisition-capital-requirement-command-v1"
)
PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_RECEIPT_SCHEMA_VERSION = (
    "planned-acquisition-capital-requirement-receipt-v1"
)


class PlannedAcquisitionCapitalRequirementError(RuntimeError):
    pass


class PlannedAcquisitionCapitalRequirementSourceNotFoundError(
    PlannedAcquisitionCapitalRequirementError
):
    pass


class PlannedAcquisitionCapitalRequirementLineageError(
    PlannedAcquisitionCapitalRequirementError
):
    pass


class PlannedAcquisitionCapitalRequirementPolicyError(
    PlannedAcquisitionCapitalRequirementError
):
    pass


class PlannedAcquisitionCapitalRequirementReplayConflictError(
    PlannedAcquisitionCapitalRequirementError
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


def _fingerprint_text(value: str) -> str:
    result = _text(value, "command_fingerprint").lower()
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise ValueError("command_fingerprint must be SHA-256 text")
    return result


def _canonical(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _canonical(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _fingerprint(value: object) -> str:
    encoded = json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CalculatePlannedAcquisitionCapitalRequirementCommand:
    command_id: str
    opportunity_identity: OpportunityIdentity
    intended_order_quantity_id: str
    acquisition_normalization_id: str
    scope_status: UpfrontCostScopeStatus
    operator_id: str
    verified_at: datetime
    requested_at: datetime
    policy_name: str
    policy_version: str
    schema_version: str = PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        for name in (
            "intended_order_quantity_id",
            "acquisition_normalization_id",
            "operator_id",
            "policy_name",
            "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "scope_status", UpfrontCostScopeStatus(self.scope_status))
        object.__setattr__(self, "verified_at", _aware(self.verified_at, "verified_at"))
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        if self.schema_version != PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported planned acquisition capital command schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class PlannedAcquisitionCapitalRequirementReceipt:
    command_id: str
    requirement_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "requirement_id", _text(self.requirement_id, "requirement_id"))
        object.__setattr__(self, "command_fingerprint", _fingerprint_text(self.command_fingerprint))
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version != PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported planned acquisition capital receipt schema")


@dataclass(frozen=True, slots=True)
class PlannedAcquisitionCapitalRequirementPublication:
    requirement: PlannedAcquisitionCapitalRequirement
    receipt: PlannedAcquisitionCapitalRequirementReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, PlannedAcquisitionCapitalRequirement):
            raise TypeError("requirement must be PlannedAcquisitionCapitalRequirement")
        if not isinstance(self.receipt, PlannedAcquisitionCapitalRequirementReceipt):
            raise TypeError("receipt must be PlannedAcquisitionCapitalRequirementReceipt")
        if self.receipt.requirement_id != self.requirement.requirement_id:
            raise ValueError("receipt must reference requirement")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class PlannedAcquisitionCapitalRequirementRepository(Protocol):
    def get_intent(self, intent_id: str) -> IntendedOrderQuantity | None: ...
    def get_normalization(self, normalization_id: str) -> AcquisitionCostNormalization | None: ...
    def get_composition(self, composition_id: str) -> LandedCostComposition | None: ...
    def get_binding(self, reference: SourcingEconomicsBindingReference) -> SourcingEconomicsBinding | None: ...
    def validate_replay(self, command_id: str, fingerprint: str) -> PlannedAcquisitionCapitalRequirementPublication | None: ...
    def save_requirement(self, command, requirement, receipt) -> PlannedAcquisitionCapitalRequirementPublication: ...


class CalculatePlannedAcquisitionCapitalRequirement:
    def __init__(
        self,
        repository: PlannedAcquisitionCapitalRequirementRepository,
        *,
        requirement_id_generator: Callable[[], str],
        calculated_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        if not all(callable(value) for value in (requirement_id_generator, calculated_clock, committed_clock)):
            raise TypeError("planned acquisition capital dependencies must be callable")
        self._repository = repository
        self._identity = requirement_id_generator
        self._calculated = calculated_clock
        self._committed = committed_clock

    def execute(
        self,
        command: CalculatePlannedAcquisitionCapitalRequirementCommand,
    ) -> PlannedAcquisitionCapitalRequirementPublication:
        if not isinstance(command, CalculatePlannedAcquisitionCapitalRequirementCommand):
            raise TypeError("command must be CalculatePlannedAcquisitionCapitalRequirementCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        if (
            command.policy_name != PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_POLICY_NAME
            or command.policy_version != PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_POLICY_VERSION
        ):
            raise PlannedAcquisitionCapitalRequirementPolicyError(
                "unsupported planned acquisition capital policy"
            )

        intent = self._repository.get_intent(command.intended_order_quantity_id)
        if intent is None:
            raise PlannedAcquisitionCapitalRequirementSourceNotFoundError(
                "exact Intended Order Quantity is missing"
            )
        normalization = self._repository.get_normalization(
            command.acquisition_normalization_id
        )
        if normalization is None:
            raise PlannedAcquisitionCapitalRequirementSourceNotFoundError(
                "exact Acquisition Cost Normalization is missing"
            )
        composition = self._repository.get_composition(normalization.composition_id)
        if composition is None:
            raise PlannedAcquisitionCapitalRequirementSourceNotFoundError(
                "exact Landed Cost Composition is missing"
            )
        binding = self._repository.get_binding(composition.binding_reference)
        if binding is None:
            raise PlannedAcquisitionCapitalRequirementSourceNotFoundError(
                "exact Sourcing Economics Binding is missing"
            )

        self._validate_lineage(command, intent, normalization, composition, binding)
        verification = UpfrontCostScopeVerification(
            status=command.scope_status,
            intended_order_quantity_id=intent.intent_id,
            acquisition_normalization_id=normalization.normalization_id,
            operator_id=command.operator_id,
            verified_at=command.verified_at,
        )
        if verification.status is UpfrontCostScopeStatus.COMPLETE:
            state = PlannedAcquisitionCapitalRequirementState.CALCULABLE
            amount = planned_acquisition_capital_amount(
                normalization.total_per_unit_acquisition_cost,
                intent.quantity,
            )
            reasons = ()
        else:
            state = PlannedAcquisitionCapitalRequirementState.BLOCKED
            amount = None
            reasons = (
                PlannedAcquisitionCapitalRequirementBlockingReason.UPFRONT_COST_SCOPE_UNVERIFIED,
            )

        source = binding.source_reference
        requirement = PlannedAcquisitionCapitalRequirement(
            requirement_id=_text(self._identity(), "requirement_id"),
            opportunity_identity=command.opportunity_identity,
            state=state,
            intended_order_quantity_id=intent.intent_id,
            acquisition_normalization_id=normalization.normalization_id,
            sourcing_binding_id=binding.binding_id,
            sourcing_admission_id=source.admission_id,
            sourcing_admission_revision=source.admission_revision,
            quote_id=source.quote_id,
            quote_revision=source.quote_revision,
            quantity=intent.quantity,
            quantity_unit=intent.quantity_unit,
            normalized_acquisition_cost_per_unit=normalization.total_per_unit_acquisition_cost,
            currency=normalization.target_currency,
            planned_acquisition_capital=amount,
            scope_verification=verification,
            blocking_reasons=reasons,
            policy_name=command.policy_name,
            policy_version=command.policy_version,
            policy_precision=PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_DECIMAL_PRECISION,
            policy_rounding=PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_ROUNDING,
            requested_at=command.requested_at,
            calculated_at=_aware(self._calculated(), "calculated_at"),
        )
        receipt = PlannedAcquisitionCapitalRequirementReceipt(
            command_id=command.command_id,
            requirement_id=requirement.requirement_id,
            command_fingerprint=command.fingerprint,
            committed_at=_aware(self._committed(), "committed_at"),
        )
        return self._repository.save_requirement(command, requirement, receipt)

    @staticmethod
    def _validate_lineage(command, intent, normalization, composition, binding) -> None:
        if any(
            value != command.opportunity_identity
            for value in (
                intent.opportunity_identity,
                normalization.opportunity_identity,
                composition.opportunity_identity,
                binding.opportunity_identity,
            )
        ):
            raise PlannedAcquisitionCapitalRequirementLineageError(
                "requirement sources use different Opportunity lineage"
            )
        if normalization.composition_id != composition.composition_id:
            raise PlannedAcquisitionCapitalRequirementLineageError(
                "normalization does not reference exact composition"
            )
        if binding.reference != composition.binding_reference:
            raise PlannedAcquisitionCapitalRequirementLineageError(
                "composition does not reference exact Sourcing binding"
            )
        source = binding.source_reference
        if (
            source.admission_id != intent.sourcing_admission_id
            or source.admission_revision != intent.sourcing_admission_revision
            or source.quote_id != intent.quote_id
            or source.quote_revision != intent.quote_revision
        ):
            raise PlannedAcquisitionCapitalRequirementLineageError(
                "intent and normalization use different Sourcing lineage"
            )


__all__ = [
    name
    for name in globals()
    if name.startswith(("Calculate", "Planned", "PLANNED"))
]
