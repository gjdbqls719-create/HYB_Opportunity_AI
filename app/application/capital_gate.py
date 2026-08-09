"""Application owner for exact-source Capital Gate policy evaluation."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Callable, Protocol

from app.domain.capital import (
    CAPITAL_GATE_POLICY_NAME,
    CAPITAL_GATE_POLICY_VERSION,
    CAPITAL_READINESS_POLICY_NAME,
    CAPITAL_READINESS_POLICY_VERSION,
    DEPLOYABLE_CAPITAL_SEMANTICS_VERSION,
    PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_POLICY_NAME,
    PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_POLICY_VERSION,
    CapitalGateAssessment,
    CapitalGateBlockingReasonCode,
    CapitalGateEvaluatedFacts,
    CapitalGateRejectionReasonCode,
    CapitalGateSourceManifest,
    CapitalGateState,
    CapitalReadinessAssessment,
    CapitalReadinessState,
    DeployableCapitalSnapshot,
    IntendedOrderQuantity,
    PlannedAcquisitionCapitalRequirement,
    PlannedAcquisitionCapitalRequirementState,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.opportunity import (
    CONSERVATIVE_ECONOMICS_POLICY_NAME,
    CONSERVATIVE_ECONOMICS_POLICY_VERSION,
    ConservativeEconomicsResult,
    ConservativeEconomicsStatus,
)
from app.domain.sourcing import CommercialFactAvailability, FounderSourcingAdmission


CAPITAL_GATE_COMMAND_SCHEMA_VERSION = "capital-gate-command-v1"
CAPITAL_GATE_RECEIPT_SCHEMA_VERSION = "capital-gate-receipt-v1"


class CapitalGateError(RuntimeError):
    pass


class CapitalGateSourceNotFoundError(CapitalGateError):
    pass


class CapitalGatePolicyError(CapitalGateError):
    pass


class CapitalGateReplayConflictError(CapitalGateError):
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
    encoded = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EvaluateCapitalGateCommand:
    command_id: str
    opportunity_identity: OpportunityIdentity
    capital_readiness_assessment_id: str
    capital_requirement_id: str
    deployable_capital_snapshot_id: str
    requested_at: datetime
    policy_name: str = CAPITAL_GATE_POLICY_NAME
    policy_version: str = CAPITAL_GATE_POLICY_VERSION
    schema_version: str = CAPITAL_GATE_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "command_id",
            "capital_readiness_assessment_id",
            "capital_requirement_id",
            "deployable_capital_snapshot_id",
            "policy_name",
            "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        if self.policy_name != CAPITAL_GATE_POLICY_NAME or self.policy_version != CAPITAL_GATE_POLICY_VERSION:
            raise CapitalGatePolicyError("unsupported Capital Gate policy")
        if self.schema_version != CAPITAL_GATE_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported Capital Gate command schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class CapitalGateReceipt:
    command_id: str
    gate_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = CAPITAL_GATE_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "gate_id", _text(self.gate_id, "gate_id"))
        fingerprint = _text(self.command_fingerprint, "command_fingerprint").lower()
        if len(fingerprint) != 64 or any(value not in "0123456789abcdef" for value in fingerprint):
            raise ValueError("command_fingerprint must be SHA-256 text")
        object.__setattr__(self, "command_fingerprint", fingerprint)
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version != CAPITAL_GATE_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported Capital Gate receipt schema")


@dataclass(frozen=True, slots=True)
class CapitalGatePublication:
    assessment: CapitalGateAssessment
    receipt: CapitalGateReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.assessment, CapitalGateAssessment):
            raise TypeError("assessment must be CapitalGateAssessment")
        if not isinstance(self.receipt, CapitalGateReceipt):
            raise TypeError("receipt must be CapitalGateReceipt")
        if self.receipt.gate_id != self.assessment.gate_id:
            raise ValueError("receipt must reference Gate assessment")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class CapitalGateRepository(Protocol):
    def get_capital_readiness(self, assessment_id: str) -> CapitalReadinessAssessment | None: ...
    def get_capital_requirement(self, requirement_id: str) -> PlannedAcquisitionCapitalRequirement | None: ...
    def get_deployable_capital(self, snapshot_id: str) -> DeployableCapitalSnapshot | None: ...
    def get_conservative_economics(self, result_id: str) -> ConservativeEconomicsResult | None: ...
    def get_intended_order_quantity(self, intent_id: str) -> IntendedOrderQuantity | None: ...
    def get_sourcing_admission(self, admission_id: str, revision: int) -> FounderSourcingAdmission | None: ...
    def validate_replay(self, command_id: str, fingerprint: str) -> CapitalGatePublication | None: ...
    def save_gate(self, command, assessment, receipt) -> CapitalGatePublication: ...


class EvaluateCapitalGate:
    def __init__(
        self,
        repository: CapitalGateRepository,
        *,
        gate_id_generator: Callable[[], str],
        evaluated_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        if not all(callable(value) for value in (gate_id_generator, evaluated_clock, committed_clock)):
            raise TypeError("Capital Gate dependencies must be callable")
        self._repository = repository
        self._identity = gate_id_generator
        self._evaluated = evaluated_clock
        self._committed = committed_clock

    def execute(self, command: EvaluateCapitalGateCommand) -> CapitalGatePublication:
        if not isinstance(command, EvaluateCapitalGateCommand):
            raise TypeError("command must be EvaluateCapitalGateCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        readiness = self._required(
            self._repository.get_capital_readiness(command.capital_readiness_assessment_id),
            "exact Capital Readiness assessment",
        )
        requirement = self._required(
            self._repository.get_capital_requirement(command.capital_requirement_id),
            "exact Planned Acquisition Capital Requirement",
        )
        deployable = self._required(
            self._repository.get_deployable_capital(command.deployable_capital_snapshot_id),
            "exact Deployable Capital snapshot",
        )
        conservative = self._required(
            self._repository.get_conservative_economics(
                readiness.source_manifest.conservative_economics_result_id
            ),
            "exact Conservative Economics result",
        )
        intent = self._required(
            self._repository.get_intended_order_quantity(requirement.intended_order_quantity_id),
            "exact Intended Order Quantity",
        )
        admission = self._required(
            self._repository.get_sourcing_admission(
                requirement.sourcing_admission_id,
                requirement.sourcing_admission_revision,
            ),
            "exact Sourcing Admission revision",
        )

        blockers = self._blocking_reasons(
            command, readiness, requirement, deployable, conservative, intent, admission
        )
        rejections: tuple[CapitalGateRejectionReasonCode, ...] = ()
        if not blockers:
            rejections = self._rejection_reasons(
                requirement, deployable, conservative, intent, admission
            )
        state = (
            CapitalGateState.BLOCKED
            if blockers
            else CapitalGateState.REJECTED
            if rejections
            else CapitalGateState.PASS
        )
        manifest = readiness.source_manifest
        assessment = CapitalGateAssessment(
            gate_id=_text(self._identity(), "gate_id"),
            source_manifest=CapitalGateSourceManifest(
                opportunity_identity=command.opportunity_identity,
                capital_readiness_assessment_id=readiness.assessment_id,
                capital_requirement_id=requirement.requirement_id,
                deployable_capital_snapshot_id=deployable.snapshot_id,
                conservative_economics_result_id=conservative.result_id,
                intended_order_quantity_id=intent.intent_id,
                acquisition_normalization_id=requirement.acquisition_normalization_id,
                sourcing_binding_id=requirement.sourcing_binding_id,
                sourcing_admission_id=requirement.sourcing_admission_id,
                sourcing_admission_revision=requirement.sourcing_admission_revision,
                quote_id=requirement.quote_id,
                quote_revision=requirement.quote_revision,
            ),
            evaluated_facts=CapitalGateEvaluatedFacts(
                capital_readiness_state=readiness.state,
                capital_requirement_state=requirement.state,
                conservative_economics_status=conservative.status,
                requirement_currency=requirement.currency,
                deployable_currency=deployable.currency,
                planned_acquisition_capital=requirement.planned_acquisition_capital,
                deployable_capital=deployable.amount,
                conservative_profit_per_unit=conservative.conservative_profit_per_unit,
                conservative_margin=conservative.conservative_margin,
                conservative_acquisition_roi=conservative.conservative_acquisition_roi,
                intended_order_quantity=intent.quantity,
                intended_order_quantity_unit=intent.quantity_unit,
                minimum_order_quantity=admission.quote_revision.minimum_order_quantity,
                deployable_capital_semantics_version=deployable.semantics_version,
            ),
            state=state,
            blocking_reasons=blockers,
            rejection_reasons=rejections,
            policy_name=command.policy_name,
            policy_version=command.policy_version,
            requested_at=command.requested_at,
            evaluated_at=_aware(self._evaluated(), "evaluated_at"),
        )
        receipt = CapitalGateReceipt(
            command.command_id,
            assessment.gate_id,
            command.fingerprint,
            _aware(self._committed(), "committed_at"),
        )
        return self._repository.save_gate(command, assessment, receipt)

    @staticmethod
    def _required(value, name):
        if value is None:
            raise CapitalGateSourceNotFoundError(f"{name} is missing")
        return value

    @staticmethod
    def _blocking_reasons(command, readiness, requirement, deployable, conservative, intent, admission):
        reasons: set[CapitalGateBlockingReasonCode] = set()
        if readiness.state is not CapitalReadinessState.READY_FOR_CAPITAL_REVIEW:
            reasons.add(CapitalGateBlockingReasonCode.CAPITAL_READINESS_BLOCKED)
        if requirement.state is not PlannedAcquisitionCapitalRequirementState.CALCULABLE:
            reasons.add(CapitalGateBlockingReasonCode.CAPITAL_REQUIREMENT_BLOCKED)
        if conservative.status is not ConservativeEconomicsStatus.CALCULABLE:
            reasons.add(CapitalGateBlockingReasonCode.CONSERVATIVE_ECONOMICS_NOT_CALCULABLE)
        opportunity = command.opportunity_identity
        if any(value != opportunity for value in (
            readiness.source_manifest.opportunity_identity,
            requirement.opportunity_identity,
            conservative.opportunity_identity,
            intent.opportunity_identity,
            admission.selling_product_lineage.opportunity_identity,
        )):
            reasons.add(CapitalGateBlockingReasonCode.SOURCE_OPPORTUNITY_MISMATCH)
        manifest = readiness.source_manifest
        if (
            manifest.conservative_economics_result_id != conservative.result_id
            or manifest.acquisition_normalization_id != requirement.acquisition_normalization_id
            or manifest.sourcing_binding_id != requirement.sourcing_binding_id
            or manifest.sourcing_admission_id != requirement.sourcing_admission_id
            or manifest.sourcing_admission_revision != requirement.sourcing_admission_revision
            or manifest.quote_id != requirement.quote_id
            or manifest.quote_revision != requirement.quote_revision
            or requirement.intended_order_quantity_id != intent.intent_id
            or requirement.quantity != intent.quantity
            or requirement.quantity_unit != intent.quantity_unit
            or intent.sourcing_admission_id != requirement.sourcing_admission_id
            or intent.sourcing_admission_revision != requirement.sourcing_admission_revision
            or intent.quote_id != requirement.quote_id
            or intent.quote_revision != requirement.quote_revision
            or admission.admission_id != requirement.sourcing_admission_id
            or admission.revision != requirement.sourcing_admission_revision
            or admission.quote_revision.quote_id != requirement.quote_id
            or admission.quote_revision.revision != requirement.quote_revision
        ):
            reasons.add(CapitalGateBlockingReasonCode.SOURCE_LINEAGE_MISMATCH)
        if requirement.currency != deployable.currency:
            reasons.add(CapitalGateBlockingReasonCode.CURRENCY_MISMATCH)
        if admission.quote_revision.minimum_order_quantity.availability is CommercialFactAvailability.UNKNOWN:
            reasons.add(CapitalGateBlockingReasonCode.MOQ_UNRESOLVED)
        if not (
            readiness.policy_name == CAPITAL_READINESS_POLICY_NAME
            and readiness.policy_version == CAPITAL_READINESS_POLICY_VERSION
            and requirement.policy_name == PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_POLICY_NAME
            and requirement.policy_version == PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_POLICY_VERSION
            and conservative.policy_name == CONSERVATIVE_ECONOMICS_POLICY_NAME
            and conservative.policy_version == CONSERVATIVE_ECONOMICS_POLICY_VERSION
            and deployable.semantics_version == DEPLOYABLE_CAPITAL_SEMANTICS_VERSION
        ):
            reasons.add(CapitalGateBlockingReasonCode.SOURCE_POLICY_UNSUPPORTED)
        return tuple(sorted(reasons, key=lambda value: value.order))

    @staticmethod
    def _rejection_reasons(requirement, deployable, conservative, intent, admission):
        reasons: set[CapitalGateRejectionReasonCode] = set()
        assert requirement.planned_acquisition_capital is not None
        assert conservative.conservative_profit_per_unit is not None
        assert conservative.conservative_margin is not None
        assert conservative.conservative_acquisition_roi is not None
        if conservative.conservative_profit_per_unit <= 0:
            reasons.add(CapitalGateRejectionReasonCode.CONSERVATIVE_PROFIT_NON_POSITIVE)
        if conservative.conservative_margin <= 0:
            reasons.add(CapitalGateRejectionReasonCode.CONSERVATIVE_MARGIN_NON_POSITIVE)
        if conservative.conservative_acquisition_roi <= 0:
            reasons.add(CapitalGateRejectionReasonCode.CONSERVATIVE_ACQUISITION_ROI_NON_POSITIVE)
        if requirement.planned_acquisition_capital > deployable.amount:
            reasons.add(CapitalGateRejectionReasonCode.INSUFFICIENT_DEPLOYABLE_CAPITAL)
        minimum = admission.quote_revision.minimum_order_quantity
        if (
            minimum.availability is CommercialFactAvailability.KNOWN
            and intent.quantity < minimum.quantity
        ):
            reasons.add(CapitalGateRejectionReasonCode.INTENDED_QUANTITY_BELOW_MOQ)
        return tuple(sorted(reasons, key=lambda value: value.order))


__all__ = [name for name in globals() if name.startswith("Capital") or name.startswith("Evaluate") or name.startswith("CAPITAL")]
