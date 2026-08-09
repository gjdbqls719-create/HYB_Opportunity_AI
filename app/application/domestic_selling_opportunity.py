"""Founder-assisted authority for creating a distinct KR selling Opportunity."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Callable, Protocol

from app.application.candidate_promotion import CandidateOpportunityBinding
from app.application.opportunity_market_identity import OpportunityMarketIdentityBinding
from app.domain.decision_engine import OpportunityIdentity
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.domain.opportunity import (
    DomesticProductEquivalenceVerification,
    DomesticSellingOpportunityAdmission,
    OpportunityLifecycle,
    OpportunityLifecycleAction,
    OpportunityLifecycleStatus,
    OpportunityLifecycleTransition,
)
from app.domain.product_observation import ProductObservationSnapshot


DOMESTIC_SELLING_OPPORTUNITY_POLICY_NAME = (
    "domestic-selling-opportunity-admission"
)
DOMESTIC_SELLING_OPPORTUNITY_POLICY_VERSION = "1.0.0"
DOMESTIC_SELLING_OPPORTUNITY_COMMAND_SCHEMA_VERSION = (
    "admit-domestic-selling-opportunity-command-v1"
)
DOMESTIC_SELLING_OPPORTUNITY_RECEIPT_SCHEMA_VERSION = (
    "domestic-selling-opportunity-admission-receipt-v1"
)


class DomesticSellingOpportunityError(RuntimeError):
    pass


class DomesticSellingOpportunitySourceNotFoundError(
    DomesticSellingOpportunityError, LookupError
):
    pass


class DomesticSellingOpportunityLineageError(DomesticSellingOpportunityError):
    pass


class DomesticSellingOpportunityPolicyError(DomesticSellingOpportunityError):
    pass


class DomesticSellingOpportunityVerificationError(DomesticSellingOpportunityError):
    pass


class DomesticSellingOpportunityReplayConflictError(DomesticSellingOpportunityError):
    pass


class DomesticSellingOpportunityCardinalityConflictError(
    DomesticSellingOpportunityError
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
    if isinstance(value, Decimal):
        return format(value, "f")
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
class DomesticSellingOpportunityAdmissionPolicy:
    name: str = DOMESTIC_SELLING_OPPORTUNITY_POLICY_NAME
    version: str = DOMESTIC_SELLING_OPPORTUNITY_POLICY_VERSION
    target_market: str = "KR"
    allowed_target_scopes: tuple[MarketObservationScope, ...] = (
        MarketObservationScope.LISTING,
        MarketObservationScope.CANONICAL_PRODUCT,
    )

    def __post_init__(self) -> None:
        for field_name in ("name", "version", "target_market"):
            object.__setattr__(
                self, field_name, _text(getattr(self, field_name), field_name)
            )
        if self.target_market != "KR":
            raise ValueError("domestic selling policy target must be KR")
        if self.allowed_target_scopes != (
            MarketObservationScope.LISTING,
            MarketObservationScope.CANONICAL_PRODUCT,
        ):
            raise ValueError("unsupported domestic selling target scopes")

    def validate(self, identity: MarketObservationIdentity) -> None:
        if identity.market.upper() != self.target_market:
            raise DomesticSellingOpportunityPolicyError(
                "target Market identity must be KR"
            )
        if identity.scope not in self.allowed_target_scopes:
            raise DomesticSellingOpportunityPolicyError(
                "target Market identity must identify a listing or canonical product"
            )


DOMESTIC_SELLING_OPPORTUNITY_POLICY_V1 = (
    DomesticSellingOpportunityAdmissionPolicy()
)


def resolve_domestic_selling_opportunity_policy(
    name: str, version: str
) -> DomesticSellingOpportunityAdmissionPolicy:
    if (
        name != DOMESTIC_SELLING_OPPORTUNITY_POLICY_NAME
        or version != DOMESTIC_SELLING_OPPORTUNITY_POLICY_VERSION
    ):
        raise DomesticSellingOpportunityPolicyError(
            "unsupported domestic selling Opportunity admission policy"
        )
    return DOMESTIC_SELLING_OPPORTUNITY_POLICY_V1


@dataclass(frozen=True, slots=True)
class AdmitDomesticSellingOpportunityCommand:
    command_id: str
    source_opportunity_id: str
    source_product_snapshot_id: str
    target_market_identity: MarketObservationIdentity
    operator_id: str
    product_equivalence_confirmed: bool
    evidence_reference: str
    verified_at: datetime
    requested_at: datetime
    policy_name: str = DOMESTIC_SELLING_OPPORTUNITY_POLICY_NAME
    policy_version: str = DOMESTIC_SELLING_OPPORTUNITY_POLICY_VERSION
    schema_version: str = DOMESTIC_SELLING_OPPORTUNITY_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "command_id",
            "source_opportunity_id",
            "source_product_snapshot_id",
            "operator_id",
            "evidence_reference",
            "policy_name",
            "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.target_market_identity, MarketObservationIdentity):
            raise TypeError("target_market_identity must be MarketObservationIdentity")
        if self.product_equivalence_confirmed is not True:
            raise DomesticSellingOpportunityVerificationError(
                "product equivalence must be explicitly confirmed"
            )
        object.__setattr__(self, "verified_at", _aware(self.verified_at, "verified_at"))
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        if self.verified_at > self.requested_at:
            raise DomesticSellingOpportunityVerificationError(
                "verified_at cannot follow requested_at"
            )
        if self.schema_version != DOMESTIC_SELLING_OPPORTUNITY_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported domestic selling Opportunity command schema")

    @property
    def fingerprint(self) -> str:
        payload = {
            name: getattr(self, name)
            for name in (
                "source_opportunity_id",
                "source_product_snapshot_id",
                "target_market_identity",
                "operator_id",
                "product_equivalence_confirmed",
                "evidence_reference",
                "verified_at",
                "requested_at",
                "policy_name",
                "policy_version",
                "schema_version",
            )
        }
        return _fingerprint(payload)


@dataclass(frozen=True, slots=True)
class DomesticSellingOpportunityAdmissionReceipt:
    command_id: str
    admission_id: str
    domestic_opportunity_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = DOMESTIC_SELLING_OPPORTUNITY_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("command_id", "admission_id", "domestic_opportunity_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        fingerprint = _text(self.command_fingerprint, "command_fingerprint")
        if len(fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in fingerprint
        ):
            raise ValueError("command_fingerprint must be lowercase SHA-256 text")
        object.__setattr__(self, "command_fingerprint", fingerprint)
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version != DOMESTIC_SELLING_OPPORTUNITY_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported domestic selling admission receipt schema")


@dataclass(frozen=True, slots=True)
class DomesticSellingOpportunityAdmissionPublication:
    lifecycle: OpportunityLifecycle
    creation_transition: OpportunityLifecycleTransition
    market_binding: OpportunityMarketIdentityBinding
    admission: DomesticSellingOpportunityAdmission
    receipt: DomesticSellingOpportunityAdmissionReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.lifecycle, OpportunityLifecycle):
            raise TypeError("lifecycle must be OpportunityLifecycle")
        if not isinstance(self.creation_transition, OpportunityLifecycleTransition):
            raise TypeError("creation_transition must be OpportunityLifecycleTransition")
        if not isinstance(self.market_binding, OpportunityMarketIdentityBinding):
            raise TypeError("market_binding must be OpportunityMarketIdentityBinding")
        if not isinstance(self.admission, DomesticSellingOpportunityAdmission):
            raise TypeError("admission must be DomesticSellingOpportunityAdmission")
        if not isinstance(self.receipt, DomesticSellingOpportunityAdmissionReceipt):
            raise TypeError("receipt must be DomesticSellingOpportunityAdmissionReceipt")
        identity = self.admission.domestic_opportunity_identity
        if (
            self.lifecycle.opportunity_id != identity.opportunity_id
            or self.lifecycle.discovery_reference != identity.discovery_reference
            or self.lifecycle.status is not OpportunityLifecycleStatus.DISCOVERED
            or self.lifecycle.version != 1
        ):
            raise ValueError("publication lifecycle differs from domestic Opportunity")
        if (
            self.creation_transition.opportunity_id != identity.opportunity_id
            or self.creation_transition.action is not OpportunityLifecycleAction.CREATE
            or self.creation_transition.version != 1
        ):
            raise ValueError("publication creation transition differs")
        if (
            self.market_binding.opportunity_id != identity.opportunity_id
            or self.market_binding.discovery_reference != identity.discovery_reference
            or self.market_binding.market_observation_identity
            != self.admission.domestic_market_identity
        ):
            raise ValueError("publication Market binding differs")
        if (
            self.receipt.admission_id != self.admission.admission_id
            or self.receipt.domestic_opportunity_id != identity.opportunity_id
            or self.receipt.committed_at < self.admission.admitted_at
        ):
            raise ValueError("publication receipt differs")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class DomesticSellingOpportunityAdmissionRepository(Protocol):
    def validate_replay(
        self, command_id: str, fingerprint: str
    ) -> DomesticSellingOpportunityAdmissionPublication | None: ...

    def get_source_lifecycle(self, opportunity_id: str) -> OpportunityLifecycle | None: ...

    def get_candidate_promotion(
        self, opportunity_id: str
    ) -> CandidateOpportunityBinding | None: ...

    def get_product_snapshot(
        self, snapshot_id: str
    ) -> ProductObservationSnapshot | None: ...

    def get_market_identity_binding(
        self, opportunity_id: str
    ) -> OpportunityMarketIdentityBinding | None: ...

    def get_admission_by_source(
        self, opportunity_id: str
    ) -> DomesticSellingOpportunityAdmissionPublication | None: ...

    def save_admission(
        self,
        command: AdmitDomesticSellingOpportunityCommand,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        market_binding: OpportunityMarketIdentityBinding,
        admission: DomesticSellingOpportunityAdmission,
        receipt: DomesticSellingOpportunityAdmissionReceipt,
    ) -> DomesticSellingOpportunityAdmissionPublication: ...


class AdmitDomesticSellingOpportunity:
    def __init__(
        self,
        repository: DomesticSellingOpportunityAdmissionRepository,
        *,
        opportunity_id_generator: Callable[[], str],
        admission_id_generator: Callable[[], str],
        admitted_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        dependencies = (
            opportunity_id_generator,
            admission_id_generator,
            admitted_clock,
            committed_clock,
        )
        if any(not callable(value) for value in dependencies):
            raise TypeError("domestic selling admission dependencies must be callable")
        self._repository = repository
        self._opportunity_identity = opportunity_id_generator
        self._admission_identity = admission_id_generator
        self._admitted = admitted_clock
        self._committed = committed_clock

    def execute(
        self, command: AdmitDomesticSellingOpportunityCommand
    ) -> DomesticSellingOpportunityAdmissionPublication:
        if not isinstance(command, AdmitDomesticSellingOpportunityCommand):
            raise TypeError("command must be AdmitDomesticSellingOpportunityCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)

        policy = resolve_domestic_selling_opportunity_policy(
            command.policy_name, command.policy_version
        )
        policy.validate(command.target_market_identity)
        source = self._required(
            self._repository.get_source_lifecycle(command.source_opportunity_id),
            "source Opportunity lifecycle",
        )
        promotion = self._required(
            self._repository.get_candidate_promotion(command.source_opportunity_id),
            "source Candidate Promotion",
        )
        snapshot = self._required(
            self._repository.get_product_snapshot(command.source_product_snapshot_id),
            "source Product Observation Snapshot",
        )
        source_binding = self._required(
            self._repository.get_market_identity_binding(command.source_opportunity_id),
            "source Opportunity Market binding",
        )
        self._validate_source(command, source, promotion, snapshot, source_binding)
        if self._repository.get_admission_by_source(command.source_opportunity_id) is not None:
            replay = self._repository.validate_replay(
                command.command_id, command.fingerprint
            )
            if replay is not None:
                return replace(replay, replayed=True)
            raise DomesticSellingOpportunityCardinalityConflictError(
                "source Opportunity already has a domestic-selling Opportunity"
            )

        admission_id = _text(self._admission_identity(), "admission_id")
        domestic_opportunity_id = _text(
            self._opportunity_identity(), "domestic_opportunity_id"
        )
        if domestic_opportunity_id == source.opportunity_id:
            raise DomesticSellingOpportunityLineageError(
                "domestic Opportunity identity must differ from source"
            )
        admitted_at = _aware(self._admitted(), "admitted_at")
        if admitted_at < command.requested_at:
            raise DomesticSellingOpportunityVerificationError(
                "admitted_at cannot precede requested_at"
            )
        discovery_reference = f"domestic-selling:{admission_id}"
        domestic_identity = OpportunityIdentity(
            domestic_opportunity_id, discovery_reference
        )
        lifecycle = OpportunityLifecycle(
            domestic_opportunity_id,
            discovery_reference,
            created_at=admitted_at,
            updated_at=admitted_at,
        )
        transition = lifecycle.creation_transition(
            operator_id=command.operator_id,
            reason="domestic selling Opportunity admitted",
        )
        market_binding = OpportunityMarketIdentityBinding(
            domestic_opportunity_id,
            discovery_reference,
            command.target_market_identity,
            admitted_at,
        )
        verification = DomesticProductEquivalenceVerification(
            operator_id=command.operator_id,
            verified_at=command.verified_at,
            evidence_reference=command.evidence_reference,
            confirmed=command.product_equivalence_confirmed,
        )
        admission = DomesticSellingOpportunityAdmission(
            admission_id=admission_id,
            source_opportunity_identity=OpportunityIdentity(
                source.opportunity_id, source.discovery_reference
            ),
            source_lifecycle_status=source.status,
            source_lifecycle_version=source.version,
            domestic_opportunity_identity=domestic_identity,
            source_candidate_id=promotion.candidate_id,
            source_candidate_opportunity_binding_id=promotion.binding_id,
            source_promotion_command_id=promotion.promotion_command_id,
            source_product_snapshot_id=snapshot.snapshot_id,
            source_market_identity=source_binding.market_observation_identity,
            domestic_market_identity=command.target_market_identity,
            product_equivalence=verification,
            policy_name=policy.name,
            policy_version=policy.version,
            requested_at=command.requested_at,
            admitted_at=admitted_at,
        )
        committed_at = _aware(self._committed(), "committed_at")
        receipt = DomesticSellingOpportunityAdmissionReceipt(
            command.command_id,
            admission_id,
            domestic_opportunity_id,
            command.fingerprint,
            committed_at,
        )
        return self._repository.save_admission(
            command, lifecycle, transition, market_binding, admission, receipt
        )

    @staticmethod
    def _required(value, name: str):
        if value is None:
            raise DomesticSellingOpportunitySourceNotFoundError(f"{name} is missing")
        return value

    @staticmethod
    def _validate_source(command, source, promotion, snapshot, source_binding) -> None:
        if (
            source.opportunity_id != command.source_opportunity_id
            or promotion.opportunity_id != source.opportunity_id
            or promotion.discovery_reference != source.discovery_reference
            or source_binding.opportunity_id != source.opportunity_id
            or source_binding.discovery_reference != source.discovery_reference
            or source_binding.market_observation_identity
            != promotion.market_observation_identity
        ):
            raise DomesticSellingOpportunityLineageError(
                "source Opportunity, Promotion, and Market lineage differ"
            )
        if (
            snapshot.snapshot_id != command.source_product_snapshot_id
            or snapshot.candidate_identity.candidate_id != promotion.candidate_id
            or snapshot.candidate_identity.discovery_reference
            != source.discovery_reference
            or snapshot.market_observation_identity
            != source_binding.market_observation_identity
            or snapshot.product.marketplace.lower()
            != source_binding.market_observation_identity.marketplace.lower()
        ):
            raise DomesticSellingOpportunityLineageError(
                "source Product Snapshot lineage differs"
            )
        if snapshot.observed_at > command.verified_at:
            raise DomesticSellingOpportunityVerificationError(
                "source Product Snapshot cannot follow verification"
            )
        if command.target_market_identity.window_ended_at > command.verified_at:
            raise DomesticSellingOpportunityVerificationError(
                "target Market observation cannot follow verification"
            )


__all__ = [
    "DOMESTIC_SELLING_OPPORTUNITY_COMMAND_SCHEMA_VERSION",
    "DOMESTIC_SELLING_OPPORTUNITY_POLICY_NAME",
    "DOMESTIC_SELLING_OPPORTUNITY_POLICY_V1",
    "DOMESTIC_SELLING_OPPORTUNITY_POLICY_VERSION",
    "DOMESTIC_SELLING_OPPORTUNITY_RECEIPT_SCHEMA_VERSION",
    "AdmitDomesticSellingOpportunity",
    "AdmitDomesticSellingOpportunityCommand",
    "DomesticSellingOpportunityAdmissionPolicy",
    "DomesticSellingOpportunityAdmissionPublication",
    "DomesticSellingOpportunityAdmissionReceipt",
    "DomesticSellingOpportunityAdmissionRepository",
    "DomesticSellingOpportunityCardinalityConflictError",
    "DomesticSellingOpportunityError",
    "DomesticSellingOpportunityLineageError",
    "DomesticSellingOpportunityPolicyError",
    "DomesticSellingOpportunityReplayConflictError",
    "DomesticSellingOpportunitySourceNotFoundError",
    "DomesticSellingOpportunityVerificationError",
    "resolve_domestic_selling_opportunity_policy",
]
