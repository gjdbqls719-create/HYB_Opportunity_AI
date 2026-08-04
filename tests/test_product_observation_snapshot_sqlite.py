from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import sqlite3

import pytest

from app.application.product_observation import (
    MalformedProductObservationSnapshotPersistenceError,
    ProductObservationSnapshotCandidateMismatchError,
    ProductObservationSnapshotCandidateNotFoundError,
    ProductObservationSnapshotCommitError,
    ProductObservationSnapshotConflictError,
    ProductObservationSnapshotHistoryError,
    ProductObservationSnapshotMarketIdentityConflictError,
    UnsupportedProductObservationSnapshotVersionError,
)
from app.domain.discovery_identity import OpportunityCandidateIdentity
from app.infrastructure.discovery import SQLiteCandidateIssuanceRepository
from app.infrastructure.product_observation import SQLiteProductObservationSnapshotRepository
from test_candidate_issuance_persistence import close, durable, issuance_command
from test_product_observation_snapshot import snapshot as foundation_snapshot


def snapshot(snapshot_id="product-observation-1"):
    return replace(
        foundation_snapshot(snapshot_id),
        candidate_identity=OpportunityCandidateIdentity("candidate-1","collector:ebay:item-1"),
        market_observation_identity=issuance_command().market_observation_identity,
    )


def setup(path):
    sources,candidates,boundary=durable(path);boundary.execute(issuance_command())
    return sources,candidates,SQLiteProductObservationSnapshotRepository(path)


def count(repo):return repo._connection.execute("SELECT COUNT(*) FROM product_observation_snapshot_history").fetchone()[0]


def test_schema_exact_round_trip_restart_and_append_only(tmp_path):
    path=tmp_path/"product.db";sources,candidates,repo=setup(path);value=snapshot()
    assert repo.save_snapshot(value)==value and repo.get_snapshot(value.snapshot_id)==value
    columns={row[1] for row in repo._connection.execute("PRAGMA table_info(product_observation_snapshot_history)")}
    assert columns=={"snapshot_id","candidate_id","candidate_discovery_reference","market_identity_payload_json","observed_product_payload_json","collector_provenance_payload_json","observed_at","snapshot_schema_version","payload_fingerprint","inserted_at"}
    assert not repo._connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%product_observation_snapshot_current%'").fetchall()
    for operation in ("UPDATE","DELETE"):
        statement="UPDATE product_observation_snapshot_history SET rowid=rowid" if operation=="UPDATE" else "DELETE FROM product_observation_snapshot_history"
        with pytest.raises(sqlite3.IntegrityError,match="append-only"):repo._connection.execute(statement)
        repo._connection.rollback()
    repo.close();candidates.close();close(sources);repo=SQLiteProductObservationSnapshotRepository(path)
    assert repo.get_snapshot(value.snapshot_id)==value;repo.close()


def test_exact_replay_conflict_and_repeated_observations(tmp_path):
    path=tmp_path/"replay.db";sources,candidates,repo=setup(path);value=snapshot()
    first=repo.save_snapshot(value);assert repo.save_snapshot(value)==first and count(repo)==1
    with pytest.raises(ProductObservationSnapshotConflictError):repo.save_snapshot(replace(value,product=replace(value.product,title="changed")))
    second=replace(value,snapshot_id="product-observation-2")
    assert repo.save_snapshot(second)==second and count(repo)==2
    assert repo.get_by_candidate(value.candidate_identity)==(value,second)
    assert repo.get_by_market_identity(value.market_observation_identity)==(value,second)
    repo.close();candidates.close();close(sources)


def test_candidate_context_and_listing_lineage_validation(tmp_path):
    path=tmp_path/"lineage.db";sources,candidates,repo=setup(path);value=snapshot()
    with pytest.raises(ProductObservationSnapshotCandidateMismatchError):
        repo.save_snapshot(replace(value,candidate_identity=OpportunityCandidateIdentity("candidate-1","other")))
    with pytest.raises(ProductObservationSnapshotMarketIdentityConflictError):
        repo.save_snapshot(replace(value,market_observation_identity=replace(value.market_observation_identity,marketplace_item_id="other")))
    with pytest.raises(ProductObservationSnapshotMarketIdentityConflictError):
        repo.save_snapshot(replace(value,product=replace(value.product,item_id="other")))
    assert count(repo)==0 and not repo._connection.in_transaction
    repo.close();candidates.close();close(sources)


def test_missing_candidate_and_unsupported_version_are_explicit(tmp_path):
    path=tmp_path/"missing.db";candidate_repo=SQLiteCandidateIssuanceRepository(path);repo=SQLiteProductObservationSnapshotRepository(path)
    with pytest.raises(ProductObservationSnapshotCandidateNotFoundError):repo.save_snapshot(snapshot())
    with pytest.raises(UnsupportedProductObservationSnapshotVersionError):repo.save_snapshot(replace(snapshot(),schema_version="future"))
    assert count(repo)==0;repo.close();candidate_repo.close()


