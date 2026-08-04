from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import sqlite3
from threading import Barrier

import pytest

from app.application.candidate_issuance import (
    CandidateCommitError, CandidateContextPersistenceError,
    CandidateHistoryPersistenceError, CandidateIssuanceCommandConflictError,
    CandidateIssuanceReplayConflictError, CandidateReceiptPersistenceError,
    MalformedCandidatePersistenceError, PersistOpportunityCandidateIssuance,
)
from app.infrastructure.discovery import SQLiteCandidateIssuanceRepository
from test_candidate_issuance_foundation import (
    Counter, ISSUED_AT, issuance_command, repositories, service, close,
)
from test_discovery_correlation_contract import market_identity


def durable(path, *, candidate="candidate-1", issued=ISSUED_AT, receipt=ISSUED_AT):
    sources = repositories(path)
    issuance = service(sources, Counter(candidate), Counter(issued))
    repo = SQLiteCandidateIssuanceRepository(path)
    boundary = PersistOpportunityCandidateIssuance(
        issuance, repo, receipt_clock=Counter(receipt)
    )
    return sources, repo, boundary


def counts(connection):
    return tuple(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                 for table in ("opportunity_candidate_history",
                               "opportunity_candidate_context_history",
                               "opportunity_candidate_issuance_receipts"))


def test_schema_cardinality_idempotency_and_append_only_triggers(tmp_path):
    path=tmp_path/"schema.db"; sources,repo,boundary=durable(path)
    boundary.execute(issuance_command()); repo.close(); repo=SQLiteCandidateIssuanceRepository(path)
    indexes=repo._connection.execute("PRAGMA index_list(opportunity_candidate_issuance_receipts)").fetchall()
    unique_columns = {
        tuple(item[2] for item in repo._connection.execute(f"PRAGMA index_info('{row[1]}')"))
        for row in indexes if row[2]
    }
    assert ("candidate_id",) not in unique_columns
    for table in ("opportunity_candidate_history","opportunity_candidate_context_history","opportunity_candidate_issuance_receipts"):
        for operation in ("UPDATE","DELETE"):
            statement=f"UPDATE {table} SET rowid=rowid" if operation=="UPDATE" else f"DELETE FROM {table}"
            with pytest.raises(sqlite3.IntegrityError,match="append-only"):repo._connection.execute(statement)
    close(sources);repo.close()


def test_initial_exact_round_trip_restart_and_response_loss_replay(tmp_path):
    path=tmp_path/"db.sqlite"; sources,repo,boundary=durable(path)
    first=boundary.execute(issuance_command())
    assert first.replayed is False and counts(repo._connection)==(1,1,1)
    candidate=repo.get_candidate("candidate-1"); context=repo.get_context("candidate-1")
    assert candidate==first.issuance.candidate_identity
    assert context==first.issuance.discovery_context
    assert repo.get_by_discovery_group("command-1","group-opaque-1")==first.issuance
    close(sources); repo.close()
    sources,repo,boundary=durable(path,candidate="must-not-win",issued=ISSUED_AT+timedelta(days=1),receipt=ISSUED_AT+timedelta(days=1))
    replay=boundary.execute(issuance_command())
    assert replay.replayed is True and replay.issuance==first.issuance and replay.receipt==first.receipt
    assert counts(repo._connection)==(1,1,1)
    close(sources);repo.close()


def test_alias_receipt_is_many_to_one_without_candidate_regeneration(tmp_path):
    path=tmp_path/"db.sqlite"; sources,repo,boundary=durable(path)
    first=boundary.execute(issuance_command())
    close(sources);repo.close()
    sources=repositories(path); generator=Counter("must-not-generate"); candidate_clock=Counter(ISSUED_AT+timedelta(days=1)); receipt_clock=Counter(ISSUED_AT+timedelta(seconds=1))
    repo=SQLiteCandidateIssuanceRepository(path)
    boundary=PersistOpportunityCandidateIssuance(service(sources,generator,candidate_clock),repo,receipt_clock=receipt_clock)
    alias_command=replace(issuance_command(),issuance_command_id="issuance-command-2")
    alias=boundary.execute(alias_command)
    assert alias.issuance==first.issuance and alias.receipt.candidate_id=="candidate-1"
    assert generator.calls==0 and candidate_clock.calls==0 and receipt_clock.calls==1
    assert counts(repo._connection)==(1,1,2)
    assert repo.list_receipts_for_candidate("candidate-1")== (first.receipt,alias.receipt)
    close(sources);repo.close()


def test_command_and_subject_conflicts_are_distinct(tmp_path):
    path=tmp_path/"db.sqlite"; sources,repo,boundary=durable(path)
    boundary.execute(issuance_command())
    with pytest.raises(CandidateIssuanceCommandConflictError):
        boundary.execute(replace(issuance_command(),requested_at=ISSUED_AT))
    with pytest.raises(CandidateIssuanceReplayConflictError):
        boundary.execute(replace(issuance_command(),issuance_command_id="other",discovery_reference="changed"))
    changed_identity=replace(market_identity(),condition="used")
    with pytest.raises(CandidateIssuanceReplayConflictError):
        boundary.execute(replace(issuance_command(),issuance_command_id="other-2",market_observation_identity=changed_identity))
    assert counts(repo._connection)==(1,1,1)
    close(sources);repo.close()


