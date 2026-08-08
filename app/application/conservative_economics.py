"""Application authority for historically reproducible Conservative Economics."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Callable, Protocol

from app.domain.decision_engine import OpportunityIdentity
from app.domain.opportunity import (
    CONSERVATIVE_ECONOMICS_DECIMAL_PRECISION,
    CONSERVATIVE_ECONOMICS_POLICY_NAME,
    CONSERVATIVE_ECONOMICS_POLICY_VERSION,
    CONSERVATIVE_ECONOMICS_ROUNDING,
    ConservativeEconomicsAssumption,
    ConservativeEconomicsAssumptionKind,
    ConservativeEconomicsBlockingCode,
    ConservativeEconomicsBlockingReason,
    ConservativeEconomicsResult,
    ConservativeEconomicsStatus,
    EconomicsSourceComposition,
    EconomicsSourceCompositionState,
    EvidenceStatus,
    calculate_conservative_unit_values,
)


CONSERVATIVE_ECONOMICS_COMMAND_SCHEMA_VERSION = "conservative-economics-command-v1"
CONSERVATIVE_ECONOMICS_RECEIPT_SCHEMA_VERSION = "conservative-economics-receipt-v1"


class ConservativeEconomicsError(RuntimeError):
    pass


class ConservativeEconomicsSourceError(ConservativeEconomicsError):
    pass


class ConservativeEconomicsPolicyError(ConservativeEconomicsError):
    pass


class ConservativeEconomicsReplayConflictError(ConservativeEconomicsError):
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
    encoded = json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ConservativeEconomicsScenario:
    scenario_name: str
    scenario_version: str
    sale_price_factor: Decimal
    assumption_owner: str

    def __post_init__(self) -> None:
        for name in ("scenario_name", "scenario_version", "assumption_owner"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.sale_price_factor, Decimal):
            raise TypeError("sale_price_factor must be Decimal")
        if not self.sale_price_factor.is_finite() or not (
            Decimal("0") < self.sale_price_factor <= Decimal("1")
        ):
            raise ValueError("sale_price_factor must be greater than zero and at most one")

    @property
    def manifest(self) -> tuple[ConservativeEconomicsAssumption, ...]:
        return (
            ConservativeEconomicsAssumption(
                ConservativeEconomicsAssumptionKind.SALE_PRICE_FACTOR,
                self.sale_price_factor,
                self.assumption_owner,
            ),
        )


@dataclass(frozen=True, slots=True)
class EvaluateConservativeEconomicsCommand:
    command_id: str
    opportunity_identity: OpportunityIdentity
    source_composition_id: str
    scenario: ConservativeEconomicsScenario
    requested_at: datetime
    policy_name: str
    policy_version: str
    schema_version: str = CONSERVATIVE_ECONOMICS_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("command_id", "source_composition_id", "policy_name", "policy_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.scenario, ConservativeEconomicsScenario):
            raise TypeError("scenario must be ConservativeEconomicsScenario")
        _aware(self.requested_at, "requested_at")
        if self.schema_version != CONSERVATIVE_ECONOMICS_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported Conservative Economics command schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class ConservativeEconomicsReceipt:
    command_id: str
    result_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = CONSERVATIVE_ECONOMICS_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "result_id", _text(self.result_id, "result_id"))
        fingerprint = _text(self.command_fingerprint, "command_fingerprint").lower()
        if len(fingerprint) != 64 or any(value not in "0123456789abcdef" for value in fingerprint):
            raise ValueError("command_fingerprint must be SHA-256 text")
        object.__setattr__(self, "command_fingerprint", fingerprint)
        _aware(self.committed_at, "committed_at")
        if self.schema_version != CONSERVATIVE_ECONOMICS_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported Conservative Economics receipt schema")


@dataclass(frozen=True, slots=True)
class ConservativeEconomicsPublication:
    result: ConservativeEconomicsResult
    receipt: ConservativeEconomicsReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.result, ConservativeEconomicsResult):
            raise TypeError("result must be ConservativeEconomicsResult")
        if not isinstance(self.receipt, ConservativeEconomicsReceipt):
            raise TypeError("receipt must be ConservativeEconomicsReceipt")
        if self.result.result_id != self.receipt.result_id:
            raise ValueError("receipt must reference result")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class ConservativeEconomicsRepository(Protocol):
    def get_source_composition(self, composition_id: str) -> EconomicsSourceComposition | None: ...

    def validate_replay(
        self, command_id: str, fingerprint: str
    ) -> ConservativeEconomicsPublication | None: ...

    def save_result(
        self,
        command: EvaluateConservativeEconomicsCommand,
        result: ConservativeEconomicsResult,
        receipt: ConservativeEconomicsReceipt,
    ) -> ConservativeEconomicsPublication: ...


def conservative_economics_blocking_reasons(
    source: EconomicsSourceComposition,
) -> tuple[ConservativeEconomicsBlockingReason, ...]:
    if not isinstance(source, EconomicsSourceComposition):
        raise TypeError("source must be EconomicsSourceComposition")
    reasons = []

    def block(code, category, reference=None):
        reasons.append(ConservativeEconomicsBlockingReason(code, category, reference))

    if source.state is EconomicsSourceCompositionState.BLOCKED:
        block(
            ConservativeEconomicsBlockingCode.SOURCE_COMPOSITION_BLOCKED,
            "source_composition",
        )
    sale = source.expected_sale_price
    if (
        sale.amount is None
        or sale.amount <= 0
        or sale.evidence.status not in {EvidenceStatus.VERIFIED, EvidenceStatus.ESTIMATED}
        or sale.evidence.reference is None
    ):
        block(
            ConservativeEconomicsBlockingCode.SALE_PRICE_NOT_READY,
            "expected_sale_price",
            sale.evidence.reference,
        )
    for value, code, category in (
        (
            source.marketplace_fee_rate,
            ConservativeEconomicsBlockingCode.MARKETPLACE_FEE_NOT_READY,
            "marketplace_fee",
        ),
        (
            source.payment_fee_rate,
            ConservativeEconomicsBlockingCode.PAYMENT_FEE_NOT_READY,
            "payment_fee",
        ),
        (
            source.fixed_fee,
            ConservativeEconomicsBlockingCode.FIXED_FEE_NOT_READY,
            "fixed_fee",
        ),
    ):
        numeric = value.rate if hasattr(value, "rate") else value.amount
        if (
            numeric is None
            or value.evidence.status is not EvidenceStatus.VERIFIED
            or value.evidence.reference is None
        ):
            block(code, category, value.evidence.reference)
    tax = source.tax_rate
    if (
        tax.rate != Decimal("0")
        or tax.evidence.status is not EvidenceStatus.VERIFIED
        or tax.evidence.reference is None
    ):
        block(
            ConservativeEconomicsBlockingCode.TAX_NOT_CAPITAL_AUTHORITATIVE,
            "tax",
            tax.evidence.reference,
        )
    duty = source.duty_cost
    if (
        duty.amount != Decimal("0")
        or duty.evidence.status is not EvidenceStatus.VERIFIED
        or duty.evidence.reference is None
    ):
        block(
            ConservativeEconomicsBlockingCode.DUTY_NOT_CAPITAL_AUTHORITATIVE,
            "duty",
            duty.evidence.reference,
        )
    other = source.other_cost
    if (
        other.amount != Decimal("0")
        or other.evidence.status is not EvidenceStatus.VERIFIED
        or other.evidence.reference is None
    ):
        block(
            ConservativeEconomicsBlockingCode.OTHER_COST_SCOPE_UNRESOLVED,
            "other_cost",
            other.evidence.reference,
        )
    if source.acquisition_cost_per_unit <= 0:
        block(
            ConservativeEconomicsBlockingCode.ACQUISITION_COST_NON_POSITIVE,
            "acquisition_cost",
        )
    if any(
        value.currency != source.economics_currency
        for value in (sale, source.fixed_fee, duty, other)
    ):
        block(
            ConservativeEconomicsBlockingCode.CURRENCY_MISMATCH,
            "economics_currency",
        )
    return tuple(reasons)


class EvaluateConservativeEconomics:
    def __init__(
        self,
        repository: ConservativeEconomicsRepository,
        *,
        result_id_generator: Callable[[], str],
        calculated_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        if not all(callable(value) for value in (result_id_generator, calculated_clock, committed_clock)):
            raise TypeError("Conservative Economics dependencies must be callable")
        self._repository = repository
        self._identity = result_id_generator
        self._calculated = calculated_clock
        self._committed = committed_clock

    def execute(
        self, command: EvaluateConservativeEconomicsCommand
    ) -> ConservativeEconomicsPublication:
        if not isinstance(command, EvaluateConservativeEconomicsCommand):
            raise TypeError("command must be EvaluateConservativeEconomicsCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        self._validate_policy(command)
        source = self._repository.get_source_composition(command.source_composition_id)
        if source is None:
            raise ConservativeEconomicsSourceError("exact Economics Source Composition is missing")
        if source.opportunity_identity != command.opportunity_identity:
            raise ConservativeEconomicsSourceError("source Opportunity differs from command")

        blockers = conservative_economics_blocking_reasons(source)
        common = {
            "result_id": _text(self._identity(), "result_id"),
            "opportunity_identity": source.opportunity_identity,
            "source_composition_id": source.composition_id,
            "source_composition_schema_version": source.schema_version,
            "economics_currency": source.economics_currency,
            "authoritative_expected_sale_price": source.expected_sale_price.amount,
            "expected_sale_price_evidence_status": source.expected_sale_price.evidence.status,
            "expected_sale_price_evidence_reference": source.expected_sale_price.evidence.reference,
            "acquisition_cost_per_unit": source.acquisition_cost_per_unit,
            "assumptions": command.scenario.manifest,
            "scenario_name": command.scenario.scenario_name,
            "scenario_version": command.scenario.scenario_version,
            "policy_name": command.policy_name,
            "policy_version": command.policy_version,
            "policy_precision": CONSERVATIVE_ECONOMICS_DECIMAL_PRECISION,
            "policy_rounding": CONSERVATIVE_ECONOMICS_ROUNDING,
            "requested_at": command.requested_at,
            "calculated_at": _aware(self._calculated(), "calculated_at"),
        }
        if blockers:
            result = ConservativeEconomicsResult(
                **common,
                conservative_sale_price=None,
                marketplace_fee=None,
                payment_fee=None,
                fixed_fee=None,
                accepted_tax_cost=None,
                accepted_duty_cost=None,
                accepted_other_cost=None,
                total_unit_cost=None,
                conservative_profit_per_unit=None,
                conservative_margin=None,
                conservative_acquisition_roi=None,
                status=ConservativeEconomicsStatus.BLOCKED,
                blocking_reasons=tuple(blockers),
            )
        else:
            values = calculate_conservative_unit_values(
                expected_sale_price=source.expected_sale_price.amount,
                sale_price_factor=command.scenario.sale_price_factor,
                acquisition_cost_per_unit=source.acquisition_cost_per_unit,
                marketplace_fee_rate=source.marketplace_fee_rate.rate,
                payment_fee_rate=source.payment_fee_rate.rate,
                fixed_fee=source.fixed_fee.amount,
                tax_cost=source.tax_rate.rate,
                duty_cost=source.duty_cost.amount,
                other_cost=source.other_cost.amount,
            )
            result = ConservativeEconomicsResult(
                **common,
                **values,
                fixed_fee=source.fixed_fee.amount,
                accepted_tax_cost=source.tax_rate.rate,
                accepted_duty_cost=source.duty_cost.amount,
                accepted_other_cost=source.other_cost.amount,
                status=ConservativeEconomicsStatus.CALCULABLE,
                blocking_reasons=(),
            )
        receipt = ConservativeEconomicsReceipt(
            command.command_id,
            result.result_id,
            command.fingerprint,
            _aware(self._committed(), "committed_at"),
        )
        return self._repository.save_result(command, result, receipt)

    @staticmethod
    def _validate_policy(command: EvaluateConservativeEconomicsCommand) -> None:
        if (
            command.policy_name != CONSERVATIVE_ECONOMICS_POLICY_NAME
            or command.policy_version != CONSERVATIVE_ECONOMICS_POLICY_VERSION
        ):
            raise ConservativeEconomicsPolicyError("unsupported Conservative Economics policy")

__all__ = [
    name
    for name in globals()
    if name.startswith("Conservative")
    or name.startswith("Evaluate")
    or name.startswith("CONSERVATIVE_ECONOMICS")
    or name == "conservative_economics_blocking_reasons"
]