def test_missing_context_is_not_treated_as_a_valid_candidate(tmp_path):
    path=tmp_path/"context.db";sources,candidates,repo=setup(path)
    candidates._connection.execute("DROP TRIGGER trg_opportunity_candidate_context_history_no_delete")
    candidates._connection.execute("DELETE FROM opportunity_candidate_context_history");candidates._connection.commit()
    with pytest.raises(ProductObservationSnapshotCandidateNotFoundError):repo.save_snapshot(snapshot())
    assert count(repo)==0 and not repo._connection.in_transaction
    repo.close();candidates.close();close(sources)


@pytest.mark.parametrize("phase,error_type",(("insert",ProductObservationSnapshotHistoryError),("commit",ProductObservationSnapshotCommitError)))
def test_atomic_failure_rolls_back_and_cleans_transaction(tmp_path,phase,error_type):
    path=tmp_path/f"{phase}.db";sources,candidates,repo=setup(path)
    if phase=="insert":repo._insert=lambda *_:(_ for _ in ()).throw(sqlite3.OperationalError("forced"))
    else:repo._commit=lambda :(_ for _ in ()).throw(sqlite3.OperationalError("forced"))
    with pytest.raises(error_type):repo.save_snapshot(snapshot())
    assert count(repo)==0 and not repo._connection.in_transaction
    assert candidates.get_candidate("candidate-1") is not None
    repo.close();candidates.close();close(sources)


@pytest.mark.parametrize("column,value,expected",(
    ("observed_product_payload_json","{",MalformedProductObservationSnapshotPersistenceError),
    ("payload_fingerprint","0"*64,MalformedProductObservationSnapshotPersistenceError),
    ("observed_at","naive",MalformedProductObservationSnapshotPersistenceError),
    ("snapshot_schema_version","v999",UnsupportedProductObservationSnapshotVersionError),
))
def test_malformed_payload_fingerprint_datetime_and_version(tmp_path,column,value,expected):
    path=tmp_path/f"{column}.db";sources,candidates,repo=setup(path);repo.save_snapshot(snapshot())
    repo._connection.execute("DROP TRIGGER trg_product_observation_snapshot_no_update")
    repo._connection.execute(f"UPDATE product_observation_snapshot_history SET {column}=?",(value,));repo._connection.commit()
    with pytest.raises(expected):repo.get_snapshot("product-observation-1")
    repo.close();candidates.close();close(sources)


def test_separate_connections_same_snapshot_converge(tmp_path):
    path=tmp_path/"race.db";sources,candidates,repo=setup(path);repo.close();candidates.close();close(sources)
    def save(_):
        repository=SQLiteProductObservationSnapshotRepository(path)
        try:return repository.save_snapshot(snapshot())
        finally:repository.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,(1,2)))
    repo=SQLiteProductObservationSnapshotRepository(path)
    assert results==[snapshot(),snapshot()] and count(repo)==1 and not repo._connection.in_transaction
    repo.close()


def test_separate_connections_changed_payload_has_one_winner_and_one_conflict(tmp_path):
    path=tmp_path/"race-conflict.db";sources,candidates,repo=setup(path);repo.close();candidates.close();close(sources)
    def save(title):
        repository=SQLiteProductObservationSnapshotRepository(path)
        try:
            return repository.save_snapshot(replace(snapshot(),product=replace(snapshot().product,title=title)))
        except Exception as error:return error
        finally:repository.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(save,("one","two")))
    assert sum(isinstance(value,ProductObservationSnapshotConflictError) for value in results)==1
    repo=SQLiteProductObservationSnapshotRepository(path)
    assert count(repo)==1 and not repo._connection.in_transaction;repo.close()


def test_queries_are_deterministic_read_only_and_isolated(tmp_path):
    path=tmp_path/"read.db";sources,candidates,repo=setup(path);repo.save_snapshot(snapshot())
    before=tuple(repo._connection.iterdump())
    assert repo.get_snapshot("product-observation-1")==repo.get_snapshot("product-observation-1")
    assert repo.get_by_candidate(snapshot().candidate_identity)==repo.get_by_candidate(snapshot().candidate_identity)
    assert tuple(repo._connection.iterdump())==before and not repo._connection.in_transaction
    forbidden=("price_intelligence_snapshot","economics_calculation_snapshot","production_safety_snapshot")
    names={row[0] for row in repo._connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not any(any(term in name for term in forbidden) for name in names)
    repo.close();candidates.close();close(sources)
