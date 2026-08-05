"""Read-only Application query for completed Discovery results and Groups."""

from __future__ import annotations

from app.application.discovery.production_execution import (
    DiscoveryCompletionReplayError,
)
from app.application.discovery_persistence import (
    DiscoveryExecutionResultNotFound,
    DiscoveryGroupRepository,
    DiscoveryResultRepository,
)
from app.domain.discovery_identity import (
    DiscoveryExecutionResult,
    FinalizedProductGroup,
)


class PersistedDiscoveryResultReader:
    """Reconstructs persisted completion facts without mutating repositories."""

    def __init__(
        self,
        *,
        result_repository: DiscoveryResultRepository,
        group_repository: DiscoveryGroupRepository,
    ) -> None:
        self._result_repository = result_repository
        self._group_repository = group_repository

    def get_execution_result(
        self, discovery_execution_id: str
    ) -> DiscoveryExecutionResult:
        result = self._result_repository.get_by_execution(
            discovery_execution_id
        )
        if result is None:
            raise DiscoveryExecutionResultNotFound(
                "completed discovery execution not found: "
                f"{discovery_execution_id}"
            )
        if not isinstance(result, DiscoveryExecutionResult):
            raise DiscoveryCompletionReplayError(
                "result repository returned malformed completion"
            )
        return result

    def get_finalized_groups(
        self, discovery_execution_id: str
    ) -> tuple[FinalizedProductGroup, ...]:
        result = self.get_execution_result(discovery_execution_id)
        groups = []
        for finalized_group_id in result.finalized_group_ids:
            group = self._group_repository.get_group(finalized_group_id)
            if group is None:
                raise DiscoveryCompletionReplayError(
                    "completed result references a missing finalized group"
                )
            if not isinstance(group, FinalizedProductGroup):
                raise DiscoveryCompletionReplayError(
                    "group repository returned malformed replay lineage"
                )
            if group.finalized_group_id != finalized_group_id:
                raise DiscoveryCompletionReplayError(
                    "group repository returned conflicting finalized group identity"
                )
            if group.discovery_execution_id != result.discovery_execution_id:
                raise DiscoveryCompletionReplayError(
                    "group execution conflicts with completed result"
                )
            groups.append(group)
        return tuple(groups)


__all__ = ["PersistedDiscoveryResultReader"]
