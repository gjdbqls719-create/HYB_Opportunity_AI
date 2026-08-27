from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application.discovery import (
    PersistedDiscoveryExecutionEntry,
)
from app.application.discovery_persistence import PersistDiscoveryCommand
from app.domain.discovery import (
    DiscoveryScreeningRecordingState,
    ScreeningProvenanceKind,
)
from app.infrastructure.discovery import (
    OrchestratorProductionDiscoveryRuntime,
    SQLiteDiscoveryCommandRepository,
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
    SQLiteDiscoveryResultRepository,
    SQLiteDiscoveryScreeningCompletionRepository,
)
from app.models import Product, ProductDataSource
from collectors.collection_fact import CollectionFact
from collectors.descriptor import CollectorDescriptor
from engine import orchestrator
from tests.test_application_group_finalization import (
    RecordingFinalizedGroupIdentityProvider,
    RecordingGroupFinalizationClock,
)
from tests.test_discovery_execution_completion import (
    RecordingDiscoveryCompletionClock,
)
from tests.test_persisted_discovery_execution_entry import (
    NOW,
    RecordingObservationIdentityProvider,
    command,
)


COMPLETED_AT = datetime(2026, 8, 27, 3, tzinfo=timezone.utc)
OBSERVED_AT = datetime(2026, 8, 27, 2, tzinfo=timezone.utc)
COLLECTOR = CollectorDescriptor("ebay", "pr6-deterministic-provider-v1")


class DeterministicScreeningIdentityProvider:
    def __init__(self) -> None:
        self.evaluation_calls = 0
        self.publication_calls = 0

    def provide_screening_evaluation_id(self) -> str:
        self.evaluation_calls += 1
        return f"screening-evaluation-{self.evaluation_calls}"

    def provide_screening_ranking_publication_id(self) -> str:
        self.publication_calls += 1
        return f"screening-publication-{self.publication_calls}"


class ForbiddenRuntime:
    def __init__(self) -> None:
        self.calls = 0

    def execute(self, *args, **kwargs):
        self.calls += 1
        pytest.fail("completed replay must not call the production runtime")


class ForbiddenScreeningIdentityProvider:
    def provide_screening_evaluation_id(self) -> str:
        pytest.fail("completed replay must not generate evaluation identities")

    def provide_screening_ranking_publication_id(self) -> str:
        pytest.fail("completed replay must not generate publication identities")


def production_command():
    value = command()
    return replace(
        value,
        parameters=replace(
            value.parameters,
            target_currency=None,
            shipping_cost=None,
            fixed_fee=None,
            fixed_fee_known=False,
        ),
    )


def product(item_id: str, title: str, price: float, rating: float) -> Product:
    return Product(
        marketplace="ebay",
        item_id=item_id,
        title=title,
        price=price,
        currency="USD",
        condition="new",
        url=f"https://example.test/{item_id}",
        shipping_cost=None,
        rating=rating,
        review_count=100,
        in_stock=True,
        data_source=ProductDataSource.PRODUCTION,
    )


def install_fake_collector(monkeypatch, products) -> None:
    def search_products(*args, collection_fact_sink=None, **kwargs):
        for value in products:
            if collection_fact_sink is not None:
                collection_fact_sink(
                    CollectionFact(
                        product=value,
                        observed_at=OBSERVED_AT,
                        collector_descriptor=COLLECTOR,
                        source_reference=value.url,
                    )
                )
        return list(products)

    monkeypatch.setattr(orchestrator, "search_products", search_products)


def open_entry(
    path,
    *,
    runtime,
    screening_repository=None,
    screening_identity_provider=None,
    replay: bool = False,
):
    commands = SQLiteDiscoveryCommandRepository(path)
    observations = SQLiteDiscoveryObservationRepository(path)
    groups = SQLiteDiscoveryGroupRepository(path)
    results = SQLiteDiscoveryResultRepository(path)
    completion = screening_repository or SQLiteDiscoveryScreeningCompletionRepository(
        path
    )
    entry = PersistedDiscoveryExecutionEntry(
        persist_command=PersistDiscoveryCommand(
            commands,
            clock=(
                (lambda: pytest.fail("command replay must not call the clock"))
                if replay
                else (lambda: NOW)
            ),
        ),
        runtime=runtime,
        observation_identity_provider=RecordingObservationIdentityProvider(
            "observation-1",
            "observation-2",
        ),
        observation_repository=observations,
        finalized_group_identity_provider=(
            RecordingFinalizedGroupIdentityProvider("group-1", "group-2")
        ),
        group_finalization_clock=(
            (lambda: pytest.fail("completed replay must not finalize Groups"))
            if replay
            else RecordingGroupFinalizationClock(COMPLETED_AT, COMPLETED_AT)
        ),
        group_repository=groups,
        discovery_completion_clock=(
            (lambda: pytest.fail("completed replay must not use current time"))
            if replay
            else RecordingDiscoveryCompletionClock(COMPLETED_AT)
        ),
        result_repository=results,
        screening_completion_repository=completion,
        screening_identity_provider=(
            screening_identity_provider
            or DeterministicScreeningIdentityProvider()
        ),
    )
    return entry, (commands, observations, groups, results, completion)


