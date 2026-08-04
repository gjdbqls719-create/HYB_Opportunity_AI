"""Read-only Application boundary for issuing pre-admission Candidate identity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

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
    "CandidateMarketIdentityConflictError",
    "IssueOpportunityCandidate",
    "IssueOpportunityCandidateCommand",
    "MalformedCandidateIssuanceCommandError",
    "UnsupportedCandidateIssuanceCommandVersionError",
]
