from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal
import sqlite3

import pytest

from app.application.price_analysis import (
    AnalyzeAndPersistPriceIntelligence,
    AnalyzeAndPersistPriceIntelligenceCommand,
    PriceAnalysisCommandConflictError,
    PriceAnalysisCandidateMismatchError,
    PriceAnalysisCommitError,
    PriceAnalysisExecutionError,
    PriceAnalysisGroupMismatchError,
    PriceAnalysisMarketIdentityConflictError,
    PriceAnalysisProductOrderConflictError,
    PriceAnalysisReceiptPersistenceError,
    PriceAnalysisSourceNotFoundError,
    UnsupportedPriceAnalysisReceiptVersionError,
)
from app.application.product_snapshot_capture import CaptureProductSnapshots
from app.infrastructure.price_intelligence import SQLitePriceAnalysisRepository
from app.application.price_intelligence_snapshot import PriceIntelligenceSnapshotHistoryError
from app.infrastructure.product_observation import SQLiteProductSnapshotCaptureRepository
from engine.price_intelligence import analyze_product_prices
from app.domain.discovery_identity import OpportunityCandidateIdentity
from test_candidate_issuance_foundation import Counter, ISSUED_AT
from test_product_snapshot_owner_wiring import capture_command, setup


GENERATED=ISSUED_AT+timedelta(minutes=10)


def prepare(path):
    issuance,_,_=setup(path)
    with SQLiteProductSnapshotCaptureRepository(path) as repo:
        CaptureProductSnapshots(repo,receipt_clock=Counter(ISSUED_AT)).execute(capture_command(issuance))
    return issuance


def command(issuance,**changes):
    values={"command_id":"price-analysis-1","candidate_identity":issuance.candidate_identity,
        "finalized_group_id":issuance.finalized_group_id,
        "product_snapshot_ids":("product-1","product-2"),
        "market_observation_identity":issuance.discovery_context.market_observation_identity,
        "fallback_multiplier":Decimal("1.50"),"analyzer_version":"price-analyzer-v1",
        "requested_at":ISSUED_AT+timedelta(minutes=5)}
    values.update(changes);return AnalyzeAndPersistPriceIntelligenceCommand(**values)


def boundary(repo,*,snapshot_id="price-1",analyzer=analyze_product_prices):
    return AnalyzeAndPersistPriceIntelligence(repo,snapshot_id_generator=Counter(snapshot_id),
        generated_clock=Counter(GENERATED),receipt_clock=Counter(GENERATED+timedelta(seconds=1)),analyzer=analyzer)


def counts(repo):
    return tuple(repo._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in (
        "price_intelligence_snapshot_history","price_intelligence_analysis_receipts"))


def test_command_is_immutable_versioned_decimal_and_deterministic(tmp_path):
    issuance=prepare(tmp_path/"contract.db");value=command(issuance)
    assert value==command(issuance) and value.fingerprint==command(issuance).fingerprint
    with pytest.raises(FrozenInstanceError):value.command_id="changed"
    with pytest.raises(TypeError):command(issuance,fallback_multiplier=1.5)
    with pytest.raises(ValueError):command(issuance,fallback_multiplier=Decimal("NaN"))
    with pytest.raises(ValueError):command(issuance,requested_at=ISSUED_AT.replace(tzinfo=None))
    with pytest.raises(ValueError):command(issuance,product_snapshot_ids=("product-1","product-1"))


def test_exact_order_runtime_reconstruction_analyzer_and_result_parity(tmp_path):
    path=tmp_path/"owner.db";issuance=prepare(path);repo=SQLitePriceAnalysisRepository(path);seen=[]
    def analyzer(products,*,fallback_multiplier):
        seen.append((tuple(products),fallback_multiplier));return analyze_product_prices(products,fallback_multiplier=fallback_multiplier)
    result=boundary(repo,analyzer=analyzer).execute(command(issuance))
    expected=analyze_product_prices(list(seen[0][0]),fallback_multiplier=Decimal("1.50"))
    assert len(seen)==1 and seen[0][1]==Decimal("1.50")
    assert result.snapshot.product_observation_snapshot_ids==("product-1","product-2")
    for name in expected.__dataclass_fields__:assert getattr(result.snapshot,name)==getattr(expected,name)
    assert result.snapshot.analyzer_version=="price-analyzer-v1" and result.snapshot.generated_at==GENERATED
    assert result.receipt.price_snapshot_id==result.snapshot.snapshot_id and counts(repo)==(1,1);repo.close()