def close_all(repositories) -> None:
    seen = set()
    for repository in repositories:
        if id(repository) not in seen:
            repository.close()
            seen.add(id(repository))


def production_runtime() -> OrchestratorProductionDiscoveryRuntime:
    return OrchestratorProductionDiscoveryRuntime(
        finder=orchestrator.find_best_opportunities
    )


def test_first_production_execution_persists_exact_screening_bundle(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "production-screening.db"
    install_fake_collector(
        monkeypatch,
        (
            product("camera", "Alpha Camera Model A", 100, 4.8),
            product("drill", "Industrial Drill Model Z", 20, 3.7),
        ),
    )
    entry, repositories = open_entry(path, runtime=production_runtime())
    try:
        response = entry.execute(production_command())
        persisted = repositories[-1].get_by_execution("execution-1")
    finally:
        close_all(repositories)

    assert response.screening_recording_state is DiscoveryScreeningRecordingState.RECORDED
    assert response.screening_completion == persisted
    assert persisted is not None
    assert persisted.execution_result == response.execution_result
    assert tuple(group.finalized_group_id for group in persisted.finalized_groups) == (
        "group-1",
        "group-2",
    )
    assert tuple(value.finalized_group_id for value in persisted.evaluations) == (
        "group-1",
        "group-2",
    )
    assert tuple(
        entry.finalized_group_id
        for entry in persisted.ranking_publication.ranked_entries
    ) == tuple(value.finalized_group_id for value in response.discovery_results)
    assert tuple(
        value.rank for value in persisted.ranking_publication.ranked_entries
    ) == (1, 2)
    assert persisted.ranking_publication.not_ranked_entries == ()
    assert persisted.ranking_publication.ranking_policy.policy_version == "1.0.0"

    groups = {
        value.finalized_group_id: value for value in persisted.finalized_groups
    }
    for evaluation in persisted.evaluations:
        assert evaluation.group_membership_fingerprint == (
            groups[evaluation.finalized_group_id].membership_fingerprint
        )
        assert evaluation.screening_policy_manifest.score.policy_version == "1.0.0"
        assert evaluation.screening_policy_manifest.recommendation.policy_version == "1.0.0"
        assert evaluation.screening_recommendation.structured_reasons
        inputs = {
            value.input_reference_id: value.evidence
            for value in evaluation.input_manifest.inputs
        }
        assert inputs["input.competitor_count"].provenance_kind is (
            ScreeningProvenanceKind.POLICY_ASSUMPTION
        )
        assert inputs["input.estimated_monthly_sales"].provenance_kind is (
            ScreeningProvenanceKind.POLICY_ASSUMPTION
        )
        assert inputs["input.competitor_count"].method_reference.policy_name == (
            "production-discovery-screening-score"
        )
        assert inputs["input.marketplace_fee_rate"].method_reference.policy_name == (
            "production-discovery-runtime-economics"
        )
        assert inputs["input.marketplace_fee_known"].method_reference.policy_name == (
            "production-discovery-safety-gate"
        )
        assert inputs["input.shipping_cost"].provenance_kind is (
            ScreeningProvenanceKind.UNKNOWN
        )
        assert inputs["input.shipping_cost"].value is None
        assert inputs["input.shipping_cost_calculation_fallback"].value == 0
        assert evaluation.final_opportunity_score.provenance_kind is (
            ScreeningProvenanceKind.CALCULATED
        )
        assert evaluation.ranking_economics_key.provenance_kind is (
            ScreeningProvenanceKind.CALCULATED
        )
        source_identities = {
            source.source_identity
            for item in evaluation.input_manifest.inputs
            for source in item.evidence.source_references
        }
        assert "policy-v3" not in source_identities
        assert "ebay-us" not in source_identities


def test_completed_screening_replay_restores_exact_bundle_without_runtime_or_suppliers(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "runtime-free.db"
    install_fake_collector(
        monkeypatch,
        (product("one", "Only Product", 50, 4.8),),
    )
    first_entry, first_repositories = open_entry(path, runtime=production_runtime())
    first = first_entry.execute(production_command())
    close_all(first_repositories)

    runtime = ForbiddenRuntime()
    replay_entry, replay_repositories = open_entry(
        path,
        runtime=runtime,
        screening_identity_provider=ForbiddenScreeningIdentityProvider(),
        replay=True,
    )
    try:
        replay = replay_entry.execute(production_command())
    finally:
        close_all(replay_repositories)

    assert runtime.calls == 0
    assert replay.completion_replayed is True
    assert replay.discovery_results == ()
    assert replay.screening_recording_state is DiscoveryScreeningRecordingState.RECORDED
    assert replay.screening_completion == first.screening_completion
    assert tuple(
        value.integrity_fingerprint
        for value in replay.screening_completion.evaluations
    ) == tuple(
        value.integrity_fingerprint
        for value in first.screening_completion.evaluations
    )
    assert (
        replay.screening_completion.ranking_publication.integrity_fingerprint
        == first.screening_completion.ranking_publication.integrity_fingerprint
    )


def test_currency_normalization_preserves_values_and_exposes_rate_provenance_limit(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "normalized.db"
    install_fake_collector(
        monkeypatch,
        (product("one", "Only Product", 50, 4.8),),
    )

    class FixedConverter:
        def convert(self, amount, source, target):
            assert (source, target) == ("USD", "KRW")
            return Decimal(str(amount)) * Decimal("1000")

    runtime = OrchestratorProductionDiscoveryRuntime(
        finder=orchestrator.find_best_opportunities,
        currency_converter=FixedConverter(),
    )
    entry, repositories = open_entry(path, runtime=runtime)
    value = production_command()
    value = replace(
        value,
        parameters=replace(value.parameters, target_currency="KRW"),
    )
    try:
        response = entry.execute(value)
    finally:
        close_all(repositories)

    evaluation = response.screening_completion.evaluations[0]
    inputs = {
        item.input_reference_id: item.evidence
        for item in evaluation.input_manifest.inputs
    }
    assert inputs["input.purchase_price"].value == Decimal("50000")
    assert inputs["input.purchase_price"].currency == "KRW"
    assert inputs["input.target_currency"].value == "KRW"
    assert inputs["input.currency_conversion_provenance"].provenance_kind is (
        ScreeningProvenanceKind.UNSUPPORTED
    )
    assert inputs["input.currency_conversion_provenance"].value is None
    assert "input.currency_conversion_provenance" in (
        inputs["input.purchase_price"].dependency_references
    )


def test_legacy_completed_result_remains_explicit_and_is_not_backfilled(
    tmp_path,
) -> None:
    path = tmp_path / "legacy.db"
    commands = SQLiteDiscoveryCommandRepository(path)
    observations = SQLiteDiscoveryObservationRepository(path)
    groups = SQLiteDiscoveryGroupRepository(path)
    results = SQLiteDiscoveryResultRepository(path)

    class EmptyRuntime:
        def execute(self, value, *, collection_checkpoint_handler, grouping_checkpoint_handler):
            collection_checkpoint_handler(())
            grouping_checkpoint_handler((), orchestrator.PRODUCTION_GROUPING_POLICY_DESCRIPTOR)
            from app.application.discovery import ProductionDiscoveryRuntimeResult

            return ProductionDiscoveryRuntimeResult(value.discovery_execution_id, (), ())

    legacy_entry = PersistedDiscoveryExecutionEntry(
        persist_command=PersistDiscoveryCommand(commands, clock=lambda: NOW),
        runtime=EmptyRuntime(),
        observation_identity_provider=RecordingObservationIdentityProvider(),
        observation_repository=observations,
        finalized_group_identity_provider=RecordingFinalizedGroupIdentityProvider(),
        group_finalization_clock=RecordingGroupFinalizationClock(),
        group_repository=groups,
        discovery_completion_clock=RecordingDiscoveryCompletionClock(COMPLETED_AT),
        result_repository=results,
    )
    legacy_entry.execute(production_command())
    close_all((commands, observations, groups, results))
    runtime = ForbiddenRuntime()
    replay_entry, replay_repositories = open_entry(
        path,
        runtime=runtime,
        screening_identity_provider=ForbiddenScreeningIdentityProvider(),
        replay=True,
    )
    try:
        replay = replay_entry.execute(production_command())
        state = replay_repositories[-1].get_recording_state("execution-1")
    finally:
        close_all(replay_repositories)

    assert runtime.calls == 0
    assert replay.completion_replayed is True
    assert replay.screening_completion is None
    assert replay.screening_recording_state is (
        DiscoveryScreeningRecordingState.SCREENING_NOT_RECORDED_LEGACY
    )
    assert state is DiscoveryScreeningRecordingState.SCREENING_NOT_RECORDED_LEGACY


def test_completion_failure_leaves_checkpoints_but_no_partial_success_and_retry_succeeds(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "failure-retry.db"
    install_fake_collector(
        monkeypatch,
        (product("one", "Only Product", 50, 4.8),),
    )

    class FailingCompletionRepository(SQLiteDiscoveryScreeningCompletionRepository):
        def _fault_point(self, name: str) -> None:
            if name == "before_commit":
                raise RuntimeError("screening completion failed")

    failing_repository = FailingCompletionRepository(path)
    failed_entry, failed_repositories = open_entry(
        path,
        runtime=production_runtime(),
        screening_repository=failing_repository,
    )
    with pytest.raises(RuntimeError, match="screening completion failed"):
        failed_entry.execute(production_command())
    assert failed_repositories[1].get_by_execution("execution-1")
    assert failed_repositories[2].get_by_execution("execution-1")
    assert failed_repositories[3].get_by_execution("execution-1") is None
    assert failing_repository.get_by_execution("execution-1") is None
    close_all(failed_repositories)

    retry_entry, retry_repositories = open_entry(path, runtime=production_runtime())
    try:
        retry = retry_entry.execute(production_command())
        persisted = retry_repositories[-1].get_by_execution("execution-1")
    finally:
        close_all(retry_repositories)
    assert retry.completion_replayed is False
    assert persisted == retry.screening_completion


def test_screening_construction_failure_cannot_commit_an_unbound_success(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "construction-failure.db"
    install_fake_collector(
        monkeypatch,
        (product("one", "Only Product", 50, 4.8),),
    )

    class MissingPolicyRuntime:
        def __init__(self) -> None:
            self.runtime = production_runtime()

        def execute(self, *args, **kwargs):
            result = self.runtime.execute(*args, **kwargs)
            return replace(
                result,
                discovery_results=tuple(
                    replace(value, screening_policy_descriptors=None)
                    for value in result.discovery_results
                ),
            )

    entry, repositories = open_entry(path, runtime=MissingPolicyRuntime())
    from app.application.discovery import DiscoveryScreeningConstructionError

    try:
        with pytest.raises(
            DiscoveryScreeningConstructionError,
            match="PR3 screening semantics",
        ):
            entry.execute(production_command())
        assert repositories[1].get_by_execution("execution-1")
        assert repositories[2].get_by_execution("execution-1")
        assert repositories[3].get_by_execution("execution-1") is None
        assert repositories[-1].get_by_execution("execution-1") is None
    finally:
        close_all(repositories)


def test_corrupt_screening_replay_fails_closed_without_runtime_fallback(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "corrupt.db"
    install_fake_collector(
        monkeypatch,
        (product("one", "Only Product", 50, 4.8),),
    )
    first_entry, first_repositories = open_entry(path, runtime=production_runtime())
    first_entry.execute(production_command())
    completion = first_repositories[-1]
    completion._connection.execute(
        "DROP TRIGGER trg_discovery_screening_evaluation_history_no_update"
    )
    completion._connection.execute(
        "UPDATE discovery_screening_evaluation_history "
        "SET integrity_fingerprint=?",
        ("a" * 64,),
    )
    completion._connection.commit()
    close_all(first_repositories)

    runtime = ForbiddenRuntime()
    replay_entry, replay_repositories = open_entry(
        path,
        runtime=runtime,
        screening_identity_provider=ForbiddenScreeningIdentityProvider(),
        replay=True,
    )
    from app.application.discovery import MalformedDiscoveryScreeningPersistenceError

    try:
        with pytest.raises(MalformedDiscoveryScreeningPersistenceError):
            replay_entry.execute(production_command())
    finally:
        close_all(replay_repositories)
    assert runtime.calls == 0


def test_zero_result_persists_and_replays_an_empty_authoritative_publication(
    tmp_path,
    monkeypatch,
) -> None:
    path = tmp_path / "zero.db"
    install_fake_collector(monkeypatch, ())
    first_entry, first_repositories = open_entry(path, runtime=production_runtime())
    first = first_entry.execute(production_command())
    close_all(first_repositories)

    assert first.execution_result.is_zero_result is True
    assert first.screening_completion.evaluations == ()
    assert first.screening_completion.ranking_publication.zero_result is True
    assert first.screening_completion.ranking_publication.ranked_entries == ()

    runtime = ForbiddenRuntime()
    replay_entry, replay_repositories = open_entry(
        path,
        runtime=runtime,
        screening_identity_provider=ForbiddenScreeningIdentityProvider(),
        replay=True,
    )
    try:
        replay = replay_entry.execute(production_command())
    finally:
        close_all(replay_repositories)
    assert runtime.calls == 0
    assert replay.screening_completion == first.screening_completion
    assert replay.screening_recording_state is DiscoveryScreeningRecordingState.RECORDED
