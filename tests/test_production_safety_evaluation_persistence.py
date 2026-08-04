from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
import sqlite3

import pytest

from app.application.production_safety_evaluation import *
from app.application.production_safety_evaluation import (
    MalformedProductionSafetyEvaluationPersistenceError,
    PRODUCTION_SAFETY_EVALUATION_SCHEMA_VERSION,
    UnsupportedProductionSafetyEvaluationVersionError,
)
from app.application.decision_readiness import DecisionReadinessService
from app.application.production_safety_runtime_adapter import ProductionSafetyRuntimeAdapter
from app.domain.opportunity import ProductionSafetyAssessment, ProductionSafetyStatus
from app.infrastructure.production_safety_evaluation import SQLiteProductionSafetyEvaluationRepository
from app.infrastructure.snapshot_chain import SQLiteSnapshotChainBindingRepository
from test_candidate_issuance_foundation import Counter
from test_snapshot_chain_binding_persistence import BOUND, boundary as chain_boundary, command as chain_command, prepare


EVALUATED = BOUND + timedelta(minutes=1)
COMMITTED = BOUND + timedelta(minutes=2)


def command(**changes):
    values = {
        "command_id": "safety-command-1",
        "opportunity_id": "opportunity-1",
        "snapshot_chain_binding_id": "chain-binding-1",
        "selected_product_snapshot_id": "product-1",
        "requested_at": BOUND + timedelta(seconds=10),
    }
    values.update(changes)
    return EvaluateAndPersistProductionSafetyCommand(**values)


def seed(path):
    prepare(path)
    with SQLiteSnapshotChainBindingRepository(path) as repository:
        chain_boundary(repository).execute(chain_command())


def service(repository, *, evaluator=None, evaluation_id="safety-evaluation-1"):
    adapter = ProductionSafetyRuntimeAdapter(
        repository._chains._owners._sources,
        supported_analyzer_version="price-analyzer-v1",
        supported_calculation_version="verified-economics-calculator-v1",
    )
    options = {} if evaluator is None else {"evaluator": evaluator}
    return EvaluateAndPersistProductionSafety(
        repository,
        adapter,
        evaluation_id_generator=Counter(evaluation_id),
        evaluated_clock=Counter(EVALUATED),
        committed_clock=Counter(COMMITTED),
        **options,
    )


def counts(repository):
    tables = (
        "production_safety_evaluation_history",
        "production_safety_evaluation_provenance",
        "production_safety_evaluation_current",
        "production_safety_evaluation_receipts",
    )
    return tuple(repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in tables)


def test_command_is_immutable_explicit_and_fingerprint_is_deterministic():
    value = command()
    assert value.fingerprint == command().fingerprint
    with pytest.raises(FrozenInstanceError):
        value.opportunity_id = "changed"
    with pytest.raises(ValueError):
        command(selected_product_snapshot_id=" ")
    with pytest.raises(ValueError):
        command(requested_at=BOUND.replace(tzinfo=None))


@pytest.mark.parametrize(
    "assessment",
    (
        ProductionSafetyAssessment(ProductionSafetyStatus.READY),
        ProductionSafetyAssessment(ProductionSafetyStatus.INSUFFICIENT_DATA, ("shipping_cost",)),
        ProductionSafetyAssessment(ProductionSafetyStatus.PROFITABILITY_FAILED, (), ("profitability_filter",)),
    ),
)
def test_engine_assessment_is_preserved_without_override(tmp_path, assessment):
    path = tmp_path / f"{assessment.status}.db"
    seed(path)
    calls = []
    def evaluator(**runtime):
        calls.append(runtime)
        return assessment
    with SQLiteProductionSafetyEvaluationRepository(path) as repository:
        result = service(repository, evaluator=evaluator).execute(command())
        assert result.evaluation.assessment == assessment
        assert len(calls) == 1


def test_existing_engine_runs_once_and_exact_provenance_round_trips(tmp_path):
    path = tmp_path / "round-trip.db"
    seed(path)
    with SQLiteProductionSafetyEvaluationRepository(path) as repository:
        result = service(repository).execute(command())
        assert counts(repository) == (1, 1, 1, 1)
        assert result.evaluation.assessment.status is ProductionSafetyStatus.READY
        assert result.provenance.snapshot_chain_binding_id == "chain-binding-1"
        assert result.provenance.selected_product_snapshot_id == "product-1"
        assert result.provenance.price_intelligence_snapshot_id == "price-intelligence-1"
        assert result.provenance.economics_calculation_snapshot_id == "economics-owner-snapshot-1"
        assert repository.get_current_production_safety_evaluation("opportunity-1") == result.evaluation
    with SQLiteProductionSafetyEvaluationRepository(path) as repository:
        assert repository.get_evaluation("safety-evaluation-1") == result.evaluation
        assert repository.get_provenance("safety-evaluation-1") == result.provenance
        assert repository.get_by_command("safety-command-1").receipt == result.receipt


