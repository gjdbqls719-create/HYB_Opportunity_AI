from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import sqlite3
import inspect

import pytest

from app.application.economics_calculation_snapshot import (
    EconomicsCalculationSnapshotBindingMismatchError,
    EconomicsCalculationSnapshotBindingNotFoundError,
    EconomicsCalculationSnapshotCommitError, EconomicsCalculationSnapshotConflictError,
    EconomicsCalculationSnapshotHistoryError, EconomicsCalculationSnapshotMarketIdentityConflictError,
    EconomicsCalculationSnapshotOpportunityNotFoundError,
    EconomicsCalculationSnapshotVerifiedSourceNotFoundError,
    MalformedEconomicsCalculationSnapshotPersistenceError,
    UnsupportedEconomicsCalculationSnapshotVersionError,
)
from app.application.verified_economics_admission import (
    FinalizeVerifiedEconomicsAdmission, FinalizeVerifiedEconomicsAdmissionCommand,
)
from app.domain.decision_engine import OpportunityIdentity
from app.infrastructure.economics_calculation import SQLiteEconomicsCalculationSnapshotRepository
from test_candidate_issuance_persistence import close
from test_candidate_issuance_foundation import issuance_command
from test_candidate_opportunity_promotion import command as promotion_command, setup_boundary
from test_economics_calculation_snapshot import NOW, inputs, snapshot as foundation_snapshot


def setup(path,*,promote=True,verified=True):
    sources,candidates,validation,promotion=setup_boundary(path)
    if promote:promotion.execute(promotion_command())
    if promote and verified:
        FinalizeVerifiedEconomicsAdmission(validation).execute(FinalizeVerifiedEconomicsAdmissionCommand(
            "opportunity-1","verified-command-1","founder",inputs(),NOW))
    repo=SQLiteEconomicsCalculationSnapshotRepository(path)
    return sources,candidates,validation,repo


def snapshot(snapshot_id="economics-calculation-1"):
    base=foundation_snapshot()
    return replace(base,snapshot_id=snapshot_id,
        opportunity_identity=OpportunityIdentity("opportunity-1","collector:ebay:item-1"),
        market_observation_identity=promotion_market(),candidate_opportunity_binding_id="binding-1",
        verified_economics_opportunity_id="opportunity-1")


def promotion_market():return issuance_command().market_observation_identity
def count(repo):return repo._connection.execute("SELECT COUNT(*) FROM economics_calculation_snapshot_history").fetchone()[0]
def cleanup(sources,candidates,validation,repo):repo.close();validation.close();candidates.close();close(sources)


def test_schema_exact_round_trip_restart_and_no_current(tmp_path):
    path=tmp_path/"econ.db";sources,candidates,validation,repo=setup(path);value=snapshot()
    assert repo.save_snapshot(value)==value and repo.get_snapshot(value.snapshot_id)==value
    columns={row[1] for row in repo._connection.execute("PRAGMA table_info(economics_calculation_snapshot_history)")}
    assert {"snapshot_id","opportunity_id","discovery_reference","market_identity_payload_json","candidate_opportunity_binding_id","candidate_id","verified_economics_opportunity_id","calculation_results_payload_json","profitability_payload_json","calculation_parameters_payload_json","canonical_analysis_payload_json","analysis_fingerprint","analysis_schema_version","calculation_version","generated_at","snapshot_schema_version","payload_fingerprint","inserted_at"}==columns
    assert not repo._connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%economics_calculation_snapshot_current%'").fetchall()
    cleanup(sources,candidates,validation,repo);repo=SQLiteEconomicsCalculationSnapshotRepository(path)
    assert repo.get_snapshot(value.snapshot_id)==value;repo.close()


def test_exact_replay_conflict_and_repeated_calculation(tmp_path):
    path=tmp_path/"replay.db";sources,candidates,validation,repo=setup(path);value=snapshot()
    assert repo.save_snapshot(value)==value and repo.save_snapshot(value)==value and count(repo)==1
    with pytest.raises(EconomicsCalculationSnapshotConflictError):repo.save_snapshot(replace(value,calculation_version="changed"))
    second=replace(value,snapshot_id="economics-calculation-2",generated_at=value.generated_at+timedelta(seconds=1))
    assert repo.save_snapshot(second)==second and count(repo)==2
    cleanup(sources,candidates,validation,repo)


def test_typed_results_analysis_profitability_parameters_and_queries_round_trip(tmp_path):
    path=tmp_path/"typed.db";sources,candidates,validation,repo=setup(path);value=snapshot();repo.save_snapshot(value);loaded=repo.get_snapshot(value.snapshot_id)
    assert loaded==value and loaded.analysis.fingerprint==value.analysis.fingerprint
    assert isinstance(loaded.roi,Decimal) and loaded.calculation_parameters==value.calculation_parameters
    assert repo.get_by_opportunity(value.opportunity_identity)==(value,)
    assert repo.get_by_market_identity(value.market_observation_identity)==(value,)
    assert repo.get_by_verified_economics_source("opportunity-1")== (value,)
    cleanup(sources,candidates,validation,repo)


def test_missing_opportunity_binding_verified_and_identity_conflicts(tmp_path):
    path=tmp_path/"missing-opp.db";sources,candidates,validation,repo=setup(path,promote=False,verified=False)
    with pytest.raises(EconomicsCalculationSnapshotOpportunityNotFoundError):repo.save_snapshot(snapshot())
    cleanup(sources,candidates,validation,repo)
    path=tmp_path/"missing-verified.db";sources,candidates,validation,repo=setup(path,verified=False)
    with pytest.raises(EconomicsCalculationSnapshotVerifiedSourceNotFoundError):repo.save_snapshot(snapshot())
    with pytest.raises(EconomicsCalculationSnapshotBindingMismatchError):repo.save_snapshot(replace(snapshot(),candidate_opportunity_binding_id="other"))
    with pytest.raises(EconomicsCalculationSnapshotMarketIdentityConflictError):repo.save_snapshot(replace(snapshot(),market_observation_identity=replace(snapshot().market_observation_identity,marketplace_item_id="other")))
    cleanup(sources,candidates,validation,repo)


