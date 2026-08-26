from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Decimal

from app.application.discovery import (
    DiscoveryScreeningCompletionBinding,
    DiscoveryScreeningCompletionBundle,
)
from app.domain.discovery import (
    DiscoveryScreeningRankingPublication,
    NotRankedScreeningEntry,
    NotRankedScreeningReasonCode,
    RankedScreeningEntry,
)
from app.domain.discovery_identity import DiscoveryExecutionResult
from app.infrastructure.discovery import (
    SQLiteDiscoveryCommandRepository,
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
)
from test_discovery_command_sqlite_persistence import receipt
from test_discovery_correlation_contract import command, group, observation
from test_discovery_screening_domain_contracts import (
    NOW as SCREENING_NOW,
    evaluation,
    unknown,
)


def prepare_completion_lineage(
    path,
    *,
    command_id: str = "command-1",
    execution_id: str = "execution-1",
    suffix: str = "1",
    group_count: int = 2,
):
    command_value = command(
        command_id=command_id,
        discovery_execution_id=execution_id,
    )
    commands = SQLiteDiscoveryCommandRepository(path)
    commands.save_command(command_value, receipt(command_value))
    commands.close()

    observations = SQLiteDiscoveryObservationRepository(path)
    observation_ids = []
    for position in range(2):
        observation_id = f"observation-{suffix}-{position + 1}"
        observation_ids.append(observation_id)
        observations.save_observation(
            replace(
                observation(),
                observation_id=observation_id,
                discovery_execution_id=execution_id,
                observed_at=observation().observed_at
                + timedelta(minutes=int(suffix), seconds=position),
            )
        )
    observations.close()

    groups = SQLiteDiscoveryGroupRepository(path)
    group_values = tuple(
        replace(
            group(),
            finalized_group_id=f"group-{suffix}-{position + 1}",
            discovery_execution_id=execution_id,
            observation_ids=tuple(observation_ids),
            representative_observation_id=observation_ids[0],
            finalized_at=group().finalized_at
            + timedelta(minutes=int(suffix), seconds=position),
        )
        for position in range(group_count)
    )
    for value in group_values:
        groups.save_group(value)
    groups.close()
    return command_value, group_values


def completion_bundle(
    command_value,
    group_values,
    *,
    suffix: str = "1",
    final_score: Decimal = Decimal("81.5000"),
):
    result = DiscoveryExecutionResult(
        command_id=command_value.command_id,
        discovery_execution_id=command_value.discovery_execution_id,
        finalized_group_ids=tuple(
            value.finalized_group_id for value in group_values
        ),
        completed_at=SCREENING_NOW + timedelta(minutes=int(suffix) + 1),
    )
    evaluations = []
    for position, group_value in enumerate(group_values):
        value = evaluation(
            evaluation_id=f"evaluation-{suffix}-{position + 1}",
            group_id=group_value.finalized_group_id,
            final_score=final_score + Decimal(position),
            net_profit=Decimal("12.3400") + Decimal(position),
            evaluated_at=SCREENING_NOW
            + timedelta(minutes=int(suffix), seconds=position),
        )
        changes = {
            "command_id": command_value.command_id,
            "discovery_execution_id": command_value.discovery_execution_id,
            "group_membership_fingerprint": (
                group_value.membership_fingerprint
            ),
            "integrity_fingerprint": "",
        }
        if position == 1:
            changes["ranking_economics_key"] = unknown(
                "per_unit_net_profit"
            )
        evaluations.append(replace(value, **changes))
    evaluation_values = tuple(evaluations)

    ranked_entries = ()
    not_ranked_entries = ()
    if evaluation_values:
        ranked_entries = (
            RankedScreeningEntry(
                rank=1,
                discovery_execution_id=command_value.discovery_execution_id,
                finalized_group_id=evaluation_values[0].finalized_group_id,
                screening_evaluation_id=(
                    evaluation_values[0].screening_evaluation_id
                ),
                evaluation_fingerprint=(
                    evaluation_values[0].integrity_fingerprint
                ),
            ),
        )
        if len(evaluation_values) > 1:
            not_ranked_entries = tuple(
                NotRankedScreeningEntry(
                    discovery_execution_id=(
                        command_value.discovery_execution_id
                    ),
                    finalized_group_id=value.finalized_group_id,
                    screening_evaluation_id=value.screening_evaluation_id,
                    evaluation_fingerprint=value.integrity_fingerprint,
                    reason_code=(
                        NotRankedScreeningReasonCode.UNKNOWN_RANKING_KEY
                    ),
                    unavailable_semantic_roles=("per_unit_net_profit",),
                )
                for value in evaluation_values[1:]
            )
    publication = DiscoveryScreeningRankingPublication(
        screening_ranking_publication_id=f"publication-{suffix}",
        command_id=command_value.command_id,
        discovery_execution_id=command_value.discovery_execution_id,
        ranked_entries=ranked_entries,
        not_ranked_entries=not_ranked_entries,
        ranking_policy=(
            evaluation_values[0].screening_policy_manifest.ranking
            if evaluation_values
            else evaluation().screening_policy_manifest.ranking
        ),
        ranking_created_at=SCREENING_NOW
        + timedelta(minutes=int(suffix) + 1),
        zero_result=not evaluation_values,
    )
    binding = DiscoveryScreeningCompletionBinding(
        command_id=result.command_id,
        discovery_execution_id=result.discovery_execution_id,
        result_schema_version=result.schema_version,
        result_fingerprint=result.fingerprint,
        screening_ranking_publication_id=(
            publication.screening_ranking_publication_id
        ),
        ranking_publication_fingerprint=publication.integrity_fingerprint,
    )
    return DiscoveryScreeningCompletionBundle(
        execution_result=result,
        finalized_groups=tuple(group_values),
        evaluations=evaluation_values,
        ranking_publication=publication,
        completion_binding=binding,
    )


def prepare_bundle(
    path,
    *,
    command_id: str = "command-1",
    execution_id: str = "execution-1",
    suffix: str = "1",
    group_count: int = 2,
):
    command_value, group_values = prepare_completion_lineage(
        path,
        command_id=command_id,
        execution_id=execution_id,
        suffix=suffix,
        group_count=group_count,
    )
    return completion_bundle(command_value, group_values, suffix=suffix)


SCREENING_TABLES = (
    "discovery_screening_evaluation_history",
    "discovery_screening_ranking_publication_history",
    "discovery_screening_completion_binding_history",
    "discovery_execution_result_history",
)


def screening_state(connection):
    return tuple(
        (
            table,
            tuple(
                tuple(row)
                for row in connection.execute(
                    f"SELECT * FROM {table} ORDER BY rowid"
                )
            ),
        )
        for table in SCREENING_TABLES
    )
