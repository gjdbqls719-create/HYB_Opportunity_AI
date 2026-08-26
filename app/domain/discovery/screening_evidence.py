"""Immutable evidence and ranking contracts for Discovery screening."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
import hashlib
import json
import re

from app.domain.discovery.screening import (
    ProductionSafetyPolicyDescriptor,
    RecommendationPolicyDescriptor,
    ScreeningPolicyDescriptors,
    ScreeningRankingPolicyDescriptor,
    ScreeningRecommendationSemantics,
    ScreeningRecommendationValue,
    ScreeningScorePolicyDescriptor,
    StructuredScreeningReason,
)


DISCOVERY_SCREENING_EVALUATION_SCHEMA_VERSION = (
    "discovery-screening-evaluation-v1"
)
DISCOVERY_SCREENING_RANKING_PUBLICATION_SCHEMA_VERSION = (
    "discovery-screening-ranking-publication-v1"
)
DISCOVERY_SCREENING_INPUT_MANIFEST_SCHEMA_VERSION = (
    "discovery-screening-input-manifest-v1"
)
DISCOVERY_SCREENING_PROVENANCE_SCHEMA_VERSION = (
    "discovery-screening-provenance-v1"
)

_SEMANTIC_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_STABLE_TOKEN = re.compile(r"^[a-z0-9]+(?:[._:-][a-z0-9]+)*$")


class ScreeningProvenanceKind(StrEnum):
    """Discovery-screening evidence meaning; separate from other Domains."""

    OBSERVED = "OBSERVED"
    CALCULATED = "CALCULATED"
    ESTIMATED = "ESTIMATED"
    POLICY_ASSUMPTION = "POLICY_ASSUMPTION"
    UNKNOWN = "UNKNOWN"
    UNSUPPORTED = "UNSUPPORTED"


class ScreeningTruthScope(StrEnum):
    """Small v1 vocabulary for the scope in which a screening fact is true."""

    SOURCE_LISTING = "SOURCE_LISTING"
    FINALIZED_GROUP = "FINALIZED_GROUP"
    KOREA_ONLY = "KOREA_ONLY"
    MIXED_GEOGRAPHY = "MIXED_GEOGRAPHY"
    POLICY_DEFINED = "POLICY_DEFINED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class ScreeningSourceKind(StrEnum):
    """Source families currently available to production Discovery screening."""

    DISCOVERY_COMMAND = "DISCOVERY_COMMAND"
    COLLECTED_PRODUCT_OBSERVATION = "COLLECTED_PRODUCT_OBSERVATION"
    FINALIZED_PRODUCT_GROUP = "FINALIZED_PRODUCT_GROUP"
    PRICE_HISTORY = "PRICE_HISTORY"
    SCREENING_POLICY = "SCREENING_POLICY"
    RUNTIME_DERIVATION = "RUNTIME_DERIVATION"


class NotRankedScreeningReasonCode(StrEnum):
    """Stable reasons that prevent fabrication of a ranking key."""

    UNKNOWN_RANKING_KEY = "UNKNOWN_RANKING_KEY"
    UNSUPPORTED_RANKING_KEY = "UNSUPPORTED_RANKING_KEY"


class DiscoveryScreeningRecordingState(StrEnum):
    """Explicit legacy state for future v1/v2 completion reads."""

    RECORDED = "RECORDED"
    SCREENING_NOT_RECORDED_LEGACY = "SCREENING_NOT_RECORDED_LEGACY"


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    if not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    if value != value.strip():
        raise ValueError(f"{name} must not contain surrounding whitespace")
    return value


def _stable_token(value: str, name: str) -> str:
    resolved = _required_text(value, name)
    if _STABLE_TOKEN.fullmatch(resolved) is None:
        raise ValueError(f"{name} must use a stable lowercase token")
    return resolved


def _semantic_version(value: str, name: str) -> str:
    resolved = _required_text(value, name)
    if _SEMANTIC_VERSION.fullmatch(resolved) is None:
        raise ValueError(f"{name} must use MAJOR.MINOR.PATCH")
    return resolved


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _optional_aware(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    return _aware(value, name)


def _fingerprint_text(value: str, name: str) -> str:
    resolved = _required_text(value, name)
    if _SHA256.fullmatch(resolved) is None:
        raise ValueError(f"{name} must be lowercase SHA-256 text")
    return resolved


def _optional_text(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    return _required_text(value, name)


def _canonical_decimal(value: Decimal) -> str:
    if not isinstance(value, Decimal):
        raise TypeError("canonical Decimal value must be Decimal")
    if not value.is_finite():
        raise ValueError("canonical Decimal value must be finite")
    if value == 0:
        return "0"
    normalized = format(value.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") if "." in normalized else normalized


def _canonical_datetime(value: datetime) -> str:
    return (
        _aware(value, "canonical datetime")
        .astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _canonical_scalar(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return {"kind": "boolean", "value": value}
    if isinstance(value, int):
        return {"kind": "integer", "value": str(value)}
    if isinstance(value, Decimal):
        return {"kind": "decimal", "value": _canonical_decimal(value)}
    if isinstance(value, str):
        return {"kind": "text", "value": value}
    raise TypeError("screening evidence value must be Decimal, int, bool, text, or None")


def _canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _canonical_string_tuple(
    values: tuple[str, ...],
    name: str,
    *,
    non_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{name} must be a tuple")
    normalized = tuple(_required_text(value, name) for value in values)
    if non_empty and not normalized:
        raise ValueError(f"{name} must not be empty")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{name} must be unique")
    if normalized != tuple(sorted(normalized)):
        raise ValueError(f"{name} must use canonical ordering")
    return normalized


@dataclass(frozen=True, slots=True)
class ScreeningPolicyReference:
    """Exact method or assumption policy referenced by provenance."""

    policy_name: str
    policy_version: str
    algorithm_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "policy_name", _required_text(self.policy_name, "policy_name")
        )
        object.__setattr__(
            self,
            "policy_version",
            _semantic_version(self.policy_version, "policy_version"),
        )
        object.__setattr__(
            self, "algorithm_id", _required_text(self.algorithm_id, "algorithm_id")
        )


@dataclass(frozen=True, slots=True)
class ScreeningSourceReference:
    """Immutable lineage reference without copying a provider payload."""

    reference_id: str
    source_kind: ScreeningSourceKind
    source_identity: str
    source_fingerprint: str | None = None
    source_revision: str | None = None
    observed_at: datetime | None = None
    effective_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "reference_id", _stable_token(self.reference_id, "reference_id")
        )
        if not isinstance(self.source_kind, ScreeningSourceKind):
            raise TypeError("source_kind must be ScreeningSourceKind")
        object.__setattr__(
            self,
            "source_identity",
            _required_text(self.source_identity, "source_identity"),
        )
        if self.source_fingerprint is not None:
            object.__setattr__(
                self,
                "source_fingerprint",
                _fingerprint_text(self.source_fingerprint, "source_fingerprint"),
            )
        object.__setattr__(
            self,
            "source_revision",
            _optional_text(self.source_revision, "source_revision"),
        )
        object.__setattr__(
            self, "observed_at", _optional_aware(self.observed_at, "observed_at")
        )
        object.__setattr__(
            self, "effective_at", _optional_aware(self.effective_at, "effective_at")
        )


@dataclass(frozen=True, slots=True)
class ScreeningEvidenceValue:
    """One typed scalar together with truthful Discovery-screening provenance."""

    semantic_role: str
    provenance_kind: ScreeningProvenanceKind
    truth_scope: ScreeningTruthScope
    value: Decimal | int | bool | str | None
    unit: str | None = None
    currency: str | None = None
    source_references: tuple[ScreeningSourceReference, ...] = ()
    dependency_references: tuple[str, ...] = ()
    method_reference: ScreeningPolicyReference | None = None
    schema_version: str = DISCOVERY_SCREENING_PROVENANCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "semantic_role", _stable_token(self.semantic_role, "semantic_role")
        )
        if not isinstance(self.provenance_kind, ScreeningProvenanceKind):
            raise TypeError("provenance_kind must be ScreeningProvenanceKind")
        if not isinstance(self.truth_scope, ScreeningTruthScope):
            raise TypeError("truth_scope must be ScreeningTruthScope")
        _canonical_scalar(self.value)
        if isinstance(self.value, Decimal) and not self.value.is_finite():
            raise ValueError("screening Decimal value must be finite")
        object.__setattr__(self, "unit", _optional_text(self.unit, "unit"))
        currency = _optional_text(self.currency, "currency")
        if currency is not None:
            currency = currency.upper()
            if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
                raise ValueError("currency must be a three-letter code")
        object.__setattr__(self, "currency", currency)
        if self.value is not None and (self.unit is not None or currency is not None) and (
            isinstance(self.value, bool)
            or not isinstance(self.value, (Decimal, int))
        ):
            raise ValueError("unit and currency require a numeric evidence value")

        if not isinstance(self.source_references, tuple):
            raise TypeError("source_references must be a tuple")
        if any(
            not isinstance(value, ScreeningSourceReference)
            for value in self.source_references
        ):
            raise TypeError("source_references must contain ScreeningSourceReference")
        reference_ids = tuple(value.reference_id for value in self.source_references)
        if len(set(reference_ids)) != len(reference_ids):
            raise ValueError("source_references must have unique reference IDs")
        if reference_ids != tuple(sorted(reference_ids)):
            raise ValueError("source_references must use canonical ordering")
        object.__setattr__(
            self,
            "dependency_references",
            _canonical_string_tuple(
                self.dependency_references, "dependency_references"
            ),
        )
        if self.method_reference is not None and not isinstance(
            self.method_reference, ScreeningPolicyReference
        ):
            raise TypeError("method_reference must be ScreeningPolicyReference")

        if self.provenance_kind in {
            ScreeningProvenanceKind.UNKNOWN,
            ScreeningProvenanceKind.UNSUPPORTED,
        } and self.value is not None:
            raise ValueError("UNKNOWN and UNSUPPORTED evidence cannot carry a value")
        if self.provenance_kind not in {
            ScreeningProvenanceKind.UNKNOWN,
            ScreeningProvenanceKind.UNSUPPORTED,
        } and self.value is None:
            raise ValueError("known screening evidence must carry an exact value")
        if self.provenance_kind is ScreeningProvenanceKind.OBSERVED:
            if not self.source_references:
                raise ValueError("OBSERVED evidence requires source lineage")
            if not any(value.observed_at is not None for value in self.source_references):
                raise ValueError("OBSERVED evidence requires an observation time")
        if (
            self.provenance_kind is ScreeningProvenanceKind.CALCULATED
            and not self.dependency_references
        ):
            raise ValueError("CALCULATED evidence requires dependency lineage")
        if self.provenance_kind in {
            ScreeningProvenanceKind.ESTIMATED,
            ScreeningProvenanceKind.POLICY_ASSUMPTION,
        } and self.method_reference is None:
            raise ValueError(
                f"{self.provenance_kind.value} evidence requires a method/policy reference"
            )
        if self.schema_version != DISCOVERY_SCREENING_PROVENANCE_SCHEMA_VERSION:
            raise ValueError("unsupported screening provenance schema version")


@dataclass(frozen=True, slots=True)
class ScreeningInputReference:
    """One available screening input and its role in the dependency graph."""

    input_reference_id: str
    dependency_role: str
    evidence: ScreeningEvidenceValue

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "input_reference_id",
            _stable_token(self.input_reference_id, "input_reference_id"),
        )
        object.__setattr__(
            self,
            "dependency_role",
            _stable_token(self.dependency_role, "dependency_role"),
        )
        if not isinstance(self.evidence, ScreeningEvidenceValue):
            raise TypeError("evidence must be ScreeningEvidenceValue")


@dataclass(frozen=True, slots=True)
class ScreeningInputManifest:
    """Available inputs plus the exact subset actually consumed by screening."""

    inputs: tuple[ScreeningInputReference, ...]
    used_input_reference_ids: tuple[str, ...]
    schema_version: str = DISCOVERY_SCREENING_INPUT_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.inputs, tuple):
            raise TypeError("inputs must be a tuple")
        if any(not isinstance(value, ScreeningInputReference) for value in self.inputs):
            raise TypeError("inputs must contain ScreeningInputReference")
        input_ids = tuple(value.input_reference_id for value in self.inputs)
        if len(set(input_ids)) != len(input_ids):
            raise ValueError("input reference IDs must be unique")
        if input_ids != tuple(sorted(input_ids)):
            raise ValueError("inputs must use canonical input-reference ordering")
        if any(
            value.input_reference_id in value.evidence.dependency_references
            for value in self.inputs
        ):
            raise ValueError("screening inputs cannot depend on themselves")
        used = _canonical_string_tuple(
            self.used_input_reference_ids,
            "used_input_reference_ids",
            non_empty=bool(self.inputs),
        )
        if not set(used).issubset(input_ids):
            raise ValueError("used input references must exist in the input manifest")
        object.__setattr__(self, "used_input_reference_ids", used)
        if self.schema_version != DISCOVERY_SCREENING_INPUT_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported screening input manifest schema version")

    @property
    def used_inputs(self) -> tuple[ScreeningInputReference, ...]:
        used = set(self.used_input_reference_ids)
        return tuple(value for value in self.inputs if value.input_reference_id in used)


def _policy_reference_to_data(value: ScreeningPolicyReference) -> dict[str, object]:
    return {
        "policy_name": value.policy_name,
        "policy_version": value.policy_version,
        "algorithm_id": value.algorithm_id,
    }


def _source_reference_to_data(value: ScreeningSourceReference) -> dict[str, object]:
    return {
        "reference_id": value.reference_id,
        "source_kind": value.source_kind.value,
        "source_identity": value.source_identity,
        "source_fingerprint": value.source_fingerprint,
        "source_revision": value.source_revision,
        "observed_at": (
            None if value.observed_at is None else _canonical_datetime(value.observed_at)
        ),
        "effective_at": (
            None if value.effective_at is None else _canonical_datetime(value.effective_at)
        ),
    }


def screening_evidence_value_to_canonical_data(
    value: ScreeningEvidenceValue,
) -> dict[str, object]:
    """Return the deterministic semantic projection used by PR4 fingerprints."""

    if not isinstance(value, ScreeningEvidenceValue):
        raise TypeError("value must be ScreeningEvidenceValue")
    return {
        "semantic_role": value.semantic_role,
        "provenance_kind": value.provenance_kind.value,
        "truth_scope": value.truth_scope.value,
        "value": _canonical_scalar(value.value),
        "unit": value.unit,
        "currency": value.currency,
        "source_references": [
            _source_reference_to_data(reference)
            for reference in value.source_references
        ],
        "dependency_references": list(value.dependency_references),
        "method_reference": (
            None
            if value.method_reference is None
            else _policy_reference_to_data(value.method_reference)
        ),
        "schema_version": value.schema_version,
    }


def screening_input_manifest_to_canonical_data(
    value: ScreeningInputManifest,
) -> dict[str, object]:
    if not isinstance(value, ScreeningInputManifest):
        raise TypeError("value must be ScreeningInputManifest")
    return {
        "inputs": [
            {
                "input_reference_id": item.input_reference_id,
                "dependency_role": item.dependency_role,
                "evidence": screening_evidence_value_to_canonical_data(item.evidence),
            }
            for item in value.inputs
        ],
        "used_input_reference_ids": list(value.used_input_reference_ids),
        "schema_version": value.schema_version,
    }


def _score_policy_to_data(
    value: ScreeningScorePolicyDescriptor,
) -> dict[str, object]:
    return {
        "policy_name": value.policy_name,
        "policy_version": value.policy_version,
        "algorithm_id": value.algorithm_id,
        "description": value.description,
        "ordered_rule_ids": list(value.ordered_rule_ids),
        "policy_assumption_inputs": list(value.policy_assumption_inputs),
    }


def _recommendation_policy_to_data(
    value: RecommendationPolicyDescriptor,
) -> dict[str, object]:
    return {
        "policy_name": value.policy_name,
        "policy_version": value.policy_version,
        "algorithm_id": value.algorithm_id,
        "description": value.description,
        "ordered_rule_ids": list(value.ordered_rule_ids),
        "reason_code_namespace": value.reason_code_namespace,
    }


def _safety_policy_to_data(
    value: ProductionSafetyPolicyDescriptor,
) -> dict[str, object]:
    return {
        "policy_name": value.policy_name,
        "policy_version": value.policy_version,
        "algorithm_id": value.algorithm_id,
        "description": value.description,
        "ordered_rule_ids": list(value.ordered_rule_ids),
    }


def _ranking_policy_to_data(
    value: ScreeningRankingPolicyDescriptor,
) -> dict[str, object]:
    return {
        "policy_name": value.policy_name,
        "policy_version": value.policy_version,
        "algorithm_id": value.algorithm_id,
        "description": value.description,
        "ordered_sort_keys": list(value.ordered_sort_keys),
        "equal_key_tie_behavior": value.equal_key_tie_behavior,
    }


def _policy_manifest_to_data(value: ScreeningPolicyDescriptors) -> dict[str, object]:
    return {
        "score": _score_policy_to_data(value.score),
        "recommendation": _recommendation_policy_to_data(value.recommendation),
        "production_safety": _safety_policy_to_data(value.production_safety),
        "ranking": _ranking_policy_to_data(value.ranking),
    }


def _recommendation_value_to_data(
    value: ScreeningRecommendationValue,
) -> dict[str, object]:
    return {
        "grade": value.grade,
        "action": value.action,
        "summary": value.summary,
    }


def _reason_to_data(value: StructuredScreeningReason) -> dict[str, object]:
    return {
        "reason_code": value.reason_code,
        "category": value.category.value,
        "polarity": value.polarity.value,
        "source_component": value.source_component,
        "message": value.message,
    }


def _recommendation_to_data(
    value: ScreeningRecommendationSemantics,
) -> dict[str, object]:
    return {
        "raw_recommendation": _recommendation_value_to_data(
            value.raw_recommendation
        ),
        "effective_recommendation": _recommendation_value_to_data(
            value.effective_recommendation
        ),
        "recommendation_score": value.recommendation_score,
        "safety_intervention_occurred": value.safety_intervention_occurred,
        "safety_status": value.safety_status,
        "structured_reasons": [
            _reason_to_data(reason) for reason in value.structured_reasons
        ],
        "safety_reasons": [_reason_to_data(reason) for reason in value.safety_reasons],
        "safety_policy": _safety_policy_to_data(value.safety_policy),
    }


def _numeric_or_missing(value: ScreeningEvidenceValue, name: str) -> None:
    if value.value is not None and (
        isinstance(value.value, bool) or not isinstance(value.value, (Decimal, int))
    ):
        raise TypeError(f"{name} must carry a numeric or missing evidence value")


@dataclass(frozen=True, slots=True)
class DiscoveryScreeningEvaluationSnapshot:
    """One exact finalized-Group screening fact; rank is intentionally absent."""

    screening_evaluation_id: str
    command_id: str
    discovery_execution_id: str
    finalized_group_id: str
    group_membership_fingerprint: str
    screening_recommendation: ScreeningRecommendationSemantics
    final_opportunity_score: ScreeningEvidenceValue
    ranking_economics_key: ScreeningEvidenceValue
    expected_economics: tuple[ScreeningEvidenceValue, ...]
    screening_policy_manifest: ScreeningPolicyDescriptors
    input_manifest: ScreeningInputManifest
    evaluated_at: datetime
    schema_version: str = DISCOVERY_SCREENING_EVALUATION_SCHEMA_VERSION
    integrity_fingerprint: str = ""

    def __post_init__(self) -> None:
        for name in (
            "screening_evaluation_id",
            "command_id",
            "discovery_execution_id",
            "finalized_group_id",
        ):
            object.__setattr__(
                self, name, _required_text(getattr(self, name), name)
            )
        object.__setattr__(
            self,
            "group_membership_fingerprint",
            _fingerprint_text(
                self.group_membership_fingerprint, "group_membership_fingerprint"
            ),
        )
        if not isinstance(
            self.screening_recommendation, ScreeningRecommendationSemantics
        ):
            raise TypeError(
                "screening_recommendation must be ScreeningRecommendationSemantics"
            )
        if not isinstance(self.final_opportunity_score, ScreeningEvidenceValue):
            raise TypeError("final_opportunity_score must be ScreeningEvidenceValue")
        if self.final_opportunity_score.semantic_role != "final_opportunity_score":
            raise ValueError(
                "final_opportunity_score evidence must use its canonical semantic role"
            )
        _numeric_or_missing(self.final_opportunity_score, "final_opportunity_score")
        if not isinstance(self.ranking_economics_key, ScreeningEvidenceValue):
            raise TypeError("ranking_economics_key must be ScreeningEvidenceValue")
        if self.ranking_economics_key.semantic_role != "per_unit_net_profit":
            raise ValueError(
                "ranking_economics_key must use per_unit_net_profit semantic role"
            )
        _numeric_or_missing(self.ranking_economics_key, "ranking_economics_key")

        if not isinstance(self.expected_economics, tuple):
            raise TypeError("expected_economics must be a tuple")
        if any(
            not isinstance(value, ScreeningEvidenceValue)
            for value in self.expected_economics
        ):
            raise TypeError("expected_economics must contain ScreeningEvidenceValue")
        roles = tuple(value.semantic_role for value in self.expected_economics)
        if not roles:
            raise ValueError("expected_economics must not be empty")
        if len(set(roles)) != len(roles):
            raise ValueError("expected_economics semantic roles must be unique")
        if roles != tuple(sorted(roles)):
            raise ValueError("expected_economics must use canonical semantic-role order")

        if not isinstance(self.screening_policy_manifest, ScreeningPolicyDescriptors):
            raise TypeError(
                "screening_policy_manifest must be ScreeningPolicyDescriptors"
            )
        if (
            self.screening_recommendation.safety_policy
            != self.screening_policy_manifest.production_safety
        ):
            raise ValueError(
                "recommendation Safety policy must match the screening policy manifest"
            )
        if not isinstance(self.input_manifest, ScreeningInputManifest):
            raise TypeError("input_manifest must be ScreeningInputManifest")
        available_dependencies = set(self.input_manifest.used_input_reference_ids)
        evidence_values = (
            self.final_opportunity_score,
            self.ranking_economics_key,
            *self.expected_economics,
            *(item.evidence for item in self.input_manifest.used_inputs),
        )
        for evidence in evidence_values:
            missing = set(evidence.dependency_references) - available_dependencies
            if missing:
                raise ValueError(
                    "evidence dependency references must identify actually used inputs"
                )
        object.__setattr__(
            self, "evaluated_at", _aware(self.evaluated_at, "evaluated_at")
        )
        if self.schema_version != DISCOVERY_SCREENING_EVALUATION_SCHEMA_VERSION:
            raise ValueError("unsupported screening evaluation schema version")
        expected = _sha256(
            discovery_screening_evaluation_to_canonical_data(
                self, include_integrity_fingerprint=False
            )
        )
        if self.integrity_fingerprint:
            supplied = _fingerprint_text(
                self.integrity_fingerprint, "integrity_fingerprint"
            )
            if supplied != expected:
                raise ValueError(
                    "screening evaluation fingerprint does not match canonical content"
                )
        object.__setattr__(self, "integrity_fingerprint", expected)

    @property
    def screening_score(self) -> int:
        """Reuse PR3's one authoritative recommendation/screening score."""

        return self.screening_recommendation.recommendation_score

    @property
    def structured_reasons(self) -> tuple[StructuredScreeningReason, ...]:
        return self.screening_recommendation.structured_reasons


