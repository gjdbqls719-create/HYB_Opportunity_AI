"""Application authority for new-to-market KR selling target admission."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime
from enum import Enum
from typing import Callable, Protocol

from app.application.candidate_promotion import (
    PROMOTION_BINDING_V2_SCHEMA_VERSION,
    CandidateOpportunityBinding,
)
from app.application.opportunity_market_identity import OpportunityMarketIdentityBinding
from app.application.opportunity_validation import FounderSelectedAdmissionBasis
from app.application.product_snapshot_capture import (
    ProductSnapshotCaptureReceipt,
    ProductSnapshotCaptureResult,
    ProductSnapshotSourceBinding,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.market_intelligence import MarketObservationScope
from app.domain.opportunity import (
    BoundedKRSearchManifest,
    NewToMarketDomesticSellingOpportunityAdmission,
    NewToMarketDomesticSellingSourceManifest,
    NewToMarketDomesticSellingTargetIdentity,
    OpportunityDomesticSellingTargetBinding,
    OpportunityLifecycle,
    OpportunityLifecycleAction,
    OpportunityLifecycleStatus,
    OpportunityLifecycleTransition,
)
from app.domain.product_observation import ProductObservationSnapshot


NEW_TO_MARKET_POLICY_NAME = "new-to-market-domestic-selling-admission"
NEW_TO_MARKET_POLICY_VERSION = "1.0.0"
NEW_TO_MARKET_COMMAND_SCHEMA_VERSION = (
    "admit-new-to-market-domestic-selling-opportunity-command-v1"
)
NEW_TO_MARKET_RECEIPT_SCHEMA_VERSION = (
    "new-to-market-domestic-selling-opportunity-admission-receipt-v1"
)


class NewToMarketDomesticSellingError(RuntimeError):
    pass


class NewToMarketDomesticSellingSourceNotFoundError(
    NewToMarketDomesticSellingError, LookupError
):
    pass


class NewToMarketDomesticSellingLineageError(NewToMarketDomesticSellingError):
    pass


class NewToMarketDomesticSellingPolicyError(NewToMarketDomesticSellingError):
    pass


class NewToMarketDomesticSellingVerificationError(NewToMarketDomesticSellingError):
    pass


class NewToMarketDomesticSellingReplayConflictError(NewToMarketDomesticSellingError):
    pass


class NewToMarketDomesticSellingCardinalityConflictError(
    NewToMarketDomesticSellingError
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


def _canonical(value):
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {key: _canonical(value[key]) for key in sorted(value)}
    if is_dataclass(value):
        return _canonical(asdict(value))
    raise TypeError(f"unsupported command value: {type(value).__name__}")


def _fingerprint(value) -> str:
    payload = json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True, slots=True)
class NewToMarketDomesticSellingAdmissionPolicy:
    name: str = NEW_TO_MARKET_POLICY_NAME
    version: str = NEW_TO_MARKET_POLICY_VERSION
    source_market: str = "US"
    source_marketplace: str = "ebay"
    target_market: str = "KR"

    def __post_init__(self) -> None:
        for name in (
            "name", "version", "source_market", "source_marketplace", "target_market"
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if (
            self.source_market != "US"
            or self.source_marketplace.lower() != "ebay"
            or self.target_market != "KR"
        ):
            raise ValueError("unsupported new-to-market admission policy")
        object.__setattr__(self, "source_marketplace", "ebay")

    def validate_source(self, binding: OpportunityMarketIdentityBinding) -> None:
        identity = binding.market_observation_identity
        if (
            identity.market.upper() != self.source_market
            or identity.marketplace.lower() != self.source_marketplace
            or identity.scope is not MarketObservationScope.LISTING
        ):
            raise NewToMarketDomesticSellingPolicyError(
                "source O1 must have the exact eBay/US listing Market binding"
            )


NEW_TO_MARKET_POLICY_V1 = NewToMarketDomesticSellingAdmissionPolicy()


def resolve_new_to_market_policy(
    name: str, version: str
) -> NewToMarketDomesticSellingAdmissionPolicy:
    if (name, version) != (NEW_TO_MARKET_POLICY_NAME, NEW_TO_MARKET_POLICY_VERSION):
        raise NewToMarketDomesticSellingPolicyError(
            "unsupported new-to-market domestic selling admission policy"
        )
    return NEW_TO_MARKET_POLICY_V1


@dataclass(frozen=True, slots=True)
class AdmitNewToMarketDomesticSellingOpportunityCommand:
    command_id: str
    source_opportunity_id: str
    source_product_snapshot_id: str
    operator_id: str
    decision_reason: str
    search_manifest: BoundedKRSearchManifest
    verified_at: datetime
    requested_at: datetime
    policy_name: str = NEW_TO_MARKET_POLICY_NAME
    policy_version: str = NEW_TO_MARKET_POLICY_VERSION
    schema_version: str = NEW_TO_MARKET_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "command_id",
            "source_opportunity_id",
            "source_product_snapshot_id",
            "operator_id",
            "decision_reason",
            "policy_name",
            "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.search_manifest, BoundedKRSearchManifest):
            raise TypeError("search_manifest must be BoundedKRSearchManifest")
        if self.search_manifest.operator_id != self.operator_id:
            raise NewToMarketDomesticSellingVerificationError(
                "bounded search operator must equal command operator"
            )
        object.__setattr__(self, "verified_at", _aware(self.verified_at, "verified_at"))
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        if self.search_manifest.performed_at > self.verified_at:
            raise NewToMarketDomesticSellingVerificationError(
                "bounded search cannot follow verification"
            )
        if self.verified_at > self.requested_at:
            raise NewToMarketDomesticSellingVerificationError(
                "verified_at cannot follow requested_at"
            )
        if self.schema_version != NEW_TO_MARKET_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported new-to-market command schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(
            {
                "source_opportunity_id": self.source_opportunity_id,
                "source_product_snapshot_id": self.source_product_snapshot_id,
                "operator_id": self.operator_id,
                "decision_reason": self.decision_reason,
                "search_manifest": self.search_manifest,
                "verified_at": self.verified_at,
                "requested_at": self.requested_at,
                "policy_name": self.policy_name,
                "policy_version": self.policy_version,
                "schema_version": self.schema_version,
            }
        )

    @property
    def subject_fingerprint(self) -> str:
        return self.fingerprint


@dataclass(frozen=True, slots=True)
class NewToMarketDomesticSellingAdmissionReceipt:
    command_id: str
    admission_id: str
    domestic_selling_target_id: str
    domestic_opportunity_id: str
    command_fingerprint: str
    subject_fingerprint: str
    committed_at: datetime
    schema_version: str = NEW_TO_MARKET_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "command_id", "admission_id", "domestic_selling_target_id",
            "domestic_opportunity_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("command_fingerprint", "subject_fingerprint"):
            value = _text(getattr(self, name), name)
            if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
                raise ValueError(f"{name} must be lowercase SHA-256 text")
            object.__setattr__(self, name, value)
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version != NEW_TO_MARKET_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported new-to-market receipt schema")


@dataclass(frozen=True, slots=True)
class NewToMarketDomesticSellingAdmissionPublication:
    lifecycle: OpportunityLifecycle
    creation_transition: OpportunityLifecycleTransition
    target_binding: OpportunityDomesticSellingTargetBinding
    admission: NewToMarketDomesticSellingOpportunityAdmission
    receipt: NewToMarketDomesticSellingAdmissionReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.lifecycle, OpportunityLifecycle):
            raise TypeError("lifecycle must be OpportunityLifecycle")
        if not isinstance(self.creation_transition, OpportunityLifecycleTransition):
            raise TypeError("creation_transition must be OpportunityLifecycleTransition")
        if not isinstance(self.target_binding, OpportunityDomesticSellingTargetBinding):
            raise TypeError("target_binding must be OpportunityDomesticSellingTargetBinding")
        if not isinstance(
            self.admission, NewToMarketDomesticSellingOpportunityAdmission
        ):
            raise TypeError("admission must be NewToMarketDomesticSellingOpportunityAdmission")
        if not isinstance(self.receipt, NewToMarketDomesticSellingAdmissionReceipt):
            raise TypeError("receipt must be NewToMarketDomesticSellingAdmissionReceipt")
        domestic = self.admission.domestic_opportunity_identity
        target = self.admission.target_identity
        if (
            self.lifecycle.opportunity_id != domestic.opportunity_id
            or self.lifecycle.discovery_reference != domestic.discovery_reference
            or self.lifecycle.status is not OpportunityLifecycleStatus.DISCOVERED
            or self.lifecycle.version != 1
            or self.creation_transition.opportunity_id != domestic.opportunity_id
            or self.creation_transition.action is not OpportunityLifecycleAction.CREATE
            or self.creation_transition.version != 1
        ):
            raise ValueError("publication lifecycle differs from domestic Opportunity")
        if (
            self.target_binding.opportunity_id != domestic.opportunity_id
            or self.target_binding.discovery_reference != domestic.discovery_reference
            or self.target_binding.target_identity != target
        ):
            raise ValueError("publication target binding differs")
        if (
            self.receipt.admission_id != self.admission.admission_id
            or self.receipt.domestic_selling_target_id
            != target.domestic_selling_target_id
            or self.receipt.domestic_opportunity_id != domestic.opportunity_id
            or self.receipt.committed_at < self.admission.admitted_at
        ):
            raise ValueError("publication receipt differs")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class NewToMarketDomesticSellingRepository(Protocol):
    def validate_replay(self, command_id: str, fingerprint: str): ...
    def get_source_lifecycle(self, opportunity_id: str): ...
    def get_candidate_promotion(self, opportunity_id: str): ...
    def get_promotion_v2_admission(self, opportunity_id: str): ...
    def get_market_identity_binding(self, opportunity_id: str): ...
    def get_product_snapshot(self, snapshot_id: str): ...
    def get_capture_receipt(self, command_id: str): ...
    def get_capture_result(self, receipt: ProductSnapshotCaptureReceipt): ...
    def get_snapshot_source_binding(self, snapshot_id: str): ...
    def get_finalized_group(self, finalized_group_id: str): ...
    def get_source_observation(self, observation_id: str): ...
    def get_existing_product_admission_by_source(self, opportunity_id: str): ...
    def get_admission_by_source(self, opportunity_id: str): ...
    def save_admission(self, command, lifecycle, transition, target_binding, admission, receipt): ...


class AdmitNewToMarketDomesticSellingOpportunity:
    def __init__(
        self,
        repository: NewToMarketDomesticSellingRepository,
        *,
        opportunity_id_generator: Callable[[], str],
        target_id_generator: Callable[[], str],
        admission_id_generator: Callable[[], str],
        admitted_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        dependencies = (
            opportunity_id_generator, target_id_generator, admission_id_generator,
            admitted_clock, committed_clock,
        )
        if any(not callable(value) for value in dependencies):
            raise TypeError("new-to-market admission dependencies must be callable")
        self._repository = repository
        self._opportunity_identity = opportunity_id_generator
        self._target_identity = target_id_generator
        self._admission_identity = admission_id_generator
        self._admitted = admitted_clock
        self._committed = committed_clock

    def execute(
        self, command: AdmitNewToMarketDomesticSellingOpportunityCommand
    ) -> NewToMarketDomesticSellingAdmissionPublication:
        if not isinstance(command, AdmitNewToMarketDomesticSellingOpportunityCommand):
            raise TypeError("command must be AdmitNewToMarketDomesticSellingOpportunityCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)

        policy = resolve_new_to_market_policy(command.policy_name, command.policy_version)
        source = self._required(
            self._repository.get_source_lifecycle(command.source_opportunity_id),
            "source Opportunity lifecycle",
        )
        promotion = self._required(
            self._repository.get_candidate_promotion(command.source_opportunity_id),
            "source Candidate Promotion",
        )
        promotion_admission = self._required(
            self._repository.get_promotion_v2_admission(command.source_opportunity_id),
            "source Candidate Promotion v2 admission",
        )
        source_binding = self._required(
            self._repository.get_market_identity_binding(command.source_opportunity_id),
            "source Opportunity Market binding",
        )
        selected_snapshot = self._required(
            self._repository.get_product_snapshot(command.source_product_snapshot_id),
            "selected source Product Snapshot",
        )
        policy.validate_source(source_binding)
        source_manifest = self._reconstruct_source(
            command, source, promotion, promotion_admission, source_binding,
            selected_snapshot,
        )

        if self._repository.get_existing_product_admission_by_source(
            command.source_opportunity_id
        ) is not None:
            raise NewToMarketDomesticSellingCardinalityConflictError(
                "source Opportunity already has an ADR-0049 domestic-selling Opportunity"
            )
        existing = self._repository.get_admission_by_source(command.source_opportunity_id)
        if existing is not None:
            if existing.receipt.subject_fingerprint != command.subject_fingerprint:
                raise NewToMarketDomesticSellingCardinalityConflictError(
                    "source Opportunity already has a conflicting new-to-market admission"
                )
            alias_receipt = NewToMarketDomesticSellingAdmissionReceipt(
                command.command_id,
                existing.admission.admission_id,
                existing.admission.target_identity.domestic_selling_target_id,
                existing.admission.domestic_opportunity_identity.opportunity_id,
                command.fingerprint,
                command.subject_fingerprint,
                existing.receipt.committed_at,
            )
            return self._repository.save_admission(
                command,
                existing.lifecycle,
                existing.creation_transition,
                existing.target_binding,
                existing.admission,
                alias_receipt,
            )

        admission_id = _text(self._admission_identity(), "admission_id")
        target_id = _text(self._target_identity(), "domestic_selling_target_id")
        domestic_opportunity_id = _text(
            self._opportunity_identity(), "domestic_opportunity_id"
        )
        if domestic_opportunity_id == source.opportunity_id:
            raise NewToMarketDomesticSellingLineageError(
                "domestic Opportunity identity must differ from source"
            )
        admitted_at = _aware(self._admitted(), "admitted_at")
        if admitted_at < command.requested_at:
            raise NewToMarketDomesticSellingVerificationError(
                "admitted_at cannot precede requested_at"
            )
        discovery_reference = f"new-to-market-domestic-selling:{admission_id}"
        domestic_identity = OpportunityIdentity(
            domestic_opportunity_id, discovery_reference
        )
        target_identity = NewToMarketDomesticSellingTargetIdentity(target_id)
        lifecycle = OpportunityLifecycle(
            domestic_opportunity_id,
            discovery_reference,
            created_at=admitted_at,
            updated_at=admitted_at,
        )
        transition = lifecycle.creation_transition(
            operator_id=command.operator_id,
            reason="new-to-market domestic selling Opportunity admitted",
        )
        target_binding = OpportunityDomesticSellingTargetBinding(
            domestic_opportunity_id, discovery_reference, target_identity, admitted_at
        )
        admission = NewToMarketDomesticSellingOpportunityAdmission(
            admission_id=admission_id,
            source_manifest=source_manifest,
            domestic_opportunity_identity=domestic_identity,
            target_identity=target_identity,
            search_manifest=command.search_manifest,
            operator_id=command.operator_id,
            decision_reason=command.decision_reason,
            verified_at=command.verified_at,
            requested_at=command.requested_at,
            admitted_at=admitted_at,
            policy_name=policy.name,
            policy_version=policy.version,
        )
        committed_at = _aware(self._committed(), "committed_at")
        receipt = NewToMarketDomesticSellingAdmissionReceipt(
            command.command_id,
            admission_id,
            target_id,
            domestic_opportunity_id,
            command.fingerprint,
            command.subject_fingerprint,
            committed_at,
        )
        return self._repository.save_admission(
            command, lifecycle, transition, target_binding, admission, receipt
        )

    @staticmethod
    def _required(value, name: str):
        if value is None:
            raise NewToMarketDomesticSellingSourceNotFoundError(f"{name} is missing")
        return value

    def _reconstruct_source(
        self, command, source, promotion, promotion_admission, source_binding,
        selected_snapshot,
    ) -> NewToMarketDomesticSellingSourceManifest:
        if (
            source.opportunity_id != command.source_opportunity_id
            or source.is_archived
            or source.status is not OpportunityLifecycleStatus.DISCOVERED
            or source.version != 1
            or promotion.opportunity_id != source.opportunity_id
            or promotion.discovery_reference != source.discovery_reference
            or promotion.schema_version != PROMOTION_BINDING_V2_SCHEMA_VERSION
            or source_binding.opportunity_id != source.opportunity_id
            or source_binding.discovery_reference != source.discovery_reference
            or source_binding.market_observation_identity
            != promotion.market_observation_identity
        ):
            raise NewToMarketDomesticSellingLineageError(
                "source O1 lifecycle, Promotion v2, and Market lineage differ"
            )
        if not isinstance(promotion_admission, FounderSelectedAdmissionBasis) or (
            promotion_admission.candidate_id != promotion.candidate_id
            or promotion_admission.candidate_opportunity_binding_id != promotion.binding_id
            or promotion_admission.finalized_group_id != promotion.finalized_group_id
            or promotion_admission.product_snapshot_capture_command_id
            != promotion.product_snapshot_capture_command_id
            or promotion_admission.product_snapshot_ids != promotion.product_snapshot_ids
            or promotion_admission.representative_product_snapshot_id
            != promotion.representative_product_snapshot_id
        ):
            raise NewToMarketDomesticSellingLineageError(
                "Candidate Promotion v2 admission/source manifest differs"
            )
        receipt = self._required(
            self._repository.get_capture_receipt(
                promotion.product_snapshot_capture_command_id
            ),
            "Product Snapshot capture receipt",
        )
        capture = self._repository.get_capture_result(receipt)
        selected_binding = self._required(
            self._repository.get_snapshot_source_binding(
                command.source_product_snapshot_id
            ),
            "selected Product Snapshot source binding",
        )
        group = self._required(
            self._repository.get_finalized_group(promotion.finalized_group_id),
            "finalized Product Group",
        )
        source_observation = self._required(
            self._repository.get_source_observation(
                selected_binding.collected_observation_id
            ),
            "selected source observation",
        )
        snapshot_ids = tuple(value.snapshot_id for value in capture.snapshots)
        binding_ids = tuple(value.product_snapshot_id for value in capture.bindings)
        observation_ids = tuple(
            value.collected_observation_id for value in capture.bindings
        )
        if (
            receipt.command_id != promotion.product_snapshot_capture_command_id
            or receipt.candidate_id != promotion.candidate_id
            or receipt.product_snapshot_ids != promotion.product_snapshot_ids
            or snapshot_ids != promotion.product_snapshot_ids
            or binding_ids != promotion.product_snapshot_ids
            or group.observation_ids != observation_ids
            or group.representative_observation_id
            != next(
                (
                    value.collected_observation_id
                    for value in capture.bindings
                    if value.product_snapshot_id
                    == promotion.representative_product_snapshot_id
                ),
                None,
            )
            or selected_snapshot.snapshot_id != command.source_product_snapshot_id
            or selected_snapshot.snapshot_id not in promotion.product_snapshot_ids
            or selected_snapshot.candidate_identity.candidate_id != promotion.candidate_id
            or selected_snapshot.candidate_identity.discovery_reference
            != source.discovery_reference
            or selected_snapshot.market_observation_identity
            != source_binding.market_observation_identity
            or selected_binding.product_snapshot_id != selected_snapshot.snapshot_id
            or selected_binding.candidate_id != promotion.candidate_id
            or selected_binding.capture_command_id
            != promotion.product_snapshot_capture_command_id
            or source_observation.observation_id
            != selected_binding.collected_observation_id
            or source_observation.product != selected_snapshot.product
            or source_observation.collector_provenance
            != selected_snapshot.collector_provenance
            or source_observation.observed_at != selected_snapshot.observed_at
        ):
            raise NewToMarketDomesticSellingLineageError(
                "exact Product Snapshot capture and source lineage differ"
            )
        if selected_snapshot.observed_at > command.verified_at:
            raise NewToMarketDomesticSellingVerificationError(
                "selected Product Snapshot cannot follow verification"
            )
        return NewToMarketDomesticSellingSourceManifest(
            source_opportunity_identity=OpportunityIdentity(
                source.opportunity_id, source.discovery_reference
            ),
            source_lifecycle_status=source.status,
            source_lifecycle_version=source.version,
            source_market_identity=source_binding.market_observation_identity,
            candidate_id=promotion.candidate_id,
            candidate_opportunity_binding_id=promotion.binding_id,
            promotion_command_id=promotion.promotion_command_id,
            promotion_admission_id=promotion_admission.admission_id,
            finalized_group_id=promotion.finalized_group_id,
            product_snapshot_capture_command_id=(
                promotion.product_snapshot_capture_command_id
            ),
            product_snapshot_ids=promotion.product_snapshot_ids,
            representative_product_snapshot_id=(
                promotion.representative_product_snapshot_id
            ),
            selected_product_snapshot_id=selected_snapshot.snapshot_id,
            selected_source_observation_id=source_observation.observation_id,
        )


__all__ = [
    "NEW_TO_MARKET_COMMAND_SCHEMA_VERSION",
    "NEW_TO_MARKET_POLICY_NAME",
    "NEW_TO_MARKET_POLICY_V1",
    "NEW_TO_MARKET_POLICY_VERSION",
    "NEW_TO_MARKET_RECEIPT_SCHEMA_VERSION",
    "AdmitNewToMarketDomesticSellingOpportunity",
    "AdmitNewToMarketDomesticSellingOpportunityCommand",
    "NewToMarketDomesticSellingAdmissionPolicy",
    "NewToMarketDomesticSellingAdmissionPublication",
    "NewToMarketDomesticSellingAdmissionReceipt",
    "NewToMarketDomesticSellingCardinalityConflictError",
    "NewToMarketDomesticSellingError",
    "NewToMarketDomesticSellingLineageError",
    "NewToMarketDomesticSellingPolicyError",
    "NewToMarketDomesticSellingReplayConflictError",
    "NewToMarketDomesticSellingSourceNotFoundError",
    "NewToMarketDomesticSellingVerificationError",
    "resolve_new_to_market_policy",
]
