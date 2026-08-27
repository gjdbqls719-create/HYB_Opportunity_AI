"""Strict canonical serialization adapter for Shadow PR2 contracts."""

from __future__ import annotations

from datetime import datetime
import json

from app.domain.decision_engine import OpportunityIdentity
from app.domain.discovery import (
    NotRankedScreeningEntry,
    NotRankedScreeningReasonCode,
    RankedScreeningEntry,
)
from app.domain.opportunity import (
    NewToMarketDomesticSellingTargetIdentity,
    ShadowBaselineAvailability,
    ShadowBaselineCompleteness,
    ShadowBaselineEvidenceDimension,
    ShadowBaselineSnapshot,
    ShadowBaselineSourceManifest,
    ShadowBaselineSourceOwner,
    ShadowBaselineSourceReference,
    ShadowBaselineSourceRole,
    ShadowBaselineTruthScope,
    ShadowCalibrationEligibility,
    ShadowCalibrationEligibilityReason,
    ShadowEvidenceClass,
    ShadowO2SubjectLineage,
    ShadowRegistrationAuthorityKind,
    ShadowRegistrationReference,
    ShadowScreeningLineage,
    ShadowValidationRegistration,
    ShadowVersionedPolicyReference,
    serialize_shadow_baseline_snapshot,
    serialize_shadow_validation_registration,
)