def discovery_screening_evaluation_to_canonical_data(
    value: DiscoveryScreeningEvaluationSnapshot,
    *,
    include_integrity_fingerprint: bool = True,
) -> dict[str, object]:
    """Canonical persisted projection; field names and ordering are deterministic."""

    if not isinstance(value, DiscoveryScreeningEvaluationSnapshot):
        raise TypeError("value must be DiscoveryScreeningEvaluationSnapshot")
    payload: dict[str, object] = {
        "screening_evaluation_id": value.screening_evaluation_id,
        "command_id": value.command_id,
        "discovery_execution_id": value.discovery_execution_id,
        "finalized_group_id": value.finalized_group_id,
        "group_membership_fingerprint": value.group_membership_fingerprint,
        "screening_recommendation": _recommendation_to_data(
            value.screening_recommendation
        ),
        "final_opportunity_score": screening_evidence_value_to_canonical_data(
            value.final_opportunity_score
        ),
        "ranking_economics_key": screening_evidence_value_to_canonical_data(
            value.ranking_economics_key
        ),
        "expected_economics": [
            screening_evidence_value_to_canonical_data(item)
            for item in value.expected_economics
        ],
        "screening_policy_manifest": _policy_manifest_to_data(
            value.screening_policy_manifest
        ),
        "input_manifest": screening_input_manifest_to_canonical_data(
            value.input_manifest
        ),
        "evaluated_at": _canonical_datetime(value.evaluated_at),
        "schema_version": value.schema_version,
    }
    if include_integrity_fingerprint:
        payload["integrity_fingerprint"] = value.integrity_fingerprint
    return payload


