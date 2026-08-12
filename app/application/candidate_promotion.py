"""Candidate-to-Opportunity admission promotion contracts and boundary."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import json
from typing import Callable, Protocol

from app.application.candidate_issuance import CandidateIssuanceRepository
from app.application.opportunity_validation.models import (
    AddToValidationQueueCommand,
    FounderSelectedAdmissionBasis,
    ValidationQueueItem,
    ValidationQueueItemV2,
)
from app.application.opportunity_validation.service import OpportunityValidationService
from app.application.opportunity_market_identity import OpportunityMarketIdentityBinding
from app.application.product_snapshot_capture import (
    ProductSnapshotCaptureRepository,
)
from app.domain.discovery_identity import DiscoveryOpportunityContext
from app.domain.market_intelligence import MarketObservationIdentity
from app.domain.opportunity import OpportunityLifecycle


PROMOTION_COMMAND_SCHEMA_VERSION = "candidate-promotion-command-v1"
PROMOTION_BINDING_SCHEMA_VERSION = "candidate-opportunity-binding-v1"
PROMOTION_RECEIPT_SCHEMA_VERSION = "candidate-promotion-receipt-v1"
PROMOTION_V2_CONTRACT_VERSION = "2.0.0"
PROMOTION_COMMAND_V2_SCHEMA_VERSION = "candidate-promotion-command-v2"
PROMOTION_BINDING_V2_SCHEMA_VERSION = "candidate-opportunity-binding-v2"
PROMOTION_RECEIPT_V2_SCHEMA_VERSION = "candidate-promotion-receipt-v2"
PROMOTION_SOURCE_V2_SCHEMA_VERSION = "candidate-promotion-source-v2"
PROMOTION_ADMISSION_V2_SCHEMA_VERSION = "candidate-promotion-admission-v2"
PROMOTION_V2_POLICY_NAME = "candidate-promotion-founder-selection"
PROMOTION_V2_POLICY_VERSION = "2.0.0"
PROMOTION_V2_ADMISSION_KIND = "founder_selected_for_deeper_validation"


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
class CandidatePromotionV2SourceNotFoundError(OpportunityCandidatePromotionError): pass
class CandidatePromotionV2LineageConflictError(OpportunityCandidatePromotionError): pass


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
class PromoteOpportunityCandidateV2Command:
    promotion_command_id: str
    candidate_id: str
    finalized_group_id: str
    representative_product_snapshot_id: str
    operator_id: str
    reason: str
    requested_at: datetime
    note: str | None = None
    contract_version: str = PROMOTION_V2_CONTRACT_VERSION
    schema_version: str = PROMOTION_COMMAND_V2_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "promotion_command_id", "candidate_id", "finalized_group_id",
            "representative_product_snapshot_id", "operator_id", "reason",
            "contract_version", "schema_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.note is not None:
            object.__setattr__(self, "note", _text(self.note, "note"))
        _aware(self.requested_at, "requested_at")
        if self.contract_version != PROMOTION_V2_CONTRACT_VERSION:
            raise UnsupportedCandidatePromotionVersionError(
                "unsupported Candidate Promotion contract version"
            )
        if self.schema_version != PROMOTION_COMMAND_V2_SCHEMA_VERSION:
            raise UnsupportedCandidatePromotionVersionError(
                "unsupported Candidate Promotion v2 command version"
            )


@dataclass(frozen=True, slots=True)
class CandidatePromotionV2SourceManifest:
    binding_id: str
    candidate_id: str
    finalized_group_id: str
    product_snapshot_capture_command_id: str
    product_snapshot_ids: tuple[str, ...]
    representative_product_snapshot_id: str
    schema_version: str = PROMOTION_SOURCE_V2_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "binding_id", "candidate_id", "finalized_group_id",
            "product_snapshot_capture_command_id", "representative_product_snapshot_id",
            "schema_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.product_snapshot_ids, tuple) or not self.product_snapshot_ids:
            raise ValueError("product_snapshot_ids must be a non-empty tuple")
        if any(not isinstance(value, str) or not value.strip() for value in self.product_snapshot_ids):
            raise ValueError("product_snapshot_ids must contain non-empty text")
        if len(set(self.product_snapshot_ids)) != len(self.product_snapshot_ids):
            raise ValueError("product_snapshot_ids must be unique")
        if self.representative_product_snapshot_id not in self.product_snapshot_ids:
            raise ValueError("representative Product Snapshot must belong to the capture")
        if self.schema_version != PROMOTION_SOURCE_V2_SCHEMA_VERSION:
            raise UnsupportedCandidatePromotionVersionError(
                "unsupported Candidate Promotion v2 source version"
            )


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
    product_snapshot_capture_command_id: str | None = None
    product_snapshot_ids: tuple[str, ...] = ()
    representative_product_snapshot_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("binding_id", "candidate_id", "opportunity_id", "discovery_reference",
                     "discovery_command_id", "discovery_execution_id", "finalized_group_id",
                     "promotion_command_id", "schema_version"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.market_observation_identity, MarketObservationIdentity):
            raise TypeError("market_observation_identity must be MarketObservationIdentity")
        _aware(self.promoted_at, "promoted_at")
        if self.schema_version == PROMOTION_BINDING_SCHEMA_VERSION:
            if (
                self.product_snapshot_capture_command_id is not None
                or self.product_snapshot_ids
                or self.representative_product_snapshot_id is not None
            ):
                raise UnsupportedCandidatePromotionVersionError(
                    "v1 promotion binding cannot contain v2 Product sources"
                )
        elif self.schema_version == PROMOTION_BINDING_V2_SCHEMA_VERSION:
            object.__setattr__(
                self,
                "product_snapshot_capture_command_id",
                _text(
                    self.product_snapshot_capture_command_id,
                    "product_snapshot_capture_command_id",
                ),
            )
            if not isinstance(self.product_snapshot_ids, tuple) or not self.product_snapshot_ids:
                raise ValueError("v2 promotion binding requires Product Snapshot IDs")
            if any(not isinstance(value, str) or not value.strip() for value in self.product_snapshot_ids):
                raise ValueError("v2 Product Snapshot IDs must contain non-empty text")
            if len(set(self.product_snapshot_ids)) != len(self.product_snapshot_ids):
                raise ValueError("v2 Product Snapshot IDs must be unique")
            object.__setattr__(
                self,
                "representative_product_snapshot_id",
                _text(
                    self.representative_product_snapshot_id,
                    "representative_product_snapshot_id",
                ),
            )
            if self.representative_product_snapshot_id not in self.product_snapshot_ids:
                raise ValueError("representative Product Snapshot must belong to binding")
        else:
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
        if self.schema_version not in (
            PROMOTION_RECEIPT_SCHEMA_VERSION,
            PROMOTION_RECEIPT_V2_SCHEMA_VERSION,
        ):
            raise UnsupportedCandidatePromotionVersionError("unsupported promotion receipt version")


@dataclass(frozen=True, slots=True)
class CandidatePromotionResult:
    item: ValidationQueueItem | ValidationQueueItemV2
    binding: CandidateOpportunityBinding
    receipt: CandidatePromotionReceipt
    replayed: bool


def _v2_payload(command: PromoteOpportunityCandidateV2Command) -> dict[str, object]:
    return {
        "candidate_id": command.candidate_id,
        "finalized_group_id": command.finalized_group_id,
        "representative_product_snapshot_id": command.representative_product_snapshot_id,
        "operator_id": command.operator_id,
        "reason": command.reason,
        "requested_at": command.requested_at.isoformat(),
        "note": command.note,
        "contract_version": command.contract_version,
        "schema_version": command.schema_version,
    }


def promotion_v2_command_fingerprint(command: PromoteOpportunityCandidateV2Command) -> str:
    return _hash(_v2_payload(command))


def promotion_v2_subject_fingerprint(
    command: PromoteOpportunityCandidateV2Command,
    source: CandidatePromotionV2SourceManifest,
) -> str:
    payload = _v2_payload(command)
    payload.pop("requested_at")
    payload.update({
        "product_snapshot_capture_command_id": source.product_snapshot_capture_command_id,
        "product_snapshot_ids": source.product_snapshot_ids,
        "source_schema_version": source.schema_version,
        "admission_kind": PROMOTION_V2_ADMISSION_KIND,
        "policy_name": PROMOTION_V2_POLICY_NAME,
        "policy_version": PROMOTION_V2_POLICY_VERSION,
    })
    return _hash(payload)


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
    def promote_candidate_v2(
        self, *, command: PromoteOpportunityCandidateV2Command, lifecycle, transition,
        market_binding, candidate_binding: CandidateOpportunityBinding,
        source_manifest: CandidatePromotionV2SourceManifest,
        admission: FounderSelectedAdmissionBasis,
        receipt: CandidatePromotionReceipt, command_fingerprint: str,
        subject_fingerprint: str,
    ) -> CandidatePromotionResult: ...
    def save_promotion_v2_alias(
        self, command: PromoteOpportunityCandidateV2Command,
        binding: CandidateOpportunityBinding,
        source_manifest: CandidatePromotionV2SourceManifest,
        receipt: CandidatePromotionReceipt,
    ) -> CandidatePromotionResult: ...


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


class PromoteOpportunityCandidateV2:
    def __init__(
        self,
        candidates: CandidateIssuanceRepository,
        captures: ProductSnapshotCaptureRepository,
        promotions: CandidatePromotionRepository,
        *,
        opportunity_id_generator: Callable[[], str],
        binding_id_generator: Callable[[], str],
        admission_id_generator: Callable[[], str],
        clock: Callable[[], datetime],
    ) -> None:
        self._candidates = candidates
        self._captures = captures
        self._promotions = promotions
        self._opportunity_id_generator = opportunity_id_generator
        self._binding_id_generator = binding_id_generator
        self._admission_id_generator = admission_id_generator
        self._clock = clock

    def execute(
        self, command: PromoteOpportunityCandidateV2Command
    ) -> CandidatePromotionResult:
        if not isinstance(command, PromoteOpportunityCandidateV2Command):
            raise TypeError("command must be PromoteOpportunityCandidateV2Command")
        fingerprint = promotion_v2_command_fingerprint(command)
        replay = self._promotions.validate_promotion_replay(
            command.promotion_command_id, fingerprint
        )
        if replay is not None:
            if replay.receipt.schema_version != PROMOTION_RECEIPT_V2_SCHEMA_VERSION:
                raise CandidatePromotionCommandConflictError(
                    "Candidate Promotion command version conflicts"
                )
            return replay

        candidate = self._candidates.get_candidate(command.candidate_id)
        if candidate is None:
            raise CandidateForPromotionNotFoundError("Candidate was not found")
        context = self._candidates.get_context(command.candidate_id)
        if context is None:
            raise CandidatePromotionContextNotFoundError("Candidate context was not found")
        if context.candidate_identity != candidate:
            raise CandidatePromotionIdentityConflictError(
                "Candidate and context identity differ"
            )
        issuance = self._candidates.get_by_discovery_group(
            context.command_id, command.finalized_group_id
        )
        if (
            issuance is None
            or issuance.candidate_identity != candidate
            or issuance.finalized_group_id != command.finalized_group_id
            or issuance.discovery_context != context
        ):
            raise CandidatePromotionV2LineageConflictError(
                "Candidate issuance and finalized Group lineage differ"
            )

        existing = self._promotions.get_promotion_by_candidate(command.candidate_id)
        if existing is not None and existing.schema_version != PROMOTION_BINDING_V2_SCHEMA_VERSION:
            raise CandidateAlreadyPromotedError(
                "Candidate is already promoted under another contract version"
            )
        source_manifest = self._load_source_manifest(command, candidate, context)
        subject = promotion_v2_subject_fingerprint(command, source_manifest)
        if existing is not None:
            if (
                existing.finalized_group_id != source_manifest.finalized_group_id
                or existing.product_snapshot_capture_command_id
                != source_manifest.product_snapshot_capture_command_id
                or existing.product_snapshot_ids != source_manifest.product_snapshot_ids
                or existing.representative_product_snapshot_id
                != source_manifest.representative_product_snapshot_id
            ):
                raise CandidateAlreadyPromotedError(
                    "Candidate Promotion v2 source differs"
                )
            committed_at = _aware(self._clock(), "committed_at")
            receipt = CandidatePromotionReceipt(
                command.promotion_command_id,
                command.candidate_id,
                existing.opportunity_id,
                fingerprint,
                subject,
                committed_at,
                PROMOTION_RECEIPT_V2_SCHEMA_VERSION,
            )
            return self._promotions.save_promotion_v2_alias(
                command, existing, source_manifest, receipt
            )

        opportunity_id = _text(
            self._opportunity_id_generator(), "opportunity_id"
        )
        binding_id = _text(self._binding_id_generator(), "binding_id")
        admission_id = _text(self._admission_id_generator(), "admission_id")
        promoted_at = _aware(self._clock(), "promoted_at")
        lifecycle = OpportunityLifecycle(
            opportunity_id,
            candidate.discovery_reference,
            created_at=promoted_at,
            updated_at=promoted_at,
        )
        transition = lifecycle.creation_transition(
            operator_id=command.operator_id,
            reason=command.reason,
            note=command.note,
        )
        market_binding = OpportunityMarketIdentityBinding(
            opportunity_id,
            candidate.discovery_reference,
            context.market_observation_identity,
            promoted_at,
        )
        binding = CandidateOpportunityBinding(
            binding_id=binding_id,
            candidate_id=candidate.candidate_id,
            opportunity_id=opportunity_id,
            discovery_reference=candidate.discovery_reference,
            market_observation_identity=context.market_observation_identity,
            discovery_command_id=context.command_id,
            discovery_execution_id=context.discovery_execution_id,
            finalized_group_id=command.finalized_group_id,
            promotion_command_id=command.promotion_command_id,
            promoted_at=promoted_at,
            schema_version=PROMOTION_BINDING_V2_SCHEMA_VERSION,
            product_snapshot_capture_command_id=(
                source_manifest.product_snapshot_capture_command_id
            ),
            product_snapshot_ids=source_manifest.product_snapshot_ids,
            representative_product_snapshot_id=(
                source_manifest.representative_product_snapshot_id
            ),
        )
        source_manifest = replace(source_manifest, binding_id=binding_id)
        admission = FounderSelectedAdmissionBasis(
            admission_id=admission_id,
            candidate_id=candidate.candidate_id,
            candidate_opportunity_binding_id=binding_id,
            discovery_command_id=context.command_id,
            discovery_execution_id=context.discovery_execution_id,
            finalized_group_id=command.finalized_group_id,
            product_snapshot_capture_command_id=(
                source_manifest.product_snapshot_capture_command_id
            ),
            product_snapshot_ids=source_manifest.product_snapshot_ids,
            representative_product_snapshot_id=(
                source_manifest.representative_product_snapshot_id
            ),
            operator_id=command.operator_id,
            reason=command.reason,
            requested_at=command.requested_at,
            promoted_at=promoted_at,
            committed_at=promoted_at,
        )
        receipt = CandidatePromotionReceipt(
            command.promotion_command_id,
            candidate.candidate_id,
            opportunity_id,
            fingerprint,
            subject,
            promoted_at,
            PROMOTION_RECEIPT_V2_SCHEMA_VERSION,
        )
        return self._promotions.promote_candidate_v2(
            command=command,
            lifecycle=lifecycle,
            transition=transition,
            market_binding=market_binding,
            candidate_binding=binding,
            source_manifest=source_manifest,
            admission=admission,
            receipt=receipt,
            command_fingerprint=fingerprint,
            subject_fingerprint=subject,
        )

    def _load_source_manifest(self, command, candidate, context):
        group = self._captures.get_group(command.finalized_group_id)
        if group is None:
            raise CandidatePromotionV2SourceNotFoundError(
                "finalized Product Group was not found"
            )
        representative_binding = self._captures.get_binding(
            command.representative_product_snapshot_id
        )
        if representative_binding is None:
            raise CandidatePromotionV2SourceNotFoundError(
                "representative Product Snapshot capture was not found"
            )
        receipt = self._captures.get_receipt(
            representative_binding.capture_command_id
        )
        if receipt is None:
            raise CandidatePromotionV2SourceNotFoundError(
                "Product Snapshot capture receipt was not found"
            )
        result = self._captures.get_result(receipt)
        product_ids = tuple(value.snapshot_id for value in result.snapshots)
        observation_ids = tuple(
            value.collected_observation_id for value in result.bindings
        )
        if (
            receipt.candidate_id != candidate.candidate_id
            or receipt.product_snapshot_ids != product_ids
            or tuple(value.product_snapshot_id for value in result.bindings)
            != product_ids
            or observation_ids != group.observation_ids
            or representative_binding.collected_observation_id
            != group.representative_observation_id
            or representative_binding.product_snapshot_id
            != command.representative_product_snapshot_id
            or representative_binding.candidate_id != candidate.candidate_id
            or representative_binding.capture_command_id != receipt.command_id
            or any(
                value.candidate_identity != candidate
                or value.market_observation_identity
                != context.market_observation_identity
                for value in result.snapshots
            )
            or any(
                value.candidate_id != candidate.candidate_id
                or value.capture_command_id != receipt.command_id
                for value in result.bindings
            )
        ):
            raise CandidatePromotionV2LineageConflictError(
                "Product Snapshot capture lineage differs"
            )
        return CandidatePromotionV2SourceManifest(
            binding_id="pending-binding",
            candidate_id=candidate.candidate_id,
            finalized_group_id=command.finalized_group_id,
            product_snapshot_capture_command_id=receipt.command_id,
            product_snapshot_ids=product_ids,
            representative_product_snapshot_id=(
                command.representative_product_snapshot_id
            ),
        )


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
        product_snapshot_capture_repository: ProductSnapshotCaptureRepository | None = None,
        admission_id_generator: Callable[[], str] | None = None,
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
        self._promote_v2 = (
            PromoteOpportunityCandidateV2(
                candidate_repository,
                product_snapshot_capture_repository,
                promotion_repository,
                opportunity_id_generator=opportunity_id_generator,
                binding_id_generator=binding_id_generator,
                admission_id_generator=admission_id_generator,
                clock=clock,
            )
            if product_snapshot_capture_repository is not None
            and admission_id_generator is not None
            else None
        )

    def execute(
        self, command: PromoteOpportunityCandidateCommand
    ) -> CandidatePromotionResult:
        return self._promote.execute(command)

    def execute_v2(
        self, command: PromoteOpportunityCandidateV2Command
    ) -> CandidatePromotionResult:
        if self._promote_v2 is None:
            raise CandidatePromotionPersistenceError(
                "Candidate Promotion v2 sources are not configured"
            )
        return self._promote_v2.execute(command)


__all__ = (
    "PROMOTION_COMMAND_SCHEMA_VERSION", "PROMOTION_BINDING_SCHEMA_VERSION",
    "PROMOTION_RECEIPT_SCHEMA_VERSION", "PromoteOpportunityCandidateCommand",
    "PROMOTION_V2_CONTRACT_VERSION", "PROMOTION_COMMAND_V2_SCHEMA_VERSION",
    "PROMOTION_BINDING_V2_SCHEMA_VERSION", "PROMOTION_RECEIPT_V2_SCHEMA_VERSION",
    "PROMOTION_SOURCE_V2_SCHEMA_VERSION", "PROMOTION_ADMISSION_V2_SCHEMA_VERSION",
    "PROMOTION_V2_POLICY_NAME", "PROMOTION_V2_POLICY_VERSION",
    "PROMOTION_V2_ADMISSION_KIND", "PromoteOpportunityCandidateV2Command",
    "CandidatePromotionV2SourceManifest", "PromoteOpportunityCandidateV2",
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
    "CandidatePromotionV2SourceNotFoundError",
    "CandidatePromotionV2LineageConflictError",
)