def _exact(value: object, keys: set[str], name: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{name} fields are malformed")
    return value


def _tuple(value: object, name: str) -> tuple:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a JSON array")
    return tuple(value)


def _datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed


def _optional_datetime(value: object, name: str) -> datetime | None:
    return None if value is None else _datetime(value, name)


def _load_json(payload: str, name: str) -> dict[str, object]:
    if not isinstance(payload, str):
        raise TypeError(f"{name} must be text")
    try:
        def reject_number(_: str) -> object:
            raise ValueError("non-integer JSON number is forbidden")

        value = json.loads(
            payload,
            parse_float=reject_number,
            parse_constant=reject_number,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise ValueError(f"{name} is not valid canonical JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    return value


def _identity(value: object, name: str) -> OpportunityIdentity:
    data = _exact(value, {"opportunity_id", "discovery_reference"}, name)
    return OpportunityIdentity(data["opportunity_id"], data["discovery_reference"])


def _policy(value: object, name: str) -> ShadowVersionedPolicyReference:
    data = _exact(value, {"policy_name", "policy_version"}, name)
    return ShadowVersionedPolicyReference(data["policy_name"], data["policy_version"])


def _target(value: object) -> NewToMarketDomesticSellingTargetIdentity:
    data = _exact(
        value,
        {"domestic_selling_target_id", "market", "kind", "schema_version"},
        "Shadow O2 target identity",
    )
    return NewToMarketDomesticSellingTargetIdentity(
        domestic_selling_target_id=data["domestic_selling_target_id"],
        market=data["market"],
        kind=data["kind"],
        schema_version=data["schema_version"],
    )


def _subject(value: object) -> ShadowO2SubjectLineage:
    keys = {
        "o2_opportunity_identity", "o2_lifecycle_status", "o2_lifecycle_version",
        "target_identity", "target_binding_fingerprint", "o2_admission_id",
        "o2_admission_fingerprint", "o1_opportunity_identity", "candidate_id",
        "candidate_opportunity_binding_id", "candidate_opportunity_binding_fingerprint",
        "promotion_command_id", "promotion_admission_id", "discovery_command_id",
        "discovery_execution_id", "finalized_group_id", "o1_source_manifest_fingerprint",
        "target_bound_at", "o2_admitted_at", "schema_version", "integrity_fingerprint",
    }
    data = _exact(value, keys, "Shadow O2 subject lineage")
    return ShadowO2SubjectLineage(
        o2_opportunity_identity=_identity(data["o2_opportunity_identity"], "O2 identity"),
        o2_lifecycle_status=data["o2_lifecycle_status"],
        o2_lifecycle_version=data["o2_lifecycle_version"],
        target_identity=_target(data["target_identity"]),
        target_binding_fingerprint=data["target_binding_fingerprint"],
        o2_admission_id=data["o2_admission_id"],
        o2_admission_fingerprint=data["o2_admission_fingerprint"],
        o1_opportunity_identity=_identity(data["o1_opportunity_identity"], "O1 identity"),
        candidate_id=data["candidate_id"],
        candidate_opportunity_binding_id=data["candidate_opportunity_binding_id"],
        candidate_opportunity_binding_fingerprint=data["candidate_opportunity_binding_fingerprint"],
        promotion_command_id=data["promotion_command_id"],
        promotion_admission_id=data["promotion_admission_id"],
        discovery_command_id=data["discovery_command_id"],
        discovery_execution_id=data["discovery_execution_id"],
        finalized_group_id=data["finalized_group_id"],
        o1_source_manifest_fingerprint=data["o1_source_manifest_fingerprint"],
        target_bound_at=_datetime(data["target_bound_at"], "target_bound_at"),
        o2_admitted_at=_datetime(data["o2_admitted_at"], "o2_admitted_at"),
        schema_version=data["schema_version"],
        integrity_fingerprint=data["integrity_fingerprint"],
    )


def _ranking_entry(value: object):
    if not isinstance(value, dict):
        raise ValueError("screening ranking entry must be an object")
    common = {
        "discovery_execution_id", "finalized_group_id",
        "screening_evaluation_id", "evaluation_fingerprint",
    }
    if "rank" in value:
        data = _exact(value, common | {"rank"}, "ranked screening entry")
        return RankedScreeningEntry(
            rank=data["rank"],
            discovery_execution_id=data["discovery_execution_id"],
            finalized_group_id=data["finalized_group_id"],
            screening_evaluation_id=data["screening_evaluation_id"],
            evaluation_fingerprint=data["evaluation_fingerprint"],
        )
    data = _exact(
        value,
        common | {"reason_code", "unavailable_semantic_roles"},
        "not-ranked screening entry",
    )
    return NotRankedScreeningEntry(
        discovery_execution_id=data["discovery_execution_id"],
        finalized_group_id=data["finalized_group_id"],
        screening_evaluation_id=data["screening_evaluation_id"],
        evaluation_fingerprint=data["evaluation_fingerprint"],
        reason_code=NotRankedScreeningReasonCode(data["reason_code"]),
        unavailable_semantic_roles=_tuple(
            data["unavailable_semantic_roles"], "unavailable_semantic_roles"
        ),
    )


def _screening(value: object) -> ShadowScreeningLineage:
    keys = {
        "screening_evaluation_id", "screening_evaluation_fingerprint",
        "screening_ranking_publication_id", "screening_ranking_publication_fingerprint",
        "ranking_entry", "command_id", "discovery_execution_id", "finalized_group_id",
        "group_membership_fingerprint", "screening_policy_manifest_fingerprint",
        "screening_input_manifest_fingerprint", "evaluated_at", "ranking_created_at",
        "evaluation_schema_version", "ranking_schema_version", "schema_version",
        "integrity_fingerprint",
    }
    data = _exact(value, keys, "Shadow screening lineage")
    return ShadowScreeningLineage(
        screening_evaluation_id=data["screening_evaluation_id"],
        screening_evaluation_fingerprint=data["screening_evaluation_fingerprint"],
        screening_ranking_publication_id=data["screening_ranking_publication_id"],
        screening_ranking_publication_fingerprint=data["screening_ranking_publication_fingerprint"],
        ranking_entry=_ranking_entry(data["ranking_entry"]),
        command_id=data["command_id"],
        discovery_execution_id=data["discovery_execution_id"],
        finalized_group_id=data["finalized_group_id"],
        group_membership_fingerprint=data["group_membership_fingerprint"],
        screening_policy_manifest_fingerprint=data["screening_policy_manifest_fingerprint"],
        screening_input_manifest_fingerprint=data["screening_input_manifest_fingerprint"],
        evaluated_at=_datetime(data["evaluated_at"], "evaluated_at"),
        ranking_created_at=_datetime(data["ranking_created_at"], "ranking_created_at"),
        evaluation_schema_version=data["evaluation_schema_version"],
        ranking_schema_version=data["ranking_schema_version"],
        schema_version=data["schema_version"],
        integrity_fingerprint=data["integrity_fingerprint"],
    )


def deserialize_shadow_validation_registration(
    payload: str,
) -> ShadowValidationRegistration:
    keys = {
        "shadow_validation_id", "baseline_snapshot_id", "authority_kind", "subject",
        "screening_lineage", "operator_id", "registration_reason", "registered_at",
        "knowledge_cutoff_at", "cadence_policy", "registration_policy",
        "evidence_class", "schema_version", "integrity_fingerprint",
    }
    data = _exact(_load_json(payload, "Shadow registration payload"), keys, "Shadow registration payload")
    value = ShadowValidationRegistration(
        shadow_validation_id=data["shadow_validation_id"],
        baseline_snapshot_id=data["baseline_snapshot_id"],
        authority_kind=ShadowRegistrationAuthorityKind(data["authority_kind"]),
        subject=_subject(data["subject"]),
        screening_lineage=_screening(data["screening_lineage"]),
        operator_id=data["operator_id"],
        registration_reason=data["registration_reason"],
        registered_at=_datetime(data["registered_at"], "registered_at"),
        knowledge_cutoff_at=_datetime(data["knowledge_cutoff_at"], "knowledge_cutoff_at"),
        cadence_policy=_policy(data["cadence_policy"], "cadence policy"),
        registration_policy=_policy(data["registration_policy"], "registration policy"),
        evidence_class=ShadowEvidenceClass(data["evidence_class"]),
        schema_version=data["schema_version"],
        integrity_fingerprint=data["integrity_fingerprint"],
    )
    if serialize_shadow_validation_registration(value) != payload:
        raise ValueError("Shadow registration payload is not canonical")
    return value


def _registration_reference(value: object) -> ShadowRegistrationReference:
    keys = {
        "shadow_validation_id", "baseline_snapshot_id", "registration_fingerprint",
        "o2_opportunity_id", "domestic_selling_target_id", "subject_lineage_fingerprint",
        "screening_evaluation_id", "screening_evaluation_fingerprint",
        "screening_ranking_publication_id", "screening_ranking_publication_fingerprint",
        "screening_input_manifest_fingerprint", "screening_lineage_fingerprint",
        "discovery_execution_id", "finalized_group_id", "screening_evaluated_at",
        "ranking_created_at", "registered_at", "knowledge_cutoff_at", "evidence_class",
        "schema_version",
    }
    data = _exact(value, keys, "Shadow registration reference")
    return ShadowRegistrationReference(
        shadow_validation_id=data["shadow_validation_id"],
        baseline_snapshot_id=data["baseline_snapshot_id"],
        registration_fingerprint=data["registration_fingerprint"],
        o2_opportunity_id=data["o2_opportunity_id"],
        domestic_selling_target_id=data["domestic_selling_target_id"],
        subject_lineage_fingerprint=data["subject_lineage_fingerprint"],
        screening_evaluation_id=data["screening_evaluation_id"],
        screening_evaluation_fingerprint=data["screening_evaluation_fingerprint"],
        screening_ranking_publication_id=data["screening_ranking_publication_id"],
        screening_ranking_publication_fingerprint=data["screening_ranking_publication_fingerprint"],
        screening_input_manifest_fingerprint=data["screening_input_manifest_fingerprint"],
        screening_lineage_fingerprint=data["screening_lineage_fingerprint"],
        discovery_execution_id=data["discovery_execution_id"],
        finalized_group_id=data["finalized_group_id"],
        screening_evaluated_at=_datetime(data["screening_evaluated_at"], "screening_evaluated_at"),
        ranking_created_at=_datetime(data["ranking_created_at"], "ranking_created_at"),
        registered_at=_datetime(data["registered_at"], "registered_at"),
        knowledge_cutoff_at=_datetime(data["knowledge_cutoff_at"], "knowledge_cutoff_at"),
        evidence_class=ShadowEvidenceClass(data["evidence_class"]),
        schema_version=data["schema_version"],
    )


def _source(value: object) -> ShadowBaselineSourceReference:
    keys = {
        "reference_id", "source_owner", "source_kind", "source_id", "baseline_role",
        "availability", "truth_scope", "source_revision", "source_schema_version",
        "source_policy_name", "source_policy_version", "source_fingerprint",
        "semantic_projection", "semantic_projection_fingerprint", "observed_at",
        "observation_window_start", "observation_window_end", "generated_at",
        "committed_at", "availability_reason", "schema_version",
    }
    data = _exact(value, keys, "Shadow baseline source")
    return ShadowBaselineSourceReference(
        reference_id=data["reference_id"],
        source_owner=ShadowBaselineSourceOwner(data["source_owner"]),
        source_kind=data["source_kind"],
        source_id=data["source_id"],
        baseline_role=ShadowBaselineSourceRole(data["baseline_role"]),
        availability=ShadowBaselineAvailability(data["availability"]),
        truth_scope=ShadowBaselineTruthScope(data["truth_scope"]),
        source_revision=data["source_revision"],
        source_schema_version=data["source_schema_version"],
        source_policy_name=data["source_policy_name"],
        source_policy_version=data["source_policy_version"],
        source_fingerprint=data["source_fingerprint"],
        semantic_projection=data["semantic_projection"],
        semantic_projection_fingerprint=data["semantic_projection_fingerprint"],
        observed_at=_optional_datetime(data["observed_at"], "observed_at"),
        observation_window_start=_optional_datetime(data["observation_window_start"], "observation_window_start"),
        observation_window_end=_optional_datetime(data["observation_window_end"], "observation_window_end"),
        generated_at=_optional_datetime(data["generated_at"], "generated_at"),
        committed_at=_optional_datetime(data["committed_at"], "committed_at"),
        availability_reason=data["availability_reason"],
        schema_version=data["schema_version"],
    )


def _manifest(value: object) -> ShadowBaselineSourceManifest:
    data = _exact(
        value,
        {"sources", "schema_version", "integrity_fingerprint"},
        "Shadow baseline source manifest",
    )
    return ShadowBaselineSourceManifest(
        sources=tuple(_source(item) for item in _tuple(data["sources"], "sources")),
        schema_version=data["schema_version"],
        integrity_fingerprint=data["integrity_fingerprint"],
    )


def deserialize_shadow_baseline_snapshot(payload: str) -> ShadowBaselineSnapshot:
    keys = {
        "registration", "source_manifest", "baseline_created_at", "completeness",
        "missing_evidence_dimensions", "calibration_eligibility",
        "calibration_reason_codes", "baseline_policy", "evidence_class",
        "schema_version", "integrity_fingerprint",
    }
    data = _exact(_load_json(payload, "Shadow baseline payload"), keys, "Shadow baseline payload")
    value = ShadowBaselineSnapshot(
        registration=_registration_reference(data["registration"]),
        source_manifest=_manifest(data["source_manifest"]),
        baseline_created_at=_datetime(data["baseline_created_at"], "baseline_created_at"),
        completeness=ShadowBaselineCompleteness(data["completeness"]),
        missing_evidence_dimensions=tuple(
            ShadowBaselineEvidenceDimension(item)
            for item in _tuple(data["missing_evidence_dimensions"], "missing_evidence_dimensions")
        ),
        calibration_eligibility=ShadowCalibrationEligibility(data["calibration_eligibility"]),
        calibration_reason_codes=tuple(
            ShadowCalibrationEligibilityReason(item)
            for item in _tuple(data["calibration_reason_codes"], "calibration_reason_codes")
        ),
        baseline_policy=_policy(data["baseline_policy"], "baseline policy"),
        evidence_class=ShadowEvidenceClass(data["evidence_class"]),
        schema_version=data["schema_version"],
        integrity_fingerprint=data["integrity_fingerprint"],
    )
    if serialize_shadow_baseline_snapshot(value) != payload:
        raise ValueError("Shadow baseline payload is not canonical")
    return value


__all__ = [
    "deserialize_shadow_baseline_snapshot",
    "deserialize_shadow_validation_registration",
]
