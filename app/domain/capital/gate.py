"""Immutable exact-source Capital Gate policy assessments."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.domain.capital.investment import DEPLOYABLE_CAPITAL_SEMANTICS_VERSION
from app.domain.capital.readiness import CapitalReadinessState
from app.domain.capital.requirement import PlannedAcquisitionCapitalRequirementState
from app.domain.decision_engine import OpportunityIdentity
from app.domain.opportunity import ConservativeEconomicsStatus
from app.domain.sourcing import SourcingQuantityFact


CAPITAL_GATE_SCHEMA_VERSION = "capital-gate-v1"
CAPITAL_GATE_SOURCE_MANIFEST_SCHEMA_VERSION = "capital-gate-source-manifest-v1"
CAPITAL_GATE_EVALUATED_FACTS_SCHEMA_VERSION = "capital-gate-evaluated-facts-v1"
CAPITAL_GATE_POLICY_NAME = "domestic-commerce-capital-gate"
CAPITAL_GATE_POLICY_VERSION = "1.0.0"


class CapitalGateState(StrEnum):
    PASS = "pass"
    REJECTED = "rejected"
    BLOCKED = "blocked"


class CapitalGateBlockingReasonCode(StrEnum):
    CAPITAL_READINESS_BLOCKED = "capital_readiness_blocked"
    CAPITAL_REQUIREMENT_BLOCKED = "capital_requirement_blocked"
    SOURCE_OPPORTUNITY_MISMATCH = "source_opportunity_mismatch"
    SOURCE_LINEAGE_MISMATCH = "source_lineage_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    CONSERVATIVE_ECONOMICS_NOT_CALCULABLE = "conservative_economics_not_calculable"
    MOQ_UNRESOLVED = "moq_unresolved"
    SOURCE_POLICY_UNSUPPORTED = "source_policy_unsupported"

    @property
    def order(self) -> int:
        return tuple(CapitalGateBlockingReasonCode).index(self)


class CapitalGateRejectionReasonCode(StrEnum):
    CONSERVATIVE_PROFIT_NON_POSITIVE = "conservative_profit_non_positive"
    CONSERVATIVE_MARGIN_NON_POSITIVE = "conservative_margin_non_positive"
    CONSERVATIVE_ACQUISITION_ROI_NON_POSITIVE = (
        "conservative_acquisition_roi_non_positive"
    )
    INSUFFICIENT_DEPLOYABLE_CAPITAL = "insufficient_deployable_capital"
    INTENDED_QUANTITY_BELOW_MOQ = "intended_quantity_below_moq"

    @property
    def order(self) -> int:
        return tuple(CapitalGateRejectionReasonCode).index(self)


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


def _positive(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _currency(value: str, name: str) -> str:
    result = _text(value, name).upper()
    if len(result) != 3 or not result.isascii() or not result.isalpha():
        raise ValueError(f"{name} must be a three-letter code")
    return result


def _decimal(value: Decimal, name: str, *, non_negative: bool = False) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal")
    if not value.is_finite() or (non_negative and value < 0):
        raise ValueError(f"{name} must be finite" + (" and non-negative" if non_negative else ""))
    return value


@dataclass(frozen=True, slots=True)
class CapitalGateSourceManifest:
    opportunity_identity: OpportunityIdentity
    capital_readiness_assessment_id: str
    capital_requirement_id: str
    deployable_capital_snapshot_id: str
    conservative_economics_result_id: str
    intended_order_quantity_id: str
    acquisition_normalization_id: str
    sourcing_binding_id: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    quote_id: str
    quote_revision: int
    schema_version: str = CAPITAL_GATE_SOURCE_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        for name in (
            "capital_readiness_assessment_id",
            "capital_requirement_id",
            "deployable_capital_snapshot_id",
            "conservative_economics_result_id",
            "intended_order_quantity_id",
            "acquisition_normalization_id",
            "sourcing_binding_id",
            "sourcing_admission_id",
            "quote_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        _positive(self.sourcing_admission_revision, "sourcing_admission_revision")
        _positive(self.quote_revision, "quote_revision")
        if self.sourcing_admission_revision != self.quote_revision:
            raise ValueError("Sourcing Admission and Quote revisions must match")
        if self.schema_version != CAPITAL_GATE_SOURCE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported Capital Gate source manifest schema")


@dataclass(frozen=True, slots=True)
class CapitalGateEvaluatedFacts:
    capital_readiness_state: CapitalReadinessState
    capital_requirement_state: PlannedAcquisitionCapitalRequirementState
    conservative_economics_status: ConservativeEconomicsStatus
    requirement_currency: str
    deployable_currency: str
    planned_acquisition_capital: Decimal | None
    deployable_capital: Decimal
    conservative_profit_per_unit: Decimal | None
    conservative_margin: Decimal | None
    conservative_acquisition_roi: Decimal | None
    intended_order_quantity: int
    intended_order_quantity_unit: str
    minimum_order_quantity: SourcingQuantityFact
    deployable_capital_semantics_version: str
    schema_version: str = CAPITAL_GATE_EVALUATED_FACTS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "capital_readiness_state", CapitalReadinessState(self.capital_readiness_state)
        )
        requirement_state = PlannedAcquisitionCapitalRequirementState(
            self.capital_requirement_state
        )
        object.__setattr__(self, "capital_requirement_state", requirement_state)
        economics_status = ConservativeEconomicsStatus(self.conservative_economics_status)
        object.__setattr__(self, "conservative_economics_status", economics_status)
        object.__setattr__(
            self, "requirement_currency", _currency(self.requirement_currency, "requirement_currency")
        )
        object.__setattr__(
            self, "deployable_currency", _currency(self.deployable_currency, "deployable_currency")
        )
        object.__setattr__(
            self, "deployable_capital", _decimal(self.deployable_capital, "deployable_capital", non_negative=True)
        )
        if requirement_state is PlannedAcquisitionCapitalRequirementState.CALCULABLE:
            object.__setattr__(
                self,
                "planned_acquisition_capital",
                _decimal(
                    self.planned_acquisition_capital,  # type: ignore[arg-type]
                    "planned_acquisition_capital",
                    non_negative=True,
                ),
            )
        elif self.planned_acquisition_capital is not None:
            raise ValueError("BLOCKED requirement cannot provide capital amount")
        metric_names = (
            "conservative_profit_per_unit",
            "conservative_margin",
            "conservative_acquisition_roi",
        )
        if economics_status is ConservativeEconomicsStatus.CALCULABLE:
            for name in metric_names:
                object.__setattr__(self, name, _decimal(getattr(self, name), name))  # type: ignore[arg-type]
        elif any(getattr(self, name) is not None for name in metric_names):
            raise ValueError("BLOCKED Conservative Economics cannot provide policy values")
        _positive(self.intended_order_quantity, "intended_order_quantity")
        object.__setattr__(
            self,
            "intended_order_quantity_unit",
            _text(self.intended_order_quantity_unit, "intended_order_quantity_unit"),
        )
        if not isinstance(self.minimum_order_quantity, SourcingQuantityFact):
            raise TypeError("minimum_order_quantity must be SourcingQuantityFact")
        if self.deployable_capital_semantics_version != DEPLOYABLE_CAPITAL_SEMANTICS_VERSION:
            raise ValueError("unsupported Deployable Capital semantics")
        if self.schema_version != CAPITAL_GATE_EVALUATED_FACTS_SCHEMA_VERSION:
            raise ValueError("unsupported Capital Gate evaluated facts schema")


@dataclass(frozen=True, slots=True)
class CapitalGateAssessment:
    gate_id: str
    source_manifest: CapitalGateSourceManifest
    evaluated_facts: CapitalGateEvaluatedFacts
    state: CapitalGateState
    blocking_reasons: tuple[CapitalGateBlockingReasonCode, ...]
    rejection_reasons: tuple[CapitalGateRejectionReasonCode, ...]
    policy_name: str
    policy_version: str
    requested_at: datetime
    evaluated_at: datetime
    schema_version: str = CAPITAL_GATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "gate_id", _text(self.gate_id, "gate_id"))
        if not isinstance(self.source_manifest, CapitalGateSourceManifest):
            raise TypeError("source_manifest must be CapitalGateSourceManifest")
        if not isinstance(self.evaluated_facts, CapitalGateEvaluatedFacts):
            raise TypeError("evaluated_facts must be CapitalGateEvaluatedFacts")
        state = CapitalGateState(self.state)
        object.__setattr__(self, "state", state)
        for name, reason_type in (
            ("blocking_reasons", CapitalGateBlockingReasonCode),
            ("rejection_reasons", CapitalGateRejectionReasonCode),
        ):
            values = getattr(self, name)
            if not isinstance(values, tuple):
                raise TypeError(f"{name} must be tuple")
            reasons = tuple(reason_type(value) for value in values)
            if len(set(reasons)) != len(reasons):
                raise ValueError(f"{name} must be unique")
            if reasons != tuple(sorted(reasons, key=lambda value: value.order)):
                raise ValueError(f"{name} must use deterministic order")
            object.__setattr__(self, name, reasons)
        if state is CapitalGateState.PASS:
            if self.blocking_reasons or self.rejection_reasons:
                raise ValueError("PASS cannot carry reasons")
        elif state is CapitalGateState.REJECTED:
            if self.blocking_reasons or not self.rejection_reasons:
                raise ValueError("REJECTED requires only rejection reasons")
        elif not self.blocking_reasons or self.rejection_reasons:
            raise ValueError("BLOCKED requires only blocking reasons")
        object.__setattr__(self, "policy_name", _text(self.policy_name, "policy_name"))
        object.__setattr__(self, "policy_version", _text(self.policy_version, "policy_version"))
        if self.policy_name != CAPITAL_GATE_POLICY_NAME or self.policy_version != CAPITAL_GATE_POLICY_VERSION:
            raise ValueError("unsupported Capital Gate policy")
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        object.__setattr__(self, "evaluated_at", _aware(self.evaluated_at, "evaluated_at"))
        if self.schema_version != CAPITAL_GATE_SCHEMA_VERSION:
            raise ValueError("unsupported Capital Gate schema")

    @property
    def blocking_reason_codes(self) -> tuple[CapitalGateBlockingReasonCode, ...]:
        return self.blocking_reasons

    @property
    def rejection_reason_codes(self) -> tuple[CapitalGateRejectionReasonCode, ...]:
        return self.rejection_reasons


__all__ = [name for name in globals() if name.startswith("Capital") or name.startswith("CAPITAL")]
