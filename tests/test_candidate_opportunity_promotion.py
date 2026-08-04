from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import sqlite3

import pytest

from app.application.candidate_promotion import (
    CandidateAlreadyPromotedError, CandidatePromotionCommandConflictError,
    CandidatePromotionReceiptError, CandidatePromotionPersistenceError,
    CandidatePromotionHistoryError, PromoteOpportunityCandidate,
    PromoteOpportunityCandidateCommand,
)
from app.application.opportunity_validation import OpportunityValidationService
from app.infrastructure.discovery import SQLiteCandidateIssuanceRepository
from app.infrastructure.opportunity_validation import SQLiteCandidatePromotionRepository
from test_candidate_issuance_foundation import Counter, ISSUED_AT
from test_candidate_issuance_persistence import close, durable, issuance_command


def command(**changes):
    value = PromoteOpportunityCandidateCommand(
        promotion_command_id="promotion-1", candidate_id="candidate-1",
        title="Camera", admission_recommendation="WATCH", admission_score=70,
        admission_roi=25, currency="USD", admission_safety_status="READY",
        operator_id="founder", reason="admitted", requested_at=ISSUED_AT,
    )
    return replace(value, **changes)


def setup_boundary(path, *, opportunity="opportunity-1", binding="binding-1", at=ISSUED_AT):
    sources, candidate_repo, issuance = durable(path)
    issuance.execute(issuance_command())
    validation_repo = SQLiteCandidatePromotionRepository(path)
    validation = OpportunityValidationService(
        queue_repository=validation_repo, lifecycle_repository=validation_repo)
    boundary = PromoteOpportunityCandidate(candidate_repo, validation_repo, validation,
        opportunity_id_generator=Counter(opportunity), binding_id_generator=Counter(binding),
        clock=Counter(at))
    return sources, candidate_repo, validation_repo, boundary


def counts(connection):
    tables=("opportunity_lifecycles","opportunity_lifecycle_transitions",
            "validation_queue_admission_snapshots","opportunity_market_identity_bindings",
            "opportunity_candidate_promotion_history","opportunity_candidate_promotion_receipts")
    return tuple(connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in tables)


def test_promotion_is_immutable_atomic_and_exactly_replayable_after_restart(tmp_path):
    path=tmp_path/"promotion.db"; sources,candidates,repo,boundary=setup_boundary(path)
    first=boundary.execute(command())
    assert first.replayed is False and first.item.opportunity_id=="opportunity-1"
    assert first.binding.candidate_id=="candidate-1"
    assert first.binding.market_observation_identity==candidates.get_context("candidate-1").market_observation_identity
    assert counts(repo._connection)==(1,1,1,1,1,1)
    with pytest.raises(FrozenInstanceError): first.binding.candidate_id="changed"
    candidates.close();repo.close();close(sources)
    candidates=SQLiteCandidateIssuanceRepository(path);repo=SQLiteCandidatePromotionRepository(path)
    boundary=PromoteOpportunityCandidate(candidates,repo,OpportunityValidationService(queue_repository=repo,lifecycle_repository=repo),
        opportunity_id_generator=Counter("must-not-generate"),binding_id_generator=Counter("must-not-generate"),clock=Counter(ISSUED_AT+timedelta(days=1)))
    replay=boundary.execute(command())
    assert replay.replayed is True and replay.item==first.item and replay.binding==first.binding and replay.receipt==first.receipt
    assert counts(repo._connection)==(1,1,1,1,1,1)
    candidates.close();repo.close()


def test_command_conflict_and_candidate_cardinality_preserve_committed_rows(tmp_path):
    path=tmp_path/"conflict.db"; sources,candidates,repo,boundary=setup_boundary(path)
    boundary.execute(command()); before=counts(repo._connection)
    with pytest.raises(CandidatePromotionCommandConflictError):
        boundary.execute(command(title="Changed"))
    with pytest.raises(CandidateAlreadyPromotedError):
        boundary.execute(command(promotion_command_id="promotion-2", opportunity_id="other"))
    assert counts(repo._connection)==before and not repo._connection.in_transaction
    candidates.close();repo.close();close(sources)