def serialize_discovery_screening_evaluation(
    value: DiscoveryScreeningEvaluationSnapshot,
) -> str:
    """Serialize one evaluation with its verified fingerprint as canonical JSON."""

    return _canonical_json(discovery_screening_evaluation_to_canonical_data(value))


@dataclass(frozen=True, slots=True)
class RankedScreeningEntry:
    rank: int
    discovery_execution_id: str
    finalized_group_id: str
    screening_evaluation_id: str
    evaluation_fingerprint: str

    def __post_init__(self) -> None:
        if isinstance(self.rank, bool) or not isinstance(self.rank, int) or self.rank < 1:
            raise ValueError("rank must be a positive integer")
        for name in (
            "discovery_execution_id",
            "finalized_group_id",
            "screening_evaluation_id",
        ):
            object.__setattr__(
                self, name, _required_text(getattr(self, name), name)
            )
        object.__setattr__(
            self,
            "evaluation_fingerprint",
            _fingerprint_text(
                self.evaluation_fingerprint, "evaluation_fingerprint"
            ),
        )


@dataclass(frozen=True, slots=True)
class NotRankedScreeningEntry:
    discovery_execution_id: str
    finalized_group_id: str
    screening_evaluation_id: str
    evaluation_fingerprint: str
    reason_code: NotRankedScreeningReasonCode
    unavailable_semantic_roles: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "discovery_execution_id",
            "finalized_group_id",
            "screening_evaluation_id",
        ):
            object.__setattr__(
                self, name, _required_text(getattr(self, name), name)
            )
        object.__setattr__(
            self,
            "evaluation_fingerprint",
            _fingerprint_text(
                self.evaluation_fingerprint, "evaluation_fingerprint"
            ),
        )
        if not isinstance(self.reason_code, NotRankedScreeningReasonCode):
            raise TypeError("reason_code must be NotRankedScreeningReasonCode")
        roles = _canonical_string_tuple(
            self.unavailable_semantic_roles,
            "unavailable_semantic_roles",
            non_empty=True,
        )
        for role in roles:
            _stable_token(role, "unavailable_semantic_role")
        object.__setattr__(self, "unavailable_semantic_roles", roles)


