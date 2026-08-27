"""Read-only Founder projection of persisted Discovery screening facts."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.application.discovery.production_execution import (
    DiscoveryCompletionReplayError,
)
from app.application.discovery.result_read import (
    FinalizedGroupReadModel,
    PersistedDiscoveryResultReader,
)
from app.application.discovery.screening_persistence import (
    DiscoveryScreeningCompletionRepository,
)
from app.application.discovery_persistence import DiscoveryExecutionResultNotFound
from app.domain.discovery import (
    DiscoveryScreeningEvaluationSnapshot,
    DiscoveryScreeningRankingPublication,
    DiscoveryScreeningRecordingState,
    NotRankedScreeningReasonCode,
)


class DiscoveryScreeningAuthorityScope(StrEnum):
    DISCOVERY_SCREENING_ONLY = "DISCOVERY_SCREENING_ONLY"


class DiscoveryScreeningExcludedAuthority(StrEnum):
    CANDIDATE_ISSUANCE = "CANDIDATE_ISSUANCE"
    O1_PROMOTION = "O1_PROMOTION"
    CAPITAL_GATE_PASS = "CAPITAL_GATE_PASS"
    FOUNDER_CAPITAL_APPROVAL = "FOUNDER_CAPITAL_APPROVAL"
    REAL_MONEY_EXECUTION_INTENT = "REAL_MONEY_EXECUTION_INTENT"


class FounderReviewPriorityLabel(StrEnum):
    HIGH = "High Review Priority"
    MEDIUM = "Medium Review Priority"
    LOW = "Low Review Priority"


DOES_NOT_AUTHORIZE = tuple(DiscoveryScreeningExcludedAuthority)


def founder_review_priority_label(score: int) -> FounderReviewPriorityLabel:
    """Present the persisted screening score without investment terminology."""

    if isinstance(score, bool) or not isinstance(score, int):
        raise TypeError("screening score must be an integer")
    if not 0 <= score <= 100:
        raise ValueError("screening score must be between 0 and 100")
    if score >= 65:
        return FounderReviewPriorityLabel.HIGH
    if score >= 45:
        return FounderReviewPriorityLabel.MEDIUM
    return FounderReviewPriorityLabel.LOW


@dataclass(frozen=True, slots=True)
class FounderScreeningEntryReadModel:
    rank: int | None
    not_ranked_reason_code: NotRankedScreeningReasonCode | None
    unavailable_semantic_roles: tuple[str, ...]
    review_priority_label: FounderReviewPriorityLabel
    evaluation: DiscoveryScreeningEvaluationSnapshot
    finalized_group: FinalizedGroupReadModel


@dataclass(frozen=True, slots=True)
class DiscoveryScreeningRankingReadModel:
    command_id: str
    discovery_execution_id: str
    screening_status: DiscoveryScreeningRecordingState
    ranking_publication: DiscoveryScreeningRankingPublication | None
    ranked: tuple[FounderScreeningEntryReadModel, ...]
    not_ranked: tuple[FounderScreeningEntryReadModel, ...]
    authority_scope: DiscoveryScreeningAuthorityScope = (
        DiscoveryScreeningAuthorityScope.DISCOVERY_SCREENING_ONLY
    )
    does_not_authorize: tuple[DiscoveryScreeningExcludedAuthority, ...] = (
        DOES_NOT_AUTHORIZE
    )


class PersistedDiscoveryScreeningReader:
    """Build one Founder read model from the exact persisted completion chain."""

    def __init__(
        self,
        *,
        screening_repository: DiscoveryScreeningCompletionRepository,
        result_reader: PersistedDiscoveryResultReader,
    ) -> None:
        self._screening_repository = screening_repository
        self._result_reader = result_reader

    def get_screening_ranking(
        self,
        discovery_execution_id: str,
    ) -> DiscoveryScreeningRankingReadModel:
        state = self._screening_repository.get_recording_state(
            discovery_execution_id
        )
        if state is None:
            raise DiscoveryExecutionResultNotFound(
                "completed discovery execution not found: "
                f"{discovery_execution_id}"
            )

        result = self._result_reader.get_execution_result(
            discovery_execution_id
        )
        if state is DiscoveryScreeningRecordingState.SCREENING_NOT_RECORDED_LEGACY:
            return DiscoveryScreeningRankingReadModel(
                command_id=result.command_id,
                discovery_execution_id=result.discovery_execution_id,
                screening_status=state,
                ranking_publication=None,
                ranked=(),
                not_ranked=(),
            )

        completion = self._screening_repository.get_by_execution(
            discovery_execution_id
        )
        if completion is None:
            raise DiscoveryCompletionReplayError(
                "recorded screening completion is missing"
            )
        if completion.execution_result != result:
            raise DiscoveryCompletionReplayError(
                "screening completion and Discovery result differ"
            )

        group_models = self._result_reader.get_finalized_group_read_models(
            discovery_execution_id
        )
        groups_by_id = {
            item.group.finalized_group_id: item for item in group_models
        }
        evaluations_by_id = {
            item.screening_evaluation_id: item
            for item in completion.evaluations
        }

        def read_entry(
            entry,
            *,
            rank: int | None,
            reason_code: NotRankedScreeningReasonCode | None,
            unavailable_semantic_roles: tuple[str, ...],
        ) -> FounderScreeningEntryReadModel:
            evaluation = evaluations_by_id.get(entry.screening_evaluation_id)
            group = groups_by_id.get(entry.finalized_group_id)
            if evaluation is None or group is None:
                raise DiscoveryCompletionReplayError(
                    "screening publication read lineage is incomplete"
                )
            return FounderScreeningEntryReadModel(
                rank=rank,
                not_ranked_reason_code=reason_code,
                unavailable_semantic_roles=unavailable_semantic_roles,
                review_priority_label=founder_review_priority_label(
                    evaluation.screening_score
                ),
                evaluation=evaluation,
                finalized_group=group,
            )

        publication = completion.ranking_publication
        ranked = tuple(
            read_entry(
                entry,
                rank=entry.rank,
                reason_code=None,
                unavailable_semantic_roles=(),
            )
            for entry in publication.ranked_entries
        )
        not_ranked = tuple(
            read_entry(
                entry,
                rank=None,
                reason_code=entry.reason_code,
                unavailable_semantic_roles=entry.unavailable_semantic_roles,
            )
            for entry in publication.not_ranked_entries
        )
        return DiscoveryScreeningRankingReadModel(
            command_id=result.command_id,
            discovery_execution_id=result.discovery_execution_id,
            screening_status=state,
            ranking_publication=publication,
            ranked=ranked,
            not_ranked=not_ranked,
        )


__all__ = [
    "DOES_NOT_AUTHORIZE",
    "DiscoveryScreeningAuthorityScope",
    "DiscoveryScreeningExcludedAuthority",
    "DiscoveryScreeningRankingReadModel",
    "FounderReviewPriorityLabel",
    "FounderScreeningEntryReadModel",
    "PersistedDiscoveryScreeningReader",
    "founder_review_priority_label",
]