def test_alias_receipt_reuses_opportunity_without_admission_or_identity_regeneration(tmp_path):
    path=tmp_path/"alias.db"; sources,candidates,repo,boundary=setup_boundary(path)
    first=boundary.execute(command())
    alias=boundary.execute(command(promotion_command_id="promotion-2", requested_at=ISSUED_AT+timedelta(hours=1)))
    assert alias.replayed is True and alias.item==first.item and alias.binding==first.binding
    assert counts(repo._connection)==(1,1,1,1,1,2)
    candidates.close();repo.close();close(sources)


def test_receipt_failure_rolls_back_complete_admission(tmp_path):
    path=tmp_path/"rollback.db"; sources,candidates,repo,boundary=setup_boundary(path)
    def fail(_): raise sqlite3.OperationalError("forced receipt failure")
    repo._insert_receipt=fail
    with pytest.raises(CandidatePromotionReceiptError): boundary.execute(command())
    assert counts(repo._connection)==(0,0,0,0,0,0) and not repo._connection.in_transaction
    assert candidates.get_candidate("candidate-1") is not None
    candidates.close();repo.close();close(sources)


@pytest.mark.parametrize("target,error_type",(
    ("lifecycle_current",CandidatePromotionPersistenceError),
    ("lifecycle_history",CandidatePromotionPersistenceError),
    ("admission",CandidatePromotionPersistenceError),
    ("market",CandidatePromotionPersistenceError),
    ("promotion",CandidatePromotionHistoryError),
))
def test_every_pre_receipt_failure_rolls_back(target,error_type,tmp_path):
    path=tmp_path/f"{target}.db";sources,candidates,repo,boundary=setup_boundary(path)
    def fail(*_):raise sqlite3.OperationalError("forced")
    if target=="lifecycle_current":repo._lifecycles._insert_current=fail
    elif target=="lifecycle_history":repo._lifecycles._insert_transition=fail
    elif target=="admission":repo._insert_admission_snapshot=fail
    elif target=="market":repo._insert_market_identity_binding=fail
    else:repo._insert_promotion=fail
    with pytest.raises(error_type):boundary.execute(command())
    assert counts(repo._connection)==(0,0,0,0,0,0) and not repo._connection.in_transaction
    candidates.close();repo.close();close(sources)


def test_append_only_queries_and_no_snapshot_handoff_fabrication(tmp_path):
    path=tmp_path/"readonly.db"; sources,candidates,repo,boundary=setup_boundary(path)
    result=boundary.execute(command()); before=counts(repo._connection)
    assert repo.get_promotion_by_candidate("candidate-1")==result.binding
    assert repo.get_promotion_by_opportunity("opportunity-1")==result.binding
    assert repo.get_promotion_receipt("promotion-1")==result.receipt
    assert counts(repo._connection)==before and not repo._connection.in_transaction
    for table in ("opportunity_candidate_promotion_history","opportunity_candidate_promotion_receipts"):
        with pytest.raises(sqlite3.IntegrityError,match="append-only"):
            repo._connection.execute(f"UPDATE {table} SET rowid=rowid")
        repo._connection.rollback()
    table_names={row[0] for row in repo._connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not {"product_observation_snapshots","price_intelligence_snapshots","economics_calculation_snapshots"} & table_names
    candidates.close();repo.close();close(sources)


def test_separate_connection_same_command_converges_without_partial_admission(tmp_path):
    path=tmp_path/"race.db";sources,initial_candidates,_,issuance=setup_boundary(path)
    # setup_boundary already issued and only its unused promotion repository is closed.
    _.close();initial_candidates.close();close(sources)
    def run(number):
        candidates=SQLiteCandidateIssuanceRepository(path)
        repo=SQLiteCandidatePromotionRepository(path)
        boundary=PromoteOpportunityCandidate(candidates,repo,
            OpportunityValidationService(queue_repository=repo,lifecycle_repository=repo),
            opportunity_id_generator=Counter(f"opportunity-{number}"),
            binding_id_generator=Counter(f"binding-{number}"),clock=Counter(ISSUED_AT))
        try:return boundary.execute(command())
        finally:candidates.close();repo.close()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(run,(1,2)))
    repo=SQLiteCandidatePromotionRepository(path)
    assert {value.item.opportunity_id for value in results} in ({"opportunity-1"},{"opportunity-2"})
    assert counts(repo._connection)==(1,1,1,1,1,1) and not repo._connection.in_transaction
    repo.close()
