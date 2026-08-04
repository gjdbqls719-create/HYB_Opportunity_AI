from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import sqlite3

import pytest

from app.application.price_intelligence_snapshot import (
    MalformedPriceIntelligenceSnapshotPersistenceError,
    PriceIntelligenceSnapshotCandidateMismatchError,
    PriceIntelligenceSnapshotCommitError, PriceIntelligenceSnapshotConflictError,
    PriceIntelligenceSnapshotHistoryError, PriceIntelligenceSnapshotMarketMismatchError,
    UnsupportedPriceIntelligenceSnapshotVersionError,
)
from app.domain.discovery_identity import OpportunityCandidateIdentity
from app.infrastructure.price_intelligence import SQLitePriceIntelligenceSnapshotRepository
from test_candidate_issuance_persistence import close
from test_price_intelligence_snapshot import snapshot as foundation_price_snapshot
from test_product_observation_snapshot_sqlite import setup as product_setup, snapshot as product_snapshot


def price_snapshot(snapshot_id="price-intelligence-1",source_ids=("product-observation-1","product-observation-2","product-observation-3")):
    return replace(foundation_price_snapshot(source_ids=source_ids),snapshot_id=snapshot_id,
        candidate_identity=OpportunityCandidateIdentity("candidate-1","collector:ebay:item-1"),
        market_observation_identity=product_snapshot().market_observation_identity)


def setup(path):
    sources,candidates,products=product_setup(path)
    for index in range(1,4):products.save_snapshot(product_snapshot(f"product-observation-{index}"))
    return sources,candidates,products,SQLitePriceIntelligenceSnapshotRepository(path)


def count(repo):return repo._connection.execute("SELECT COUNT(*) FROM price_intelligence_snapshot_history").fetchone()[0]


def test_schema_exact_round_trip_restart_and_no_current_projection(tmp_path):
    path=tmp_path/"price.db";sources,candidates,products,repo=setup(path);value=price_snapshot()
    assert repo.save_snapshot(value)==value and repo.get_snapshot(value.snapshot_id)==value
    columns={row[1] for row in repo._connection.execute("PRAGMA table_info(price_intelligence_snapshot_history)")}
    assert {"snapshot_id","candidate_id","discovery_reference","market_identity_payload_json","ordered_product_snapshot_ids_json","analyzer_version","currency","lowest_price","average_price","median_price","highest_price","price_range","variation_rate","stability","recommended_price","sample_size","generated_at","schema_version","payload_fingerprint","inserted_at"}==columns
    assert not repo._connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%price_intelligence_snapshot_current%'").fetchall()
    repo.close();products.close();candidates.close();close(sources);repo=SQLitePriceIntelligenceSnapshotRepository(path)
    assert repo.get_snapshot(value.snapshot_id)==value;repo.close()


def test_exact_replay_changed_payload_conflict_and_same_cohort_new_snapshot(tmp_path):
    path=tmp_path/"replay.db";sources,candidates,products,repo=setup(path);value=price_snapshot()
    assert repo.save_snapshot(value)==value and repo.save_snapshot(value)==value and count(repo)==1
    with pytest.raises(PriceIntelligenceSnapshotConflictError):repo.save_snapshot(replace(value,analyzer_version="changed"))
    second=replace(value,snapshot_id="price-intelligence-2")
    assert repo.save_snapshot(second)==second and count(repo)==2
    repo.close();products.close();candidates.close();close(sources)


def test_ordered_product_ids_decimal_and_queries_are_exact(tmp_path):
    path=tmp_path/"order.db";sources,candidates,products,repo=setup(path);value=price_snapshot(source_ids=("product-observation-3","product-observation-1","product-observation-2"))
    repo.save_snapshot(value);loaded=repo.get_snapshot(value.snapshot_id)
    assert loaded==value and loaded.product_observation_snapshot_ids==value.product_observation_snapshot_ids
    assert loaded.lowest_price is not None and type(loaded.lowest_price) is type(value.lowest_price)
    assert repo.get_by_candidate(value.candidate_identity)==(value,)
    assert repo.get_by_market_identity(value.market_observation_identity)==(value,)
    repo.close();products.close();candidates.close();close(sources)


def test_candidate_market_and_product_lineage_failures(tmp_path):
    path=tmp_path/"lineage.db";sources,candidates,products,repo=setup(path);value=price_snapshot()
    with pytest.raises(PriceIntelligenceSnapshotCandidateMismatchError):repo.save_snapshot(replace(value,candidate_identity=OpportunityCandidateIdentity("candidate-1","other")))
    with pytest.raises(PriceIntelligenceSnapshotMarketMismatchError):repo.save_snapshot(replace(value,market_observation_identity=replace(value.market_observation_identity,marketplace_item_id="other")))
    with pytest.raises(PriceIntelligenceSnapshotHistoryError):repo.save_snapshot(price_snapshot(source_ids=("product-observation-1","product-observation-2","missing")))
    assert count(repo)==0 and not repo._connection.in_transaction
    repo.close();products.close();candidates.close();close(sources)


