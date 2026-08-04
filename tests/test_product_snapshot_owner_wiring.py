from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import sqlite3

import pytest

from app.application.candidate_issuance import PersistOpportunityCandidateIssuance
from app.application.product_snapshot_capture import (
    CaptureProductSnapshots,
    CaptureProductSnapshotsCommand,
    ProductSnapshotCaptureHistoryError,
    ProductSnapshotSourceConflictError,
    SnapshotOwnerCommandConflictError,
    SnapshotOwnerCommitError,
)
from app.infrastructure.discovery import (
    SQLiteCandidateIssuanceRepository,
    SQLiteDiscoveryCommandRepository,
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
    SQLiteDiscoveryResultRepository,
)
from app.infrastructure.product_observation import SQLiteProductSnapshotCaptureRepository
from test_candidate_issuance_foundation import Counter, ISSUED_AT, issuance_command, service
from test_discovery_command_sqlite_persistence import receipt
from test_discovery_correlation_contract import NOW, command, group, market_identity, observation
from test_discovery_execution_result_sqlite_persistence import result


def setup(path):
    command_repo=SQLiteDiscoveryCommandRepository(path); command_repo.save_command(command(),receipt(command()))
    observation_repo=SQLiteDiscoveryObservationRepository(path)
    first=replace(observation(),candidate_market_identity=market_identity())
    second=replace(first,observation_id="observation-2",observed_at=NOW+timedelta(seconds=1))
    observation_repo.save_observation(first);observation_repo.save_observation(second)
    group_repo=SQLiteDiscoveryGroupRepository(path);group_repo.save_group(group())
    result_repo=SQLiteDiscoveryResultRepository(path);result_repo.save_result(result())
    sources=(command_repo,result_repo,group_repo,observation_repo)
    candidates=SQLiteCandidateIssuanceRepository(path)
    boundary=PersistOpportunityCandidateIssuance(service(sources,Counter("candidate-1"),Counter(ISSUED_AT)),candidates,receipt_clock=Counter(ISSUED_AT))
    issuance=boundary.execute(issuance_command()).issuance
    for value in sources:value.close()
    candidates.close()
    return issuance,first,second


def capture_command(issuance, **changes):
    values={"command_id":"capture-1","candidate_identity":issuance.candidate_identity,
        "finalized_group_id":issuance.finalized_group_id,
        "observation_snapshot_ids":(("observation-1","product-1"),("observation-2","product-2")),
        "market_observation_identity":issuance.discovery_context.market_observation_identity,
        "requested_at":NOW+timedelta(minutes=3)}
    values.update(changes);return CaptureProductSnapshotsCommand(**values)


def counts(repo):
    return tuple(repo._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] for table in (
        "product_observation_snapshot_history","product_snapshot_source_binding_history","product_snapshot_capture_receipts"))


def test_exact_collector_source_capture_round_trip_and_restart(tmp_path):
    path=tmp_path/"owner.db";issuance,first,second=setup(path);repo=SQLiteProductSnapshotCaptureRepository(path)
    service_=CaptureProductSnapshots(repo,receipt_clock=Counter(ISSUED_AT+timedelta(minutes=2)))
    result_=service_.execute(capture_command(issuance))
    assert result_.replayed is False and counts(repo)==(2,2,1)
    assert tuple(value.product for value in result_.snapshots)==(first.product,second.product)
    assert tuple(value.collector_provenance for value in result_.snapshots)==(first.collector_provenance,second.collector_provenance)
    assert tuple(value.observed_at for value in result_.snapshots)==(first.observed_at,second.observed_at)
    assert tuple(value.collected_observation_id for value in result_.bindings)==("observation-1","observation-2")
    repo.close();repo=SQLiteProductSnapshotCaptureRepository(path)
    replay=CaptureProductSnapshots(repo,receipt_clock=Counter(ISSUED_AT+timedelta(days=1))).execute(capture_command(issuance))
    assert replay.replayed is True and replay.receipt==result_.receipt and replay.snapshots==result_.snapshots
    repo.close()


def test_replay_does_not_recreate_timestamp_and_changed_payload_conflicts(tmp_path):
    path=tmp_path/"replay.db";issuance,_,_=setup(path);repo=SQLiteProductSnapshotCaptureRepository(path);clock=Counter(ISSUED_AT)
    boundary=CaptureProductSnapshots(repo,receipt_clock=clock);first=boundary.execute(capture_command(issuance));second=boundary.execute(capture_command(issuance))
    assert second.replayed and second.receipt==first.receipt and clock.calls==1
    with pytest.raises(SnapshotOwnerCommandConflictError):
        boundary.execute(replace(capture_command(issuance),requested_at=NOW+timedelta(days=1)))
    assert counts(repo)==(2,2,1);repo.close()


