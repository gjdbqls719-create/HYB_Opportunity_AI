from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from app.application.discovery import (
    DiscoveryScreeningCompletionBinding,
    PersistedDiscoveryResultReader,
    PersistedDiscoveryScreeningReader,
    founder_review_priority_label,
)
from app.application.discovery_persistence import DiscoveryExecutionResultNotFound
from app.domain.discovery import (
    DiscoveryScreeningRankingPublication,
    DiscoveryScreeningRecordingState,
    RankedScreeningEntry,
)
from app.domain.discovery_identity import DiscoveryExecutionResult
from app.infrastructure.discovery import (
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
    SQLiteDiscoveryResultRepository,
    SQLiteDiscoveryScreeningCompletionRepository,
)
from tests.discovery_screening_persistence_support import (
    prepare_bundle,
    prepare_completion_lineage,
)


def reader(path):
    results = SQLiteDiscoveryResultRepository(path)
    groups = SQLiteDiscoveryGroupRepository(path)
    observations = SQLiteDiscoveryObservationRepository(path)
    screening = SQLiteDiscoveryScreeningCompletionRepository(path)
    value = PersistedDiscoveryScreeningReader(
        screening_repository=screening,
        result_reader=PersistedDiscoveryResultReader(
            result_repository=results,
            group_repository=groups,
            observation_repository=observations,
        ),
    )
    return value, (results, groups, observations, screening)


def close_all(*repositories) -> None:
    for repository in repositories:
        repository.close()


def reverse_ranked_bundle(bundle):
    first, second = bundle.evaluations
    second = replace(
        second,
        ranking_economics_key=first.ranking_economics_key,
        integrity_fingerprint="",
    )
    evaluations = (first, second)
    publication = DiscoveryScreeningRankingPublication(
        screening_ranking_publication_id=(
            bundle.ranking_publication.screening_ranking_publication_id
        ),
        command_id=bundle.execution_result.command_id,
        discovery_execution_id=bundle.execution_result.discovery_execution_id,
        ranked_entries=(
            RankedScreeningEntry(
                rank=1,
                discovery_execution_id=second.discovery_execution_id,
                finalized_group_id=second.finalized_group_id,
                screening_evaluation_id=second.screening_evaluation_id,
                evaluation_fingerprint=second.integrity_fingerprint,
            ),
            RankedScreeningEntry(
                rank=2,
                discovery_execution_id=first.discovery_execution_id,
                finalized_group_id=first.finalized_group_id,
                screening_evaluation_id=first.screening_evaluation_id,
                evaluation_fingerprint=first.integrity_fingerprint,
            ),
        ),
        not_ranked_entries=(),
        ranking_policy=bundle.ranking_publication.ranking_policy,
        ranking_created_at=bundle.ranking_publication.ranking_created_at,
        zero_result=False,
    )
    binding = DiscoveryScreeningCompletionBinding(
        command_id=bundle.execution_result.command_id,
        discovery_execution_id=bundle.execution_result.discovery_execution_id,
        result_schema_version=bundle.execution_result.schema_version,
        result_fingerprint=bundle.execution_result.fingerprint,
        screening_ranking_publication_id=(
            publication.screening_ranking_publication_id
        ),
        ranking_publication_fingerprint=publication.integrity_fingerprint,
    )
    return replace(
        bundle,
        evaluations=evaluations,
        ranking_publication=publication,
        completion_binding=binding,
    )


def test_recorded_read_uses_exact_publication_order_and_evaluation_mapping(
    tmp_path,
) -> None:
    path = tmp_path / "screening-read.db"
    expected = reverse_ranked_bundle(prepare_bundle(path))
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    repository.save_completion_bundle(expected)
    repository.close()
    query, repositories = reader(path)
    try:
        result = query.get_screening_ranking("execution-1")
    finally:
        close_all(*repositories)

    assert result.screening_status is DiscoveryScreeningRecordingState.RECORDED
    assert result.ranking_publication == expected.ranking_publication
    assert [item.rank for item in result.ranked] == [1, 2]
    assert [item.finalized_group.group.finalized_group_id for item in result.ranked] == [
        "group-1-2",
        "group-1-1",
    ]
    assert [item.evaluation.screening_evaluation_id for item in result.ranked] == [
        "evaluation-1-2",
        "evaluation-1-1",
    ]
    assert result.ranked[0].review_priority_label == "High Review Priority"
    assert result.ranked[0].evaluation.screening_policy_manifest == (
        expected.evaluations[1].screening_policy_manifest
    )
    assert result.ranked[0].evaluation.input_manifest == (
        expected.evaluations[1].input_manifest
    )
    assert result.authority_scope == "DISCOVERY_SCREENING_ONLY"
    assert tuple(value.value for value in result.does_not_authorize) == (
        "CANDIDATE_ISSUANCE",
        "O1_PROMOTION",
        "CAPITAL_GATE_PASS",
        "FOUNDER_CAPITAL_APPROVAL",
        "REAL_MONEY_EXECUTION_INTENT",
    )