def test_existing_opportunity_without_candidate_binding_is_explicit(tmp_path):
    from test_opportunity_market_identity_binding import command,identity,service
    path=tmp_path/"binding.db";sources,candidates,validation,_=setup_boundary(path);service(validation).add(command(identity()))
    repo=SQLiteEconomicsCalculationSnapshotRepository(path)
    value=replace(snapshot(),opportunity_identity=OpportunityIdentity("opp-bound","ebay:item-1"),verified_economics_opportunity_id="opp-bound")
    with pytest.raises(EconomicsCalculationSnapshotBindingNotFoundError):repo.save_snapshot(value)
    cleanup(sources,candidates,validation,repo)


@pytest.mark.parametrize("phase,error_type",(("insert",EconomicsCalculationSnapshotHistoryError),("commit",EconomicsCalculationSnapshotCommitError)))
def test_atomic_failure_rolls_back_preserving_sources(tmp_path,phase,error_type):
    path=tmp_path/f"{phase}.db";sources,candidates,validation,repo=setup(path);before=source_counts(repo._connection)
    if phase=="insert":repo._insert=lambda *_:(_ for _ in ()).throw(sqlite3.OperationalError("forced"))
    else:repo._commit=lambda :(_ for _ in ()).throw(sqlite3.OperationalError("forced"))
    with pytest.raises(error_type):repo.save_snapshot(snapshot())
    assert count(repo)==0 and source_counts(repo._connection)==before and not repo._connection.in_transaction
    cleanup(sources,candidates,validation,repo)


def source_counts(connection):
    return tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in ("opportunity_lifecycles","opportunity_candidate_promotion_history","verified_economics_snapshots"))


@pytest.mark.parametrize("column,value,expected",(
    ("calculation_results_payload_json","{",MalformedEconomicsCalculationSnapshotPersistenceError),
    ("analysis_fingerprint","0"*64,MalformedEconomicsCalculationSnapshotPersistenceError),
    ("canonical_analysis_payload_json","{",MalformedEconomicsCalculationSnapshotPersistenceError),
    ("generated_at","naive",MalformedEconomicsCalculationSnapshotPersistenceError),
    ("payload_fingerprint","0"*64,MalformedEconomicsCalculationSnapshotPersistenceError),
    ("snapshot_schema_version","future",UnsupportedEconomicsCalculationSnapshotVersionError),
))
def test_malformed_persistence_is_explicit(tmp_path,column,value,expected):
    path=tmp_path/f"{column}.db";sources,candidates,validation,repo=setup(path);repo.save_snapshot(snapshot())
    repo._connection.execute("DROP TRIGGER trg_economics_calculation_snapshot_no_update")
    repo._connection.execute(f"UPDATE economics_calculation_snapshot_history SET {column}=?",(value,));repo._connection.commit()
    with pytest.raises(expected):repo.get_snapshot("economics-calculation-1")
    cleanup(sources,candidates,validation,repo)


def test_append_only_read_only_and_isolation(tmp_path):
    path=tmp_path/"read.db";sources,candidates,validation,repo=setup(path);repo.save_snapshot(snapshot());before=tuple(repo._connection.iterdump())
    assert repo.get_snapshot("economics-calculation-1")==repo.get_snapshot("economics-calculation-1")
    assert tuple(repo._connection.iterdump())==before and not repo._connection.in_transaction
    for operation in ("UPDATE","DELETE"):
        statement="UPDATE economics_calculation_snapshot_history SET rowid=rowid" if operation=="UPDATE" else "DELETE FROM economics_calculation_snapshot_history"
        with pytest.raises(sqlite3.IntegrityError,match="append-only"):repo._connection.execute(statement)
        repo._connection.rollback()
    cleanup(sources,candidates,validation,repo)


def test_repository_never_runs_calculator_analyzer_or_latest_price_selection():
    from app.infrastructure.economics_calculation.sqlite_repository import SQLiteEconomicsCalculationSnapshotRepository
    source=inspect.getsource(SQLiteEconomicsCalculationSnapshotRepository)
    assert "calculate_verified_economics" not in source
    assert "analyze_product_prices" not in source
    assert "latest" not in source.lower()
    assert "price_intelligence_snapshot_id" not in source


def test_separate_connections_replay_and_changed_payload_conflict(tmp_path):
    path=tmp_path/"race.db";sources,candidates,validation,repo=setup(path);cleanup(sources,candidates,validation,repo)
    def save(version):
        repository=SQLiteEconomicsCalculationSnapshotRepository(path)
        try:return repository.save_snapshot(replace(snapshot(),calculation_version=version))
        except Exception as error:return error
        finally:repository.close()
    with ThreadPoolExecutor(max_workers=2) as pool:same=list(pool.map(lambda _:save("v1"),(1,2)))
    assert all(not isinstance(value,Exception) for value in same)
    path2=tmp_path/"race-conflict.db";sources,candidates,validation,repo=setup(path2);cleanup(sources,candidates,validation,repo)
    def changed(version):
        repository=SQLiteEconomicsCalculationSnapshotRepository(path2)
        try:return repository.save_snapshot(replace(snapshot(),calculation_version=version))
        except Exception as error:return error
        finally:repository.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(changed,("v1","v2")))
    assert sum(isinstance(value,EconomicsCalculationSnapshotConflictError) for value in results)==1
