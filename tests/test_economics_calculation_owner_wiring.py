from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError,replace
from datetime import timedelta
import sqlite3

import pytest

from app.application.economics_calculation_owner import (
    CalculateAndPersistEconomics,CalculateAndPersistEconomicsCommand,
    EconomicsCalculationBindingConflictError,EconomicsCalculationCommandConflictError,
    EconomicsCalculationExecutionError,EconomicsCalculationMarketIdentityConflictError,
    EconomicsCalculationOwnerCommitError,EconomicsCalculationPriceSourceConflictError,
    EconomicsCalculationReceiptPersistenceError,EconomicsCalculationSourceContext,
    EconomicsCalculationSourceNotFoundError,UnsupportedEconomicsCalculationReceiptVersionError,
)
from app.application.economics_calculation_snapshot import EconomicsCalculationSnapshotHistoryError
from app.infrastructure.economics_calculation import SQLiteEconomicsCalculationOwnerRepository
from engine.opportunity import calculate_verified_economics
from test_candidate_issuance_foundation import Counter
from test_economics_calculation_snapshot import NOW,parameters
from test_economics_calculation_snapshot_sqlite import cleanup,setup


GENERATED=NOW+timedelta(minutes=20)

def prepare(path):
    sources,candidates,validation,repo=setup(path);cleanup(sources,candidates,validation,repo)

def source(**changes):
    from test_candidate_issuance_foundation import issuance_command
    values={"opportunity_id":"opportunity-1","candidate_opportunity_binding_id":"binding-1","candidate_id":"candidate-1","price_intelligence_snapshot_id":"price-intelligence-1","price_analysis_command_id":"price-analysis-1","verified_economics_opportunity_id":"opportunity-1","market_observation_identity":issuance_command().market_observation_identity,"economics_calculation_command_id":"economics-owner-1","requested_at":NOW+timedelta(minutes=10)}
    values.update(changes);return EconomicsCalculationSourceContext(**values)

def command(**changes):
    values={"command_id":"economics-owner-1","source":source(),"calculation_parameters":parameters(),"calculation_version":"verified-economics-calculator-v1","requested_at":source().requested_at}
    values.update(changes);return CalculateAndPersistEconomicsCommand(**values)

def boundary(repo,*,snapshot_id="economics-owner-snapshot-1",calculator=calculate_verified_economics):
    return CalculateAndPersistEconomics(repo,snapshot_id_generator=Counter(snapshot_id),generated_clock=Counter(GENERATED),receipt_clock=Counter(GENERATED+timedelta(seconds=1)),calculator=calculator)

def counts(repo):return tuple(repo._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("economics_calculation_snapshot_history","economics_calculation_receipts"))

def test_source_and_command_are_immutable_versioned_and_fingerprinted(tmp_path):
    prepare(tmp_path/"contract.db");value=source();cmd=command()
    assert value==source() and cmd.fingerprint==command().fingerprint
    with pytest.raises(FrozenInstanceError):value.candidate_id="changed"
    with pytest.raises(ValueError):source(candidate_id="opportunity-1")
    with pytest.raises(ValueError):source(requested_at=NOW.replace(tzinfo=None))
    with pytest.raises(ValueError):command(command_id="different")

def test_exact_sources_calculator_arguments_result_parity_and_price_is_provenance_only(tmp_path):
    path=tmp_path/"owner.db";prepare(path);repo=SQLiteEconomicsCalculationOwnerRepository(path);seen=[]
    def calculator(**kwargs):seen.append(kwargs);return calculate_verified_economics(**kwargs)
    result=boundary(repo,calculator=calculator).execute(command());kwargs=seen[0]
    assert len(seen)==1 and kwargs["economics"]==repo._sources.get_verified_economics_snapshot("opportunity-1").inputs
    assert kwargs["context"]==dict(parameters().context_items) and "price" not in kwargs
    assert result.snapshot.price_intelligence_snapshot_id=="price-intelligence-1" and result.snapshot.candidate_id=="candidate-1"
    expected=calculate_verified_economics(**kwargs)
    for name in ("marketplace_fee","payment_fee","tax_cost","landed_cost","selling_cost","total_cost","net_profit","roi","landed_cost_roi","margin_rate"):assert getattr(result.snapshot,name)==getattr(expected,name)
    assert result.snapshot.analysis.to_runtime_mapping()==expected.analysis and counts(repo)==(1,1);repo.close()

def test_restart_response_loss_replay_calls_no_owner_dependencies(tmp_path):
    path=tmp_path/"replay.db";prepare(path);repo=SQLiteEconomicsCalculationOwnerRepository(path);first=boundary(repo).execute(command());repo.close()
    class Fail:
        def __call__(self,*_,**__):raise AssertionError("must not be called")
    repo=SQLiteEconomicsCalculationOwnerRepository(path);replay=CalculateAndPersistEconomics(repo,snapshot_id_generator=Fail(),generated_clock=Fail(),receipt_clock=Fail(),calculator=Fail()).execute(command())
    assert replay.replayed and replay.snapshot==first.snapshot and replay.receipt==first.receipt and counts(repo)==(1,1);repo.close()

