"""Application core for exact target-bound Domestic Market Validation v2."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
from typing import Callable, Protocol

from app.application.competition_v2_admission import CompetitionV2Publication
from app.application.demand_v2_admission import DemandV2Publication
from app.domain.market_intelligence.demand_v2 import CompetitionCohortReference
from app.domain.market_intelligence.domestic_market_validation import (
    DomesticMarketValidationState,
)
from app.domain.market_intelligence.domestic_market_validation_v2 import (
    DOMESTIC_MARKET_VALIDATION_V2_POLICY_NAME,
    DOMESTIC_MARKET_VALIDATION_V2_POLICY_VERSION,
    DomesticMarketCompetitionV2Source,
    DomesticMarketDemandV2Source,
    DomesticMarketValidationV2Assessment,
    DomesticMarketValidationV2Reason,
    DomesticMarketValidationV2SourceManifest,
    DomesticMarketVerificationV2,
    domestic_market_validation_v2_reason_codes,
)
from app.domain.opportunity import OpportunityDomesticSellingTargetBinding


DOMESTIC_MARKET_VALIDATION_V2_COMMAND_SCHEMA_VERSION = (
    "domestic-market-validation-command-v2"
)
DOMESTIC_MARKET_VALIDATION_V2_RECEIPT_SCHEMA_VERSION = (
    "domestic-market-validation-receipt-v2"
)


class DomesticMarketValidationV2Error(RuntimeError):
    pass


class DomesticMarketValidationV2PolicyError(DomesticMarketValidationV2Error):
    pass


class DomesticMarketValidationV2SourceNotFoundError(DomesticMarketValidationV2Error):
    pass


class DomesticMarketValidationV2SourceConflictError(DomesticMarketValidationV2Error):
    pass


class DomesticMarketValidationV2ReplayConflictError(DomesticMarketValidationV2Error):
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
    return value


def _fingerprint(value: object) -> str:
    encoded = json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ValidateDomesticMarketV2Command:
    command_id: str
    opportunity_id: str
    competition_observation_id: str
    demand_observation_id: str
    verification: DomesticMarketVerificationV2
    requested_at: datetime
    policy_name: str = DOMESTIC_MARKET_VALIDATION_V2_POLICY_NAME
    policy_version: str = DOMESTIC_MARKET_VALIDATION_V2_POLICY_VERSION
    schema_version: str = DOMESTIC_MARKET_VALIDATION_V2_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "command_id", "opportunity_id", "competition_observation_id",
            "demand_observation_id", "policy_name", "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.verification, DomesticMarketVerificationV2):
            raise TypeError("verification must be DomesticMarketVerificationV2")
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        if (
            self.policy_name != DOMESTIC_MARKET_VALIDATION_V2_POLICY_NAME
            or self.policy_version != DOMESTIC_MARKET_VALIDATION_V2_POLICY_VERSION
        ):
            raise DomesticMarketValidationV2PolicyError(
                "unsupported Domestic Market Validation v2 policy"
            )
        if self.schema_version != DOMESTIC_MARKET_VALIDATION_V2_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported Domestic Market Validation v2 command schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class DomesticMarketValidationV2Receipt:
    command_id: str
    assessment_id: str
    command_fingerprint: str
    source_manifest_fingerprint: str
    committed_at: datetime
    schema_version: str = DOMESTIC_MARKET_VALIDATION_V2_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(
            self, "assessment_id", _text(self.assessment_id, "assessment_id")
        )
        for name in ("command_fingerprint", "source_manifest_fingerprint"):
            fingerprint = _text(getattr(self, name), name).lower()
            if len(fingerprint) != 64 or any(
                value not in "0123456789abcdef" for value in fingerprint
            ):
                raise ValueError(f"{name} must be SHA-256 text")
            object.__setattr__(self, name, fingerprint)
        object.__setattr__(
            self, "committed_at", _aware(self.committed_at, "committed_at")
        )
        if self.schema_version != DOMESTIC_MARKET_VALIDATION_V2_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported Domestic Market Validation v2 receipt schema")


@dataclass(frozen=True, slots=True)
class DomesticMarketValidationV2Publication:
    assessment: DomesticMarketValidationV2Assessment
    receipt: DomesticMarketValidationV2Receipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.assessment, DomesticMarketValidationV2Assessment):
            raise TypeError("assessment must be DomesticMarketValidationV2Assessment")
        if not isinstance(self.receipt, DomesticMarketValidationV2Receipt):
            raise TypeError("receipt must be DomesticMarketValidationV2Receipt")
        if self.receipt.assessment_id != self.assessment.assessment_id:
            raise ValueError("receipt must reference assessment")
        if (
            self.receipt.source_manifest_fingerprint
            != self.assessment.source_manifest_fingerprint
        ):
            raise ValueError("receipt must reference the exact source manifest")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class DomesticMarketValidationV2PersistenceRepository(Protocol):
    def validate_replay(
        self, command_id: str, command_fingerprint: str,
    ) -> DomesticMarketValidationV2Publication | None: ...

    def save_assessment(
        self,
        command: ValidateDomesticMarketV2Command,
        assessment: DomesticMarketValidationV2Assessment,
        receipt: DomesticMarketValidationV2Receipt,
    ) -> DomesticMarketValidationV2Publication: ...

    def get_assessment(
        self, assessment_id: str,
    ) -> DomesticMarketValidationV2Assessment | None: ...

    def get_receipt(
        self, command_id: str,
    ) -> DomesticMarketValidationV2Receipt | None: ...


class DomesticMarketValidationV2SourceRepository(Protocol):
    """Read-only ports over already-owned immutable upstream authorities."""

    def get_target_binding(
        self, opportunity_id: str,
    ) -> OpportunityDomesticSellingTargetBinding | None: ...

    def get_competition_publication(
        self, observation_id: str,
    ) -> CompetitionV2Publication | None: ...

    def get_competition_authority_fingerprint(self, cohort_id: str) -> str | None: ...

    def get_demand_publication(
        self, observation_id: str,
    ) -> DemandV2Publication | None: ...

    def get_demand_authority_fingerprint(self, observation_id: str) -> str | None: ...


class ValidateDomesticMarketV2ForCapital:
    def __init__(
        self,
        repository: DomesticMarketValidationV2SourceRepository,
        *,
        assessment_id_generator: Callable[[], str],
        evaluated_clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._assessment_id = assessment_id_generator
        self._evaluated = evaluated_clock

    def resolve_source_manifest(
        self,
        opportunity_id: str,
        competition_observation_id: str,
        demand_observation_id: str,
    ) -> DomesticMarketValidationV2SourceManifest:
        opportunity_id = _text(opportunity_id, "opportunity_id")
        competition_observation_id = _text(
            competition_observation_id, "competition_observation_id"
        )
        demand_observation_id = _text(demand_observation_id, "demand_observation_id")
        binding = self._repository.get_target_binding(opportunity_id)
        if binding is None:
            raise DomesticMarketValidationV2SourceNotFoundError(
                "Opportunity domestic-selling target binding is unavailable"
            )
        if not isinstance(binding, OpportunityDomesticSellingTargetBinding):
            raise DomesticMarketValidationV2SourceConflictError(
                "Opportunity binding is not the ADR-0060 target authority"
            )
        if binding.opportunity_id != opportunity_id:
            raise DomesticMarketValidationV2SourceConflictError(
                "Opportunity target binding identity conflicts with the request"
            )

        competition = self._repository.get_competition_publication(
            competition_observation_id
        )
        if competition is None:
            raise DomesticMarketValidationV2SourceNotFoundError(
                "named Competition v2 publication is unavailable"
            )
        demand = self._repository.get_demand_publication(demand_observation_id)
        if demand is None:
            raise DomesticMarketValidationV2SourceNotFoundError(
                "named Demand v2 publication is unavailable"
            )
        self._validate_publication_lineage(
            opportunity_id, binding, competition_observation_id,
            demand_observation_id, competition, demand,
        )

        competition_fingerprint = (
            self._repository.get_competition_authority_fingerprint(
                competition.cohort.cohort_id
            )
        )
        if competition_fingerprint is None:
            raise DomesticMarketValidationV2SourceNotFoundError(
                "Competition v2 authority fingerprint is unavailable"
            )
        demand_fingerprint = self._repository.get_demand_authority_fingerprint(
            demand_observation_id
        )
        if demand_fingerprint is None:
            raise DomesticMarketValidationV2SourceNotFoundError(
                "Demand v2 authority fingerprint is unavailable"
            )
        self._validate_cross_authority_reference(
            demand.observation.comparable_cohort.manifest.source_competition_cohort,
            competition,
            competition_fingerprint,
        )

        return DomesticMarketValidationV2SourceManifest(
            target_binding=binding,
            competition=DomesticMarketCompetitionV2Source(
                observation_identity=competition.observation_identity,
                cohort_id=competition.cohort.cohort_id,
                authority_fingerprint=competition_fingerprint,
                observation_schema_version=competition.cohort.observation_schema_version,
                cohort_policy_version=competition.cohort.cohort_policy_version,
                assessment_schema_version=competition.assessment.schema_version,
                assessment_policy_version=competition.assessment.policy_version,
                availability=competition.assessment.availability,
                generated_at=competition.assessment.generated_at,
                committed_at=competition.committed_at,
                artifact_reference=competition.cohort.artifact_reference,
                artifact_sha256=competition.cohort.artifact_sha256,
            ),
            demand=DomesticMarketDemandV2Source(
                observation_id=demand.observation.observation_id,
                assessment_id=demand.assessment.assessment_id,
                comparable_cohort_id=demand.observation.comparable_cohort.cohort_id,
                authority_fingerprint=demand_fingerprint,
                observation_schema_version=demand.observation.schema_version,
                assessment_schema_version=demand.assessment.schema_version,
                assessment_policy_version=demand.assessment.policy_version,
                comparable_cohort_version=(
                    demand.observation.comparable_cohort.manifest.schema_version
                ),
                market_intent_status=demand.assessment.market_intent_status,
                comparable_response_status=demand.assessment.comparable_response_status,
                availability=demand.assessment.availability,
                generated_at=demand.generated_at,
                committed_at=demand.committed_at,
                source_competition_cohort=(
                    demand.observation.comparable_cohort.manifest.source_competition_cohort
                ),
            ),
        )

    def execute(
        self, command: ValidateDomesticMarketV2Command,
    ) -> DomesticMarketValidationV2Assessment:
        if not isinstance(command, ValidateDomesticMarketV2Command):
            raise TypeError("command must be ValidateDomesticMarketV2Command")
        manifest = self.resolve_source_manifest(
            command.opportunity_id,
            command.competition_observation_id,
            command.demand_observation_id,
        )
        evaluated_at = _aware(self._evaluated(), "evaluated_at")
        reason_codes = domestic_market_validation_v2_reason_codes(
            manifest, command.verification, evaluated_at,
        )
        reasons = tuple(DomesticMarketValidationV2Reason(code) for code in reason_codes)
        state = (
            DomesticMarketValidationState.VALIDATED_FOR_CAPITAL
            if not reasons else DomesticMarketValidationState.BLOCKED
        )
        return DomesticMarketValidationV2Assessment(
            assessment_id=_text(self._assessment_id(), "assessment_id"),
            source_manifest=manifest,
            verification=command.verification,
            state=state,
            blocking_reasons=reasons,
            policy_name=command.policy_name,
            policy_version=command.policy_version,
            requested_at=command.requested_at,
            evaluated_at=evaluated_at,
        )

    @staticmethod
    def _validate_publication_lineage(
        opportunity_id,
        binding,
        competition_observation_id,
        demand_observation_id,
        competition,
        demand,
    ) -> None:
        target = binding.target_identity
        if (
            not isinstance(competition, CompetitionV2Publication)
            or competition.opportunity_id != opportunity_id
            or competition.observation_id != competition_observation_id
            or competition.cohort.subject != target
            or competition.assessment.subject != target
            or competition.assessment.source_cohort_id != competition.cohort.cohort_id
        ):
            raise DomesticMarketValidationV2SourceConflictError(
                "Competition v2 publication conflicts with the ADR-0060 target"
            )
        if (
            not isinstance(demand, DemandV2Publication)
            or demand.opportunity_id != opportunity_id
            or demand.observation.observation_id != demand_observation_id
            or demand.assessment.source_observation_id != demand_observation_id
            or demand.observation.subject != target
            or demand.assessment.subject != target
            or demand.observation.comparable_cohort.manifest.subject != target
        ):
            raise DomesticMarketValidationV2SourceConflictError(
                "Demand v2 publication conflicts with the ADR-0060 target"
            )

    @staticmethod
    def _validate_cross_authority_reference(
        reference: CompetitionCohortReference | None,
        competition: CompetitionV2Publication,
        authority_fingerprint: str,
    ) -> None:
        if reference is None:
            return
        identity = competition.observation_identity
        cohort = competition.cohort
        if (
            reference.competition_observation_id != identity.observation_id
            or reference.observation_identity_kind != identity.identity_kind.value
            or reference.observation_identity_version != identity.identity_version
            or reference.cohort_id != cohort.cohort_id
            or reference.authority_fingerprint != authority_fingerprint
            or reference.observation_schema_version != cohort.observation_schema_version
            or reference.cohort_policy_version != cohort.cohort_policy_version
            or reference.artifact_reference != cohort.artifact_reference
            or reference.artifact_sha256 != cohort.artifact_sha256
        ):
            raise DomesticMarketValidationV2SourceConflictError(
                "Demand v2 Competition cohort reference conflicts with selected authority"
            )


class PersistDomesticMarketValidationV2ForCapital:
    """Replay-first persistence boundary around the pure PR A authority core."""

    def __init__(
        self,
        repository: DomesticMarketValidationV2PersistenceRepository,
        owner: ValidateDomesticMarketV2ForCapital,
        *,
        committed_clock: Callable[[], datetime],
    ) -> None:
        self._repository = repository
        self._owner = owner
        self._committed = committed_clock

    def execute(
        self, command: ValidateDomesticMarketV2Command,
    ) -> DomesticMarketValidationV2Publication:
        if not isinstance(command, ValidateDomesticMarketV2Command):
            raise TypeError("command must be ValidateDomesticMarketV2Command")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replay
        assessment = self._owner.execute(command)
        receipt = DomesticMarketValidationV2Receipt(
            command_id=command.command_id,
            assessment_id=assessment.assessment_id,
            command_fingerprint=command.fingerprint,
            source_manifest_fingerprint=assessment.source_manifest_fingerprint,
            committed_at=_aware(self._committed(), "committed_at"),
        )
        return self._repository.save_assessment(command, assessment, receipt)


__all__ = [
    name for name in globals()
    if name.startswith("DomesticMarket") or name.startswith("ValidateDomestic")
    or name.startswith("PersistDomestic") or name.startswith("DOMESTIC_MARKET")
]
