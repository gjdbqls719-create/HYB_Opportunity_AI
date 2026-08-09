"""Application owner for exact-source Capital evidence readiness."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
import hashlib
import json
from typing import Callable, Protocol

from app.application.sourcing import DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2
from app.domain.capital import (
    CAPITAL_READINESS_POLICY_NAME,
    CAPITAL_READINESS_POLICY_VERSION,
    CAPITAL_READINESS_SCHEMA_VERSION_V2,
    CapitalReadinessAssessment,
    CapitalReadinessReason,
    CapitalReadinessReasonCode,
    CapitalReadinessSourceManifest,
    CapitalReadinessState,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.market_intelligence import (
    DOMESTIC_MARKET_VALIDATION_POLICY_NAME,
    DOMESTIC_MARKET_VALIDATION_POLICY_VERSION,
    DomesticMarketValidationAssessment,
    DomesticMarketValidationState,
)
from app.domain.opportunity import (
    CONSERVATIVE_ECONOMICS_POLICY_NAME,
    CONSERVATIVE_ECONOMICS_POLICY_VERSION,
    ConservativeEconomicsResult,
    ConservativeEconomicsStatus,
    EconomicsSourceComposition,
)
from app.domain.sourcing import (
    AcquisitionCostNormalization,
    CriticalCostCompleteness,
    CriticalCostCompletenessState,
    FounderSourcingAdmission,
    MatchVerificationStatus,
    SourcingEconomicsBinding,
    SourcingEconomicsBindingReference,
    SourcingEconomicsSourceReference,
)


CAPITAL_READINESS_COMMAND_SCHEMA_VERSION = "capital-readiness-command-v1"
CAPITAL_READINESS_RECEIPT_SCHEMA_VERSION = "capital-readiness-receipt-v1"


class CapitalReadinessError(RuntimeError):
    pass


class CapitalReadinessSourceNotFoundError(CapitalReadinessError):
    pass


class CapitalReadinessReplayConflictError(CapitalReadinessError):
    pass


class CapitalReadinessPolicyError(CapitalReadinessError):
    pass


class CapitalReadinessSourceConflictError(CapitalReadinessError):
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
    return hashlib.sha256(json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class EvaluateCapitalReadinessCommand:
    command_id: str
    opportunity_identity: OpportunityIdentity
    conservative_economics_result_id: str
    domestic_market_validation_assessment_id: str
    critical_cost_assessment_id: str
    requested_at: datetime
    policy_name: str = CAPITAL_READINESS_POLICY_NAME
    policy_version: str = CAPITAL_READINESS_POLICY_VERSION
    schema_version: str = CAPITAL_READINESS_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "command_id", "conservative_economics_result_id",
            "domestic_market_validation_assessment_id", "critical_cost_assessment_id",
            "policy_name", "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        object.__setattr__(
            self,
            "requested_at",
            _aware(self.requested_at, "requested_at"),
        )
        if (
            self.policy_name != CAPITAL_READINESS_POLICY_NAME
            or self.policy_version != CAPITAL_READINESS_POLICY_VERSION
        ):
            raise CapitalReadinessPolicyError("unsupported Capital Readiness policy")
        if self.schema_version != CAPITAL_READINESS_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported Capital Readiness command schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class CapitalReadinessReceipt:
    command_id: str
    assessment_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = CAPITAL_READINESS_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "assessment_id", _text(self.assessment_id, "assessment_id"))
        fingerprint = _text(self.command_fingerprint, "command_fingerprint").lower()
        if len(fingerprint) != 64 or any(value not in "0123456789abcdef" for value in fingerprint):
            raise ValueError("command_fingerprint must be SHA-256 text")
        object.__setattr__(self, "command_fingerprint", fingerprint)
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version != CAPITAL_READINESS_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported Capital Readiness receipt schema")


@dataclass(frozen=True, slots=True)
class CapitalReadinessPublication:
    assessment: CapitalReadinessAssessment
    receipt: CapitalReadinessReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.assessment, CapitalReadinessAssessment):
            raise TypeError("assessment must be CapitalReadinessAssessment")
        if not isinstance(self.receipt, CapitalReadinessReceipt):
            raise TypeError("receipt must be CapitalReadinessReceipt")
        if self.receipt.assessment_id != self.assessment.assessment_id:
            raise ValueError("receipt must reference assessment")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class CapitalReadinessRepository(Protocol):
    def validate_replay(self, command_id: str, fingerprint: str) -> CapitalReadinessPublication | None: ...
    def get_conservative_economics_result(self, result_id: str) -> ConservativeEconomicsResult | None: ...
    def get_economics_source_composition(self, composition_id: str) -> EconomicsSourceComposition | None: ...
    def get_acquisition_normalization(self, normalization_id: str) -> AcquisitionCostNormalization | None: ...
    def get_critical_cost_assessment(self, assessment_id: str) -> CriticalCostCompleteness | None: ...
    def get_domestic_market_validation(self, assessment_id: str) -> DomesticMarketValidationAssessment | None: ...
    def get_sourcing_binding(self, reference: SourcingEconomicsBindingReference) -> SourcingEconomicsBinding | None: ...
    def get_sourcing_admission(self, reference: SourcingEconomicsSourceReference) -> FounderSourcingAdmission | None: ...
    def save_assessment(self, command, assessment, receipt) -> CapitalReadinessPublication: ...


class EvaluateCapitalReadiness:
    def __init__(
        self,
        repository: CapitalReadinessRepository,
        *,
        assessment_id_generator: Callable[[], str],
        evaluated_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        if not all(callable(value) for value in (
            assessment_id_generator, evaluated_clock, committed_clock,
        )):
            raise TypeError("Capital Readiness dependencies must be callable")
        self._repository = repository
        self._identity = assessment_id_generator
        self._evaluated = evaluated_clock
        self._committed = committed_clock

    def execute(self, command: EvaluateCapitalReadinessCommand) -> CapitalReadinessPublication:
        if not isinstance(command, EvaluateCapitalReadinessCommand):
            raise TypeError("command must be EvaluateCapitalReadinessCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)

        conservative = self._required(
            self._repository.get_conservative_economics_result(
                command.conservative_economics_result_id
            ),
            "exact Conservative Economics result",
        )
        source = self._required(
            self._repository.get_economics_source_composition(
                conservative.source_composition_id
            ),
            "exact Economics Source Composition",
        )
        normalization = self._required(
            self._repository.get_acquisition_normalization(
                source.acquisition_normalization_id
            ),
            "exact Acquisition Cost Normalization",
        )
        critical = self._required(
            self._repository.get_critical_cost_assessment(
                command.critical_cost_assessment_id
            ),
            "exact Critical Cost assessment",
        )
        market = self._required(
            self._repository.get_domestic_market_validation(
                command.domestic_market_validation_assessment_id
            ),
            "exact Domestic Market Validation assessment",
        )
        binding = self._required(
            self._repository.get_sourcing_binding(critical.binding_reference),
            "exact Sourcing Economics Binding",
        )
        admission = self._required(
            self._repository.get_sourcing_admission(critical.source_reference),
            "exact Sourcing Admission revision",
        )

        evaluated_at = _aware(self._evaluated(), "evaluated_at")
        reasons: set[CapitalReadinessReasonCode] = set()
        if conservative.status is not ConservativeEconomicsStatus.CALCULABLE:
            reasons.add(CapitalReadinessReasonCode.CONSERVATIVE_ECONOMICS_BLOCKED)
        if market.state is not DomesticMarketValidationState.VALIDATED_FOR_CAPITAL:
            reasons.add(CapitalReadinessReasonCode.DOMESTIC_MARKET_NOT_VALIDATED)
        if critical.state is not CriticalCostCompletenessState.COMPLETE:
            reasons.add(CapitalReadinessReasonCode.CRITICAL_COST_INCOMPLETE)

        opportunity = command.opportunity_identity
        if any(value != opportunity for value in (
            conservative.opportunity_identity,
            source.opportunity_identity,
            normalization.opportunity_identity,
            critical.opportunity_identity,
            binding.opportunity_identity,
            admission.selling_product_lineage.opportunity_identity,
        )) or (
            market.source_manifest.opportunity_id != opportunity.opportunity_id
            or market.source_manifest.discovery_reference != opportunity.discovery_reference
        ):
            reasons.add(CapitalReadinessReasonCode.SOURCE_OPPORTUNITY_MISMATCH)

        if (
            conservative.source_composition_id != source.composition_id
            or source.acquisition_normalization_id != normalization.normalization_id
            or critical.acquisition_normalization_id != normalization.normalization_id
            or normalization.composition_id != critical.composition_id
            or binding.reference != critical.binding_reference
            or binding.source_reference != critical.source_reference
            or admission.to_economics_source_reference() != critical.source_reference
            or admission.quote_revision.quote_id != critical.source_reference.quote_id
            or admission.quote_revision.revision != critical.source_reference.quote_revision
            or source.verified_economics_opportunity_id
            != critical.verified_economics_opportunity_id
            or source.verified_economics_snapshot_at
            != critical.verified_economics_snapshot_at
            or source.verified_economics_schema_version
            != critical.verified_economics_schema_version
            or admission.selling_product_lineage.market_observation_identity
            != market.source_manifest.market_identity
        ):
            reasons.add(CapitalReadinessReasonCode.SOURCING_LINEAGE_MISMATCH)

        if admission.match_verification.status is not MatchVerificationStatus.VERIFIED_MATCH:
            reasons.add(CapitalReadinessReasonCode.PRODUCT_MATCH_NOT_VERIFIED)
        valid_until = admission.quote_revision.valid_until
        if valid_until is None:
            reasons.add(CapitalReadinessReasonCode.QUOTE_VALIDITY_MISSING)
        elif valid_until <= evaluated_at:
            reasons.add(CapitalReadinessReasonCode.QUOTE_EXPIRED)
        if not self._supported_policies(conservative, critical, market):
            reasons.add(CapitalReadinessReasonCode.SOURCE_POLICY_UNSUPPORTED)

        manifest = CapitalReadinessSourceManifest(
            opportunity_identity=opportunity,
            conservative_economics_result_id=conservative.result_id,
            economics_source_composition_id=source.composition_id,
            acquisition_normalization_id=normalization.normalization_id,
            landed_cost_composition_id=critical.composition_id,
            domestic_market_validation_assessment_id=market.assessment_id,
            critical_cost_assessment_id=command.critical_cost_assessment_id,
            sourcing_binding_id=binding.binding_id,
            sourcing_admission_id=admission.admission_id,
            sourcing_admission_revision=admission.revision,
            quote_id=admission.quote_revision.quote_id,
            quote_revision=admission.quote_revision.revision,
            product_match_verification_id=admission.match_verification.verification_id,
            quote_valid_until=valid_until,
        )
        ordered = tuple(
            CapitalReadinessReason(code)
            for code in sorted(reasons, key=lambda value: value.order)
        )
        state = (
            CapitalReadinessState.READY_FOR_CAPITAL_REVIEW
            if not ordered else CapitalReadinessState.BLOCKED
        )
        assessment = CapitalReadinessAssessment(
            assessment_id=_text(self._identity(), "assessment_id"),
            source_manifest=manifest,
            state=state,
            blocking_reasons=ordered,
            policy_name=command.policy_name,
            policy_version=command.policy_version,
            requested_at=command.requested_at,
            evaluated_at=evaluated_at,
            schema_version=CAPITAL_READINESS_SCHEMA_VERSION_V2,
        )
        receipt = CapitalReadinessReceipt(
            command.command_id,
            assessment.assessment_id,
            command.fingerprint,
            _aware(self._committed(), "committed_at"),
        )
        return self._repository.save_assessment(command, assessment, receipt)

    @staticmethod
    def _required(value, name):
        if value is None:
            raise CapitalReadinessSourceNotFoundError(f"{name} is missing")
        return value

    @staticmethod
    def _supported_policies(conservative, critical, market) -> bool:
        return (
            conservative.policy_name == CONSERVATIVE_ECONOMICS_POLICY_NAME
            and conservative.policy_version == CONSERVATIVE_ECONOMICS_POLICY_VERSION
            and critical.policy_name
            == DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2.name
            and critical.policy_version
            == DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2.version
            and market.policy_name == DOMESTIC_MARKET_VALIDATION_POLICY_NAME
            and market.policy_version == DOMESTIC_MARKET_VALIDATION_POLICY_VERSION
        )


@dataclass(frozen=True, slots=True)
class CapitalReadinessProductionRequest:
    command_id: str
    opportunity_id: str
    conservative_economics_result_id: str
    domestic_market_validation_assessment_id: str
    critical_cost_assessment_id: str
    requested_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "command_id",
            "opportunity_id",
            "conservative_economics_result_id",
            "domestic_market_validation_assessment_id",
            "critical_cost_assessment_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))


@dataclass(frozen=True, slots=True)
class CapitalReadinessProductionResult:
    publication: CapitalReadinessPublication
    critical_cost_normalization_id: str | None


class CapitalReadinessProductionEntry:
    """Bind exact terminal sources to the route Opportunity, then call the owner."""

    def __init__(
        self,
        repository: CapitalReadinessRepository,
        owner: EvaluateCapitalReadiness,
    ) -> None:
        self._repository = repository
        self._owner = owner

    def execute(
        self, request: CapitalReadinessProductionRequest
    ) -> CapitalReadinessProductionResult:
        if not isinstance(request, CapitalReadinessProductionRequest):
            raise TypeError("request must be CapitalReadinessProductionRequest")
        conservative = self._repository.get_conservative_economics_result(
            request.conservative_economics_result_id
        )
        if conservative is None:
            raise CapitalReadinessSourceNotFoundError(
                "exact Conservative Economics result is missing"
            )
        identity = conservative.opportunity_identity
        if identity.opportunity_id != request.opportunity_id:
            raise CapitalReadinessSourceConflictError(
                "Conservative Economics differs from route Opportunity"
            )
        command = EvaluateCapitalReadinessCommand(
            command_id=request.command_id,
            opportunity_identity=identity,
            conservative_economics_result_id=(
                request.conservative_economics_result_id
            ),
            domestic_market_validation_assessment_id=(
                request.domestic_market_validation_assessment_id
            ),
            critical_cost_assessment_id=request.critical_cost_assessment_id,
            requested_at=request.requested_at,
        )
        replay = self._repository.validate_replay(
            command.command_id, command.fingerprint
        )
        critical = self._repository.get_critical_cost_assessment(
            request.critical_cost_assessment_id
        )
        if replay is not None:
            return CapitalReadinessProductionResult(
                publication=replace(replay, replayed=True),
                critical_cost_normalization_id=(
                    None if critical is None else critical.acquisition_normalization_id
                ),
            )
        market = self._repository.get_domestic_market_validation(
            request.domestic_market_validation_assessment_id
        )
        if critical is None:
            raise CapitalReadinessSourceNotFoundError(
                "exact Critical Cost assessment is missing"
            )
        if market is None:
            raise CapitalReadinessSourceNotFoundError(
                "exact Domestic Market Validation assessment is missing"
            )
        if (
            critical.opportunity_identity != identity
            or market.source_manifest.opportunity_id != identity.opportunity_id
            or market.source_manifest.discovery_reference
            != identity.discovery_reference
        ):
            raise CapitalReadinessSourceConflictError(
                "terminal sources differ from route Opportunity"
            )
        publication = self._owner.execute(command)
        return CapitalReadinessProductionResult(
            publication=publication,
            critical_cost_normalization_id=(
                critical.acquisition_normalization_id
            ),
        )


__all__ = [name for name in globals() if name.startswith("Capital") or name.startswith("Evaluate") or name.startswith("CAPITAL")]
