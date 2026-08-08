"""Application authority for exact domestic market validation."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Callable, Protocol

from app.application.assessment_snapshot import (
    CompetitionAssessmentSnapshot,
    DemandAssessmentSnapshot,
)
from app.application.decision_composition import (
    ASSESSMENT_SCHEMA_VERSION,
    COMPETITION_POLICY_VERSION,
    DEMAND_POLICY_VERSION,
)
from app.application.opportunity_market_identity import OpportunityMarketIdentityBinding
from app.domain.decision_engine import DecisionEvidenceAvailability, OpportunityIdentity
from app.domain.market_intelligence import (
    CompetitionObservation,
    DemandObservation,
    DOMESTIC_MARKET_VALIDATION_POLICY_NAME,
    DOMESTIC_MARKET_VALIDATION_POLICY_VERSION,
    DomesticMarketAnalysisSourceManifest,
    DomesticMarketMetricEvidence,
    DomesticMarketValidationAssessment,
    DomesticMarketValidationReason,
    DomesticMarketValidationReasonCode,
    DomesticMarketValidationSourceManifest,
    DomesticMarketValidationState,
    DomesticMarketVerification,
    MarketEvidenceStatus,
    MarketObservationIdentity,
)


DOMESTIC_MARKET_VALIDATION_COMMAND_SCHEMA_VERSION = "domestic-market-validation-command-v1"
DOMESTIC_MARKET_VALIDATION_RECEIPT_SCHEMA_VERSION = "domestic-market-validation-receipt-v1"

COMPETITION_REQUIRED_METRICS = (
    "competitor_count",
    "rocket_seller_count",
    "price_spread",
    "median_price",
)
DEMAND_REQUIRED_METRICS = (
    "search_volume",
    "review_count",
    "rating",
    "coupang_popularity_rank",
    "itemscout_popularity_rank",
)
ACCEPTED_EVIDENCE_STATUSES = frozenset({
    MarketEvidenceStatus.OBSERVED,
    MarketEvidenceStatus.VERIFIED,
    MarketEvidenceStatus.HUMAN_VERIFIED,
})


class DomesticMarketValidationError(RuntimeError):
    pass


class DomesticMarketValidationReplayConflictError(DomesticMarketValidationError):
    pass


class DomesticMarketValidationPolicyError(DomesticMarketValidationError):
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
class ValidateDomesticMarketCommand:
    command_id: str
    opportunity_identity: OpportunityIdentity
    market_identity: MarketObservationIdentity
    competition_observation_id: str
    competition_assessment_id: str
    demand_observation_id: str
    demand_assessment_id: str
    accepted_external_signal_ids: tuple[str, ...]
    verification: DomesticMarketVerification
    requested_at: datetime
    policy_name: str = DOMESTIC_MARKET_VALIDATION_POLICY_NAME
    policy_version: str = DOMESTIC_MARKET_VALIDATION_POLICY_VERSION
    schema_version: str = DOMESTIC_MARKET_VALIDATION_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "command_id",
            "competition_observation_id",
            "competition_assessment_id",
            "demand_observation_id",
            "demand_assessment_id",
            "policy_name",
            "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.market_identity, MarketObservationIdentity):
            raise TypeError("market_identity must be MarketObservationIdentity")
        if not isinstance(self.accepted_external_signal_ids, tuple):
            raise TypeError("accepted_external_signal_ids must be tuple")
        normalized = tuple(_text(value, "external signal id") for value in self.accepted_external_signal_ids)
        if len(set(normalized)) != len(normalized):
            raise ValueError("accepted_external_signal_ids must be unique")
        object.__setattr__(self, "accepted_external_signal_ids", normalized)
        if not isinstance(self.verification, DomesticMarketVerification):
            raise TypeError("verification must be DomesticMarketVerification")
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        if (
            self.policy_name != DOMESTIC_MARKET_VALIDATION_POLICY_NAME
            or self.policy_version != DOMESTIC_MARKET_VALIDATION_POLICY_VERSION
        ):
            raise DomesticMarketValidationPolicyError("unsupported domestic market validation policy")
        if self.schema_version != DOMESTIC_MARKET_VALIDATION_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported domestic market validation command schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class DomesticMarketValidationReceipt:
    command_id: str
    assessment_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = DOMESTIC_MARKET_VALIDATION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "assessment_id", _text(self.assessment_id, "assessment_id"))
        fingerprint = _text(self.command_fingerprint, "command_fingerprint").lower()
        if len(fingerprint) != 64 or any(value not in "0123456789abcdef" for value in fingerprint):
            raise ValueError("command_fingerprint must be SHA-256 text")
        object.__setattr__(self, "command_fingerprint", fingerprint)
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version != DOMESTIC_MARKET_VALIDATION_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported domestic market validation receipt schema")


@dataclass(frozen=True, slots=True)
class DomesticMarketValidationPublication:
    assessment: DomesticMarketValidationAssessment
    receipt: DomesticMarketValidationReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.assessment, DomesticMarketValidationAssessment):
            raise TypeError("assessment must be DomesticMarketValidationAssessment")
        if not isinstance(self.receipt, DomesticMarketValidationReceipt):
            raise TypeError("receipt must be DomesticMarketValidationReceipt")
        if self.receipt.assessment_id != self.assessment.assessment_id:
            raise ValueError("receipt must reference assessment")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class DomesticMarketValidationRepository(Protocol):
    def validate_replay(self, command_id: str, fingerprint: str) -> DomesticMarketValidationPublication | None: ...
    def get_market_identity_binding(self, opportunity_id: str) -> OpportunityMarketIdentityBinding | None: ...
    def get_observation_by_id(self, observation_id: str): ...
    def get_competition_assessment_snapshot(self, snapshot_id: str): ...
    def get_demand_assessment_snapshot(self, snapshot_id: str): ...
    def get_human_verified_external_signals_by_ids(self, identity, signal_ids): ...
    def save_assessment(self, command, assessment, receipt) -> DomesticMarketValidationPublication: ...
    def get_assessment(self, assessment_id: str) -> DomesticMarketValidationAssessment | None: ...
    def get_receipt(self, command_id: str) -> DomesticMarketValidationReceipt | None: ...


class ValidateDomesticMarketForCapital:
    def __init__(
        self,
        repository: DomesticMarketValidationRepository,
        *,
        assessment_id_generator: Callable[[], str],
        evaluated_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._assessment_id = assessment_id_generator
        self._evaluated = evaluated_clock
        self._committed = committed_clock

    def execute(self, command: ValidateDomesticMarketCommand) -> DomesticMarketValidationPublication:
        if not isinstance(command, ValidateDomesticMarketCommand):
            raise TypeError("command must be ValidateDomesticMarketCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replay

        evaluated_at = _aware(self._evaluated(), "evaluated_at")
        reasons: set[DomesticMarketValidationReasonCode] = set()
        binding = self._repository.get_market_identity_binding(
            command.opportunity_identity.opportunity_id
        )
        if command.market_identity.market.upper() != "KR":
            reasons.add(DomesticMarketValidationReasonCode.NON_DOMESTIC_MARKET)
        if (
            binding is None
            or binding.opportunity_id != command.opportunity_identity.opportunity_id
            or binding.discovery_reference != command.opportunity_identity.discovery_reference
            or binding.market_observation_identity != command.market_identity
        ):
            reasons.add(DomesticMarketValidationReasonCode.OPPORTUNITY_MARKET_LINEAGE_MISMATCH)

        competition_observation = self._repository.get_observation_by_id(
            command.competition_observation_id
        )
        competition_snapshot = self._repository.get_competition_assessment_snapshot(
            command.competition_assessment_id
        )
        competition_source = self._evaluate_competition(
            command,
            competition_observation,
            competition_snapshot,
            evaluated_at,
            reasons,
        )

        demand_observation = self._repository.get_observation_by_id(
            command.demand_observation_id
        )
        demand_snapshot = self._repository.get_demand_assessment_snapshot(
            command.demand_assessment_id
        )
        demand_source = self._evaluate_demand(
            command,
            demand_observation,
            demand_snapshot,
            evaluated_at,
            reasons,
        )

        expected_reviewed = (
            command.competition_observation_id,
            command.competition_assessment_id,
            command.demand_observation_id,
            command.demand_assessment_id,
            *command.accepted_external_signal_ids,
        )
        if command.verification.reviewed_source_ids != expected_reviewed:
            reasons.add(DomesticMarketValidationReasonCode.OPPORTUNITY_MARKET_LINEAGE_MISMATCH)
        if not command.verification.current_use_confirmed:
            reasons.add(DomesticMarketValidationReasonCode.CURRENT_USE_VERIFICATION_MISSING)
        if command.verification.verified_at > evaluated_at:
            reasons.add(DomesticMarketValidationReasonCode.SOURCE_TIME_IN_FUTURE)

        if command.accepted_external_signal_ids:
            signals = self._repository.get_human_verified_external_signals_by_ids(
                command.market_identity,
                command.accepted_external_signal_ids,
            )
            if (
                tuple(getattr(value, "signal_id", None) for value in signals)
                != command.accepted_external_signal_ids
                or any(getattr(value, "identity", None) != command.market_identity for value in signals)
            ):
                reasons.add(DomesticMarketValidationReasonCode.OPPORTUNITY_MARKET_LINEAGE_MISMATCH)

        manifest = DomesticMarketValidationSourceManifest(
            opportunity_id=command.opportunity_identity.opportunity_id,
            discovery_reference=command.opportunity_identity.discovery_reference,
            market_identity=command.market_identity,
            competition=competition_source,
            demand=demand_source,
            accepted_external_signal_ids=command.accepted_external_signal_ids,
        )
        ordered = tuple(
            DomesticMarketValidationReason(code)
            for code in sorted(reasons, key=lambda value: value.order)
        )
        state = (
            DomesticMarketValidationState.VALIDATED_FOR_CAPITAL
            if not ordered
            else DomesticMarketValidationState.BLOCKED
        )
        assessment = DomesticMarketValidationAssessment(
            assessment_id=_text(self._assessment_id(), "assessment_id"),
            source_manifest=manifest,
            verification=command.verification,
            state=state,
            blocking_reasons=ordered,
            policy_name=command.policy_name,
            policy_version=command.policy_version,
            requested_at=command.requested_at,
            evaluated_at=evaluated_at,
        )
        receipt = DomesticMarketValidationReceipt(
            command.command_id,
            assessment.assessment_id,
            command.fingerprint,
            _aware(self._committed(), "committed_at"),
        )
        return self._repository.save_assessment(command, assessment, receipt)

    def _evaluate_competition(self, command, observation, snapshot, evaluated_at, reasons):
        if not isinstance(observation, CompetitionObservation) or not isinstance(
            snapshot, CompetitionAssessmentSnapshot
        ):
            reasons.add(DomesticMarketValidationReasonCode.COMPETITION_SOURCE_MISSING)
        if isinstance(snapshot, CompetitionAssessmentSnapshot) and (
            snapshot.availability is not DecisionEvidenceAvailability.COMPLETE
        ):
            reasons.add(DomesticMarketValidationReasonCode.COMPETITION_ASSESSMENT_NOT_COMPLETE)
        self._lineage(command, observation, snapshot, "competition", reasons)
        evidence = self._evidence(
            observation,
            COMPETITION_REQUIRED_METRICS,
            DomesticMarketValidationReasonCode.COMPETITION_REQUIRED_METRIC_MISSING,
            DomesticMarketValidationReasonCode.COMPETITION_PROVENANCE_INSUFFICIENT,
            command.verification.verified_at,
            evaluated_at,
            reasons,
        )
        return self._source_manifest(
            command.competition_observation_id,
            command.competition_assessment_id,
            observation,
            snapshot,
            evidence,
        )

    def _evaluate_demand(self, command, observation, snapshot, evaluated_at, reasons):
        if not isinstance(observation, DemandObservation) or not isinstance(
            snapshot, DemandAssessmentSnapshot
        ):
            reasons.add(DomesticMarketValidationReasonCode.DEMAND_SOURCE_MISSING)
        if isinstance(snapshot, DemandAssessmentSnapshot) and (
            snapshot.availability is not DecisionEvidenceAvailability.COMPLETE
        ):
            reasons.add(DomesticMarketValidationReasonCode.DEMAND_ASSESSMENT_PARTIAL)
        self._lineage(command, observation, snapshot, "demand", reasons)
        evidence = self._evidence(
            observation,
            DEMAND_REQUIRED_METRICS,
            DomesticMarketValidationReasonCode.DEMAND_REQUIRED_METRIC_MISSING,
            DomesticMarketValidationReasonCode.DEMAND_PROVENANCE_INSUFFICIENT,
            command.verification.verified_at,
            evaluated_at,
            reasons,
        )
        return self._source_manifest(
            command.demand_observation_id,
            command.demand_assessment_id,
            observation,
            snapshot,
            evidence,
        )

    @staticmethod
    def _lineage(command, observation, snapshot, source_type, reasons) -> None:
        expected_observation_id = getattr(command, f"{source_type}_observation_id")
        if observation is not None and (
            getattr(observation, "observation_id", None) != expected_observation_id
            or getattr(observation, "identity", None) != command.market_identity
        ):
            reasons.add(DomesticMarketValidationReasonCode.OPPORTUNITY_MARKET_LINEAGE_MISMATCH)
        if snapshot is not None and (
            getattr(snapshot, "source_observation_id", None) != expected_observation_id
            or getattr(snapshot, "identity", None) != command.market_identity
            or getattr(snapshot, "schema_version", None) != ASSESSMENT_SCHEMA_VERSION
            or getattr(snapshot, "policy_version", None)
            != (COMPETITION_POLICY_VERSION if source_type == "competition" else DEMAND_POLICY_VERSION)
        ):
            reasons.add(DomesticMarketValidationReasonCode.OPPORTUNITY_MARKET_LINEAGE_MISMATCH)

    @staticmethod
    def _evidence(
        observation,
        required_metrics,
        missing_reason,
        provenance_reason,
        verified_at,
        evaluated_at,
        reasons,
    ) -> tuple[DomesticMarketMetricEvidence, ...]:
        if observation is None or not hasattr(observation, "evidence"):
            return ()
        if observation.observed_at > verified_at or observation.observed_at > evaluated_at:
            reasons.add(DomesticMarketValidationReasonCode.SOURCE_TIME_IN_FUTURE)
        result = []
        for metric in required_metrics:
            item = observation.evidence.get(metric)
            if item is None or item.value is None:
                reasons.add(missing_reason)
                continue
            result.append(DomesticMarketMetricEvidence(
                metric=metric,
                value=item.value,
                source=item.source,
                reference=item.reference,
                observed_at=item.observed_at,
                collection_method=item.collection_method,
                status=item.status,
                confidence=item.confidence,
                unit=item.unit,
            ))
            if item.source is None or item.reference is None or not item.collection_method:
                reasons.add(provenance_reason)
            if item.status not in ACCEPTED_EVIDENCE_STATUSES:
                reasons.add(DomesticMarketValidationReasonCode.REQUIRED_EVIDENCE_STATUS_UNSUPPORTED)
            if item.observed_at is None:
                reasons.add(DomesticMarketValidationReasonCode.SOURCE_TIME_UNKNOWN)
            elif item.observed_at > verified_at or item.observed_at > evaluated_at:
                reasons.add(DomesticMarketValidationReasonCode.SOURCE_TIME_IN_FUTURE)
        return tuple(result)

    @staticmethod
    def _source_manifest(observation_id, assessment_id, observation, snapshot, evidence):
        return DomesticMarketAnalysisSourceManifest(
            observation_id=observation_id,
            assessment_id=assessment_id,
            observation_schema_version=getattr(observation, "schema_version", None),
            assessment_schema_version=getattr(snapshot, "schema_version", None),
            assessment_policy_version=getattr(snapshot, "policy_version", None),
            availability=(
                getattr(getattr(snapshot, "availability", None), "value", None)
            ),
            evidence=evidence,
        )


__all__ = [
    name for name in globals()
    if name.startswith("DomesticMarket") or name.startswith("ValidateDomestic")
    or name.startswith("DOMESTIC_MARKET")
]