def test_response_loss_replay_does_not_reconstruct_execute_generate_or_reclock(tmp_path):
    path = tmp_path / "replay.db"
    seed(path)
    with SQLiteProductionSafetyEvaluationRepository(path) as repository:
        first = service(repository).execute(command())
    class Fail:
        def __call__(self, *args, **kwargs):
            raise AssertionError("must not be called during replay")
    with SQLiteProductionSafetyEvaluationRepository(path) as repository:
        adapter = Fail()
        replay = EvaluateAndPersistProductionSafety(
            repository, adapter,
            evaluation_id_generator=Fail(), evaluated_clock=Fail(), committed_clock=Fail(),
            evaluator=Fail(),
        ).execute(command())
        assert replay.replayed and replay.evaluation == first.evaluation and replay.receipt == first.receipt
        assert counts(repository) == (1, 1, 1, 1)


def test_command_conflict_alias_and_selected_product_version(tmp_path):
    path = tmp_path / "version.db"
    seed(path)
    with SQLiteProductionSafetyEvaluationRepository(path) as repository:
        first = service(repository).execute(command())
        with pytest.raises(ProductionSafetyEvaluationCommandConflictError):
            service(repository).execute(replace(command(), selected_product_snapshot_id="product-2"))
        alias = service(repository, evaluation_id="unused").execute(replace(command(), command_id="safety-command-2"))
        second = service(repository, evaluation_id="safety-evaluation-2").execute(
            replace(command(), command_id="safety-command-3", selected_product_snapshot_id="product-2")
        )
        assert alias.evaluation == first.evaluation
        assert second.evaluation.evaluation_version == 2
        assert repository.get_current_production_safety_evaluation("opportunity-1") == second.evaluation
        assert counts(repository) == (2, 2, 1, 3)


@pytest.mark.parametrize(
    "phase,error",
    (
        ("history", ProductionSafetyEvaluationHistoryError),
        ("provenance", ProductionSafetyProvenancePersistenceError),
        ("current", ProductionSafetyCurrentProjectionError),
        ("receipt", ProductionSafetyReceiptPersistenceError),
        ("commit", ProductionSafetyEvaluationCommitError),
    ),
)
def test_atomic_failure_matrix(tmp_path, phase, error):
    path = tmp_path / f"{phase}.db"
    seed(path)
    with SQLiteProductionSafetyEvaluationRepository(path) as repository:
        method = {
            "history": "_insert_history", "provenance": "_insert_provenance",
            "current": "_project_current", "receipt": "_insert_receipt", "commit": "_commit",
        }[phase]
        setattr(repository, method, lambda *_: (_ for _ in ()).throw(sqlite3.OperationalError(phase)))
        source_before = tuple(repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in (
            "opportunity_snapshot_chain_binding_history", "product_observation_snapshot_history",
            "price_intelligence_snapshot_history", "economics_calculation_snapshot_history",
        ))
        with pytest.raises(error):
            service(repository).execute(command())
        assert counts(repository) == (0, 0, 0, 0)
        assert not repository._connection.in_transaction
        assert source_before == tuple(repository._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in (
            "opportunity_snapshot_chain_binding_history", "product_observation_snapshot_history",
            "price_intelligence_snapshot_history", "economics_calculation_snapshot_history",
        ))


def test_missing_chain_opportunity_and_product_conflicts_are_explicit(tmp_path):
    path = tmp_path / "lineage.db"
    seed(path)
    with SQLiteProductionSafetyEvaluationRepository(path) as repository:
        with pytest.raises(ProductionSafetyChainNotFoundError):
            service(repository).execute(command(snapshot_chain_binding_id="missing"))
        with pytest.raises(ProductionSafetySelectedProductConflictError):
            service(repository).execute(command(selected_product_snapshot_id="missing"))
        with pytest.raises(ProductionSafetySourceLineageError):
            service(repository).execute(command(opportunity_id="other"))
        assert counts(repository) == (0, 0, 0, 0)