def _ranked_entry_to_data(value: RankedScreeningEntry) -> dict[str, object]:
    return {
        "rank": value.rank,
        "discovery_execution_id": value.discovery_execution_id,
        "finalized_group_id": value.finalized_group_id,
        "screening_evaluation_id": value.screening_evaluation_id,
        "evaluation_fingerprint": value.evaluation_fingerprint,
    }


def _not_ranked_entry_to_data(
    value: NotRankedScreeningEntry,
) -> dict[str, object]:
    return {
        "discovery_execution_id": value.discovery_execution_id,
        "finalized_group_id": value.finalized_group_id,
        "screening_evaluation_id": value.screening_evaluation_id,
        "evaluation_fingerprint": value.evaluation_fingerprint,
        "reason_code": value.reason_code.value,
        "unavailable_semantic_roles": list(value.unavailable_semantic_roles),
    }


@dataclass(frozen=True, slots=True)
class DiscoveryScreeningRankingPublication:
    """One immutable execution-level review-priority ranking publication."""

    screening_ranking_publication_id: str
    command_id: str
    discovery_execution_id: str
    ranked_entries: tuple[RankedScreeningEntry, ...]
    not_ranked_entries: tuple[NotRankedScreeningEntry, ...]
    ranking_policy: ScreeningRankingPolicyDescriptor
    ranking_created_at: datetime
    zero_result: bool
    schema_version: str = DISCOVERY_SCREENING_RANKING_PUBLICATION_SCHEMA_VERSION
    integrity_fingerprint: str = ""

    def __post_init__(self) -> None:
        for name in (
            "screening_ranking_publication_id",
            "command_id",
            "discovery_execution_id",
        ):
            object.__setattr__(
                self, name, _required_text(getattr(self, name), name)
            )
        if not isinstance(self.ranked_entries, tuple):
            raise TypeError("ranked_entries must be a tuple")
        if any(not isinstance(value, RankedScreeningEntry) for value in self.ranked_entries):
            raise TypeError("ranked_entries must contain RankedScreeningEntry")
        if not isinstance(self.not_ranked_entries, tuple):
            raise TypeError("not_ranked_entries must be a tuple")
        if any(
            not isinstance(value, NotRankedScreeningEntry)
            for value in self.not_ranked_entries
        ):
            raise TypeError(
                "not_ranked_entries must contain NotRankedScreeningEntry"
            )
        if not isinstance(self.ranking_policy, ScreeningRankingPolicyDescriptor):
            raise TypeError(
                "ranking_policy must be ScreeningRankingPolicyDescriptor"
            )
        if not isinstance(self.zero_result, bool):
            raise TypeError("zero_result must be bool")

        ranks = tuple(value.rank for value in self.ranked_entries)
        if ranks != tuple(range(1, len(self.ranked_entries) + 1)):
            raise ValueError("ranks must be contiguous and start at 1")
        all_entries = (*self.ranked_entries, *self.not_ranked_entries)
        if any(
            value.discovery_execution_id != self.discovery_execution_id
            for value in all_entries
        ):
            raise ValueError("all ranking entries must belong to one execution")
        evaluation_ids = tuple(value.screening_evaluation_id for value in all_entries)
        if len(set(evaluation_ids)) != len(evaluation_ids):
            raise ValueError(
                "each screening evaluation must appear exactly once in a publication"
            )
        group_ids = tuple(value.finalized_group_id for value in all_entries)
        if len(set(group_ids)) != len(group_ids):
            raise ValueError(
                "ranked and not-ranked entries cannot overlap finalized Groups"
            )
        if self.zero_result and all_entries:
            raise ValueError("zero-result publication cannot contain entries")
        if not self.zero_result and not all_entries:
            raise ValueError("non-zero publication must contain an evaluation entry")
        if self.schema_version != DISCOVERY_SCREENING_RANKING_PUBLICATION_SCHEMA_VERSION:
            raise ValueError("unsupported screening ranking publication schema version")
        object.__setattr__(
            self,
            "ranking_created_at",
            _aware(self.ranking_created_at, "ranking_created_at"),
        )
        expected = _sha256(
            discovery_screening_ranking_publication_to_canonical_data(
                self, include_integrity_fingerprint=False
            )
        )
        if self.integrity_fingerprint:
            supplied = _fingerprint_text(
                self.integrity_fingerprint, "integrity_fingerprint"
            )
            if supplied != expected:
                raise ValueError(
                    "screening ranking publication fingerprint does not match canonical content"
                )
        object.__setattr__(self, "integrity_fingerprint", expected)