def test_response_loss_and_restart_replay_do_not_call_owner_dependencies(tmp_path):
    path=tmp_path/"replay.db";issuance=prepare(path);repo=SQLitePriceAnalysisRepository(path);first=boundary(repo).execute(command(issuance));repo.close()
    class Fail:
        def __call__(self,*_,**__):raise AssertionError("owner dependency must not be called")
    repo=SQLitePriceAnalysisRepository(path)
    replay=AnalyzeAndPersistPriceIntelligence(repo,snapshot_id_generator=Fail(),generated_clock=Fail(),receipt_clock=Fail(),analyzer=Fail()).execute(command(issuance))
    assert replay.replayed and replay.snapshot==first.snapshot and replay.receipt==first.receipt and counts(repo)==(1,1);repo.close()


def test_changed_order_fallback_and_version_conflict(tmp_path):
    path=tmp_path/"conflict.db";issuance=prepare(path);repo=SQLitePriceAnalysisRepository(path);boundary(repo).execute(command(issuance))
    for changed in (replace(command(issuance),product_snapshot_ids=("product-2","product-1")),replace(command(issuance),fallback_multiplier=Decimal("1.6")),replace(command(issuance),analyzer_version="v2")):
        with pytest.raises(PriceAnalysisCommandConflictError):boundary(repo).execute(changed)
    assert counts(repo)==(1,1);repo.close()


def test_missing_product_and_exact_group_source_order_are_rejected(tmp_path):
    path=tmp_path/"lineage.db";issuance=prepare(path);repo=SQLitePriceAnalysisRepository(path)
    with pytest.raises(PriceAnalysisSourceNotFoundError):boundary(repo).execute(replace(command(issuance),product_snapshot_ids=("missing","product-2")))
    with pytest.raises(PriceAnalysisProductOrderConflictError):boundary(repo).execute(replace(command(issuance),product_snapshot_ids=("product-2","product-1"),command_id="other"))
    assert counts(repo)==(0,0);repo.close()


def test_candidate_group_and_market_mismatch_are_distinct(tmp_path):
    path=tmp_path/"identity.db";issuance=prepare(path);repo=SQLitePriceAnalysisRepository(path)
    with pytest.raises(PriceAnalysisCandidateMismatchError):
        boundary(repo).execute(replace(command(issuance),candidate_identity=OpportunityCandidateIdentity("candidate-1","other")))
    with pytest.raises(PriceAnalysisGroupMismatchError):
        boundary(repo).execute(replace(command(issuance),finalized_group_id="other"))
    with pytest.raises(PriceAnalysisMarketIdentityConflictError):
        boundary(repo).execute(replace(command(issuance),market_observation_identity=replace(command(issuance).market_observation_identity,condition="used")))
    assert counts(repo)==(0,0);repo.close()


def test_analyzer_failure_is_not_persistence_failure(tmp_path):
    path=tmp_path/"analyzer.db";issuance=prepare(path);repo=SQLitePriceAnalysisRepository(path)
    def fail(*_,**__):raise ValueError("domain failure")
    with pytest.raises(PriceAnalysisExecutionError):boundary(repo,analyzer=fail).execute(command(issuance))
    assert counts(repo)==(0,0);repo.close()


def test_different_commands_same_exact_cohort_create_distinct_analysis_facts(tmp_path):
    path=tmp_path/"repeat.db";issuance=prepare(path);repo=SQLitePriceAnalysisRepository(path)
    first=boundary(repo,snapshot_id="price-1").execute(command(issuance))
    second=boundary(repo,snapshot_id="price-2").execute(replace(command(issuance),command_id="price-analysis-2"))
    assert first.snapshot.snapshot_id!=second.snapshot.snapshot_id and counts(repo)==(2,2)
    values=repo.get_by_candidate_group(issuance.candidate_identity.candidate_id,issuance.finalized_group_id)
    assert tuple(value.snapshot for value in values)==(first.snapshot,second.snapshot);repo.close()


