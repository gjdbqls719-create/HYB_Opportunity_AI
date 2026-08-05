"""Candidate-to-Opportunity admission promotion contracts and boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import json
from typing import Callable, Protocol

from app.application.candidate_issuance import CandidateIssuanceRepository
from app.application.opportunity_validation.models import AddToValidationQueueCommand, ValidationQueueItem
from app.application.opportunity_validation.service import OpportunityValidationService
from app.application.opportunity_market_identity import OpportunityMarketIdentityBinding
from app.domain.discovery_identity import DiscoveryOpportunityContext
from app.domain.market_intelligence import MarketObservationIdentity


PROMOTION_COMMAND_SCHEMA_VERSION = "candidate-promotion-command-v1"
PROMOTION_BINDING_SCHEMA_VERSION = "candidate-opportunity-binding-v1"
PROMOTION_RECEIPT_SCHEMA_VERSION = "candidate-promotion-receipt-v1"


class OpportunityCandidatePromotionError(RuntimeError): pass
class CandidateForPromotionNotFoundError(OpportunityCandidatePromotionError): pass
class CandidatePromotionContextNotFoundError(OpportunityCandidatePromotionError): pass
class CandidateAlreadyPromotedError(OpportunityCandidatePromotionError): pass
class OpportunityAlreadyBoundToCandidateError(OpportunityCandidatePromotionError): pass
class CandidatePromotionIdentityConflictError(OpportunityCandidatePromotionError): pass
class CandidatePromotionMarketIdentityConflictError(OpportunityCandidatePromotionError): pass
class CandidatePromotionCommandConflictError(OpportunityCandidatePromotionError): pass
class MalformedCandidatePromotionPersistenceError(OpportunityCandidatePromotionError): pass
class UnsupportedCandidatePromotionVersionError(MalformedCandidatePromotionPersistenceError): pass
class CandidatePromotionHistoryError(OpportunityCandidatePromotionError): pass
class CandidatePromotionReceiptError(OpportunityCandidatePromotionError): pass
class CandidatePromotionCommitError(OpportunityCandidatePromotionError): pass
class CandidatePromotionPersistenceError(OpportunityCandidatePromotionError): pass


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime): raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None: raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class PromoteOpportunityCandidateCommand:
    promotion_command_id: str
    candidate_id: str
    title: str
    admission_recommendation: str
    admission_score: float
    admission_roi: float
    currency: str
    admission_safety_status: str
    operator_id: str
    reason: str
    requested_at: datetime
    opportunity_id: str | None = None
    note: str | None = None
    schema_version: str = PROMOTION_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("promotion_command_id", "candidate_id", "title", "admission_recommendation",
                     "currency", "admission_safety_status", "operator_id", "reason", "schema_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.opportunity_id is not None:
            object.__setattr__(self, "opportunity_id", _text(self.opportunity_id, "opportunity_id"))
        _aware(self.requested_at, "requested_at")
        if self.schema_version != PROMOTION_COMMAND_SCHEMA_VERSION:
            raise UnsupportedCandidatePromotionVersionError("unsupported promotion command version")


@dataclass(frozen=True, slots=True)
class CandidateOpportunityBinding:
    binding_id: str
    candidate_id: str
    opportunity_id: str
    discovery_reference: str
    market_observation_identity: MarketObservationIdentity
    discovery_command_id: str
    discovery_execution_id: str
    finalized_group_id: str
    promotion_command_id: str
    promoted_at: datetime
    schema_version: str = PROMOTION_BINDING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("binding_id", "candidate_id", "opportunity_id", "discovery_reference",
                     "discovery_command_id", "discovery_execution_id", "finalized_group_id",
                     "promotion_command_id", "schema_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.market_observation_identity, MarketObservationIdentity):
            raise TypeError("market_observation_identity must be MarketObservationIdentity")
        _aware(self.promoted_at, "promoted_at")
        if self.schema_version != PROMOTION_BINDING_SCHEMA_VERSION:
            raise UnsupportedCandidatePromotionVersionError("unsupported promotion binding version")


@dataclass(frozen=True, slots=True)
class CandidatePromotionReceipt:
    promotion_command_id: str
    candidate_id: str
    opportunity_id: str
    command_fingerprint: str
    subject_fingerprint: str
    committed_at: datetime
    schema_version: str = PROMOTION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("promotion_command_id", "candidate_id", "opportunity_id", "schema_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("command_fingerprint", "subject_fingerprint"):
            value = _text(getattr(self, name), name)
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError(f"{name} must be lowercase SHA-256 text")
        _aware(self.committed_at, "committed_at")
        if self.schema_version != PROMOTION_RECEIPT_SCHEMA_VERSION:
            raise UnsupportedCandidatePromotionVersionError("unsupported promotion receipt version")


@dataclass(frozen=True, slots=True)
class CandidatePromotionResult:
    item: ValidationQueueItem
    binding: CandidateOpportunityBinding
    receipt: CandidatePromotionReceipt
    replayed: bool


def _payload(command: PromoteOpportunityCandidateCommand) -> dict[str, object]:
    return {name: getattr(command, name) for name in (
        "candidate_id", "title", "admission_recommendation", "admission_score", "admission_roi",
        "currency", "admission_safety_status", "operator_id", "reason", "opportunity_id", "note", "schema_version"
    )} | {"requested_at": command.requested_at.isoformat()}


def _hash(payload: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def promotion_command_fingerprint(command: PromoteOpportunityCandidateCommand) -> str:
    return _hash(_payload(command))


def promotion_subject_fingerprint(command: PromoteOpportunityCandidateCommand) -> str:
    payload = _payload(command); payload.pop("opportunity_id"); payload.pop("requested_at")
    return _hash(payload)


class CandidatePromotionRepository(Protocol):
    def validate_promotion_replay(self, command_id: str, fingerprint: str) -> CandidatePromotionResult | None: ...
    def get_promotion_by_candidate(self, candidate_id: str) -> CandidateOpportunityBinding | None: ...
    def get_promotion_by_opportunity(self, opportunity_id: str) -> CandidateOpportunityBinding | None: ...
    def get_promotion_receipt(self, command_id: str) -> CandidatePromotionReceipt | None: ...
    def promote_candidate(self, *, lifecycle, transition, snapshot, market_binding,
                          candidate_binding: CandidateOpportunityBinding,
                          receipt: CandidatePromotionReceipt,
                          command_fingerprint: str, subject_fingerprint: str) -> CandidatePromotionResult: ...
    def save_promotion_alias(self, binding: CandidateOpportunityBinding,
                             receipt: CandidatePromotionReceipt) -> CandidatePromotionResult: ...


class PromoteOpportunityCandidate:
    def __init__(self, candidates: CandidateIssuanceRepository,
                 promotions: CandidatePromotionRepository,
                 validation: OpportunityValidationService, *,
                 opportunity_id_generator: Callable[[], str],
                 binding_id_generator: Callable[[], str], clock: Callable[[], datetime]) -> None:
        self._candidates, self._promotions, self._validation = candidates, promotions, validation
        self._opportunity_id_generator = opportunity_id_generator
        self._binding_id_generator = binding_id_generator
        self._clock = clock

    def execute(self, command: PromoteOpportunityCandidateCommand) -> CandidatePromotionResult:
        if not isinstance(command, PromoteOpportunityCandidateCommand):
            raise TypeError("command must be PromoteOpportunityCandidateCommand")
        fingerprint = promotion_command_fingerprint(command)
        replay = self._promotions.validate_promotion_replay(command.promotion_command_id, fingerprint)
        if replay is not None: return replay
        candidate = self._candidates.get_candidate(command.candidate_id)
        if candidate is None: raise CandidateForPromotionNotFoundError("Candidate was not found")
        context = self._candidates.get_context(command.candidate_id)
        if context is None: raise CandidatePromotionContextNotFoundError("Candidate context was not found")
        if context.candidate_identity != candidate:
            raise CandidatePromotionIdentityConflictError("Candidate and context identity differ")
        existing = self._promotions.get_promotion_by_candidate(command.candidate_id)
        subject = promotion_subject_fingerprint(command)
        if existing is not None:
            if command.opportunity_id is not None and command.opportunity_id != existing.opportunity_id:
                raise CandidateAlreadyPromotedError("Candidate is already promoted to another Opportunity")
            receipt = CandidatePromotionReceipt(command.promotion_command_id, command.candidate_id,
                existing.opportunity_id, fingerprint, subject, _aware(self._clock(), "committed_at"))
            alias = replace(existing, promotion_command_id=command.promotion_command_id)
            return self._promotions.save_promotion_alias(alias, receipt)
        opportunity_id = command.opportunity_id or _text(self._opportunity_id_generator(), "opportunity_id")
        promoted_at = _aware(self._clock(), "promoted_at")
        admission = AddToValidationQueueCommand(
            discovery_reference=candidate.discovery_reference,
            marketplace=context.market_observation_identity.marketplace,
            title=command.title, admission_recommendation=command.admission_recommendation,
            admission_score=command.admission_score, admission_roi=command.admission_roi,
            currency=command.currency, admission_safety_status=command.admission_safety_status,
            operator_id=command.operator_id, reason=command.reason, captured_at=command.requested_at,
            opportunity_id=opportunity_id, note=command.note,
            market_observation_identity=context.market_observation_identity)
        lifecycle, transition, snapshot = self._validation.prepare_admission(admission)
        market_binding = self._validation.prepare_market_binding(admission, lifecycle)
        issuance = self._candidates.get_by_discovery_group(context.command_id, self._finalized_group(command.candidate_id))
        if issuance is None or issuance.candidate_identity != candidate:
            raise CandidatePromotionIdentityConflictError("Candidate issuance lineage is unavailable")
        binding = CandidateOpportunityBinding(_text(self._binding_id_generator(), "binding_id"),
            candidate.candidate_id, opportunity_id, candidate.discovery_reference,
            context.market_observation_identity, context.command_id, context.discovery_execution_id,
            issuance.finalized_group_id, command.promotion_command_id, promoted_at)
        receipt = CandidatePromotionReceipt(command.promotion_command_id, candidate.candidate_id,
            opportunity_id, fingerprint, subject, promoted_at)
        return self._promotions.promote_candidate(lifecycle=lifecycle, transition=transition,
            snapshot=snapshot, market_binding=market_binding, candidate_binding=binding,
            receipt=receipt, command_fingerprint=fingerprint, subject_fingerprint=subject)

    def _finalized_group(self, candidate_id: str) -> str:
        receipts = self._candidates.list_receipts_for_candidate(candidate_id)
        if not receipts: raise CandidatePromotionIdentityConflictError("Candidate issuance receipt is unavailable")
        return receipts[0].finalized_group_id


class CandidatePromotionProductionEntry:
    """Composes persisted Candidate promotion with Validation admission."""

    def __init__(
        self,
        *,
        candidate_repository: CandidateIssuanceRepository,
        promotion_repository: CandidatePromotionRepository,
        opportunity_id_generator: Callable[[], str],
        binding_id_generator: Callable[[], str],
        clock: Callable[[], datetime],
    ) -> None:
        validation = OpportunityValidationService(
            queue_repository=promotion_repository,
            lifecycle_repository=promotion_repository,
        )
        self._promote = PromoteOpportunityCandidate(
            candidate_repository,
            promotion_repository,
            validation,
            opportunity_id_generator=opportunity_id_generator,
            binding_id_generator=binding_id_generator,
            clock=clock,
        )

    def execute(
        self, command: PromoteOpportunityCandidateCommand
    ) -> CandidatePromotionResult:
        return self._promote.execute(command)


__all__ = (
    "PROMOTION_COMMAND_SCHEMA_VERSION", "PROMOTION_BINDING_SCHEMA_VERSION",
    "PROMOTION_RECEIPT_SCHEMA_VERSION", "PromoteOpportunityCandidateCommand",
    "CandidateOpportunityBinding", "CandidatePromotionReceipt",
    "CandidatePromotionResult", "CandidatePromotionRepository",
    "PromoteOpportunityCandidate", "CandidatePromotionProductionEntry",
    "promotion_command_fingerprint",
    "promotion_subject_fingerprint", "OpportunityCandidatePromotionError",
    "CandidateForPromotionNotFoundError", "CandidatePromotionContextNotFoundError",
    "CandidateAlreadyPromotedError", "OpportunityAlreadyBoundToCandidateError",
    "CandidatePromotionIdentityConflictError", "CandidatePromotionMarketIdentityConflictError",
    "CandidatePromotionCommandConflictError", "MalformedCandidatePromotionPersistenceError",
    "UnsupportedCandidatePromotionVersionError", "CandidatePromotionHistoryError",
    "CandidatePromotionReceiptError", "CandidatePromotionCommitError",
    "CandidatePromotionPersistenceError",
)