def discovery_screening_ranking_publication_to_canonical_data(
    value: DiscoveryScreeningRankingPublication,
    *,
    include_integrity_fingerprint: bool = True,
) -> dict[str, object]:
    """Canonical persisted projection including ordered ranking semantics."""

    if not isinstance(value, DiscoveryScreeningRankingPublication):
        raise TypeError("value must be DiscoveryScreeningRankingPublication")
    payload: dict[str, object] = {
        "screening_ranking_publication_id": (
            value.screening_ranking_publication_id
        ),
        "command_id": value.command_id,
        "discovery_execution_id": value.discovery_execution_id,
        "ranked_entries": [
            _ranked_entry_to_data(item) for item in value.ranked_entries
        ],
        "not_ranked_entries": [
            _not_ranked_entry_to_data(item) for item in value.not_ranked_entries
        ],
        "ranking_policy": _ranking_policy_to_data(value.ranking_policy),
        "ranking_created_at": _canonical_datetime(value.ranking_created_at),
        "zero_result": value.zero_result,
        "schema_version": value.schema_version,
    }
    if include_integrity_fingerprint:
        payload["integrity_fingerprint"] = value.integrity_fingerprint
    return payload


def serialize_discovery_screening_ranking_publication(
    value: DiscoveryScreeningRankingPublication,
) -> str:
    """Serialize one ranking publication as canonical JSON for future storage."""

    return _canonical_json(
        discovery_screening_ranking_publication_to_canonical_data(value)
    )


