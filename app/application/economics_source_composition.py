"""Application owner for exact authoritative Economics source composition."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Callable, Protocol

from app.application.verified_economics_snapshot import VerifiedEconomicsSnapshot
from app.domain.decision_engine import OpportunityIdentity
from app.domain.opportunity import (
    ECONOMICS_SOURCE_COMPOSITION_POLICY_NAME,
    ECONOMICS_SOURCE_COMPOSITION_POLICY_VERSION,
    EconomicsSourceBlockingCode,
    EconomicsSourceBlockingReason,
    EconomicsSourceComposition,
    EconomicsSourceCompositionState,
    EvidenceStatus,
    MoneyInput,
)
from app.domain.sourcing import AcquisitionCostNormalization


ECONOMICS_SOURCE_COMPOSITION_COMMAND_SCHEMA_VERSION = (
    "economics-source-composition-command-v1"
)
ECONOMICS_SOURCE_COMPOSITION_RECEIPT_SCHEMA_VERSION = (
    "economics-source-composition-receipt-v1"
)


class EconomicsSourceCompositionError(RuntimeError):
    pass


class EconomicsSourceCompositionSourceError(EconomicsSourceCompositionError):
    pass


class EconomicsSourceCompositionPolicyError(EconomicsSourceCompositionError):
    pass


class EconomicsSourceCompositionReplayConflictError(
    EconomicsSourceCompositionError
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


def _canonical(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _canonical(getattr(value, field.name))
            for field in fields(value)
        }
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
        _canonical(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ComposeEconomicsSourcesCommand:
    command_id: str
    opportunity_identity: OpportunityIdentity
    acquisition_normalization_id: str
    verified_economics_opportunity_id: str
    verified_economics_snapshot_at: datetime
    verified_economics_schema_version: str
    requested_at: datetime
    policy_name: str
    policy_version: str
    schema_version: str = ECONOMICS_SOURCE_COMPOSITION_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "command_id",
            "acquisition_normalization_id",
            "verified_economics_opportunity_id",
            "verified_economics_schema_version",
            "policy_name",
            "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        _aware(self.verified_economics_snapshot_at, "verified_economics_snapshot_at")
        _aware(self.requested_at, "requested_at")
        if self.schema_version != ECONOMICS_SOURCE_COMPOSITION_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported Economics Source Composition command schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class EconomicsSourceCompositionReceipt:
    command_id: str
    composition_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = ECONOMICS_SOURCE_COMPOSITION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(
            self, "composition_id", _text(self.composition_id, "composition_id")
        )
        fingerprint = _text(self.command_fingerprint, "command_fingerprint").lower()
        if len(fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in fingerprint
        ):
            raise ValueError("command_fingerprint must be SHA-256 text")
        object.__setattr__(self, "command_fingerprint", fingerprint)
        _aware(self.committed_at, "committed_at")
        if self.schema_version != ECONOMICS_SOURCE_COMPOSITION_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported Economics Source Composition receipt schema")


@dataclass(frozen=True, slots=True)
class EconomicsSourceCompositionResult:
    composition: EconomicsSourceComposition
    receipt: EconomicsSourceCompositionReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.composition, EconomicsSourceComposition):
            raise TypeError("composition must be EconomicsSourceComposition")
        if not isinstance(self.receipt, EconomicsSourceCompositionReceipt):
            raise TypeError("receipt must be EconomicsSourceCompositionReceipt")
        if self.composition.composition_id != self.receipt.composition_id:
            raise ValueError("receipt must reference composition")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class EconomicsSourceCompositionRepository(Protocol):
    def get_normalization(
        self, normalization_id: str
    ) -> AcquisitionCostNormalization | None: ...

    def get_verified_economics_snapshot(
        self, opportunity_id: str
    ) -> VerifiedEconomicsSnapshot | None: ...

    def validate_replay(
        self, command_id: str, fingerprint: str
    ) -> EconomicsSourceCompositionResult | None: ...

    def save_composition(
        self,
        command: ComposeEconomicsSourcesCommand,
        composition: EconomicsSourceComposition,
        receipt: EconomicsSourceCompositionReceipt,
    ) -> EconomicsSourceCompositionResult: ...


class ComposeEconomicsSources:
    def __init__(
        self,
        repository: EconomicsSourceCompositionRepository,
        *,
        composition_id_generator: Callable[[], str],
        composed_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        if not all(
            callable(value)
            for value in (
                composition_id_generator,
                composed_clock,
                committed_clock,
            )
        ):
            raise TypeError("Economics source composition dependencies must be callable")
        self._repository = repository
        self._identity = composition_id_generator
        self._composed = composed_clock
        self._committed = committed_clock

    def execute(
        self, command: ComposeEconomicsSourcesCommand
    ) -> EconomicsSourceCompositionResult:
        if not isinstance(command, ComposeEconomicsSourcesCommand):
            raise TypeError("command must be ComposeEconomicsSourcesCommand")
        replay = self._repository.validate_replay(
            command.command_id, command.fingerprint
        )
        if replay is not None:
            return replace(replay, replayed=True)
        self._validate_policy(command)
        normalization = self._repository.get_normalization(
            command.acquisition_normalization_id
        )
        if normalization is None:
            raise EconomicsSourceCompositionSourceError(
                "exact Acquisition Cost Normalization is missing"
            )
        if normalization.opportunity_identity != command.opportunity_identity:
            raise EconomicsSourceCompositionSourceError(
                "normalization Opportunity differs from command"
            )
        verified = self._repository.get_verified_economics_snapshot(
            command.verified_economics_opportunity_id
        )
        if verified is None:
            raise EconomicsSourceCompositionSourceError(
                "exact Verified Economics Snapshot is missing"
            )
        if (
            verified.opportunity_id != command.opportunity_identity.opportunity_id
            or verified.opportunity_id != command.verified_economics_opportunity_id
            or verified.snapshot_at != command.verified_economics_snapshot_at
            or verified.schema_version != command.verified_economics_schema_version
        ):
            raise EconomicsSourceCompositionSourceError(
                "Verified Economics exact source differs from command"
            )
        inputs = verified.inputs
        blockers = self._blocking_reasons(
            inputs, normalization.target_currency
        )
        composition = EconomicsSourceComposition(
            composition_id=_text(self._identity(), "composition_id"),
            opportunity_identity=normalization.opportunity_identity,
            acquisition_normalization_id=normalization.normalization_id,
            acquisition_policy_name=normalization.policy_name,
            acquisition_policy_version=normalization.policy_version,
            acquisition_cost_per_unit=normalization.total_per_unit_acquisition_cost,
            economics_currency=normalization.target_currency,
            verified_economics_opportunity_id=verified.opportunity_id,
            verified_economics_snapshot_at=verified.snapshot_at,
            verified_economics_schema_version=verified.schema_version,
            expected_sale_price=inputs.expected_sale_price,
            marketplace_fee_rate=inputs.marketplace_fee_rate,
            payment_fee_rate=inputs.payment_fee_rate,
            fixed_fee=inputs.fixed_fee,
            tax_rate=inputs.tax_rate,
            duty_cost=inputs.duty_cost,
            other_cost=inputs.other_cost,
            state=(
                EconomicsSourceCompositionState.BLOCKED
                if blockers
                else EconomicsSourceCompositionState.READY
            ),
            blocking_reasons=tuple(blockers),
            policy_name=command.policy_name,
            policy_version=command.policy_version,
            requested_at=command.requested_at,
            composed_at=_aware(self._composed(), "composed_at"),
        )
        receipt = EconomicsSourceCompositionReceipt(
            command.command_id,
            composition.composition_id,
            command.fingerprint,
            _aware(self._committed(), "committed_at"),
        )
        return self._repository.save_composition(command, composition, receipt)

    @staticmethod
    def _validate_policy(command: ComposeEconomicsSourcesCommand) -> None:
        if (
            command.policy_name != ECONOMICS_SOURCE_COMPOSITION_POLICY_NAME
            or command.policy_version != ECONOMICS_SOURCE_COMPOSITION_POLICY_VERSION
        ):
            raise EconomicsSourceCompositionPolicyError(
                "unsupported Economics Source Composition policy"
            )

    @classmethod
    def _blocking_reasons(cls, inputs, currency):
        reasons = []
        required = (
            (
                "expected_sale_price",
                inputs.expected_sale_price,
                EconomicsSourceBlockingCode.EXPECTED_SALE_PRICE_MISSING,
                {EvidenceStatus.VERIFIED, EvidenceStatus.ESTIMATED},
            ),
            (
                "marketplace_fee",
                inputs.marketplace_fee_rate,
                EconomicsSourceBlockingCode.MARKETPLACE_FEE_MISSING,
                {EvidenceStatus.VERIFIED},
            ),
            (
                "payment_fee",
                inputs.payment_fee_rate,
                EconomicsSourceBlockingCode.PAYMENT_FEE_MISSING,
                {EvidenceStatus.VERIFIED},
            ),
            (
                "fixed_fee",
                inputs.fixed_fee,
                EconomicsSourceBlockingCode.FIXED_FEE_MISSING,
                {EvidenceStatus.VERIFIED},
            ),
            (
                "tax",
                inputs.tax_rate,
                EconomicsSourceBlockingCode.TAX_MISSING,
                {EvidenceStatus.VERIFIED},
            ),
            (
                "duty",
                inputs.duty_cost,
                EconomicsSourceBlockingCode.DUTY_MISSING,
                {EvidenceStatus.VERIFIED},
            ),
            (
                "other_cost",
                inputs.other_cost,
                EconomicsSourceBlockingCode.OTHER_COST_MISSING,
                {EvidenceStatus.VERIFIED},
            ),
        )
        for category, value, missing_code, allowed_statuses in required:
            numeric = value.amount if isinstance(value, MoneyInput) else value.rate
            evidence = value.evidence
            if numeric is None or evidence.status in {
                EvidenceStatus.MISSING,
                EvidenceStatus.UNSUPPORTED,
            }:
                reasons.append(
                    EconomicsSourceBlockingReason(
                        missing_code, category, evidence.reference
                    )
                )
            elif evidence.status not in allowed_statuses:
                reasons.append(
                    EconomicsSourceBlockingReason(
                        EconomicsSourceBlockingCode.EVIDENCE_NOT_VERIFIED,
                        category,
                        evidence.reference,
                    )
                )
            elif evidence.reference is None:
                reasons.append(
                    EconomicsSourceBlockingReason(
                        EconomicsSourceBlockingCode.EVIDENCE_REFERENCE_MISSING,
                        category,
                    )
                )
        if inputs.other_cost.amount not in {None, Decimal("0")}:
            reasons.append(
                EconomicsSourceBlockingReason(
                    EconomicsSourceBlockingCode.OTHER_COST_SCOPE_UNRESOLVED,
                    "other_cost",
                    inputs.other_cost.evidence.reference,
                )
            )
        if inputs.currency != currency:
            reasons.append(
                EconomicsSourceBlockingReason(
                    EconomicsSourceBlockingCode.CURRENCY_MISMATCH,
                    "economics_currency",
                )
            )
        return reasons


__all__ = [
    name
    for name in globals()
    if name.startswith("ComposeEconomics")
    or name.startswith("EconomicsSource")
    or name.startswith("ECONOMICS_SOURCE")
]
