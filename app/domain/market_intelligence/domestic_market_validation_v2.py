"""Target-bound Capital trust admission over exact Competition/Demand v2 authorities."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from enum import Enum, StrEnum
import hashlib
import json
import re

from app.domain.market_intelligence.competition_v2 import (
    BOUNDED_COHORT_POLICY_VERSION,
    COMPETITION_V2_ASSESSMENT_VERSION,
    COMPETITION_V2_OBSERVATION_VERSION,
    COMPETITION_V2_POLICY_VERSION,
    CompetitionV2Availability,
    CompetitionV2ObservationIdentity,
)
from app.domain.market_intelligence.demand_v2 import (
    DEMAND_COMPARABLE_COHORT_VERSION,
    DEMAND_V2_ASSESSMENT_VERSION,
    DEMAND_V2_OBSERVATION_VERSION,
    DEMAND_V2_POLICY_VERSION,
    CompetitionCohortReference,
    DemandFamilyStatus,
    DemandV2Availability,
)
from app.domain.market_intelligence.domestic_market_validation import (
    DomesticMarketValidationState,
)
from app.domain.opportunity import OpportunityDomesticSellingTargetBinding


DOMESTIC_MARKET_VALIDATION_V2_SCHEMA_VERSION = "domestic-market-validation-v2"
DOMESTIC_MARKET_VALIDATION_V2_SOURCE_MANIFEST_SCHEMA_VERSION = (
    "domestic-market-source-manifest-v2"
)
DOMESTIC_MARKET_VERIFICATION_V2_SCHEMA_VERSION = (
    "domestic-market-current-use-verification-v2"
)
DOMESTIC_MARKET_VALIDATION_V2_POLICY_NAME = "domestic-market-validation"
DOMESTIC_MARKET_VALIDATION_V2_POLICY_VERSION = "2.0.0"

_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_COMPETITION_CORE_ADMISSIBLE = frozenset({
    CompetitionV2Availability.COMPLETE_WITH_MARKETPLACE_SIGNAL,
    CompetitionV2Availability.COMPLETE_CORE_WITH_PARTIAL_MARKETPLACE_SIGNAL,
    CompetitionV2Availability.COMPLETE_CORE_ONLY,
})


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


def _sha256(value: str, name: str) -> str:
    normalized = _text(value, name).lower()
    if not _SHA256.fullmatch(normalized):
        raise ValueError(f"{name} must be SHA-256 text")
    return normalized


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


class DomesticMarketValidationV2ReasonCode(StrEnum):
    COMPETITION_V2_CORE_UNAVAILABLE = "competition_v2_core_unavailable"
    DEMAND_V2_MARKET_INTENT_INCOMPLETE = "demand_v2_market_intent_incomplete"
    DEMAND_V2_COMPARABLE_RESPONSE_INCOMPLETE = (
        "demand_v2_comparable_response_incomplete"
    )
    DEMAND_V2_CORE_INCOMPLETE = "demand_v2_core_incomplete"
    SOURCE_TIME_UNKNOWN = "source_time_unknown"
    SOURCE_TIME_IN_FUTURE = "source_time_in_future"
    CURRENT_USE_VERIFICATION_MISSING = "current_use_verification_missing"
    REVIEWED_SOURCE_MANIFEST_FINGERPRINT_MISMATCH = (
        "reviewed_source_manifest_fingerprint_mismatch"
    )

    @property
    def order(self) -> int:
        return _REASON_ORDER.index(self)


_REASON_ORDER = tuple(DomesticMarketValidationV2ReasonCode)


@dataclass(frozen=True, slots=True)
class DomesticMarketCompetitionV2Source:
    observation_identity: CompetitionV2ObservationIdentity
    cohort_id: str
    authority_fingerprint: str
    observation_schema_version: str
    cohort_policy_version: str
    assessment_schema_version: str
    assessment_policy_version: str
    availability: CompetitionV2Availability
    generated_at: datetime
    committed_at: datetime
    artifact_reference: str
    artifact_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.observation_identity, CompetitionV2ObservationIdentity):
            raise TypeError("observation_identity must be CompetitionV2ObservationIdentity")
        object.__setattr__(self, "cohort_id", _text(self.cohort_id, "cohort_id"))
        object.__setattr__(
            self, "authority_fingerprint",
            _sha256(self.authority_fingerprint, "authority_fingerprint"),
        )
        expected_versions = {
            "observation_schema_version": COMPETITION_V2_OBSERVATION_VERSION,
            "cohort_policy_version": BOUNDED_COHORT_POLICY_VERSION,
            "assessment_schema_version": COMPETITION_V2_ASSESSMENT_VERSION,
            "assessment_policy_version": COMPETITION_V2_POLICY_VERSION,
        }
        for name, expected in expected_versions.items():
            if getattr(self, name) != expected:
                raise ValueError(f"unsupported Competition v2 {name}")
        object.__setattr__(
            self, "availability", CompetitionV2Availability(self.availability),
        )
        object.__setattr__(self, "generated_at", _aware(self.generated_at, "generated_at"))
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        object.__setattr__(
            self, "artifact_reference", _text(self.artifact_reference, "artifact_reference"),
        )
        object.__setattr__(
            self, "artifact_sha256", _sha256(self.artifact_sha256, "artifact_sha256"),
        )


@dataclass(frozen=True, slots=True)
class DomesticMarketDemandV2Source:
    observation_id: str
    assessment_id: str
    comparable_cohort_id: str
    authority_fingerprint: str
    observation_schema_version: str
    assessment_schema_version: str
    assessment_policy_version: str
    comparable_cohort_version: str
    market_intent_status: DemandFamilyStatus
    comparable_response_status: DemandFamilyStatus
    availability: DemandV2Availability
    generated_at: datetime
    committed_at: datetime
    source_competition_cohort: CompetitionCohortReference | None

    def __post_init__(self) -> None:
        for name in ("observation_id", "assessment_id", "comparable_cohort_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(
            self, "authority_fingerprint",
            _sha256(self.authority_fingerprint, "authority_fingerprint"),
        )
        expected_versions = {
            "observation_schema_version": DEMAND_V2_OBSERVATION_VERSION,
            "assessment_schema_version": DEMAND_V2_ASSESSMENT_VERSION,
            "assessment_policy_version": DEMAND_V2_POLICY_VERSION,
            "comparable_cohort_version": DEMAND_COMPARABLE_COHORT_VERSION,
        }
        for name, expected in expected_versions.items():
            if getattr(self, name) != expected:
                raise ValueError(f"unsupported Demand v2 {name}")
        object.__setattr__(
            self, "market_intent_status", DemandFamilyStatus(self.market_intent_status),
        )
        object.__setattr__(
            self, "comparable_response_status",
            DemandFamilyStatus(self.comparable_response_status),
        )
        object.__setattr__(self, "availability", DemandV2Availability(self.availability))
        object.__setattr__(self, "generated_at", _aware(self.generated_at, "generated_at"))
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.source_competition_cohort is not None and not isinstance(
            self.source_competition_cohort, CompetitionCohortReference
        ):
            raise TypeError(
                "source_competition_cohort must be CompetitionCohortReference or None"
            )


@dataclass(frozen=True, slots=True)
class DomesticMarketValidationV2SourceManifest:
    target_binding: OpportunityDomesticSellingTargetBinding
    competition: DomesticMarketCompetitionV2Source
    demand: DomesticMarketDemandV2Source
    schema_version: str = DOMESTIC_MARKET_VALIDATION_V2_SOURCE_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.target_binding, OpportunityDomesticSellingTargetBinding):
            raise TypeError("target_binding must be OpportunityDomesticSellingTargetBinding")
        if not isinstance(self.competition, DomesticMarketCompetitionV2Source):
            raise TypeError("competition must be a DomesticMarketCompetitionV2Source")
        if not isinstance(self.demand, DomesticMarketDemandV2Source):
            raise TypeError("demand must be a DomesticMarketDemandV2Source")
        if self.schema_version != DOMESTIC_MARKET_VALIDATION_V2_SOURCE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported Domestic Market Validation v2 source manifest schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class DomesticMarketVerificationV2:
    operator_id: str
    verified_at: datetime
    current_use_confirmed: bool
    reviewed_source_manifest_fingerprint: str
    schema_version: str = DOMESTIC_MARKET_VERIFICATION_V2_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "operator_id", _text(self.operator_id, "operator_id"))
        object.__setattr__(self, "verified_at", _aware(self.verified_at, "verified_at"))
        if not isinstance(self.current_use_confirmed, bool):
            raise TypeError("current_use_confirmed must be bool")
        object.__setattr__(
            self,
            "reviewed_source_manifest_fingerprint",
            _sha256(
                self.reviewed_source_manifest_fingerprint,
                "reviewed_source_manifest_fingerprint",
            ),
        )
        if self.schema_version != DOMESTIC_MARKET_VERIFICATION_V2_SCHEMA_VERSION:
            raise ValueError("unsupported Domestic Market Verification v2 schema")


@dataclass(frozen=True, slots=True)
class DomesticMarketValidationV2Reason:
    code: DomesticMarketValidationV2ReasonCode

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", DomesticMarketValidationV2ReasonCode(self.code))


def domestic_market_validation_v2_reason_codes(
    source_manifest: DomesticMarketValidationV2SourceManifest,
    verification: DomesticMarketVerificationV2,
    evaluated_at: datetime,
) -> tuple[DomesticMarketValidationV2ReasonCode, ...]:
    if not isinstance(source_manifest, DomesticMarketValidationV2SourceManifest):
        raise TypeError("source_manifest must be DomesticMarketValidationV2SourceManifest")
    if not isinstance(verification, DomesticMarketVerificationV2):
        raise TypeError("verification must be DomesticMarketVerificationV2")
    evaluated = _aware(evaluated_at, "evaluated_at")
    reasons: set[DomesticMarketValidationV2ReasonCode] = set()
    if source_manifest.competition.availability not in _COMPETITION_CORE_ADMISSIBLE:
        reasons.add(DomesticMarketValidationV2ReasonCode.COMPETITION_V2_CORE_UNAVAILABLE)
    if source_manifest.demand.market_intent_status is not DemandFamilyStatus.COMPLETE:
        reasons.add(
            DomesticMarketValidationV2ReasonCode.DEMAND_V2_MARKET_INTENT_INCOMPLETE
        )
    if source_manifest.demand.comparable_response_status is not DemandFamilyStatus.COMPLETE:
        reasons.add(
            DomesticMarketValidationV2ReasonCode.DEMAND_V2_COMPARABLE_RESPONSE_INCOMPLETE
        )
    if source_manifest.demand.availability is not DemandV2Availability.COMPLETE_CORE:
        reasons.add(DomesticMarketValidationV2ReasonCode.DEMAND_V2_CORE_INCOMPLETE)
    source_times = (
        source_manifest.target_binding.bound_at,
        source_manifest.competition.generated_at,
        source_manifest.competition.committed_at,
        source_manifest.demand.generated_at,
        source_manifest.demand.committed_at,
    )
    if any(value > verification.verified_at for value in source_times):
        reasons.add(DomesticMarketValidationV2ReasonCode.SOURCE_TIME_IN_FUTURE)
    if verification.verified_at > evaluated:
        reasons.add(DomesticMarketValidationV2ReasonCode.SOURCE_TIME_IN_FUTURE)
    if not verification.current_use_confirmed:
        reasons.add(
            DomesticMarketValidationV2ReasonCode.CURRENT_USE_VERIFICATION_MISSING
        )
    if verification.reviewed_source_manifest_fingerprint != source_manifest.fingerprint:
        reasons.add(
            DomesticMarketValidationV2ReasonCode.REVIEWED_SOURCE_MANIFEST_FINGERPRINT_MISMATCH
        )
    return tuple(sorted(reasons, key=lambda value: value.order))


@dataclass(frozen=True, slots=True)
class DomesticMarketValidationV2Assessment:
    assessment_id: str
    source_manifest: DomesticMarketValidationV2SourceManifest
    verification: DomesticMarketVerificationV2
    state: DomesticMarketValidationState
    blocking_reasons: tuple[DomesticMarketValidationV2Reason, ...]
    policy_name: str
    policy_version: str
    requested_at: datetime
    evaluated_at: datetime
    schema_version: str = DOMESTIC_MARKET_VALIDATION_V2_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "assessment_id", _text(self.assessment_id, "assessment_id"))
        if not isinstance(self.source_manifest, DomesticMarketValidationV2SourceManifest):
            raise TypeError("source_manifest must be DomesticMarketValidationV2SourceManifest")
        if not isinstance(self.verification, DomesticMarketVerificationV2):
            raise TypeError("verification must be DomesticMarketVerificationV2")
        object.__setattr__(self, "state", DomesticMarketValidationState(self.state))
        if not isinstance(self.blocking_reasons, tuple) or any(
            not isinstance(item, DomesticMarketValidationV2Reason)
            for item in self.blocking_reasons
        ):
            raise TypeError("blocking_reasons must be a DomesticMarketValidationV2Reason tuple")
        requested = _aware(self.requested_at, "requested_at")
        evaluated = _aware(self.evaluated_at, "evaluated_at")
        object.__setattr__(self, "requested_at", requested)
        object.__setattr__(self, "evaluated_at", evaluated)
        expected_codes = domestic_market_validation_v2_reason_codes(
            self.source_manifest, self.verification, evaluated,
        )
        actual_codes = tuple(item.code for item in self.blocking_reasons)
        if actual_codes != expected_codes:
            raise ValueError("DMV v2 reasons must exactly match the v2 trust policy")
        expected_state = (
            DomesticMarketValidationState.VALIDATED_FOR_CAPITAL
            if not expected_codes else DomesticMarketValidationState.BLOCKED
        )
        if self.state is not expected_state:
            raise ValueError("DMV v2 state must be derived from the v2 trust policy")
        object.__setattr__(self, "policy_name", _text(self.policy_name, "policy_name"))
        object.__setattr__(self, "policy_version", _text(self.policy_version, "policy_version"))
        if (
            self.policy_name != DOMESTIC_MARKET_VALIDATION_V2_POLICY_NAME
            or self.policy_version != DOMESTIC_MARKET_VALIDATION_V2_POLICY_VERSION
        ):
            raise ValueError("unsupported Domestic Market Validation v2 policy")
        if self.schema_version != DOMESTIC_MARKET_VALIDATION_V2_SCHEMA_VERSION:
            raise ValueError("unsupported Domestic Market Validation v2 schema")

    @property
    def source_manifest_fingerprint(self) -> str:
        return self.source_manifest.fingerprint

    @property
    def reason_codes(self) -> tuple[DomesticMarketValidationV2ReasonCode, ...]:
        return tuple(item.code for item in self.blocking_reasons)


__all__ = [
    name for name in globals()
    if name.startswith("DomesticMarket") or name.startswith("DOMESTIC_MARKET")
    or name == "domestic_market_validation_v2_reason_codes"
]
