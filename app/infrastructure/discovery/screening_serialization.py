"""Strict readers for the canonical Discovery screening payloads from PR4."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import json

from app.application.discovery.screening_persistence import (
    DiscoveryScreeningCompletionBinding,
)
from app.domain.discovery import (
    DiscoveryScreeningEvaluationSnapshot,
    DiscoveryScreeningRankingPublication,
    DiscoveryScreeningRecordingState,
    NotRankedScreeningEntry,
    NotRankedScreeningReasonCode,
    ProductionSafetyPolicyDescriptor,
    RankedScreeningEntry,
    RecommendationPolicyDescriptor,
    ScreeningEvidenceValue,
    ScreeningInputManifest,
    ScreeningInputReference,
    ScreeningPolicyDescriptors,
    ScreeningPolicyReference,
    ScreeningProvenanceKind,
    ScreeningRankingPolicyDescriptor,
    ScreeningReasonCategory,
    ScreeningReasonPolarity,
    ScreeningRecommendationSemantics,
    ScreeningRecommendationValue,
    ScreeningScorePolicyDescriptor,
    ScreeningSourceKind,
    ScreeningSourceReference,
    ScreeningTruthScope,
    StructuredScreeningReason,
)


def _object(
    value: object,
    keys: set[str],
    name: str,
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{name} has unsupported fields")
    return value


def _list(value: object, name: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed


def _optional_datetime(value: object, name: str) -> datetime | None:
    return None if value is None else _datetime(value, name)


def _string_tuple(value: object, name: str) -> tuple[str, ...]:
    values = _list(value, name)
    if any(not isinstance(item, str) for item in values):
        raise ValueError(f"{name} must contain text")
    return tuple(values)


def _scalar(value: object) -> Decimal | int | bool | str | None:
    if value is None:
        return None
    data = _object(value, {"kind", "value"}, "screening scalar")
    kind = data["kind"]
    raw = data["value"]
    if kind == "boolean":
        if not isinstance(raw, bool):
            raise ValueError("boolean screening scalar is malformed")
        return raw
    if kind == "integer":
        if not isinstance(raw, str):
            raise ValueError("integer screening scalar is malformed")
        parsed = int(raw)
        if str(parsed) != raw:
            raise ValueError("integer screening scalar is not canonical")
        return parsed
    if kind == "decimal":
        if not isinstance(raw, str):
            raise ValueError("decimal screening scalar is malformed")
        return Decimal(raw)
    if kind == "text":
        if not isinstance(raw, str):
            raise ValueError("text screening scalar is malformed")
        return raw
    raise ValueError("screening scalar kind is unsupported")


def _policy_reference(value: object) -> ScreeningPolicyReference:
    data = _object(
        value,
        {"policy_name", "policy_version", "algorithm_id"},
        "screening policy reference",
    )
    return ScreeningPolicyReference(
        policy_name=data["policy_name"],
        policy_version=data["policy_version"],
        algorithm_id=data["algorithm_id"],
    )


def _source_reference(value: object) -> ScreeningSourceReference:
    data = _object(
        value,
        {
            "reference_id",
            "source_kind",
            "source_identity",
            "source_fingerprint",
            "source_revision",
            "observed_at",
            "effective_at",
        },
        "screening source reference",
    )
    return ScreeningSourceReference(
        reference_id=data["reference_id"],
        source_kind=ScreeningSourceKind(data["source_kind"]),
        source_identity=data["source_identity"],
        source_fingerprint=data["source_fingerprint"],
        source_revision=data["source_revision"],
        observed_at=_optional_datetime(data["observed_at"], "observed_at"),
        effective_at=_optional_datetime(data["effective_at"], "effective_at"),
    )


def _evidence(value: object) -> ScreeningEvidenceValue:
    data = _object(
        value,
        {
            "semantic_role",
            "provenance_kind",
            "truth_scope",
            "value",
            "unit",
            "currency",
            "source_references",
            "dependency_references",
            "method_reference",
            "schema_version",
        },
        "screening evidence",
    )
    sources = _list(data["source_references"], "source_references")
    method = data["method_reference"]
    return ScreeningEvidenceValue(
        semantic_role=data["semantic_role"],
        provenance_kind=ScreeningProvenanceKind(data["provenance_kind"]),
        truth_scope=ScreeningTruthScope(data["truth_scope"]),
        value=_scalar(data["value"]),
        unit=data["unit"],
        currency=data["currency"],
        source_references=tuple(_source_reference(item) for item in sources),
        dependency_references=_string_tuple(
            data["dependency_references"],
            "dependency_references",
        ),
        method_reference=None if method is None else _policy_reference(method),
        schema_version=data["schema_version"],
    )


def _input_manifest(value: object) -> ScreeningInputManifest:
    data = _object(
        value,
        {"inputs", "used_input_reference_ids", "schema_version"},
        "screening input manifest",
    )
    inputs = []
    for value in _list(data["inputs"], "inputs"):
        item = _object(
            value,
            {"input_reference_id", "dependency_role", "evidence"},
            "screening input reference",
        )
        inputs.append(
            ScreeningInputReference(
                input_reference_id=item["input_reference_id"],
                dependency_role=item["dependency_role"],
                evidence=_evidence(item["evidence"]),
            )
        )
    return ScreeningInputManifest(
        inputs=tuple(inputs),
        used_input_reference_ids=_string_tuple(
            data["used_input_reference_ids"],
            "used_input_reference_ids",
        ),
        schema_version=data["schema_version"],
    )


def _score_policy(value: object) -> ScreeningScorePolicyDescriptor:
    data = _object(
        value,
        {
            "policy_name",
            "policy_version",
            "algorithm_id",
            "description",
            "ordered_rule_ids",
            "policy_assumption_inputs",
        },
        "screening score policy",
    )
    return ScreeningScorePolicyDescriptor(
        data["policy_name"],
        data["policy_version"],
        data["algorithm_id"],
        data["description"],
        _string_tuple(data["ordered_rule_ids"], "ordered_rule_ids"),
        _string_tuple(
            data["policy_assumption_inputs"],
            "policy_assumption_inputs",
        ),
    )


def _recommendation_policy(value: object) -> RecommendationPolicyDescriptor:
    data = _object(
        value,
        {
            "policy_name",
            "policy_version",
            "algorithm_id",
            "description",
            "ordered_rule_ids",
            "reason_code_namespace",
        },
        "recommendation policy",
    )
    return RecommendationPolicyDescriptor(
        data["policy_name"],
        data["policy_version"],
        data["algorithm_id"],
        data["description"],
        _string_tuple(data["ordered_rule_ids"], "ordered_rule_ids"),
        data["reason_code_namespace"],
    )


def _safety_policy(value: object) -> ProductionSafetyPolicyDescriptor:
    data = _object(
        value,
        {
            "policy_name",
            "policy_version",
            "algorithm_id",
            "description",
            "ordered_rule_ids",
        },
        "production Safety policy",
    )
    return ProductionSafetyPolicyDescriptor(
        data["policy_name"],
        data["policy_version"],
        data["algorithm_id"],
        data["description"],
        _string_tuple(data["ordered_rule_ids"], "ordered_rule_ids"),
    )


def _ranking_policy(value: object) -> ScreeningRankingPolicyDescriptor:
    data = _object(
        value,
        {
            "policy_name",
            "policy_version",
            "algorithm_id",
            "description",
            "ordered_sort_keys",
            "equal_key_tie_behavior",
        },
        "screening ranking policy",
    )
    return ScreeningRankingPolicyDescriptor(
        data["policy_name"],
        data["policy_version"],
        data["algorithm_id"],
        data["description"],
        _string_tuple(data["ordered_sort_keys"], "ordered_sort_keys"),
        data["equal_key_tie_behavior"],
    )


def _policy_manifest(value: object) -> ScreeningPolicyDescriptors:
    data = _object(
        value,
        {"score", "recommendation", "production_safety", "ranking"},
        "screening policy manifest",
    )
    return ScreeningPolicyDescriptors(
        _score_policy(data["score"]),
        _recommendation_policy(data["recommendation"]),
        _safety_policy(data["production_safety"]),
        _ranking_policy(data["ranking"]),
    )


def _recommendation_value(value: object) -> ScreeningRecommendationValue:
    data = _object(
        value,
        {"grade", "action", "summary"},
        "screening recommendation value",
    )
    return ScreeningRecommendationValue(
        data["grade"],
        data["action"],
        data["summary"],
    )


def _reason(value: object) -> StructuredScreeningReason:
    data = _object(
        value,
        {"reason_code", "category", "polarity", "source_component", "message"},
        "structured screening reason",
    )
    return StructuredScreeningReason(
        data["reason_code"],
        ScreeningReasonCategory(data["category"]),
        ScreeningReasonPolarity(data["polarity"]),
        data["source_component"],
        data["message"],
    )


def _recommendation(value: object) -> ScreeningRecommendationSemantics:
    data = _object(
        value,
        {
            "raw_recommendation",
            "effective_recommendation",
            "recommendation_score",
            "safety_intervention_occurred",
            "safety_status",
            "structured_reasons",
            "safety_reasons",
            "safety_policy",
        },
        "screening recommendation",
    )
    return ScreeningRecommendationSemantics(
        raw_recommendation=_recommendation_value(data["raw_recommendation"]),
        effective_recommendation=_recommendation_value(
            data["effective_recommendation"]
        ),
        recommendation_score=data["recommendation_score"],
        safety_intervention_occurred=data["safety_intervention_occurred"],
        safety_status=data["safety_status"],
        structured_reasons=tuple(
            _reason(item)
            for item in _list(data["structured_reasons"], "structured_reasons")
        ),
        safety_reasons=tuple(
            _reason(item)
            for item in _list(data["safety_reasons"], "safety_reasons")
        ),
        safety_policy=_safety_policy(data["safety_policy"]),
    )


def deserialize_discovery_screening_evaluation(
    payload_json: str,
) -> DiscoveryScreeningEvaluationSnapshot:
    data = _object(
        json.loads(payload_json),
        {
            "screening_evaluation_id",
            "command_id",
            "discovery_execution_id",
            "finalized_group_id",
            "group_membership_fingerprint",
            "screening_recommendation",
            "final_opportunity_score",
            "ranking_economics_key",
            "expected_economics",
            "screening_policy_manifest",
            "input_manifest",
            "evaluated_at",
            "schema_version",
            "integrity_fingerprint",
        },
        "screening evaluation payload",
    )
    return DiscoveryScreeningEvaluationSnapshot(
        screening_evaluation_id=data["screening_evaluation_id"],
        command_id=data["command_id"],
        discovery_execution_id=data["discovery_execution_id"],
        finalized_group_id=data["finalized_group_id"],
        group_membership_fingerprint=data["group_membership_fingerprint"],
        screening_recommendation=_recommendation(
            data["screening_recommendation"]
        ),
        final_opportunity_score=_evidence(data["final_opportunity_score"]),
        ranking_economics_key=_evidence(data["ranking_economics_key"]),
        expected_economics=tuple(
            _evidence(item)
            for item in _list(data["expected_economics"], "expected_economics")
        ),
        screening_policy_manifest=_policy_manifest(
            data["screening_policy_manifest"]
        ),
        input_manifest=_input_manifest(data["input_manifest"]),
        evaluated_at=_datetime(data["evaluated_at"], "evaluated_at"),
        schema_version=data["schema_version"],
        integrity_fingerprint=data["integrity_fingerprint"],
    )


def _ranked_entry(value: object) -> RankedScreeningEntry:
    data = _object(
        value,
        {
            "rank",
            "discovery_execution_id",
            "finalized_group_id",
            "screening_evaluation_id",
            "evaluation_fingerprint",
        },
        "ranked screening entry",
    )
    return RankedScreeningEntry(
        data["rank"],
        data["discovery_execution_id"],
        data["finalized_group_id"],
        data["screening_evaluation_id"],
        data["evaluation_fingerprint"],
    )


def _not_ranked_entry(value: object) -> NotRankedScreeningEntry:
    data = _object(
        value,
        {
            "discovery_execution_id",
            "finalized_group_id",
            "screening_evaluation_id",
            "evaluation_fingerprint",
            "reason_code",
            "unavailable_semantic_roles",
        },
        "not-ranked screening entry",
    )
    return NotRankedScreeningEntry(
        data["discovery_execution_id"],
        data["finalized_group_id"],
        data["screening_evaluation_id"],
        data["evaluation_fingerprint"],
        NotRankedScreeningReasonCode(data["reason_code"]),
        _string_tuple(
            data["unavailable_semantic_roles"],
            "unavailable_semantic_roles",
        ),
    )


def deserialize_discovery_screening_ranking_publication(
    payload_json: str,
) -> DiscoveryScreeningRankingPublication:
    data = _object(
        json.loads(payload_json),
        {
            "screening_ranking_publication_id",
            "command_id",
            "discovery_execution_id",
            "ranked_entries",
            "not_ranked_entries",
            "ranking_policy",
            "ranking_created_at",
            "zero_result",
            "schema_version",
            "integrity_fingerprint",
        },
        "screening ranking publication payload",
    )
    return DiscoveryScreeningRankingPublication(
        screening_ranking_publication_id=data[
            "screening_ranking_publication_id"
        ],
        command_id=data["command_id"],
        discovery_execution_id=data["discovery_execution_id"],
        ranked_entries=tuple(
            _ranked_entry(item)
            for item in _list(data["ranked_entries"], "ranked_entries")
        ),
        not_ranked_entries=tuple(
            _not_ranked_entry(item)
            for item in _list(
                data["not_ranked_entries"],
                "not_ranked_entries",
            )
        ),
        ranking_policy=_ranking_policy(data["ranking_policy"]),
        ranking_created_at=_datetime(
            data["ranking_created_at"],
            "ranking_created_at",
        ),
        zero_result=data["zero_result"],
        schema_version=data["schema_version"],
        integrity_fingerprint=data["integrity_fingerprint"],
    )


def deserialize_discovery_screening_completion_binding(
    payload_json: str,
) -> DiscoveryScreeningCompletionBinding:
    data = _object(
        json.loads(payload_json),
        {
            "command_id",
            "discovery_execution_id",
            "result_schema_version",
            "result_fingerprint",
            "screening_ranking_publication_id",
            "ranking_publication_fingerprint",
            "screening_recording_state",
            "schema_version",
            "integrity_fingerprint",
        },
        "screening completion binding payload",
    )
    return DiscoveryScreeningCompletionBinding(
        command_id=data["command_id"],
        discovery_execution_id=data["discovery_execution_id"],
        result_schema_version=data["result_schema_version"],
        result_fingerprint=data["result_fingerprint"],
        screening_ranking_publication_id=data[
            "screening_ranking_publication_id"
        ],
        ranking_publication_fingerprint=data[
            "ranking_publication_fingerprint"
        ],
        screening_recording_state=DiscoveryScreeningRecordingState(
            data["screening_recording_state"]
        ),
        schema_version=data["schema_version"],
        integrity_fingerprint=data["integrity_fingerprint"],
    )


__all__ = [
    "deserialize_discovery_screening_completion_binding",
    "deserialize_discovery_screening_evaluation",
    "deserialize_discovery_screening_ranking_publication",
]