__all__ = [
    "DISCOVERY_SCREENING_EVALUATION_SCHEMA_VERSION",
    "DISCOVERY_SCREENING_INPUT_MANIFEST_SCHEMA_VERSION",
    "DISCOVERY_SCREENING_PROVENANCE_SCHEMA_VERSION",
    "DISCOVERY_SCREENING_RANKING_PUBLICATION_SCHEMA_VERSION",
    "DiscoveryScreeningEvaluationSnapshot",
    "DiscoveryScreeningRankingPublication",
    "DiscoveryScreeningRecordingState",
    "NotRankedScreeningEntry",
    "NotRankedScreeningReasonCode",
    "RankedScreeningEntry",
    "ScreeningEvidenceValue",
    "ScreeningInputManifest",
    "ScreeningInputReference",
    "ScreeningPolicyReference",
    "ScreeningProvenanceKind",
    "ScreeningSourceKind",
    "ScreeningSourceReference",
    "ScreeningTruthScope",
    "discovery_screening_evaluation_to_canonical_data",
    "discovery_screening_ranking_publication_to_canonical_data",
    "screening_evidence_value_to_canonical_data",
    "screening_input_manifest_to_canonical_data",
    "serialize_discovery_screening_evaluation",
    "serialize_discovery_screening_ranking_publication",
]