@pytest.mark.parametrize("stage,error_type",(("candidate",CandidateHistoryPersistenceError),("context",CandidateContextPersistenceError),("receipt",CandidateReceiptPersistenceError),("commit",CandidateCommitError)))
def test_initial_atomic_failure_matrix(tmp_path,stage,error_type):
    class Failing(SQLiteCandidateIssuanceRepository):
        def _insert_candidate(self,*a):
            if stage=="candidate":raise sqlite3.OperationalError("candidate")
            return super()._insert_candidate(*a)
        def _insert_context(self,*a):
            if stage=="context":raise sqlite3.OperationalError("context")
            return super()._insert_context(*a)
        def _insert_receipt(self,*a):
            if stage=="receipt":raise sqlite3.OperationalError("receipt")
            return super()._insert_receipt(*a)
        def _commit(self):
            if stage=="commit":raise sqlite3.OperationalError("commit")
            return super()._commit()
    path=tmp_path/"db.sqlite"; sources=repositories(path); repo=Failing(path)
    boundary=PersistOpportunityCandidateIssuance(service(sources,Counter("candidate-1"),Counter(ISSUED_AT)),repo,receipt_clock=Counter(ISSUED_AT))
    with pytest.raises(error_type):boundary.execute(issuance_command())
    assert counts(repo._connection)==(0,0,0) and repo._connection.in_transaction is False
    close(sources);repo.close()


@pytest.mark.parametrize("stage,error_type",(("receipt",CandidateReceiptPersistenceError),("commit",CandidateCommitError)))
def test_alias_atomic_failure_preserves_initial(tmp_path,stage,error_type):
    path=tmp_path/"db.sqlite"; sources,repo,boundary=durable(path); boundary.execute(issuance_command());close(sources);repo.close()
    class Failing(SQLiteCandidateIssuanceRepository):
        def _insert_receipt(self,*a):
            if stage=="receipt":raise sqlite3.OperationalError("receipt")
            return super()._insert_receipt(*a)
        def _commit(self):
            if stage=="commit":raise sqlite3.OperationalError("commit")
            return super()._commit()
    sources=repositories(path);repo=Failing(path);boundary=PersistOpportunityCandidateIssuance(service(sources,Counter("unused"),Counter(ISSUED_AT)),repo,receipt_clock=Counter(ISSUED_AT+timedelta(seconds=1)))
    with pytest.raises(error_type):boundary.execute(replace(issuance_command(),issuance_command_id="alias"))
    assert counts(repo._connection)==(1,1,1) and repo._connection.in_transaction is False
    close(sources);repo.close()


def _race(path,left,right):
    barrier=Barrier(2)
    def run(command,n):
        sources=repositories(path);repo=SQLiteCandidateIssuanceRepository(path)
        try:
            boundary=PersistOpportunityCandidateIssuance(service(sources,Counter(f"candidate-{n}"),Counter(ISSUED_AT+timedelta(seconds=n))),repo,receipt_clock=Counter(ISSUED_AT+timedelta(seconds=n)))
            barrier.wait();return boundary.execute(command)
        finally:close(sources);repo.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=(pool.submit(run,left,1),pool.submit(run,right,2));results=[];errors=[]
        for future in futures:
            try:results.append(future.result())
            except Exception as error:errors.append(error)
    return results,errors


def test_concurrent_initial_aliases_converge_to_one_candidate(tmp_path):
    path=tmp_path/"db.sqlite"; sources=repositories(path);close(sources)
    results,errors=_race(path,issuance_command(),replace(issuance_command(),issuance_command_id="alias"))
    assert errors==[] and len({r.issuance.candidate_identity.candidate_id for r in results})==1
    repo=SQLiteCandidateIssuanceRepository(path);assert counts(repo._connection)==(1,1,2);repo.close()


def test_same_command_concurrent_changed_payload_has_one_conflict(tmp_path):
    path=tmp_path/"db.sqlite"; sources=repositories(path);close(sources)
    changed=replace(issuance_command(),requested_at=ISSUED_AT)
    results,errors=_race(path,issuance_command(),changed)
    assert len(results)==1 and len(errors)==1 and isinstance(errors[0],CandidateIssuanceCommandConflictError)


def test_read_queries_zero_write_and_malformed_fingerprint(tmp_path):
    path=tmp_path/"db.sqlite"; sources,repo,boundary=durable(path);saved=boundary.execute(issuance_command())
    before=counts(repo._connection)
    assert repo.get_receipt_by_command("issuance-command-1")==saved.receipt
    assert repo.validate_command_replay("issuance-command-1",saved.receipt.command_fingerprint)
    assert repo.validate_subject_replay("command-1","group-opaque-1",saved.receipt.subject_fingerprint)==saved.issuance
    assert counts(repo._connection)==before and repo._connection.in_transaction is False
    repo._connection.execute("DROP TRIGGER trg_opportunity_candidate_issuance_receipts_no_update")
    repo._connection.execute("UPDATE opportunity_candidate_issuance_receipts SET command_fingerprint=?",("a"*64,));repo._connection.commit()
    with pytest.raises(MalformedCandidatePersistenceError):repo.get_receipt_by_command("issuance-command-1")
    close(sources);repo.close()