def test_changed_price_parameters_and_version_conflict(tmp_path):
    path=tmp_path/"conflict.db";prepare(path);repo=SQLiteEconomicsCalculationOwnerRepository(path);boundary(repo).execute(command())
    changed_source=replace(source(),price_intelligence_snapshot_id="other")
    for changed in (replace(command(),source=changed_source),replace(command(),calculation_parameters=replace(parameters(),minimum_roi=parameters().minimum_roi+1)),replace(command(),calculation_version="v2")):
        with pytest.raises(EconomicsCalculationCommandConflictError):boundary(repo).execute(changed)
    assert counts(repo)==(1,1);repo.close()

def test_binding_market_and_price_receipt_lineage_errors_are_distinct(tmp_path):
    path=tmp_path/"lineage.db";prepare(path);repo=SQLiteEconomicsCalculationOwnerRepository(path)
    with pytest.raises(EconomicsCalculationBindingConflictError):repo.load_sources(replace(source(),candidate_id="other"))
    with pytest.raises(EconomicsCalculationMarketIdentityConflictError):repo.load_sources(replace(source(),market_observation_identity=replace(source().market_observation_identity,condition="used")))
    with pytest.raises(EconomicsCalculationSourceNotFoundError):repo.load_sources(replace(source(),price_intelligence_snapshot_id="missing"))
    with pytest.raises(EconomicsCalculationSourceNotFoundError):repo.load_sources(replace(source(),price_analysis_command_id="missing"))
    repo.close()

def test_calculator_failure_is_not_persistence_failure(tmp_path):
    path=tmp_path/"calculator.db";prepare(path);repo=SQLiteEconomicsCalculationOwnerRepository(path)
    def fail(**_):raise ValueError("formula input invalid")
    with pytest.raises(EconomicsCalculationExecutionError):boundary(repo,calculator=fail).execute(command())
    assert counts(repo)==(0,0);repo.close()

def test_distinct_commands_same_source_create_new_calculation_facts_and_queries(tmp_path):
    path=tmp_path/"repeat.db";prepare(path);repo=SQLiteEconomicsCalculationOwnerRepository(path);first=boundary(repo,snapshot_id="econ-1").execute(command())
    source2=replace(source(),economics_calculation_command_id="economics-owner-2")
    second=boundary(repo,snapshot_id="econ-2").execute(replace(command(),command_id="economics-owner-2",source=source2))
    assert first.snapshot.snapshot_id!=second.snapshot.snapshot_id and counts(repo)==(2,2)
    assert tuple(v.snapshot for v in repo.get_by_opportunity("opportunity-1"))==(first.snapshot,second.snapshot)
    assert tuple(v.snapshot for v in repo.get_by_price_snapshot("price-intelligence-1"))==(first.snapshot,second.snapshot);repo.close()

@pytest.mark.parametrize("phase,error",(("snapshot",EconomicsCalculationSnapshotHistoryError),("receipt",EconomicsCalculationReceiptPersistenceError),("commit",EconomicsCalculationOwnerCommitError)))
def test_atomic_failure_matrix(tmp_path,phase,error):
    path=tmp_path/f"{phase}.db";prepare(path);repo=SQLiteEconomicsCalculationOwnerRepository(path)
    if phase=="snapshot":repo._economics._insert=lambda *_:(_ for _ in ()).throw(sqlite3.OperationalError("snapshot"))
    elif phase=="receipt":repo._insert_receipt=lambda *_:(_ for _ in ()).throw(sqlite3.OperationalError("receipt"))
    else:repo._commit=lambda :(_ for _ in ()).throw(sqlite3.OperationalError("commit"))
    source_counts=tuple(repo._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("price_intelligence_snapshot_history","verified_economics_snapshots","opportunity_candidate_promotion_history"))
    with pytest.raises(error):boundary(repo).execute(command())
    assert counts(repo)==(0,0) and not repo._connection.in_transaction
    assert source_counts==tuple(repo._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("price_intelligence_snapshot_history","verified_economics_snapshots","opportunity_candidate_promotion_history"));repo.close()

def test_append_only_read_only_and_same_command_concurrency(tmp_path):
    path=tmp_path/"race.db";prepare(path)
    def execute():
        with SQLiteEconomicsCalculationOwnerRepository(path) as repo:return boundary(repo).execute(command())
    with ThreadPoolExecutor(max_workers=2) as pool:results=tuple(pool.map(lambda _:execute(),range(2)))
    assert sum(not v.replayed for v in results)==1 and results[0].snapshot==results[1].snapshot
    with SQLiteEconomicsCalculationOwnerRepository(path) as repo:
        before=counts(repo);assert repo.get_result(repo.get_receipt("economics-owner-1")).snapshot==results[0].snapshot and counts(repo)==before and not repo._connection.in_transaction
        for operation in ("UPDATE","DELETE"):
            statement="UPDATE economics_calculation_receipts SET rowid=rowid" if operation=="UPDATE" else "DELETE FROM economics_calculation_receipts"
            with pytest.raises(sqlite3.IntegrityError,match="append-only"):repo._connection.execute(statement)
            repo._connection.rollback()

def test_unsupported_receipt_version_is_explicit(tmp_path):
    path=tmp_path/"version.db";prepare(path);repo=SQLiteEconomicsCalculationOwnerRepository(path);boundary(repo).execute(command())
    repo._connection.execute("DROP TRIGGER trg_economics_owner_receipt_no_update");repo._connection.execute("UPDATE economics_calculation_receipts SET receipt_schema_version='future'");repo._connection.commit()
    with pytest.raises(UnsupportedEconomicsCalculationReceiptVersionError):repo.get_receipt("economics-owner-1")
    repo.close()
