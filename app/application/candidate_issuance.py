"""Read-only Application boundary for issuing pre-admission Candidate identity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol
import hashlib
import json

from app.application.discovery_persistence import (
    DiscoveryCommandRepository,
    DiscoveryGroupRepository,
    DiscoveryObservationRepository,
    DiscoveryResultRepository,
)
from app.domain.discovery_identity import (
    DiscoveryOpportunityContext,
    OpportunityCandidateIdentity,
)
from app.domain.market_intelligence import (
    MarketObservationIdentity,
    MarketObservationScope,
)


CANDIDATE_ISSUANCE_COMMAND_SCHEMA_VERSION = "candidate-issuance-command-v1"
CANDIDATE_ISSUANCE_RESULT_SCHEMA_VERSION = "candidate-issuance-result-v1"
OPPORTUNITY_CANDIDATE_SCHEMA_VERSION = "opportunity-candidate-v1"
OPPORTUNITY_CANDIDATE_RECEIPT_SCHEMA_VERSION = "opportunity-candidate-receipt-v1"


class CandidateIssuanceError(RuntimeError):
    pass


class CandidateDiscoveryCommandNotFoundError(CandidateIssuanceError):
    pass


class CandidateDiscoveryResultNotFoundError(CandidateIssuanceError):
    pass


class CandidateFinalizedGroupNotFoundError(CandidateIssuanceError):
    pass


class CandidateExecutionMismatchError(CandidateIssuanceError):
    pass


class CandidateGroupNotInResultError(CandidateIssuanceError):
    pass


class CandidateDiscoveryReferenceConflictError(CandidateIssuanceError):
    pass


class CandidateMarketIdentityConflictError(CandidateIssuanceError):
    pass


class CandidateIdentityGenerationError(CandidateIssuanceError):
    pass


class MalformedCandidateIssuanceCommandError(ValueError):
    pass


class UnsupportedCandidateIssuanceCommandVersionError(
    MalformedCandidateIssuanceCommandError
):
    pass


class CandidatePersistenceError(CandidateIssuanceError): pass
class CandidateIssuanceNotFoundError(CandidatePersistenceError): pass
class CandidateIssuanceCommandConflictError(CandidatePersistenceError): pass
class CandidateIssuanceReplayConflictError(CandidatePersistenceError): pass
class DuplicateOpportunityCandidateError(CandidatePersistenceError): pass
class CandidateLineageConflictError(CandidatePersistenceError): pass
class MalformedCandidatePersistenceError(CandidatePersistenceError): pass
class UnsupportedCandidatePersistenceVersionError(MalformedCandidatePersistenceError): pass
class CandidateHistoryPersistenceError(CandidatePersistenceError): pass
class CandidateContextPersistenceError(CandidatePersistenceError): pass
class CandidateReceiptPersistenceError(CandidatePersistenceError): pass
class CandidateCommitError(CandidatePersistenceError): pass


def _required(value: str, name: str, error_type: type[Exception]) -> str:
    if not isinstance(value, str) or not value.strip():
        raise error_type(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str, error_type: type[Exception]) -> datetime:
    if not isinstance(value, datetime):
        raise error_type(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise error_type(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class IssueOpportunityCandidateCommand:
    issuance_command_id: str
    discovery_command_id: str
    discovery_execution_id: str
    finalized_group_id: str
    discovery_reference: str
    market_observation_identity: MarketObservationIdentity
    requested_at: datetime
    schema_version: str = CANDIDATE_ISSUANCE_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "issuance_command_id",
            "discovery_command_id",
            "discovery_execution_id",
            "finalized_group_id",
            "discovery_reference",
        ):
            object.__setattr__(
                self,
                name,
                _required(
                    getattr(self, name),
                    name,
                    MalformedCandidateIssuanceCommandError,
                ),
            )
        if not isinstance(self.market_observation_identity, MarketObservationIdentity):
            raise MalformedCandidateIssuanceCommandError(
                "market_observation_identity must be MarketObservationIdentity"
            )
        _aware(
            self.requested_at,
            "requested_at",
            MalformedCandidateIssuanceCommandError,
        )
        if self.schema_version != CANDIDATE_ISSUANCE_COMMAND_SCHEMA_VERSION:
            raise UnsupportedCandidateIssuanceCommandVersionError(
                f"unsupported candidate issuance command version: {self.schema_version}"
            )


@dataclass(frozen=True, slots=True)
class CandidateIssuanceResult:
    candidate_identity: OpportunityCandidateIdentity
    discovery_context: DiscoveryOpportunityContext
    discovery_command_id: str
    finalized_group_id: str
    issued_at: datetime
    schema_version: str = CANDIDATE_ISSUANCE_RESULT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.candidate_identity, OpportunityCandidateIdentity):
            raise TypeError("candidate_identity must be OpportunityCandidateIdentity")
        if not isinstance(self.discovery_context, DiscoveryOpportunityContext):
            raise TypeError("discovery_context must be DiscoveryOpportunityContext")
        if self.discovery_context.candidate_identity != self.candidate_identity:
            raise ValueError("discovery context must preserve candidate identity")
        for name in ("discovery_command_id", "finalized_group_id"):
            object.__setattr__(
                self, name, _required(getattr(self, name), name, ValueError)
            )
        if self.discovery_context.command_id != self.discovery_command_id:
            raise ValueError("discovery context must preserve command identity")
        _aware(self.issued_at, "issued_at", ValueError)
        if self.schema_version != CANDIDATE_ISSUANCE_RESULT_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported candidate issuance result version: {self.schema_version}"
            )


def _identity_value(identity: MarketObservationIdentity) -> dict[str, object]:
    return {
        "scope": identity.scope.value, "market": identity.market,
        "marketplace": identity.marketplace,
        "canonical_product_id": identity.canonical_product_id,
        "marketplace_item_id": identity.marketplace_item_id,
        "normalized_query": identity.normalized_query, "category": identity.category,
        "variant_identity": identity.variant_identity, "condition": identity.condition,
        "window_started_at": identity.window_started_at.isoformat(),
        "window_ended_at": identity.window_ended_at.isoformat(),
    }


def _hash(value: dict[str, object]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def candidate_subject_fingerprint(command: IssueOpportunityCandidateCommand) -> str:
    return _hash({
        "discovery_command_id": command.discovery_command_id,
        "discovery_execution_id": command.discovery_execution_id,
        "finalized_group_id": command.finalized_group_id,
        "discovery_reference": command.discovery_reference,
        "market_observation_identity": _identity_value(command.market_observation_identity),
        "schema_version": command.schema_version,
    })


def candidate_command_fingerprint(command: IssueOpportunityCandidateCommand) -> str:
    return _hash({
        "subject_fingerprint": candidate_subject_fingerprint(command),
        "requested_at": command.requested_at.isoformat(),
        "schema_version": command.schema_version,
    })


@dataclass(frozen=True, slots=True)
class OpportunityCandidateIssuanceReceipt:
    issuance_command_id: str
    discovery_command_id: str
    discovery_execution_id: str
    finalized_group_id: str
    candidate_id: str
    command_fingerprint: str
    subject_fingerprint: str
    discovery_reference: str
    market_observation_identity: MarketObservationIdentity
    requested_at: datetime
    receipt_committed_at: datetime
    schema_version: str = OPPORTUNITY_CANDIDATE_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in ("issuance_command_id", "discovery_command_id", "discovery_execution_id",
                     "finalized_group_id", "candidate_id", "discovery_reference"):
            object.__setattr__(self, name, _required(getattr(self, name), name, ValueError))
        for name in ("command_fingerprint", "subject_fingerprint"):
            value = _required(getattr(self, name), name, ValueError)
            if len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
                raise ValueError(f"{name} must be lowercase SHA-256 text")
        if not isinstance(self.market_observation_identity, MarketObservationIdentity):
            raise TypeError("market_observation_identity must be MarketObservationIdentity")
        _aware(self.requested_at, "requested_at", ValueError)
        _aware(self.receipt_committed_at, "receipt_committed_at", ValueError)
        if self.schema_version != OPPORTUNITY_CANDIDATE_RECEIPT_SCHEMA_VERSION:
            raise UnsupportedCandidatePersistenceVersionError("unsupported candidate receipt version")


@dataclass(frozen=True, slots=True)
class DurableCandidateIssuanceResult:
    issuance: CandidateIssuanceResult
    receipt: OpportunityCandidateIssuanceReceipt
    replayed: bool


class CandidateIssuanceRepository(Protocol):
    def save_initial_issuance(self, command: IssueOpportunityCandidateCommand,
                              issuance: CandidateIssuanceResult,
                              receipt: OpportunityCandidateIssuanceReceipt) -> DurableCandidateIssuanceResult: ...
    def save_alias_receipt(self, command: IssueOpportunityCandidateCommand,
                           receipt: OpportunityCandidateIssuanceReceipt) -> DurableCandidateIssuanceResult: ...
    def get_candidate(self, candidate_id: str) -> OpportunityCandidateIdentity | None: ...
    def get_context(self, candidate_id: str) -> DiscoveryOpportunityContext | None: ...
    def get_receipt_by_command(self, issuance_command_id: str) -> OpportunityCandidateIssuanceReceipt | None: ...
    def get_by_discovery_group(self, discovery_command_id: str, finalized_group_id: str) -> CandidateIssuanceResult | None: ...
    def list_receipts_for_candidate(self, candidate_id: str) -> tuple[OpportunityCandidateIssuanceReceipt, ...]: ...
    def validate_command_replay(self, issuance_command_id: str, command_fingerprint: str) -> DurableCandidateIssuanceResult | None: ...
    def validate_subject_replay(self, discovery_command_id: str, finalized_group_id: str, subject_fingerprint: str) -> CandidateIssuanceResult | None: ...


class PersistOpportunityCandidateIssuance:
    def __init__(self, issuance_service: "IssueOpportunityCandidate",
                 repository: CandidateIssuanceRepository, *,
                 receipt_clock: Callable[[], datetime]) -> None:
        self._issuance_service = issuance_service
        self._repository = repository
        self._receipt_clock = receipt_clock

    def execute(self, command: IssueOpportunityCandidateCommand) -> DurableCandidateIssuanceResult:
        command_fingerprint = candidate_command_fingerprint(command)
        subject_fingerprint = candidate_subject_fingerprint(command)
        replay = self._repository.validate_command_replay(
            command.issuance_command_id, command_fingerprint
        )
        if replay is not None:
            return DurableCandidateIssuanceResult(replay.issuance, replay.receipt, True)
        existing = self._repository.validate_subject_replay(
            command.discovery_command_id, command.finalized_group_id, subject_fingerprint
        )
        if existing is not None:
            receipt = self._receipt(command, existing.candidate_identity.candidate_id,
                                    command_fingerprint, subject_fingerprint)
            return self._repository.save_alias_receipt(command, receipt)
        issuance = self._issuance_service.execute(command)
        receipt = self._receipt(command, issuance.candidate_identity.candidate_id,
                                command_fingerprint, subject_fingerprint)
        return self._repository.save_initial_issuance(command, issuance, receipt)

    def _receipt(self, command, candidate_id, command_fingerprint, subject_fingerprint):
        return OpportunityCandidateIssuanceReceipt(
            issuance_command_id=command.issuance_command_id,
            discovery_command_id=command.discovery_command_id,
            discovery_execution_id=command.discovery_execution_id,
            finalized_group_id=command.finalized_group_id,
            candidate_id=candidate_id,
            command_fingerprint=command_fingerprint,
            subject_fingerprint=subject_fingerprint,
            discovery_reference=command.discovery_reference,
            market_observation_identity=command.market_observation_identity,
            requested_at=command.requested_at,
            receipt_committed_at=self._receipt_clock(),
        )
class IssueOpportunityCandidate:
    """Issues identity from persisted Discovery facts without writing or replaying."""

    def __init__(
        self,
        command_repository: DiscoveryCommandRepository,
        result_repository: DiscoveryResultRepository,
        group_repository: DiscoveryGroupRepository,
        observation_repository: DiscoveryObservationRepository,
        *,
        candidate_id_generator: Callable[[], str],
        clock: Callable[[], datetime],
    ) -> None:
        if not callable(candidate_id_generator):
            raise TypeError("candidate_id_generator must be callable")
        if not callable(clock):
            raise TypeError("clock must be callable")
        self._commands = command_repository
        self._results = result_repository
        self._groups = group_repository
        self._observations = observation_repository
        self._candidate_id_generator = candidate_id_generator
        self._clock = clock

    def execute(
        self, request: IssueOpportunityCandidateCommand
    ) -> CandidateIssuanceResult:
        if not isinstance(request, IssueOpportunityCandidateCommand):
            raise TypeError("request must be IssueOpportunityCandidateCommand")
        command = self._commands.get_command(request.discovery_command_id)
        if command is None:
            raise CandidateDiscoveryCommandNotFoundError(
                "authoritative Discovery command was not found"
            )
        if command.discovery_execution_id != request.discovery_execution_id:
            raise CandidateExecutionMismatchError(
                "Discovery command execution does not match issuance request"
            )
        result = self._results.get_by_execution(request.discovery_execution_id)
        if result is None:
            raise CandidateDiscoveryResultNotFoundError(
                "authoritative completed Discovery result was not found"
            )
        if (
            result.command_id != command.command_id
            or result.discovery_execution_id != command.discovery_execution_id
        ):
            raise CandidateExecutionMismatchError(
                "Discovery command and completed result lineage do not match"
            )
        if result.is_zero_result:
            raise CandidateGroupNotInResultError(
                "zero-result Discovery execution cannot issue a Candidate"
            )
        group = self._groups.get_group(request.finalized_group_id)
        if group is None:
            raise CandidateFinalizedGroupNotFoundError(
                "authoritative finalized ProductGroup was not found"
            )
        if group.finalized_group_id not in result.finalized_group_ids:
            raise CandidateGroupNotInResultError(
                "finalized ProductGroup is not part of the completed result"
            )
        if group.discovery_execution_id != result.discovery_execution_id:
            raise CandidateExecutionMismatchError(
                "finalized ProductGroup execution does not match result"
            )
        representative = self._observations.get_observation(
            group.representative_observation_id
        )
        if representative is None:
            raise CandidateMarketIdentityConflictError(
                "representative observation is required for identity validation"
            )
        if representative.discovery_execution_id != group.discovery_execution_id:
            raise CandidateExecutionMismatchError(
                "representative observation execution does not match group"
            )
        self._validate_market_identity(
            request.market_observation_identity,
            representative.source_marketplace,
            representative.source_item_id,
        )
        # The explicit request field is the authoritative source in this
        # foundation. It is deliberately never derived from Group or Product data.
        discovery_reference = _required(
            request.discovery_reference,
            "discovery_reference",
            CandidateDiscoveryReferenceConflictError,
        )
        try:
            candidate_id = _required(
                self._candidate_id_generator(),
                "candidate_id",
                CandidateIdentityGenerationError,
            )
        except CandidateIdentityGenerationError:
            raise
        except Exception as error:
            raise CandidateIdentityGenerationError(
                "candidate ID generation failed"
            ) from error
        try:
            issued_at = _aware(
                self._clock(), "issued_at", CandidateIdentityGenerationError
            )
        except CandidateIdentityGenerationError:
            raise
        except Exception as error:
            raise CandidateIdentityGenerationError(
                "candidate issuance clock failed"
            ) from error
        identity = OpportunityCandidateIdentity(candidate_id, discovery_reference)
        context = DiscoveryOpportunityContext(
            candidate_identity=identity,
            market_observation_identity=request.market_observation_identity,
            discovery_execution_id=request.discovery_execution_id,
            command_id=request.discovery_command_id,
            requested_at=request.requested_at,
        )
        return CandidateIssuanceResult(
            candidate_identity=identity,
            discovery_context=context,
            discovery_command_id=request.discovery_command_id,
            finalized_group_id=request.finalized_group_id,
            issued_at=issued_at,
        )

    @staticmethod
    def _validate_market_identity(
        identity: MarketObservationIdentity,
        source_marketplace: str,
        source_item_id: str,
    ) -> None:
        if identity.scope not in {
            MarketObservationScope.LISTING,
            MarketObservationScope.CANONICAL_PRODUCT,
        }:
            raise CandidateMarketIdentityConflictError(
                "Candidate Market identity must use listing or canonical_product scope"
            )
        if identity.marketplace != source_marketplace:
            raise CandidateMarketIdentityConflictError(
                "Candidate Market identity marketplace does not match observation"
            )
        if (
            identity.scope is MarketObservationScope.LISTING
            and identity.marketplace_item_id != source_item_id
        ):
            raise CandidateMarketIdentityConflictError(
                "listing Market identity item does not match observation source"
            )


__all__ = [
    "CANDIDATE_ISSUANCE_COMMAND_SCHEMA_VERSION",
    "CANDIDATE_ISSUANCE_RESULT_SCHEMA_VERSION",
    "CandidateDiscoveryCommandNotFoundError",
    "CandidateDiscoveryReferenceConflictError",
    "CandidateDiscoveryResultNotFoundError",
    "CandidateExecutionMismatchError",
    "CandidateFinalizedGroupNotFoundError",
    "CandidateGroupNotInResultError",
    "CandidateIdentityGenerationError",
    "CandidateIssuanceError",
    "CandidateIssuanceResult",
    "CandidateIssuanceRepository",
    "DurableCandidateIssuanceResult",
    "OpportunityCandidateIssuanceReceipt",
    "PersistOpportunityCandidateIssuance",
    "candidate_command_fingerprint",
    "candidate_subject_fingerprint",
    "CandidateMarketIdentityConflictError",
    "IssueOpportunityCandidate",
    "IssueOpportunityCandidateCommand",
    "MalformedCandidateIssuanceCommandError",
    "UnsupportedCandidateIssuanceCommandVersionError",
]
