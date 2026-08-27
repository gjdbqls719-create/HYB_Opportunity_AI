"""Immutable Opportunity-owned contracts for Shadow validation registration."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum, StrEnum
import hashlib
import json
import re
from typing import TYPE_CHECKING

from app.domain.discovery import (
    DiscoveryScreeningEvaluationSnapshot,
    DiscoveryScreeningRankingPublication,
    NotRankedScreeningEntry,
    RankedScreeningEntry,
    screening_input_manifest_to_canonical_data,
)
from app.domain.opportunity.lifecycle import OpportunityLifecycleStatus
from app.domain.opportunity.new_to_market_domestic_selling import (
    NewToMarketDomesticSellingOpportunityAdmission,
    NewToMarketDomesticSellingTargetIdentity,
    OpportunityDomesticSellingTargetBinding,
)

if TYPE_CHECKING:
    from app.domain.decision_engine import OpportunityIdentity


SHADOW_O2_SUBJECT_LINEAGE_SCHEMA_VERSION = "shadow-o2-subject-lineage-v1"
SHADOW_SCREENING_LINEAGE_SCHEMA_VERSION = "shadow-screening-lineage-v1"
SHADOW_BASELINE_SOURCE_REFERENCE_SCHEMA_VERSION = (
    "shadow-baseline-source-reference-v1"
)
SHADOW_BASELINE_SOURCE_MANIFEST_SCHEMA_VERSION = (
    "shadow-baseline-source-manifest-v1"
)
SHADOW_REGISTRATION_REFERENCE_SCHEMA_VERSION = "shadow-registration-reference-v1"
SHADOW_VALIDATION_REGISTRATION_SCHEMA_VERSION = "shadow-validation-registration-v1"
SHADOW_BASELINE_SNAPSHOT_SCHEMA_VERSION = "shadow-baseline-snapshot-v1"
SHADOW_REGISTRATION_POLICY_NAME = "shadow-validation-registration"
SHADOW_REGISTRATION_POLICY_VERSION = "1.0.0"
SHADOW_BASELINE_POLICY_NAME = "shadow-validation-baseline"
SHADOW_BASELINE_POLICY_VERSION = "1.0.0"

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SEMANTIC_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_STABLE_TOKEN = re.compile(r"^[a-z0-9]+(?:[._:-][a-z0-9]+)*$")


class ShadowRegistrationAuthorityKind(StrEnum):
    MACHINE_SCREENING_BASED = "MACHINE_SCREENING_BASED"


class ShadowEvidenceClass(StrEnum):
    SHADOW_MARKET_THESIS = "SHADOW_MARKET_THESIS"


class ShadowBaselineSourceOwner(StrEnum):
    DISCOVERY = "DISCOVERY"
    OPPORTUNITY = "OPPORTUNITY"
    COMPETITION = "COMPETITION"
    DEMAND = "DEMAND"
    SOURCING = "SOURCING"
    ECONOMICS = "ECONOMICS"


class ShadowBaselineSourceRole(StrEnum):
    O2_SUBJECT_LINEAGE = "O2_SUBJECT_LINEAGE"
    SCREENING_EVALUATION = "SCREENING_EVALUATION"
    SCREENING_RANKING_PUBLICATION = "SCREENING_RANKING_PUBLICATION"
    SCREENING_USED_INPUT_MANIFEST = "SCREENING_USED_INPUT_MANIFEST"
    ADDITIONAL_BASELINE_EVIDENCE = "ADDITIONAL_BASELINE_EVIDENCE"
    MISSING_EVIDENCE_MARKER = "MISSING_EVIDENCE_MARKER"


class ShadowBaselineAvailability(StrEnum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"


class ShadowBaselineTruthScope(StrEnum):
    SOURCE_DEFINED = "SOURCE_DEFINED"
    KOREA_ONLY = "KOREA_ONLY"
    MIXED_GEOGRAPHY = "MIXED_GEOGRAPHY"
    POLICY_DEFINED = "POLICY_DEFINED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ShadowBaselineCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    PARTIAL = "PARTIAL"


class ShadowBaselineEvidenceDimension(StrEnum):
    COMPETITION = "COMPETITION"
    DEMAND = "DEMAND"
    SOURCING = "SOURCING"
    ECONOMICS = "ECONOMICS"


class ShadowCalibrationEligibility(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    PROVISIONAL = "PROVISIONAL"
    INELIGIBLE = "INELIGIBLE"


class ShadowCalibrationEligibilityReason(StrEnum):
    INCOMPLETE_BASELINE = "INCOMPLETE_BASELINE"
    SOURCE_AVAILABILITY_TIME_UNAVAILABLE = "SOURCE_AVAILABILITY_TIME_UNAVAILABLE"
    SOURCE_PROVENANCE_LIMITED = "SOURCE_PROVENANCE_LIMITED"
    MIXED_GEOGRAPHY_EVIDENCE = "MIXED_GEOGRAPHY_EVIDENCE"
    KNOWN_HINDSIGHT_AT_REGISTRATION = "KNOWN_HINDSIGHT_AT_REGISTRATION"
    UNSUPPORTED_EVIDENCE_SCOPE = "UNSUPPORTED_EVIDENCE_SCOPE"


def _text(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    if not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    if value != value.strip():
        raise ValueError(f"{name} must not contain surrounding whitespace")
    return value


def _optional_text(value: str | None, name: str) -> str | None:
    return None if value is None else _text(value, name)


def _stable_token(value: str, name: str) -> str:
    value = _text(value, name)
    if _STABLE_TOKEN.fullmatch(value) is None:
        raise ValueError(f"{name} must use a stable lowercase token")
    return value


def _semantic_version(value: str, name: str) -> str:
    value = _text(value, name)
    if _SEMANTIC_VERSION.fullmatch(value) is None:
        raise ValueError(f"{name} must use MAJOR.MINOR.PATCH")
    return value


def _fingerprint(value: str, name: str) -> str:
    value = _text(value, name)
    if _SHA256.fullmatch(value) is None:
        raise ValueError(f"{name} must be lowercase SHA-256 text")
    return value


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _optional_aware(value: datetime | None, name: str) -> datetime | None:
    return None if value is None else _aware(value, name)


def _canonical_datetime(value: datetime) -> str:
    return (
        _aware(value, "canonical datetime")
        .astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _canonical_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError("canonical Decimal must be finite")
    if value == 0:
        return "0"
    result = format(value.normalize(), "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def _canonical(value: object) -> object:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Decimal):
        return {"kind": "decimal", "value": _canonical_decimal(value)}
    if isinstance(value, datetime):
        return _canonical_datetime(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_canonical(item) for item in value]
    if isinstance(value, list):
        return [_canonical(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in value.items()}
    if is_dataclass(value):
        return {
            field.name: _canonical(getattr(value, field.name))
            for field in fields(value)
        }
    raise TypeError(f"unsupported canonical value: {type(value).__name__}")


def _canonical_json(value: object) -> str:
    return json.dumps(
        _canonical(value), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _integrity(value: object, supplied: str, name: str) -> str:
    expected = _sha256(value)
    if supplied and _fingerprint(supplied, name) != expected:
        raise ValueError(f"{name} does not match canonical content")
    return expected


def _enum_tuple(value: tuple[object, ...], enum_type, name: str) -> tuple:
    if not isinstance(value, tuple):
        raise TypeError(f"{name} must be a tuple")
    try:
        result = tuple(enum_type(item) for item in value)
    except ValueError as error:
        raise ValueError(f"{name} contains an unsupported value") from error
    if len(set(result)) != len(result):
        raise ValueError(f"{name} must be unique")
    if result != tuple(sorted(result, key=lambda item: item.value)):
        raise ValueError(f"{name} must use canonical ordering")
    return result


@dataclass(frozen=True, slots=True)
class ShadowVersionedPolicyReference:
    policy_name: str
    policy_version: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy_name", _stable_token(self.policy_name, "policy_name"))
        object.__setattr__(
            self, "policy_version", _semantic_version(self.policy_version, "policy_version")
        )


@dataclass(frozen=True, slots=True)
class ShadowO2SubjectLineage:
    """Exact O2 reference plus the minimum persisted Candidate/O1 lineage."""

    o2_opportunity_identity: OpportunityIdentity
    o2_lifecycle_status: OpportunityLifecycleStatus
    o2_lifecycle_version: int
    target_identity: NewToMarketDomesticSellingTargetIdentity
    target_binding_fingerprint: str
    o2_admission_id: str
    o2_admission_fingerprint: str
    o1_opportunity_identity: OpportunityIdentity
    candidate_id: str
    candidate_opportunity_binding_id: str
    candidate_opportunity_binding_fingerprint: str
    promotion_command_id: str
    promotion_admission_id: str
    discovery_command_id: str
    discovery_execution_id: str
    finalized_group_id: str
    o1_source_manifest_fingerprint: str
    target_bound_at: datetime
    o2_admitted_at: datetime
    schema_version: str = SHADOW_O2_SUBJECT_LINEAGE_SCHEMA_VERSION
    integrity_fingerprint: str = ""

    def __post_init__(self) -> None:
        from app.domain.decision_engine import OpportunityIdentity

        if not isinstance(self.o2_opportunity_identity, OpportunityIdentity):
            raise TypeError("o2_opportunity_identity must be OpportunityIdentity")
        if not isinstance(self.o1_opportunity_identity, OpportunityIdentity):
            raise TypeError("o1_opportunity_identity must be OpportunityIdentity")
        if self.o1_opportunity_identity == self.o2_opportunity_identity:
            raise ValueError("O1 and O2 Opportunity identities must differ")
        try:
            status = OpportunityLifecycleStatus(self.o2_lifecycle_status)
        except ValueError as error:
            raise ValueError("unsupported O2 lifecycle status") from error
        object.__setattr__(self, "o2_lifecycle_status", status)
        if isinstance(self.o2_lifecycle_version, bool) or not isinstance(
            self.o2_lifecycle_version, int
        ) or self.o2_lifecycle_version < 1:
            raise ValueError("o2_lifecycle_version must be a positive integer")
        if not isinstance(self.target_identity, NewToMarketDomesticSellingTargetIdentity):
            raise TypeError(
                "target_identity must be NewToMarketDomesticSellingTargetIdentity"
            )
        for name in (
            "o2_admission_id", "candidate_id", "candidate_opportunity_binding_id",
            "promotion_command_id", "promotion_admission_id", "discovery_command_id",
            "discovery_execution_id", "finalized_group_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in (
            "target_binding_fingerprint", "o2_admission_fingerprint",
            "candidate_opportunity_binding_fingerprint",
            "o1_source_manifest_fingerprint",
        ):
            object.__setattr__(self, name, _fingerprint(getattr(self, name), name))
        object.__setattr__(
            self, "target_bound_at", _aware(self.target_bound_at, "target_bound_at")
        )
        object.__setattr__(
            self, "o2_admitted_at", _aware(self.o2_admitted_at, "o2_admitted_at")
        )
        if self.target_bound_at > self.o2_admitted_at:
            raise ValueError("target binding cannot follow O2 admission")
        if self.schema_version != SHADOW_O2_SUBJECT_LINEAGE_SCHEMA_VERSION:
            raise ValueError("unsupported Shadow O2 subject lineage schema")
        object.__setattr__(
            self,
            "integrity_fingerprint",
            _integrity(
                shadow_o2_subject_lineage_to_canonical_data(
                    self, include_integrity_fingerprint=False
                ),
                self.integrity_fingerprint,
                "integrity_fingerprint",
            ),
        )

    @classmethod
    def from_authorities(
        cls,
        *,
        admission: NewToMarketDomesticSellingOpportunityAdmission,
        target_binding: OpportunityDomesticSellingTargetBinding,
        o2_lifecycle_status: OpportunityLifecycleStatus,
        o2_lifecycle_version: int,
        discovery_command_id: str,
        discovery_execution_id: str,
        candidate_opportunity_binding_fingerprint: str,
    ) -> "ShadowO2SubjectLineage":
        if not isinstance(admission, NewToMarketDomesticSellingOpportunityAdmission):
            raise TypeError("admission must be NewToMarketDomesticSellingOpportunityAdmission")
        if not isinstance(target_binding, OpportunityDomesticSellingTargetBinding):
            raise TypeError("target_binding must be OpportunityDomesticSellingTargetBinding")
        if (
            target_binding.opportunity_id
            != admission.domestic_opportunity_identity.opportunity_id
            or target_binding.discovery_reference
            != admission.domestic_opportunity_identity.discovery_reference
            or target_binding.target_identity != admission.target_identity
        ):
            raise ValueError("O2 admission and target binding lineage differ")
        source = admission.source_manifest
        return cls(
            o2_opportunity_identity=admission.domestic_opportunity_identity,
            o2_lifecycle_status=o2_lifecycle_status,
            o2_lifecycle_version=o2_lifecycle_version,
            target_identity=admission.target_identity,
            target_binding_fingerprint=_sha256(target_binding),
            o2_admission_id=admission.admission_id,
            o2_admission_fingerprint=_sha256(admission),
            o1_opportunity_identity=source.source_opportunity_identity,
            candidate_id=source.candidate_id,
            candidate_opportunity_binding_id=source.candidate_opportunity_binding_id,
            candidate_opportunity_binding_fingerprint=(
                candidate_opportunity_binding_fingerprint
            ),
            promotion_command_id=source.promotion_command_id,
            promotion_admission_id=source.promotion_admission_id,
            discovery_command_id=discovery_command_id,
            discovery_execution_id=discovery_execution_id,
            finalized_group_id=source.finalized_group_id,
            o1_source_manifest_fingerprint=_sha256(source),
            target_bound_at=target_binding.bound_at,
            o2_admitted_at=admission.admitted_at,
        )


def shadow_o2_subject_lineage_to_canonical_data(
    value: ShadowO2SubjectLineage,
    *,
    include_integrity_fingerprint: bool = True,
) -> dict[str, object]:
    if not isinstance(value, ShadowO2SubjectLineage):
        raise TypeError("value must be ShadowO2SubjectLineage")
    payload = {
        field.name: _canonical(getattr(value, field.name))
        for field in fields(value)
        if field.name != "integrity_fingerprint"
    }
    if include_integrity_fingerprint:
        payload["integrity_fingerprint"] = value.integrity_fingerprint
    return payload


@dataclass(frozen=True, slots=True)
class ShadowScreeningLineage:
    """Exact persisted ADR-0067 evaluation/publication relationship."""

    screening_evaluation_id: str
    screening_evaluation_fingerprint: str
    screening_ranking_publication_id: str
    screening_ranking_publication_fingerprint: str
    ranking_entry: RankedScreeningEntry | NotRankedScreeningEntry
    command_id: str
    discovery_execution_id: str
    finalized_group_id: str
    group_membership_fingerprint: str
    screening_policy_manifest_fingerprint: str
    screening_input_manifest_fingerprint: str
    evaluated_at: datetime
    ranking_created_at: datetime
    evaluation_schema_version: str
    ranking_schema_version: str
    schema_version: str = SHADOW_SCREENING_LINEAGE_SCHEMA_VERSION
    integrity_fingerprint: str = ""

    def __post_init__(self) -> None:
        for name in (
            "screening_evaluation_id", "screening_ranking_publication_id",
            "command_id", "discovery_execution_id", "finalized_group_id",
            "evaluation_schema_version", "ranking_schema_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in (
            "screening_evaluation_fingerprint",
            "screening_ranking_publication_fingerprint",
            "group_membership_fingerprint",
            "screening_policy_manifest_fingerprint",
            "screening_input_manifest_fingerprint",
        ):
            object.__setattr__(self, name, _fingerprint(getattr(self, name), name))
        if not isinstance(self.ranking_entry, (RankedScreeningEntry, NotRankedScreeningEntry)):
            raise TypeError("ranking_entry must be an ADR-0067 ranked or not-ranked entry")
        entry = self.ranking_entry
        if (
            entry.discovery_execution_id != self.discovery_execution_id
            or entry.finalized_group_id != self.finalized_group_id
            or entry.screening_evaluation_id != self.screening_evaluation_id
            or entry.evaluation_fingerprint != self.screening_evaluation_fingerprint
        ):
            raise ValueError("screening ranking entry differs from evaluation lineage")
        object.__setattr__(self, "evaluated_at", _aware(self.evaluated_at, "evaluated_at"))
        object.__setattr__(
            self, "ranking_created_at", _aware(self.ranking_created_at, "ranking_created_at")
        )
        if self.evaluated_at > self.ranking_created_at:
            raise ValueError("screening evaluation cannot follow ranking publication")
        if self.schema_version != SHADOW_SCREENING_LINEAGE_SCHEMA_VERSION:
            raise ValueError("unsupported Shadow screening lineage schema")
        object.__setattr__(
            self,
            "integrity_fingerprint",
            _integrity(
                shadow_screening_lineage_to_canonical_data(
                    self, include_integrity_fingerprint=False
                ),
                self.integrity_fingerprint,
                "integrity_fingerprint",
            ),
        )

    @classmethod
    def from_authorities(
        cls,
        evaluation: DiscoveryScreeningEvaluationSnapshot,
        publication: DiscoveryScreeningRankingPublication,
    ) -> "ShadowScreeningLineage":
        if not isinstance(evaluation, DiscoveryScreeningEvaluationSnapshot):
            raise TypeError("evaluation must be DiscoveryScreeningEvaluationSnapshot")
        if not isinstance(publication, DiscoveryScreeningRankingPublication):
            raise TypeError("publication must be DiscoveryScreeningRankingPublication")
        if (
            evaluation.command_id != publication.command_id
            or evaluation.discovery_execution_id != publication.discovery_execution_id
        ):
            raise ValueError("screening evaluation and publication authority differ")
        matches = tuple(
            entry
            for entry in (*publication.ranked_entries, *publication.not_ranked_entries)
            if entry.screening_evaluation_id == evaluation.screening_evaluation_id
        )
        if len(matches) != 1:
            raise ValueError("screening publication must reference the exact evaluation")
        entry = matches[0]
        if (
            entry.finalized_group_id != evaluation.finalized_group_id
            or entry.evaluation_fingerprint != evaluation.integrity_fingerprint
        ):
            raise ValueError("screening publication entry fingerprint or Group differs")
        return cls(
            screening_evaluation_id=evaluation.screening_evaluation_id,
            screening_evaluation_fingerprint=evaluation.integrity_fingerprint,
            screening_ranking_publication_id=(
                publication.screening_ranking_publication_id
            ),
            screening_ranking_publication_fingerprint=(
                publication.integrity_fingerprint
            ),
            ranking_entry=entry,
            command_id=evaluation.command_id,
            discovery_execution_id=evaluation.discovery_execution_id,
            finalized_group_id=evaluation.finalized_group_id,
            group_membership_fingerprint=evaluation.group_membership_fingerprint,
            screening_policy_manifest_fingerprint=_sha256(
                evaluation.screening_policy_manifest
            ),
            screening_input_manifest_fingerprint=_sha256(
                screening_input_manifest_to_canonical_data(evaluation.input_manifest)
            ),
            evaluated_at=evaluation.evaluated_at,
            ranking_created_at=publication.ranking_created_at,
            evaluation_schema_version=evaluation.schema_version,
            ranking_schema_version=publication.schema_version,
        )


def shadow_screening_lineage_to_canonical_data(
    value: ShadowScreeningLineage,
    *,
    include_integrity_fingerprint: bool = True,
) -> dict[str, object]:
    if not isinstance(value, ShadowScreeningLineage):
        raise TypeError("value must be ShadowScreeningLineage")
    payload = {
        field.name: _canonical(getattr(value, field.name))
        for field in fields(value)
        if field.name != "integrity_fingerprint"
    }
    if include_integrity_fingerprint:
        payload["integrity_fingerprint"] = value.integrity_fingerprint
    return payload


@dataclass(frozen=True, slots=True)
class ShadowValidationRegistration:
    shadow_validation_id: str
    baseline_snapshot_id: str
    authority_kind: ShadowRegistrationAuthorityKind
    subject: ShadowO2SubjectLineage
    screening_lineage: ShadowScreeningLineage
    operator_id: str
    registration_reason: str
    registered_at: datetime
    knowledge_cutoff_at: datetime
    cadence_policy: ShadowVersionedPolicyReference
    registration_policy: ShadowVersionedPolicyReference = ShadowVersionedPolicyReference(
        SHADOW_REGISTRATION_POLICY_NAME, SHADOW_REGISTRATION_POLICY_VERSION
    )
    evidence_class: ShadowEvidenceClass = ShadowEvidenceClass.SHADOW_MARKET_THESIS
    schema_version: str = SHADOW_VALIDATION_REGISTRATION_SCHEMA_VERSION
    integrity_fingerprint: str = ""

    def __post_init__(self) -> None:
        for name in ("shadow_validation_id", "baseline_snapshot_id", "operator_id", "registration_reason"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        try:
            authority = ShadowRegistrationAuthorityKind(self.authority_kind)
        except ValueError as error:
            raise ValueError("unsupported Shadow registration authority kind") from error
        if authority is not ShadowRegistrationAuthorityKind.MACHINE_SCREENING_BASED:
            raise ValueError("Shadow MVP requires MACHINE_SCREENING_BASED authority")
        object.__setattr__(self, "authority_kind", authority)
        try:
            evidence_class = ShadowEvidenceClass(self.evidence_class)
        except ValueError as error:
            raise ValueError("unsupported Shadow evidence class") from error
        if evidence_class is not ShadowEvidenceClass.SHADOW_MARKET_THESIS:
            raise ValueError("Shadow registration evidence must be SHADOW_MARKET_THESIS")
        object.__setattr__(self, "evidence_class", evidence_class)
        if not isinstance(self.subject, ShadowO2SubjectLineage):
            raise TypeError("subject must be ShadowO2SubjectLineage")
        if not isinstance(self.screening_lineage, ShadowScreeningLineage):
            raise TypeError("screening_lineage must be ShadowScreeningLineage")
        if not isinstance(self.cadence_policy, ShadowVersionedPolicyReference):
            raise TypeError("cadence_policy must be ShadowVersionedPolicyReference")
        if not isinstance(self.registration_policy, ShadowVersionedPolicyReference):
            raise TypeError("registration_policy must be ShadowVersionedPolicyReference")
        if self.registration_policy != ShadowVersionedPolicyReference(
            SHADOW_REGISTRATION_POLICY_NAME, SHADOW_REGISTRATION_POLICY_VERSION
        ):
            raise ValueError("unsupported Shadow registration policy")
        object.__setattr__(self, "registered_at", _aware(self.registered_at, "registered_at"))
        object.__setattr__(
            self, "knowledge_cutoff_at", _aware(self.knowledge_cutoff_at, "knowledge_cutoff_at")
        )
        if self.knowledge_cutoff_at > self.registered_at:
            raise ValueError("knowledge_cutoff_at cannot follow registered_at")
        if self.screening_lineage.ranking_created_at > self.knowledge_cutoff_at:
            raise ValueError("screening authority cannot be created after knowledge cutoff")
        if max(self.subject.target_bound_at, self.subject.o2_admitted_at) > self.knowledge_cutoff_at:
            raise ValueError("O2 subject authority cannot be created after knowledge cutoff")
        if (
            self.subject.discovery_command_id != self.screening_lineage.command_id
            or self.subject.discovery_execution_id
            != self.screening_lineage.discovery_execution_id
            or self.subject.finalized_group_id != self.screening_lineage.finalized_group_id
        ):
            raise ValueError("O2 and screening Candidate/Group lineage differ")
        if self.schema_version != SHADOW_VALIDATION_REGISTRATION_SCHEMA_VERSION:
            raise ValueError("unsupported Shadow validation registration schema")
        object.__setattr__(
            self,
            "integrity_fingerprint",
            _integrity(
                shadow_validation_registration_to_canonical_data(
                    self, include_integrity_fingerprint=False
                ),
                self.integrity_fingerprint,
                "integrity_fingerprint",
            ),
        )

    def reference(self) -> "ShadowRegistrationReference":
        return ShadowRegistrationReference.from_registration(self)


def shadow_validation_registration_to_canonical_data(
    value: ShadowValidationRegistration,
    *,
    include_integrity_fingerprint: bool = True,
) -> dict[str, object]:
    if not isinstance(value, ShadowValidationRegistration):
        raise TypeError("value must be ShadowValidationRegistration")
    payload = {
        field.name: _canonical(getattr(value, field.name))
        for field in fields(value)
        if field.name != "integrity_fingerprint"
    }
    if include_integrity_fingerprint:
        payload["integrity_fingerprint"] = value.integrity_fingerprint
    return payload


@dataclass(frozen=True, slots=True)
class ShadowRegistrationReference:
    shadow_validation_id: str
    baseline_snapshot_id: str
    registration_fingerprint: str
    o2_opportunity_id: str
    domestic_selling_target_id: str
    subject_lineage_fingerprint: str
    screening_evaluation_id: str
    screening_evaluation_fingerprint: str
    screening_ranking_publication_id: str
    screening_ranking_publication_fingerprint: str
    screening_input_manifest_fingerprint: str
    screening_lineage_fingerprint: str
    discovery_execution_id: str
    finalized_group_id: str
    screening_evaluated_at: datetime
    ranking_created_at: datetime
    registered_at: datetime
    knowledge_cutoff_at: datetime
    evidence_class: ShadowEvidenceClass = ShadowEvidenceClass.SHADOW_MARKET_THESIS
    schema_version: str = SHADOW_REGISTRATION_REFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "shadow_validation_id", "baseline_snapshot_id", "o2_opportunity_id",
            "domestic_selling_target_id", "screening_evaluation_id",
            "screening_ranking_publication_id", "discovery_execution_id",
            "finalized_group_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in (
            "registration_fingerprint", "subject_lineage_fingerprint",
            "screening_evaluation_fingerprint",
            "screening_ranking_publication_fingerprint",
            "screening_input_manifest_fingerprint", "screening_lineage_fingerprint",
        ):
            object.__setattr__(self, name, _fingerprint(getattr(self, name), name))
        for name in (
            "screening_evaluated_at", "ranking_created_at", "registered_at",
            "knowledge_cutoff_at",
        ):
            object.__setattr__(self, name, _aware(getattr(self, name), name))
        if not (
            self.screening_evaluated_at
            <= self.ranking_created_at
            <= self.knowledge_cutoff_at
            <= self.registered_at
        ):
            raise ValueError("registration reference time lineage is invalid")
        try:
            evidence_class = ShadowEvidenceClass(self.evidence_class)
        except ValueError as error:
            raise ValueError("unsupported Shadow evidence class") from error
        if evidence_class is not ShadowEvidenceClass.SHADOW_MARKET_THESIS:
            raise ValueError("Shadow reference evidence must be SHADOW_MARKET_THESIS")
        object.__setattr__(self, "evidence_class", evidence_class)
        if self.schema_version != SHADOW_REGISTRATION_REFERENCE_SCHEMA_VERSION:
            raise ValueError("unsupported Shadow registration-reference schema")

    @classmethod
    def from_registration(
        cls, value: ShadowValidationRegistration
    ) -> "ShadowRegistrationReference":
        if not isinstance(value, ShadowValidationRegistration):
            raise TypeError("value must be ShadowValidationRegistration")
        return cls(
            shadow_validation_id=value.shadow_validation_id,
            baseline_snapshot_id=value.baseline_snapshot_id,
            registration_fingerprint=value.integrity_fingerprint,
            o2_opportunity_id=value.subject.o2_opportunity_identity.opportunity_id,
            domestic_selling_target_id=value.subject.target_identity.domestic_selling_target_id,
            subject_lineage_fingerprint=value.subject.integrity_fingerprint,
            screening_evaluation_id=value.screening_lineage.screening_evaluation_id,
            screening_evaluation_fingerprint=(
                value.screening_lineage.screening_evaluation_fingerprint
            ),
            screening_ranking_publication_id=(
                value.screening_lineage.screening_ranking_publication_id
            ),
            screening_ranking_publication_fingerprint=(
                value.screening_lineage.screening_ranking_publication_fingerprint
            ),
            screening_input_manifest_fingerprint=(
                value.screening_lineage.screening_input_manifest_fingerprint
            ),
            screening_lineage_fingerprint=value.screening_lineage.integrity_fingerprint,
            discovery_execution_id=value.screening_lineage.discovery_execution_id,
            finalized_group_id=value.screening_lineage.finalized_group_id,
            screening_evaluated_at=value.screening_lineage.evaluated_at,
            ranking_created_at=value.screening_lineage.ranking_created_at,
            registered_at=value.registered_at,
            knowledge_cutoff_at=value.knowledge_cutoff_at,
        )


def serialize_shadow_validation_registration(
    value: ShadowValidationRegistration,
) -> str:
    return _canonical_json(shadow_validation_registration_to_canonical_data(value))




__all__ = [
    name
    for name in globals()
    if name.startswith("SHADOW_")
    or name.startswith("Shadow")
    or name.startswith("serialize_shadow")
    or name.startswith("shadow_")
]