def test_new_command_can_alias_exact_publication_but_cannot_duplicate_source(tmp_path):
    path=tmp_path/"alias.db";issuance,_,_=setup(path);repo=SQLiteProductSnapshotCaptureRepository(path)
    first=CaptureProductSnapshots(repo,receipt_clock=Counter(ISSUED_AT)).execute(capture_command(issuance))
    alias=CaptureProductSnapshots(repo,receipt_clock=Counter(ISSUED_AT+timedelta(seconds=1))).execute(
        replace(capture_command(issuance),command_id="capture-2"))
    assert alias.snapshots==first.snapshots and alias.bindings==first.bindings and counts(repo)==(2,2,2)
    changed=replace(capture_command(issuance),command_id="capture-3",
        observation_snapshot_ids=(("observation-1","product-3"),("observation-2","product-4")))
    with pytest.raises(ProductSnapshotSourceConflictError):
        CaptureProductSnapshots(repo,receipt_clock=Counter(ISSUED_AT)).execute(changed)
    assert counts(repo)==(2,2,2);repo.close()


def test_exact_group_order_and_candidate_market_identity_are_required(tmp_path):
    path=tmp_path/"lineage.db";issuance,_,_=setup(path);repo=SQLiteProductSnapshotCaptureRepository(path);boundary=CaptureProductSnapshots(repo,receipt_clock=Counter(ISSUED_AT))
    with pytest.raises(ProductSnapshotSourceConflictError):
        boundary.execute(replace(capture_command(issuance),observation_snapshot_ids=(("observation-2","product-2"),("observation-1","product-1"))))
    with pytest.raises(ProductSnapshotSourceConflictError):
        boundary.execute(replace(capture_command(issuance),market_observation_identity=replace(market_identity(),condition="used")))
    assert counts(repo)==(0,0,0);repo.close()


def test_append_only_triggers_and_read_only_replay_queries(tmp_path):
    path=tmp_path/"trigger.db";issuance,_,_=setup(path);repo=SQLiteProductSnapshotCaptureRepository(path)
    value=CaptureProductSnapshots(repo,receipt_clock=Counter(ISSUED_AT)).execute(capture_command(issuance));before=counts(repo)
    assert repo.get_result(repo.get_receipt("capture-1")).snapshots==value.snapshots
    assert counts(repo)==before and not repo._connection.in_transaction
    for table in ("product_snapshot_source_binding_history","product_snapshot_capture_receipts"):
        for operation in ("UPDATE","DELETE"):
            statement=f"UPDATE {table} SET rowid=rowid" if operation=="UPDATE" else f"DELETE FROM {table}"
            with pytest.raises(sqlite3.IntegrityError,match="append-only"):repo._connection.execute(statement)
            repo._connection.rollback()
    repo.close()


@pytest.mark.parametrize("phase,error_type",(("insert",ProductSnapshotCaptureHistoryError),("commit",SnapshotOwnerCommitError)))
def test_atomic_failure_rolls_back_every_owner_fact(tmp_path,phase,error_type):
    path=tmp_path/f"{phase}.db";issuance,_,_=setup(path);repo=SQLiteProductSnapshotCaptureRepository(path)
    if phase=="insert":
        repo._snapshots._insert=lambda *_:(_ for _ in ()).throw(sqlite3.OperationalError("forced insert"))
    else:
        repo._commit=lambda :(_ for _ in ()).throw(sqlite3.OperationalError("forced commit"))
    with pytest.raises(error_type):CaptureProductSnapshots(repo,receipt_clock=Counter(ISSUED_AT)).execute(capture_command(issuance))
    assert counts(repo)==(0,0,0) and not repo._connection.in_transaction;repo.close()


def test_same_command_multi_connection_is_one_capture(tmp_path):
    path=tmp_path/"concurrent.db";issuance,_,_=setup(path)
    def execute():
        with SQLiteProductSnapshotCaptureRepository(path) as repo:
            return CaptureProductSnapshots(repo,receipt_clock=Counter(ISSUED_AT)).execute(capture_command(issuance))
    with ThreadPoolExecutor(max_workers=2) as pool: results=tuple(pool.map(lambda _:execute(),range(2)))
    assert sum(not value.replayed for value in results)==1
    with SQLiteProductSnapshotCaptureRepository(path) as repo: assert counts(repo)==(2,2,1)