@pytest.mark.parametrize("phase,error_type",(("snapshot",PriceIntelligenceSnapshotHistoryError),("receipt",PriceAnalysisReceiptPersistenceError),("commit",PriceAnalysisCommitError)))
def test_atomic_failure_matrix(tmp_path,phase,error_type):
    path=tmp_path/f"{phase}.db";issuance=prepare(path);repo=SQLitePriceAnalysisRepository(path)
    if phase=="snapshot":repo._prices._insert=lambda *_:(_ for _ in ()).throw(sqlite3.OperationalError("snapshot"))
    elif phase=="receipt":repo._insert_receipt=lambda *_:(_ for _ in ()).throw(sqlite3.OperationalError("receipt"))
    else:repo._commit=lambda :(_ for _ in ()).throw(sqlite3.OperationalError("commit"))
    before=repo._connection.execute("SELECT COUNT(*) FROM product_observation_snapshot_history").fetchone()[0]
    with pytest.raises(error_type):boundary(repo).execute(command(issuance))
    assert counts(repo)==(0,0) and not repo._connection.in_transaction
    assert repo._connection.execute("SELECT COUNT(*) FROM product_observation_snapshot_history").fetchone()[0]==before;repo.close()


def test_receipt_trigger_read_only_queries_and_same_command_concurrency(tmp_path):
    path=tmp_path/"concurrent.db";issuance=prepare(path)
    def execute():
        with SQLitePriceAnalysisRepository(path) as repo:return boundary(repo).execute(command(issuance))
    with ThreadPoolExecutor(max_workers=2) as pool:results=tuple(pool.map(lambda _:execute(),range(2)))
    assert sum(not value.replayed for value in results)==1 and results[0].snapshot==results[1].snapshot
    with SQLitePriceAnalysisRepository(path) as repo:
        before=counts(repo);receipt=repo.get_receipt("price-analysis-1");assert repo.get_result(receipt).snapshot==results[0].snapshot
        assert counts(repo)==before and not repo._connection.in_transaction
        for operation in ("UPDATE","DELETE"):
            statement="UPDATE price_intelligence_analysis_receipts SET rowid=rowid" if operation=="UPDATE" else "DELETE FROM price_intelligence_analysis_receipts"
            with pytest.raises(sqlite3.IntegrityError,match="append-only"):repo._connection.execute(statement)
            repo._connection.rollback()


def test_unsupported_receipt_version_is_explicit(tmp_path):
    path=tmp_path/"version.db";issuance=prepare(path);repo=SQLitePriceAnalysisRepository(path);boundary(repo).execute(command(issuance))
    repo._connection.execute("DROP TRIGGER trg_price_analysis_receipt_no_update")
    repo._connection.execute("UPDATE price_intelligence_analysis_receipts SET receipt_schema_version='future'");repo._connection.commit()
    with pytest.raises(UnsupportedPriceAnalysisReceiptVersionError):repo.get_receipt("price-analysis-1")
    repo.close()


def test_same_command_changed_payload_multi_connection_converges_to_conflict(tmp_path):
    path=tmp_path/"changed-race.db";issuance=prepare(path)
    commands=(command(issuance),replace(command(issuance),fallback_multiplier=Decimal("1.75")))
    def execute(value):
        try:
            with SQLitePriceAnalysisRepository(path) as repo:return boundary(repo).execute(value)
        except Exception as error:return error
    with ThreadPoolExecutor(max_workers=2) as pool:results=tuple(pool.map(execute,commands))
    assert sum(isinstance(value,PriceAnalysisCommandConflictError) for value in results)==1
    assert sum(hasattr(value,"snapshot") for value in results)==1
    with SQLitePriceAnalysisRepository(path) as repo:assert counts(repo)==(1,1)
