"""Application owner for immutable actual acquisition settlement revisions."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Callable, Protocol

from app.domain.capital import (
    ACTUAL_ACQUISITION_POLICY_NAME,
    ACTUAL_ACQUISITION_POLICY_VERSION,
    ActualAcquisitionCostFact,
    ActualAcquisitionFactAvailability,
    ActualAcquisitionSettlement,
    ActualAcquisitionSettlementSourceManifest,
    ActualAcquisitionSettlementState,
    OtherMandatoryAcquisitionCosts,
    PurchaseExecutionRecord,
    evaluate_actual_acquisition_settlement,
)


ACTUAL_ACQUISITION_COMMAND_SCHEMA_VERSION = "actual-acquisition-settlement-command-v1"
ACTUAL_ACQUISITION_RECEIPT_SCHEMA_VERSION = "actual-acquisition-settlement-receipt-v1"


class ActualAcquisitionSettlementError(RuntimeError):
    pass


class ActualAcquisitionSettlementSourceNotFoundError(ActualAcquisitionSettlementError):
    pass


class ActualAcquisitionSettlementOpportunityConflictError(ActualAcquisitionSettlementError):
    pass


class ActualAcquisitionSettlementRevisionConflictError(ActualAcquisitionSettlementError):
    pass


class ActualAcquisitionSettlementTerminalConflictError(ActualAcquisitionSettlementError):
    pass


class ActualAcquisitionSettlementReplayConflictError(ActualAcquisitionSettlementError):
    pass


class ActualAcquisitionSettlementSourceLineageError(ActualAcquisitionSettlementError):
    pass


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _optional_text(value: str | None, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _currency(value: str) -> str:
    result = _text(value, "target_currency").upper()
    if len(result) != 3 or not result.isascii() or not result.isalpha():
        raise ValueError("target_currency must be a three-letter currency code")
    return result


def _canonical(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _canonical(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
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


def _fingerprint_text(value: str) -> str:
    result = _text(value, "command_fingerprint").lower()
    if len(result) != 64 or any(character not in "0123456789abcdef" for character in result):
        raise ValueError("command_fingerprint must be SHA-256 text")
    return result


@dataclass(frozen=True, slots=True)
class AdmitActualAcquisitionSettlementCommand:
    command_id: str
    opportunity_id: str
    purchase_execution_record_id: str
    predecessor_settlement_id: str | None
    target_currency: str
    fixed_cost_facts: tuple[ActualAcquisitionCostFact, ...]
    other_mandatory_costs: OtherMandatoryAcquisitionCosts
    operator_id: str
    requested_at: datetime
    policy_name: str = ACTUAL_ACQUISITION_POLICY_NAME
    policy_version: str = ACTUAL_ACQUISITION_POLICY_VERSION
    schema_version: str = ACTUAL_ACQUISITION_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("command_id", "opportunity_id", "purchase_execution_record_id", "operator_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "predecessor_settlement_id", _optional_text(self.predecessor_settlement_id, "predecessor_settlement_id"))
        object.__setattr__(self, "target_currency", _currency(self.target_currency))
        if not isinstance(self.fixed_cost_facts, tuple) or any(
            not isinstance(value, ActualAcquisitionCostFact) for value in self.fixed_cost_facts
        ):
            raise TypeError("fixed_cost_facts must be a tuple of ActualAcquisitionCostFact")
        if not isinstance(self.other_mandatory_costs, OtherMandatoryAcquisitionCosts):
            raise TypeError("other_mandatory_costs must be OtherMandatoryAcquisitionCosts")
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        if (
            self.policy_name != ACTUAL_ACQUISITION_POLICY_NAME
            or self.policy_version != ACTUAL_ACQUISITION_POLICY_VERSION
        ):
            raise ValueError("unsupported actual acquisition settlement policy")
        if self.schema_version != ACTUAL_ACQUISITION_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported actual acquisition settlement command schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class ActualAcquisitionSettlementReceipt:
    command_id: str
    settlement_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = ACTUAL_ACQUISITION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "settlement_id", _text(self.settlement_id, "settlement_id"))
        object.__setattr__(self, "command_fingerprint", _fingerprint_text(self.command_fingerprint))
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version != ACTUAL_ACQUISITION_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported actual acquisition settlement receipt schema")


@dataclass(frozen=True, slots=True)
class ActualAcquisitionSettlementPublication:
    settlement: ActualAcquisitionSettlement
    receipt: ActualAcquisitionSettlementReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.settlement, ActualAcquisitionSettlement):
            raise TypeError("settlement must be ActualAcquisitionSettlement")
        if not isinstance(self.receipt, ActualAcquisitionSettlementReceipt):
            raise TypeError("receipt must be ActualAcquisitionSettlementReceipt")
        if self.receipt.settlement_id != self.settlement.settlement_id:
            raise ValueError("receipt must reference settlement")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class ActualAcquisitionSettlementRepository(Protocol):
    def validate_replay(self, command_id: str, fingerprint: str) -> ActualAcquisitionSettlementPublication | None: ...
    def get_purchase_execution_record(self, record_id: str) -> PurchaseExecutionRecord | None: ...
    def get_settlement(self, settlement_id: str) -> ActualAcquisitionSettlement | None: ...
    def get_chain_tip_for_cardinality(self, purchase_execution_record_id: str) -> ActualAcquisitionSettlement | None: ...
    def save(self, command, settlement, receipt) -> ActualAcquisitionSettlementPublication: ...


def actual_acquisition_manifest_from_purchase(
    purchase: PurchaseExecutionRecord,
) -> ActualAcquisitionSettlementSourceManifest:
    source = purchase.source_manifest
    return ActualAcquisitionSettlementSourceManifest(
        opportunity_identity=source.opportunity_identity,
        purchase_execution_record_id=purchase.record_id,
        real_money_execution_intent_id=source.real_money_execution_intent_id,
        founder_capital_approval_id=source.founder_capital_approval_id,
        capital_gate_id=source.capital_gate_id,
        capital_requirement_id=source.capital_requirement_id,
        intended_order_quantity_id=source.intended_order_quantity_id,
        sourcing_admission_id=source.sourcing_admission_id,
        sourcing_admission_revision=source.sourcing_admission_revision,
        supplier_id=source.supplier_id,
        source_platform=source.source_platform,
        external_supplier_reference=source.external_supplier_reference,
        sourcing_product_id=source.sourcing_product_id,
        external_product_reference=source.external_product_reference,
        option_reference=source.option_reference,
        sku_reference=source.sku_reference,
        quote_id=source.quote_id,
        quote_revision=source.quote_revision,
        executed_quantity=purchase.actual_quantity,
        executed_quantity_unit=purchase.actual_quantity_unit,
        external_order_reference=purchase.external_order_reference,
        purchase_executed_at=purchase.executed_at,
        purchase_policy_name=purchase.policy_name,
        purchase_policy_version=purchase.policy_version,
        purchase_record_schema_version=purchase.schema_version,
    )


class AdmitActualAcquisitionSettlement:
    def __init__(
        self,
        repository: ActualAcquisitionSettlementRepository,
        *,
        settlement_id_generator: Callable[[], str],
        admitted_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        if not all(callable(value) for value in (settlement_id_generator, admitted_clock, committed_clock)):
            raise TypeError("actual acquisition settlement dependencies must be callable")
        self._repository = repository
        self._identity = settlement_id_generator
        self._admitted = admitted_clock
        self._committed = committed_clock

    def execute(
        self, command: AdmitActualAcquisitionSettlementCommand
    ) -> ActualAcquisitionSettlementPublication:
        if not isinstance(command, AdmitActualAcquisitionSettlementCommand):
            raise TypeError("command must be AdmitActualAcquisitionSettlementCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)

        purchase = self._repository.get_purchase_execution_record(
            command.purchase_execution_record_id
        )
        if purchase is None:
            raise ActualAcquisitionSettlementSourceNotFoundError(
                "exact Purchase Execution Record is missing"
            )
        if purchase.source_manifest.opportunity_identity.opportunity_id != command.opportunity_id:
            raise ActualAcquisitionSettlementOpportunityConflictError(
                "Purchase Execution Record differs from route Opportunity"
            )

        tip = self._repository.get_chain_tip_for_cardinality(purchase.record_id)
        late_replay = self._repository.validate_replay(
            command.command_id, command.fingerprint
        )
        if late_replay is not None:
            return replace(late_replay, replayed=True)
        predecessor = None
        if command.predecessor_settlement_id is None:
            if tip is not None:
                raise ActualAcquisitionSettlementRevisionConflictError(
                    "first settlement revision already exists"
                )
            revision = 1
        else:
            predecessor = self._repository.get_settlement(
                command.predecessor_settlement_id
            )
            if predecessor is None:
                raise ActualAcquisitionSettlementSourceNotFoundError(
                    "exact predecessor settlement is missing"
                )
            if predecessor.source_manifest.purchase_execution_record_id != purchase.record_id:
                raise ActualAcquisitionSettlementRevisionConflictError(
                    "predecessor belongs to a different Purchase Execution Record"
                )
            if tip is None or tip.settlement_id != predecessor.settlement_id:
                raise ActualAcquisitionSettlementRevisionConflictError(
                    "predecessor is not the exact settlement chain tip"
                )
            if predecessor.state is ActualAcquisitionSettlementState.COMPLETE:
                raise ActualAcquisitionSettlementTerminalConflictError(
                    "COMPLETE settlement is terminal"
                )
            if predecessor.target_currency != command.target_currency:
                raise ActualAcquisitionSettlementRevisionConflictError(
                    "settlement target currency cannot change across revisions"
                )
            for old, new in zip(predecessor.fixed_cost_facts, command.fixed_cost_facts, strict=True):
                if (
                    old.availability is not ActualAcquisitionFactAvailability.UNKNOWN
                    and new.availability is ActualAcquisitionFactAvailability.UNKNOWN
                ):
                    raise ActualAcquisitionSettlementRevisionConflictError(
                        "known settlement fact cannot regress to UNKNOWN"
                    )
            if (
                predecessor.other_mandatory_costs.availability
                is not ActualAcquisitionFactAvailability.UNKNOWN
                and command.other_mandatory_costs.availability
                is ActualAcquisitionFactAvailability.UNKNOWN
            ):
                raise ActualAcquisitionSettlementRevisionConflictError(
                    "resolved other mandatory scope cannot regress to UNKNOWN"
                )
            revision = predecessor.revision + 1

        reasons, normalized, batch_total, per_unit = evaluate_actual_acquisition_settlement(
            command.fixed_cost_facts,
            command.other_mandatory_costs,
            command.target_currency,
            purchase.actual_quantity,
        )
        state = (
            ActualAcquisitionSettlementState.BLOCKED
            if reasons
            else ActualAcquisitionSettlementState.COMPLETE
        )
        settlement = ActualAcquisitionSettlement(
            settlement_id=_text(self._identity(), "settlement_id"),
            source_manifest=actual_acquisition_manifest_from_purchase(purchase),
            revision=revision,
            predecessor_settlement_id=command.predecessor_settlement_id,
            target_currency=command.target_currency,
            fixed_cost_facts=command.fixed_cost_facts,
            other_mandatory_costs=command.other_mandatory_costs,
            normalized_categories=normalized,
            state=state,
            blocking_reasons=reasons,
            acquisition_batch_total=batch_total,
            acquisition_per_unit=per_unit,
            operator_id=command.operator_id,
            requested_at=command.requested_at,
            admitted_at=_aware(self._admitted(), "admitted_at"),
            policy_name=command.policy_name,
            policy_version=command.policy_version,
        )
        receipt = ActualAcquisitionSettlementReceipt(
            command_id=command.command_id,
            settlement_id=settlement.settlement_id,
            command_fingerprint=command.fingerprint,
            committed_at=_aware(self._committed(), "committed_at"),
        )
        return self._repository.save(command, settlement, receipt)


__all__ = [
    name
    for name in globals()
    if name.startswith(("ActualAcquisition", "AdmitActual", "ACTUAL_ACQUISITION"))
    or name == "actual_acquisition_manifest_from_purchase"
]
