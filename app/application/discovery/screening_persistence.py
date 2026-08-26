"""Persistence boundary contracts for atomic Discovery screening completion."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Protocol

from app.domain.discovery import (
    DiscoveryScreeningEvaluationSnapshot,
    DiscoveryScreeningRankingPublication,
    DiscoveryScreeningRecordingState,
)
from app.domain.discovery_identity import (
    DiscoveryExecutionResult,
    FinalizedProductGroup,
)


DISCOVERY_SCREENING_COMPLETION_BINDING_SCHEMA_VERSION = (
    "discovery-screening-completion-binding-v1"
)


class DiscoveryScreeningPersistenceError(RuntimeError):
    pass


class DiscoveryScreeningCompletionConflictError(
    DiscoveryScreeningPersistenceError
):
    pass


class DiscoveryScreeningCompletionLineageError(
    DiscoveryScreeningPersistenceError
):
    pass


class DiscoveryScreeningHistoryError(DiscoveryScreeningPersistenceError):
    pass


class DiscoveryScreeningCommitError(DiscoveryScreeningPersistenceError):
    pass


class MalformedDiscoveryScreeningPersistenceError(
    DiscoveryScreeningPersistenceError
):
    pass


class UnsupportedDiscoveryScreeningVersionError(
    MalformedDiscoveryScreeningPersistenceError
):
    pass


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    if not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    if value != value.strip():
        raise ValueError(f"{name} must not contain surrounding whitespace")
    return value


def _fingerprint(value: str, name: str) -> str:
    resolved = _required_text(value, name)
    if len(resolved) != 64 or any(
        character not in "0123456789abcdef" for character in resolved
    ):
        raise ValueError(f"{name} must be lowercase SHA-256 text")
    return resolved


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


@dataclass(frozen=True, slots=True)
class DiscoveryScreeningCompletionBinding:
    """Immutable link from one completion result to one ranking publication."""

    command_id: str
    discovery_execution_id: str
    result_schema_version: str
    result_fingerprint: str
    screening_ranking_publication_id: str
    ranking_publication_fingerprint: str
    screening_recording_state: DiscoveryScreeningRecordingState = (
        DiscoveryScreeningRecordingState.RECORDED
    )
    schema_version: str = DISCOVERY_SCREENING_COMPLETION_BINDING_SCHEMA_VERSION
    integrity_fingerprint: str = ""

    def __post_init__(self) -> None:
        for name in (
            "command_id",
            "discovery_execution_id",
            "result_schema_version",
            "screening_ranking_publication_id",
        ):
            object.__setattr__(
                self,
                name,
                _required_text(getattr(self, name), name),
            )
        for name in (
            "result_fingerprint",
            "ranking_publication_fingerprint",
        ):
            object.__setattr__(
                self,
                name,
                _fingerprint(getattr(self, name), name),
            )
        if self.screening_recording_state is not (
            DiscoveryScreeningRecordingState.RECORDED
        ):
            raise ValueError("a screening completion binding must be RECORDED")
        if self.schema_version != (
            DISCOVERY_SCREENING_COMPLETION_BINDING_SCHEMA_VERSION
        ):
            raise ValueError("unsupported screening completion binding version")
        expected = hashlib.sha256(
            _canonical_json(
                discovery_screening_completion_binding_to_canonical_data(
                    self,
                    include_integrity_fingerprint=False,
                )
            ).encode("utf-8")
        ).hexdigest()
        if self.integrity_fingerprint:
            supplied = _fingerprint(
                self.integrity_fingerprint,
                "integrity_fingerprint",
            )
            if supplied != expected:
                raise ValueError(
                    "screening completion binding fingerprint does not match "
                    "canonical content"
                )
        object.__setattr__(self, "integrity_fingerprint", expected)


def discovery_screening_completion_binding_to_canonical_data(
    value: DiscoveryScreeningCompletionBinding,
    *,
    include_integrity_fingerprint: bool = True,
) -> dict[str, object]:
    if not isinstance(value, DiscoveryScreeningCompletionBinding):
        raise TypeError("value must be DiscoveryScreeningCompletionBinding")
    payload: dict[str, object] = {
        "command_id": value.command_id,
        "discovery_execution_id": value.discovery_execution_id,
        "result_schema_version": value.result_schema_version,
        "result_fingerprint": value.result_fingerprint,
        "screening_ranking_publication_id": (
            value.screening_ranking_publication_id
        ),
        "ranking_publication_fingerprint": (
            value.ranking_publication_fingerprint
        ),
        "screening_recording_state": value.screening_recording_state.value,
        "schema_version": value.schema_version,
    }
    if include_integrity_fingerprint:
        payload["integrity_fingerprint"] = value.integrity_fingerprint
    return payload


def serialize_discovery_screening_completion_binding(
    value: DiscoveryScreeningCompletionBinding,
) -> str:
    return _canonical_json(
        discovery_screening_completion_binding_to_canonical_data(value)
    )


@dataclass(frozen=True, slots=True)
class DiscoveryScreeningCompletionBundle:
    """One exact successful completion committed through one transaction."""

    execution_result: DiscoveryExecutionResult
    finalized_groups: tuple[FinalizedProductGroup, ...]
    evaluations: tuple[DiscoveryScreeningEvaluationSnapshot, ...]
    ranking_publication: DiscoveryScreeningRankingPublication
    completion_binding: DiscoveryScreeningCompletionBinding

    def __post_init__(self) -> None:
        if not isinstance(self.execution_result, DiscoveryExecutionResult):
            raise TypeError("execution_result must be DiscoveryExecutionResult")
        if not isinstance(self.finalized_groups, tuple) or any(
            not isinstance(value, FinalizedProductGroup)
            for value in self.finalized_groups
        ):
            raise TypeError("finalized_groups must contain FinalizedProductGroup")
        if not isinstance(self.evaluations, tuple) or any(
            not isinstance(value, DiscoveryScreeningEvaluationSnapshot)
            for value in self.evaluations
        ):
            raise TypeError(
                "evaluations must contain DiscoveryScreeningEvaluationSnapshot"
            )
        if not isinstance(
            self.ranking_publication,
            DiscoveryScreeningRankingPublication,
        ):
            raise TypeError(
                "ranking_publication must be "
                "DiscoveryScreeningRankingPublication"
            )
        if not isinstance(
            self.completion_binding,
            DiscoveryScreeningCompletionBinding,
        ):
            raise TypeError(
                "completion_binding must be "
                "DiscoveryScreeningCompletionBinding"
            )

        result = self.execution_result
        publication = self.ranking_publication
        binding = self.completion_binding
        group_ids = tuple(value.finalized_group_id for value in self.finalized_groups)
        evaluation_group_ids = tuple(
            value.finalized_group_id for value in self.evaluations
        )
        if group_ids != result.finalized_group_ids:
            raise DiscoveryScreeningCompletionLineageError(
                "completion Groups must match the result's exact ordered Groups"
            )
        if evaluation_group_ids != group_ids:
            raise DiscoveryScreeningCompletionLineageError(
                "screening evaluations must follow the exact result Group order"
            )
        if any(
            group.discovery_execution_id != result.discovery_execution_id
            for group in self.finalized_groups
        ):
            raise DiscoveryScreeningCompletionLineageError(
                "completion Groups must belong to the result execution"
            )
        for group, evaluation in zip(
            self.finalized_groups,
            self.evaluations,
            strict=True,
        ):
            if (
                evaluation.command_id != result.command_id
                or evaluation.discovery_execution_id
                != result.discovery_execution_id
                or evaluation.finalized_group_id != group.finalized_group_id
                or evaluation.group_membership_fingerprint
                != group.membership_fingerprint
            ):
                raise DiscoveryScreeningCompletionLineageError(
                    "screening evaluation and finalized Group lineage differ"
                )

        if (
            publication.command_id != result.command_id
            or publication.discovery_execution_id
            != result.discovery_execution_id
        ):
            raise DiscoveryScreeningCompletionLineageError(
                "ranking publication and result lineage differ"
            )
        entries = (*publication.ranked_entries, *publication.not_ranked_entries)
        by_evaluation_id = {
            value.screening_evaluation_id: value for value in self.evaluations
        }
        if set(value.screening_evaluation_id for value in entries) != set(
            by_evaluation_id
        ):
            raise DiscoveryScreeningCompletionLineageError(
                "ranking publication must reference every exact evaluation"
            )
        for entry in entries:
            evaluation = by_evaluation_id[entry.screening_evaluation_id]
            if (
                entry.finalized_group_id != evaluation.finalized_group_id
                or entry.discovery_execution_id
                != evaluation.discovery_execution_id
                or entry.evaluation_fingerprint
                != evaluation.integrity_fingerprint
            ):
                raise DiscoveryScreeningCompletionLineageError(
                    "ranking entry and evaluation integrity lineage differ"
                )
        if any(
            value.screening_policy_manifest.ranking != publication.ranking_policy
            for value in self.evaluations
        ):
            raise DiscoveryScreeningCompletionLineageError(
                "evaluation and publication ranking policy differ"
            )
        if publication.zero_result != result.is_zero_result:
            raise DiscoveryScreeningCompletionLineageError(
                "publication and result zero-result semantics differ"
            )

        if (
            binding.command_id != result.command_id
            or binding.discovery_execution_id != result.discovery_execution_id
            or binding.result_schema_version != result.schema_version
            or binding.result_fingerprint != result.fingerprint
            or binding.screening_ranking_publication_id
            != publication.screening_ranking_publication_id
            or binding.ranking_publication_fingerprint
            != publication.integrity_fingerprint
        ):
            raise DiscoveryScreeningCompletionLineageError(
                "completion binding does not match result and publication"
            )

    @property
    def screening_recording_state(self) -> DiscoveryScreeningRecordingState:
        return self.completion_binding.screening_recording_state


class DiscoveryScreeningCompletionRepository(Protocol):
    def save_completion_bundle(
        self,
        bundle: DiscoveryScreeningCompletionBundle,
    ) -> DiscoveryScreeningCompletionBundle: ...

    def get_by_execution(
        self,
        discovery_execution_id: str,
    ) -> DiscoveryScreeningCompletionBundle | None: ...

    def get_by_command(
        self,
        command_id: str,
    ) -> DiscoveryScreeningCompletionBundle | None: ...

    def get_by_publication(
        self,
        screening_ranking_publication_id: str,
    ) -> DiscoveryScreeningCompletionBundle | None: ...

    def get_evaluation(
        self,
        screening_evaluation_id: str,
    ) -> DiscoveryScreeningEvaluationSnapshot | None: ...

    def get_ranking_publication(
        self,
        screening_ranking_publication_id: str,
    ) -> DiscoveryScreeningRankingPublication | None: ...

    def get_recording_state(
        self,
        discovery_execution_id: str,
    ) -> DiscoveryScreeningRecordingState | None: ...


__all__ = [
    "DISCOVERY_SCREENING_COMPLETION_BINDING_SCHEMA_VERSION",
    "DiscoveryScreeningCommitError",
    "DiscoveryScreeningCompletionBinding",
    "DiscoveryScreeningCompletionBundle",
    "DiscoveryScreeningCompletionConflictError",
    "DiscoveryScreeningCompletionLineageError",
    "DiscoveryScreeningCompletionRepository",
    "DiscoveryScreeningHistoryError",
    "DiscoveryScreeningPersistenceError",
    "MalformedDiscoveryScreeningPersistenceError",
    "UnsupportedDiscoveryScreeningVersionError",
    "discovery_screening_completion_binding_to_canonical_data",
    "serialize_discovery_screening_completion_binding",
]