def test_append_only_read_only_and_same_subject_concurrency(tmp_path):
    path = tmp_path / "race.db"
    seed(path)
    def execute(index):
        with SQLiteProductionSafetyEvaluationRepository(path) as repository:
            return service(repository, evaluation_id=f"safety-evaluation-{index}").execute(
                replace(command(), command_id=f"safety-command-{index}")
            )
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(execute, (1, 2)))
    assert results[0].evaluation == results[1].evaluation
    with SQLiteProductionSafetyEvaluationRepository(path) as repository:
        assert counts(repository) == (1, 1, 1, 2)
        before = counts(repository)
        repository.get_by_opportunity("opportunity-1")
        repository.get_by_subject("chain-binding-1", "product-1")
        repository.get_receipts_by_evaluation(results[0].evaluation.evaluation_id)
        assert counts(repository) == before and not repository._connection.in_transaction
        for table in (
            "production_safety_evaluation_history",
            "production_safety_evaluation_provenance",
            "production_safety_evaluation_receipts",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                repository._connection.execute(f"DELETE FROM {table}")
            repository._connection.rollback()


def test_decision_readiness_uses_operational_current_and_ignores_legacy_row(tmp_path):
    path = tmp_path / "readiness.db"
    seed(path)
    class Assessments:
        def get_latest_competition_assessment_snapshot(self, identity): return None
        def get_latest_demand_assessment_snapshot(self, identity): return None
        def get_human_verified_external_signals_by_ids(self, identity, ids): return ()
    class Reviews:
        def list_opportunity_bindings(self, opportunity_id): return ()
    with SQLiteProductionSafetyEvaluationRepository(path) as repository:
        sources = repository._chains._owners._sources
        before = DecisionReadinessService(sources, Assessments(), Reviews(), repository).execute("opportunity-1")
        assert before["sources"]["production_safety"]["status"] == "missing"
        service(repository).execute(command())
        after = DecisionReadinessService(sources, Assessments(), Reviews(), repository).execute("opportunity-1")
        assert after["sources"]["production_safety"]["status"] == "ready"


def test_unsupported_and_malformed_operational_rows_are_explicit(tmp_path):
    path = tmp_path / "malformed.db"
    seed(path)
    with SQLiteProductionSafetyEvaluationRepository(path) as repository:
        service(repository).execute(command())
        repository._connection.execute("DROP TRIGGER trg_production_safety_evaluation_history_no_update")
        repository._connection.execute(
            "UPDATE production_safety_evaluation_history SET evaluation_schema_version='future'"
        )
        repository._connection.commit()
        with pytest.raises(UnsupportedProductionSafetyEvaluationVersionError):
            repository.get_evaluation("safety-evaluation-1")
        repository._connection.execute(
            "UPDATE production_safety_evaluation_history SET evaluation_schema_version=?, subject_fingerprint='broken'",
            (PRODUCTION_SAFETY_EVALUATION_SCHEMA_VERSION,),
        )
        repository._connection.commit()
        with pytest.raises(MalformedProductionSafetyEvaluationPersistenceError):
            repository.get_evaluation("safety-evaluation-1")


def test_failed_next_version_preserves_previous_current(tmp_path):
    path = tmp_path / "preserve-current.db"
    seed(path)
    with SQLiteProductionSafetyEvaluationRepository(path) as repository:
        first = service(repository).execute(command()).evaluation
        repository._insert_receipt = lambda *_: (_ for _ in ()).throw(sqlite3.OperationalError("receipt"))
        with pytest.raises(ProductionSafetyReceiptPersistenceError):
            service(repository, evaluation_id="safety-evaluation-2").execute(
                replace(command(), command_id="safety-command-2", selected_product_snapshot_id="product-2")
            )
        assert repository.get_current_production_safety_evaluation("opportunity-1") == first
        assert counts(repository) == (1, 1, 1, 1)


def test_concurrent_different_products_create_contiguous_versions(tmp_path):
    path = tmp_path / "product-race.db"
    seed(path)
    commands = (
        command(),
        replace(command(), command_id="safety-command-2", selected_product_snapshot_id="product-2"),
    )
    def execute(index_command):
        index, value = index_command
        with SQLiteProductionSafetyEvaluationRepository(path) as repository:
            return service(repository, evaluation_id=f"safety-evaluation-{index}").execute(value)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(execute, enumerate(commands, 1)))
    assert sorted(result.evaluation.evaluation_version for result in results) == [1, 2]
    with SQLiteProductionSafetyEvaluationRepository(path) as repository:
        assert counts(repository) == (2, 2, 1, 2)
