"""Immutable source-manifest and knowledge snapshot contracts for Shadow baselines."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
import json

from app.domain.opportunity.shadow_validation import (
    SHADOW_BASELINE_POLICY_NAME,
    SHADOW_BASELINE_POLICY_VERSION,
    SHADOW_BASELINE_SNAPSHOT_SCHEMA_VERSION,
    SHADOW_BASELINE_SOURCE_MANIFEST_SCHEMA_VERSION,
    SHADOW_BASELINE_SOURCE_REFERENCE_SCHEMA_VERSION,
    ShadowBaselineAvailability,
    ShadowBaselineCompleteness,
    ShadowBaselineEvidenceDimension,
    ShadowBaselineSourceOwner,
    ShadowBaselineSourceRole,
    ShadowBaselineTruthScope,
    ShadowCalibrationEligibility,
    ShadowCalibrationEligibilityReason,
    ShadowEvidenceClass,
    ShadowRegistrationReference,
    ShadowVersionedPolicyReference,
    _aware,
    _canonical,
    _canonical_json,
    _enum_tuple,
    _fingerprint,
    _integrity,
    _optional_aware,
    _optional_text,
    _semantic_version,
    _sha256,
    _stable_token,
    _text,
)


@dataclass(frozen=True, slots=True)
class ShadowBaselineSourceReference:
    """One explicitly selected baseline projection owned by an upstream boundary."""

    reference_id: str
    source_owner: ShadowBaselineSourceOwner
    source_kind: str
    source_id: str
    baseline_role: ShadowBaselineSourceRole
    availability: ShadowBaselineAvailability
    truth_scope: ShadowBaselineTruthScope
    source_revision: str | None = None
    source_schema_version: str | None = None
    source_policy_name: str | None = None
    source_policy_version: str | None = None
    source_fingerprint: str | None = None
    semantic_projection: str | None = None
    semantic_projection_fingerprint: str | None = None
    observed_at: datetime | None = None
    observation_window_start: datetime | None = None
    observation_window_end: datetime | None = None
    generated_at: datetime | None = None
    committed_at: datetime | None = None
    availability_reason: str | None = None
    schema_version: str = SHADOW_BASELINE_SOURCE_REFERENCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "reference_id", _stable_token(self.reference_id, "reference_id"))
        object.__setattr__(self, "source_kind", _stable_token(self.source_kind, "source_kind"))
        object.__setattr__(self, "source_id", _text(self.source_id, "source_id"))
        for name in (
            "source_revision", "source_schema_version", "source_policy_name",
            "availability_reason",
        ):
            object.__setattr__(self, name, _optional_text(getattr(self, name), name))
        if self.source_policy_version is not None:
            object.__setattr__(
                self,
                "source_policy_version",
                _semantic_version(self.source_policy_version, "source_policy_version"),
            )
        try:
            object.__setattr__(self, "source_owner", ShadowBaselineSourceOwner(self.source_owner))
            object.__setattr__(self, "baseline_role", ShadowBaselineSourceRole(self.baseline_role))
            object.__setattr__(self, "availability", ShadowBaselineAvailability(self.availability))
            object.__setattr__(self, "truth_scope", ShadowBaselineTruthScope(self.truth_scope))
        except ValueError as error:
            raise ValueError("unsupported Shadow baseline source enum value") from error
        if self.source_fingerprint is not None:
            object.__setattr__(
                self, "source_fingerprint", _fingerprint(self.source_fingerprint, "source_fingerprint")
            )
        projection = self.semantic_projection
        if projection is not None:
            projection = _text(projection, "semantic_projection")
            try:
                decoded = json.loads(projection)
            except json.JSONDecodeError as error:
                raise ValueError("semantic_projection must be canonical JSON") from error
            if not isinstance(decoded, dict) or _canonical_json(decoded) != projection:
                raise ValueError("semantic_projection must be a canonical JSON object")
            expected_projection_fingerprint = _sha256(decoded)
            if self.semantic_projection_fingerprint is not None and _fingerprint(
                self.semantic_projection_fingerprint, "semantic_projection_fingerprint"
            ) != expected_projection_fingerprint:
                raise ValueError("semantic projection fingerprint does not match content")
            object.__setattr__(self, "semantic_projection", projection)
            object.__setattr__(
                self,
                "semantic_projection_fingerprint",
                expected_projection_fingerprint,
            )
        elif self.semantic_projection_fingerprint is not None:
            object.__setattr__(
                self,
                "semantic_projection_fingerprint",
                _fingerprint(
                    self.semantic_projection_fingerprint,
                    "semantic_projection_fingerprint",
                ),
            )
        for name in (
            "observed_at", "observation_window_start", "observation_window_end",
            "generated_at", "committed_at",
        ):
            object.__setattr__(self, name, _optional_aware(getattr(self, name), name))
        if (self.observation_window_start is None) != (self.observation_window_end is None):
            raise ValueError("observation window start and end must be supplied together")
        if (
            self.observation_window_start is not None
            and self.observation_window_start > self.observation_window_end
        ):
            raise ValueError("observation window start cannot follow end")
        if self.availability is ShadowBaselineAvailability.AVAILABLE:
            if self.availability_reason is not None:
                raise ValueError("available source cannot carry an availability reason")
            if self.source_fingerprint is None and self.semantic_projection_fingerprint is None:
                raise ValueError("available source requires exact fingerprint or projection")
        else:
            if self.availability_reason is None:
                raise ValueError("unavailable source requires an explicit reason")
            if any(
                value is not None
                for value in (
                    self.source_fingerprint,
                    self.semantic_projection,
                    self.semantic_projection_fingerprint,
                    self.observed_at,
                    self.observation_window_start,
                    self.generated_at,
                    self.committed_at,
                )
            ):
                raise ValueError("unavailable source cannot carry fabricated evidence facts")
            if self.baseline_role is not ShadowBaselineSourceRole.MISSING_EVIDENCE_MARKER:
                raise ValueError("unavailable source must be a missing-evidence marker")
        if self.schema_version != SHADOW_BASELINE_SOURCE_REFERENCE_SCHEMA_VERSION:
            raise ValueError("unsupported Shadow baseline source-reference schema")

    @property
    def authority_times(self) -> tuple[datetime, ...]:
        return tuple(
            value
            for value in (
                self.observed_at,
                self.observation_window_end,
                self.generated_at,
                self.committed_at,
            )
            if value is not None
        )


@dataclass(frozen=True, slots=True)
class ShadowBaselineSourceManifest:
    sources: tuple[ShadowBaselineSourceReference, ...]
    schema_version: str = SHADOW_BASELINE_SOURCE_MANIFEST_SCHEMA_VERSION
    integrity_fingerprint: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.sources, tuple) or not self.sources:
            raise ValueError("sources must be a non-empty tuple")
        if any(not isinstance(item, ShadowBaselineSourceReference) for item in self.sources):
            raise TypeError("sources must contain ShadowBaselineSourceReference")
        reference_ids = tuple(item.reference_id for item in self.sources)
        if len(set(reference_ids)) != len(reference_ids):
            raise ValueError("baseline source references must be unique")
        if reference_ids != tuple(sorted(reference_ids)):
            raise ValueError("baseline sources must use canonical reference-ID ordering")
        identities = tuple(
            (item.source_owner, item.source_kind, item.source_id, item.source_revision)
            for item in self.sources
            if item.availability is ShadowBaselineAvailability.AVAILABLE
        )
        if len(set(identities)) != len(identities):
            raise ValueError("duplicate authoritative baseline source")
        required_roles = {
            ShadowBaselineSourceRole.O2_SUBJECT_LINEAGE,
            ShadowBaselineSourceRole.SCREENING_EVALUATION,
            ShadowBaselineSourceRole.SCREENING_RANKING_PUBLICATION,
            ShadowBaselineSourceRole.SCREENING_USED_INPUT_MANIFEST,
        }
        roles = tuple(item.baseline_role for item in self.sources)
        if any(roles.count(role) != 1 for role in required_roles):
            raise ValueError("baseline requires one exact O2 and screening authority manifest")
        required = tuple(item for item in self.sources if item.baseline_role in required_roles)
        if any(item.availability is not ShadowBaselineAvailability.AVAILABLE for item in required):
            raise ValueError("required O2 and screening authority sources must be available")
        if self.schema_version != SHADOW_BASELINE_SOURCE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported Shadow baseline source manifest schema")
        object.__setattr__(
            self,
            "integrity_fingerprint",
            _integrity(
                shadow_baseline_source_manifest_to_canonical_data(
                    self, include_integrity_fingerprint=False
                ),
                self.integrity_fingerprint,
                "integrity_fingerprint",
            ),
        )


def shadow_baseline_source_manifest_to_canonical_data(
    value: ShadowBaselineSourceManifest,
    *,
    include_integrity_fingerprint: bool = True,
) -> dict[str, object]:
    if not isinstance(value, ShadowBaselineSourceManifest):
        raise TypeError("value must be ShadowBaselineSourceManifest")
    payload = {
        "sources": [_canonical(item) for item in value.sources],
        "schema_version": value.schema_version,
    }
    if include_integrity_fingerprint:
        payload["integrity_fingerprint"] = value.integrity_fingerprint
    return payload


@dataclass(frozen=True, slots=True)
class ShadowBaselineSnapshot:
    """The exact historical knowledge state frozen for one registration."""

    registration: ShadowRegistrationReference
    source_manifest: ShadowBaselineSourceManifest
    baseline_created_at: datetime
    completeness: ShadowBaselineCompleteness
    missing_evidence_dimensions: tuple[ShadowBaselineEvidenceDimension, ...]
    calibration_eligibility: ShadowCalibrationEligibility
    calibration_reason_codes: tuple[ShadowCalibrationEligibilityReason, ...]
    baseline_policy: ShadowVersionedPolicyReference = ShadowVersionedPolicyReference(
        SHADOW_BASELINE_POLICY_NAME, SHADOW_BASELINE_POLICY_VERSION
    )
    evidence_class: ShadowEvidenceClass = ShadowEvidenceClass.SHADOW_MARKET_THESIS
    schema_version: str = SHADOW_BASELINE_SNAPSHOT_SCHEMA_VERSION
    integrity_fingerprint: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.registration, ShadowRegistrationReference):
            raise TypeError("registration must be ShadowRegistrationReference")
        if not isinstance(self.source_manifest, ShadowBaselineSourceManifest):
            raise TypeError("source_manifest must be ShadowBaselineSourceManifest")
        object.__setattr__(
            self, "baseline_created_at", _aware(self.baseline_created_at, "baseline_created_at")
        )
        if self.baseline_created_at < self.registration.registered_at:
            raise ValueError("baseline_created_at cannot precede registration")
        try:
            completeness = ShadowBaselineCompleteness(self.completeness)
            eligibility = ShadowCalibrationEligibility(self.calibration_eligibility)
            evidence_class = ShadowEvidenceClass(self.evidence_class)
        except ValueError as error:
            raise ValueError("unsupported Shadow baseline status value") from error
        object.__setattr__(self, "completeness", completeness)
        object.__setattr__(self, "calibration_eligibility", eligibility)
        if evidence_class is not ShadowEvidenceClass.SHADOW_MARKET_THESIS:
            raise ValueError("Shadow baseline evidence must be SHADOW_MARKET_THESIS")
        object.__setattr__(self, "evidence_class", evidence_class)
        missing = _enum_tuple(
            self.missing_evidence_dimensions,
            ShadowBaselineEvidenceDimension,
            "missing_evidence_dimensions",
        )
        reasons = _enum_tuple(
            self.calibration_reason_codes,
            ShadowCalibrationEligibilityReason,
            "calibration_reason_codes",
        )
        object.__setattr__(self, "missing_evidence_dimensions", missing)
        object.__setattr__(self, "calibration_reason_codes", reasons)
        if completeness is ShadowBaselineCompleteness.COMPLETE and missing:
            raise ValueError("complete baseline cannot have missing evidence dimensions")
        if completeness is ShadowBaselineCompleteness.PARTIAL and not missing:
            raise ValueError("partial baseline requires missing evidence dimensions")
        if completeness is ShadowBaselineCompleteness.PARTIAL and (
            ShadowCalibrationEligibilityReason.INCOMPLETE_BASELINE not in reasons
        ):
            raise ValueError("partial baseline requires INCOMPLETE_BASELINE reason")
        if eligibility is ShadowCalibrationEligibility.ELIGIBLE:
            if completeness is not ShadowBaselineCompleteness.COMPLETE or reasons:
                raise ValueError("eligible baseline must be complete with no reason codes")
        elif not reasons:
            raise ValueError("provisional or ineligible baseline requires reason codes")
        hindsight_reasons = {
            ShadowCalibrationEligibilityReason.KNOWN_HINDSIGHT_AT_REGISTRATION,
            ShadowCalibrationEligibilityReason.UNSUPPORTED_EVIDENCE_SCOPE,
        }
        if eligibility is ShadowCalibrationEligibility.INELIGIBLE and not (
            set(reasons) & hindsight_reasons
        ):
            raise ValueError("ineligible baseline requires a known disqualifying reason")
        if eligibility is ShadowCalibrationEligibility.PROVISIONAL and (
            set(reasons) & hindsight_reasons
        ):
            raise ValueError("known hindsight or unsupported scope is ineligible")
        if not isinstance(self.baseline_policy, ShadowVersionedPolicyReference):
            raise TypeError("baseline_policy must be ShadowVersionedPolicyReference")
        if self.baseline_policy != ShadowVersionedPolicyReference(
            SHADOW_BASELINE_POLICY_NAME, SHADOW_BASELINE_POLICY_VERSION
        ):
            raise ValueError("unsupported Shadow baseline policy")
        self._validate_source_manifest()
        if self.schema_version != SHADOW_BASELINE_SNAPSHOT_SCHEMA_VERSION:
            raise ValueError("unsupported Shadow baseline snapshot schema")
        object.__setattr__(
            self,
            "integrity_fingerprint",
            _integrity(
                shadow_baseline_snapshot_to_canonical_data(
                    self, include_integrity_fingerprint=False
                ),
                self.integrity_fingerprint,
                "integrity_fingerprint",
            ),
        )

    @property
    def baseline_snapshot_id(self) -> str:
        return self.registration.baseline_snapshot_id

    @property
    def shadow_validation_id(self) -> str:
        return self.registration.shadow_validation_id

    @property
    def knowledge_cutoff_at(self) -> datetime:
        return self.registration.knowledge_cutoff_at

    def _validate_source_manifest(self) -> None:
        by_role = {item.baseline_role: item for item in self.source_manifest.sources}
        expected = (
            (
                ShadowBaselineSourceRole.O2_SUBJECT_LINEAGE,
                ShadowBaselineSourceOwner.OPPORTUNITY,
                self.registration.o2_opportunity_id,
                self.registration.subject_lineage_fingerprint,
                None,
            ),
            (
                ShadowBaselineSourceRole.SCREENING_EVALUATION,
                ShadowBaselineSourceOwner.DISCOVERY,
                self.registration.screening_evaluation_id,
                self.registration.screening_evaluation_fingerprint,
                self.registration.screening_evaluated_at,
            ),
            (
                ShadowBaselineSourceRole.SCREENING_RANKING_PUBLICATION,
                ShadowBaselineSourceOwner.DISCOVERY,
                self.registration.screening_ranking_publication_id,
                self.registration.screening_ranking_publication_fingerprint,
                self.registration.ranking_created_at,
            ),
            (
                ShadowBaselineSourceRole.SCREENING_USED_INPUT_MANIFEST,
                ShadowBaselineSourceOwner.DISCOVERY,
                self.registration.screening_evaluation_id,
                None,
                self.registration.screening_evaluated_at,
            ),
        )
        for role, owner, source_id, source_fingerprint, generated_at in expected:
            source = by_role[role]
            if source.source_owner is not owner or source.source_id != source_id:
                raise ValueError("baseline required source identity differs from registration")
            if source_fingerprint is not None and source.source_fingerprint != source_fingerprint:
                raise ValueError("baseline required source fingerprint differs from registration")
            if role is ShadowBaselineSourceRole.SCREENING_USED_INPUT_MANIFEST and (
                source.semantic_projection_fingerprint
                != self.registration.screening_input_manifest_fingerprint
            ):
                raise ValueError("baseline screening input manifest differs from registration")
            if generated_at is not None and source.generated_at != generated_at:
                raise ValueError("baseline screening source time differs from registration")
        for source in self.source_manifest.sources:
            if any(value > self.knowledge_cutoff_at for value in source.authority_times):
                raise ValueError("future evidence cannot be included in Shadow baseline")
        unresolved_time = any(
            source.availability is ShadowBaselineAvailability.AVAILABLE
            and not source.authority_times
            for source in self.source_manifest.sources
        )
        reason = ShadowCalibrationEligibilityReason.SOURCE_AVAILABILITY_TIME_UNAVAILABLE
        if unresolved_time:
            if self.calibration_eligibility is ShadowCalibrationEligibility.ELIGIBLE:
                raise ValueError("eligible baseline requires source availability times")
            if reason not in self.calibration_reason_codes:
                raise ValueError("unresolved source time requires an eligibility reason")
        elif reason in self.calibration_reason_codes:
            raise ValueError("source availability-time reason has no matching source")


def shadow_baseline_snapshot_to_canonical_data(
    value: ShadowBaselineSnapshot,
    *,
    include_integrity_fingerprint: bool = True,
) -> dict[str, object]:
    if not isinstance(value, ShadowBaselineSnapshot):
        raise TypeError("value must be ShadowBaselineSnapshot")
    payload = {
        field.name: _canonical(getattr(value, field.name))
        for field in fields(value)
        if field.name != "integrity_fingerprint"
    }
    if include_integrity_fingerprint:
        payload["integrity_fingerprint"] = value.integrity_fingerprint
    return payload


def serialize_shadow_baseline_snapshot(value: ShadowBaselineSnapshot) -> str:
    return _canonical_json(shadow_baseline_snapshot_to_canonical_data(value))


__all__ = [
    "ShadowBaselineSnapshot",
    "ShadowBaselineSourceManifest",
    "ShadowBaselineSourceReference",
    "serialize_shadow_baseline_snapshot",
    "shadow_baseline_snapshot_to_canonical_data",
    "shadow_baseline_source_manifest_to_canonical_data",
]