def test_founder_review_priority_mapping_uses_safe_screening_score_labels() -> None:
    assert founder_review_priority_label(100) == "High Review Priority"
    assert founder_review_priority_label(65) == "High Review Priority"
    assert founder_review_priority_label(64) == "Medium Review Priority"
    assert founder_review_priority_label(45) == "Medium Review Priority"
    assert founder_review_priority_label(44) == "Low Review Priority"
    assert founder_review_priority_label(0) == "Low Review Priority"


def test_not_ranked_entry_has_no_inferred_rank_and_preserves_reason(tmp_path) -> None:
    path = tmp_path / "not-ranked.db"
    expected = prepare_bundle(path)
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    repository.save_completion_bundle(expected)
    repository.close()
    query, repositories = reader(path)
    try:
        result = query.get_screening_ranking("execution-1")
    finally:
        close_all(*repositories)

    assert [item.rank for item in result.ranked] == [1]
    assert len(result.not_ranked) == 1
    assert result.not_ranked[0].rank is None
    assert result.not_ranked[0].not_ranked_reason_code.value == (
        "UNKNOWN_RANKING_KEY"
    )
    assert result.not_ranked[0].unavailable_semantic_roles == (
        "per_unit_net_profit",
    )


def test_legacy_read_is_explicit_and_does_not_treat_group_order_as_rank(
    tmp_path,
) -> None:
    path = tmp_path / "legacy.db"
    command, groups = prepare_completion_lineage(path)
    results = SQLiteDiscoveryResultRepository(path)
    results.save_result(
        DiscoveryExecutionResult(
            command_id=command.command_id,
            discovery_execution_id=command.discovery_execution_id,
            finalized_group_ids=tuple(group.finalized_group_id for group in groups),
            completed_at=groups[-1].finalized_at + timedelta(minutes=1),
        )
    )
    results.close()
    query, repositories = reader(path)
    try:
        result = query.get_screening_ranking("execution-1")
    finally:
        close_all(*repositories)

    assert result.screening_status is (
        DiscoveryScreeningRecordingState.SCREENING_NOT_RECORDED_LEGACY
    )
    assert result.ranking_publication is None
    assert result.ranked == result.not_ranked == ()


def test_missing_execution_and_corrupt_screening_fail_closed(tmp_path) -> None:
    missing_reader, missing_repositories = reader(tmp_path / "missing.db")
    try:
        with pytest.raises(DiscoveryExecutionResultNotFound):
            missing_reader.get_screening_ranking("missing")
    finally:
        close_all(*missing_repositories)

    path = tmp_path / "corrupt.db"
    expected = prepare_bundle(path)
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    repository.save_completion_bundle(expected)
    repository._connection.execute(
        "DROP TRIGGER trg_discovery_screening_ranking_publication_history_no_update"
    )
    repository._connection.execute(
        "UPDATE discovery_screening_ranking_publication_history "
        "SET integrity_fingerprint=?",
        ("a" * 64,),
    )
    repository._connection.commit()
    repository.close()
    corrupt_reader, corrupt_repositories = reader(path)
    try:
        with pytest.raises(RuntimeError, match="malformed"):
            corrupt_reader.get_screening_ranking("execution-1")
    finally:
        close_all(*corrupt_repositories)


def test_read_capability_has_no_runtime_policy_collector_or_write_dependency(
    tmp_path,
) -> None:
    path = tmp_path / "pure-read.db"
    expected = prepare_bundle(path)
    repository = SQLiteDiscoveryScreeningCompletionRepository(path)
    repository.save_completion_bundle(expected)
    repository.close()
    query, repositories = reader(path)
    before = tuple(item._connection.total_changes for item in repositories)
    try:
        first = query.get_screening_ranking("execution-1")
        second = query.get_screening_ranking("execution-1")
        after = tuple(item._connection.total_changes for item in repositories)
    finally:
        close_all(*repositories)

    assert first == second
    assert before == after
    for forbidden in (
        "_runtime",
        "_collector",
        "_policy_resolver",
        "_identity_provider",
        "_clock",
    ):
        assert not hasattr(query, forbidden)