def test_domain_sample_size_and_unsupported_version_are_rejected(tmp_path):
    value=price_snapshot()
    with pytest.raises(ValueError):replace(value,sample_size=2)
    path=tmp_path/"version.db";sources,candidates,products,repo=setup(path)
    with pytest.raises(UnsupportedPriceIntelligenceSnapshotVersionError):repo.save_snapshot(replace(value,schema_version="future"))
    repo.close();products.close();candidates.close();close(sources)


@pytest.mark.parametrize("phase,error_type",(("insert",PriceIntelligenceSnapshotHistoryError),("commit",PriceIntelligenceSnapshotCommitError)))
def test_atomic_failure_rolls_back_without_product_changes(tmp_path,phase,error_type):
    path=tmp_path/f"{phase}.db";sources,candidates,products,repo=setup(path);product_count=count_products(products)
    if phase=="insert":repo._insert=lambda *_:(_ for _ in ()).throw(sqlite3.OperationalError("forced"))
    else:repo._commit=lambda :(_ for _ in ()).throw(sqlite3.OperationalError("forced"))
    with pytest.raises(error_type):repo.save_snapshot(price_snapshot())
    assert count(repo)==0 and count_products(products)==product_count and not repo._connection.in_transaction
    repo.close();products.close();candidates.close();close(sources)


def count_products(repo):return repo._connection.execute("SELECT COUNT(*) FROM product_observation_snapshot_history").fetchone()[0]


@pytest.mark.parametrize("column,value,expected",(
    ("ordered_product_snapshot_ids_json","{",MalformedPriceIntelligenceSnapshotPersistenceError),
    ("lowest_price","NaN",MalformedPriceIntelligenceSnapshotPersistenceError),
    ("generated_at","naive",MalformedPriceIntelligenceSnapshotPersistenceError),
    ("payload_fingerprint","0"*64,MalformedPriceIntelligenceSnapshotPersistenceError),
    ("schema_version","future",UnsupportedPriceIntelligenceSnapshotVersionError),
))
def test_malformed_persistence_is_explicit(tmp_path,column,value,expected):
    path=tmp_path/f"{column}.db";sources,candidates,products,repo=setup(path);repo.save_snapshot(price_snapshot())
    repo._connection.execute("DROP TRIGGER trg_price_intelligence_snapshot_no_update")
    repo._connection.execute(f"UPDATE price_intelligence_snapshot_history SET {column}=?",(value,));repo._connection.commit()
    with pytest.raises(expected):repo.get_snapshot("price-intelligence-1")
    repo.close();products.close();candidates.close();close(sources)


def test_append_only_and_read_queries_make_zero_writes(tmp_path):
    path=tmp_path/"read.db";sources,candidates,products,repo=setup(path);repo.save_snapshot(price_snapshot());before=tuple(repo._connection.iterdump())
    assert repo.get_snapshot("price-intelligence-1")==repo.get_snapshot("price-intelligence-1")
    assert tuple(repo._connection.iterdump())==before and not repo._connection.in_transaction
    for operation in ("UPDATE","DELETE"):
        statement="UPDATE price_intelligence_snapshot_history SET rowid=rowid" if operation=="UPDATE" else "DELETE FROM price_intelligence_snapshot_history"
        with pytest.raises(sqlite3.IntegrityError,match="append-only"):repo._connection.execute(statement)
        repo._connection.rollback()
    repo.close();products.close();candidates.close();close(sources)


def test_separate_connections_same_payload_converge_and_changed_payload_conflicts(tmp_path):
    path=tmp_path/"race.db";sources,candidates,products,repo=setup(path);repo.close();products.close();candidates.close();close(sources)
    def save(version):
        repository=SQLitePriceIntelligenceSnapshotRepository(path)
        try:return repository.save_snapshot(replace(price_snapshot(),analyzer_version=version))
        except Exception as error:return error
        finally:repository.close()
    with ThreadPoolExecutor(max_workers=2) as pool:same=list(pool.map(lambda _:save("v1"),(1,2)))
    assert all(not isinstance(value,Exception) for value in same)
    repo=SQLitePriceIntelligenceSnapshotRepository(path);assert count(repo)==1;repo.close()
    path2=tmp_path/"race-conflict.db";sources,candidates,products,repo=setup(path2);repo.close();products.close();candidates.close();close(sources)
    def changed(version):
        repository=SQLitePriceIntelligenceSnapshotRepository(path2)
        try:return repository.save_snapshot(replace(price_snapshot(),analyzer_version=version))
        except Exception as error:return error
        finally:repository.close()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(changed,("v1","v2")))
    assert sum(isinstance(value,PriceIntelligenceSnapshotConflictError) for value in results)==1
