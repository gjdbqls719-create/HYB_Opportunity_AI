from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import inspect

import pytest

from app.application.candidate_issuance import (
    CandidateGroupNotInResultError,
    CandidateIdentityGenerationError,
    CandidateIssuanceCommandConflictError,
    CandidateIssuanceProductionEntry,
)
from app.infrastructure.discovery import SQLiteCandidateIssuanceRepository
from test_candidate_issuance_foundation import (
    Counter,
    ISSUED_AT,
    close,
    issuance_command,
    repositories,
)
from test_candidate_issuance_persistence import counts
from test_discovery_execution_result_sqlite_persistence import result


class Fail:
    def __init__(self, message="dependency must not be called"):
        self.message = message
        self.calls = 0

    def __call__(self):
        self.calls += 1
        raise AssertionError(self.message)


def production_entry(
    path,
    *,
    candidate_id_generator,
    issuance_clock,
    receipt_clock,
    completed=True,
):
    sources = repositories(path, completed=completed)
    candidates = SQLiteCandidateIssuanceRepository(path)
    entry = CandidateIssuanceProductionEntry(
        command_repository=sources[0],
        result_repository=sources[1],
        group_repository=sources[2],
        observation_repository=sources[3],
        candidate_repository=candidates,
        candidate_id_generator=candidate_id_generator,
        issuance_clock=issuance_clock,
        receipt_clock=receipt_clock,
    )
    return sources, candidates, entry


def test_production_entry_commits_existing_candidate_contract_from_completed_discovery(
    tmp_path,
):
    path = tmp_path / "candidate-production.db"
    candidate_id = Counter("candidate-production-1")
    issued_at = Counter(ISSUED_AT)
    committed_at = Counter(ISSUED_AT + timedelta(seconds=1))
    sources, candidates, entry = production_entry(
        path,
        candidate_id_generator=candidate_id,
        issuance_clock=issued_at,
        receipt_clock=committed_at,
    )

    response = entry.execute(issuance_command())

    assert response.replayed is False
    assert response.issuance.candidate_identity.candidate_id == "candidate-production-1"
    assert response.issuance.candidate_identity.discovery_reference == (
        "collector:ebay:item-1"
    )
    assert response.issuance.discovery_context.market_observation_identity == (
        issuance_command().market_observation_identity
    )
    assert response.receipt.candidate_id == response.issuance.candidate_identity.candidate_id
    assert response.receipt.discovery_command_id == "command-1"
    assert response.receipt.discovery_execution_id == "execution-1"
    assert response.receipt.finalized_group_id == "group-opaque-1"
    assert response.receipt.receipt_committed_at == committed_at.value
    assert candidate_id.calls == issued_at.calls == committed_at.calls == 1
    assert counts(candidates._connection) == (1, 1, 1)
    assert candidates.get_candidate("candidate-production-1") == (
        response.issuance.candidate_identity
    )
    assert candidates.get_context("candidate-production-1") == (
        response.issuance.discovery_context
    )
    close(sources)
    candidates.close()


def test_production_entry_exact_replay_after_restart_uses_no_suppliers(tmp_path):
    path = tmp_path / "candidate-replay.db"
    sources, candidates, entry = production_entry(
        path,
        candidate_id_generator=Counter("candidate-1"),
        issuance_clock=Counter(ISSUED_AT),
        receipt_clock=Counter(ISSUED_AT + timedelta(seconds=1)),
    )
    first = entry.execute(issuance_command())
    close(sources)
    candidates.close()

    candidate_id = Fail()
    issued_at = Fail()
    committed_at = Fail()
    sources, candidates, restarted = production_entry(
        path,
        candidate_id_generator=candidate_id,
        issuance_clock=issued_at,
        receipt_clock=committed_at,
    )

    replay = restarted.execute(issuance_command())

    assert replay.replayed is True
    assert replay.issuance == first.issuance
    assert replay.receipt == first.receipt
    assert candidate_id.calls == issued_at.calls == committed_at.calls == 0
    assert counts(candidates._connection) == (1, 1, 1)
    close(sources)
    candidates.close()


def test_production_entry_subject_alias_reuses_candidate_and_adds_only_receipt(
    tmp_path,
):
    path = tmp_path / "candidate-alias.db"
    sources, candidates, entry = production_entry(
        path,
        candidate_id_generator=Counter("candidate-1"),
        issuance_clock=Counter(ISSUED_AT),
        receipt_clock=Counter(ISSUED_AT),
    )
    first = entry.execute(issuance_command())
    close(sources)
    candidates.close()

    candidate_id = Fail()
    issued_at = Fail()
    committed_at = Counter(ISSUED_AT + timedelta(seconds=1))
    sources, candidates, restarted = production_entry(
        path,
        candidate_id_generator=candidate_id,
        issuance_clock=issued_at,
        receipt_clock=committed_at,
    )

    alias = restarted.execute(
        replace(issuance_command(), issuance_command_id="issuance-command-2")
    )

    assert alias.issuance == first.issuance
    assert alias.receipt.issuance_command_id == "issuance-command-2"
    assert alias.receipt.candidate_id == first.issuance.candidate_identity.candidate_id
    assert candidate_id.calls == issued_at.calls == 0
    assert committed_at.calls == 1
    assert counts(candidates._connection) == (1, 1, 2)
    close(sources)
    candidates.close()


def test_production_entry_rejects_zero_result_without_issuing_or_writing(tmp_path):
    path = tmp_path / "candidate-zero.db"
    candidate_id = Fail()
    issued_at = Fail()
    committed_at = Fail()
    sources, candidates, entry = production_entry(
        path,
        candidate_id_generator=candidate_id,
        issuance_clock=issued_at,
        receipt_clock=committed_at,
        completed=False,
    )
    sources[1].save_result(result(finalized_group_ids=()))

    with pytest.raises(CandidateGroupNotInResultError):
        entry.execute(issuance_command())

    assert candidate_id.calls == issued_at.calls == committed_at.calls == 0
    assert counts(candidates._connection) == (0, 0, 0)
    close(sources)
    candidates.close()


def test_production_entry_preserves_conflicts_and_supplier_failure_isolation(tmp_path):
    path = tmp_path / "candidate-failures.db"
    sources, candidates, entry = production_entry(
        path,
        candidate_id_generator=Counter("candidate-1"),
        issuance_clock=Counter(ISSUED_AT),
        receipt_clock=Counter(ISSUED_AT),
    )
    entry.execute(issuance_command())
    before = counts(candidates._connection)

    with pytest.raises(CandidateIssuanceCommandConflictError):
        entry.execute(replace(issuance_command(), requested_at=ISSUED_AT))

    assert counts(candidates._connection) == before
    close(sources)
    candidates.close()

    path = tmp_path / "candidate-provider.db"
    sources, candidates, entry = production_entry(
        path,
        candidate_id_generator=Fail("candidate provider failed"),
        issuance_clock=Counter(ISSUED_AT),
        receipt_clock=Counter(ISSUED_AT),
    )
    with pytest.raises(CandidateIdentityGenerationError, match="generation failed"):
        entry.execute(issuance_command())
    assert counts(candidates._connection) == (0, 0, 0)
    close(sources)
    candidates.close()


def test_production_entry_concurrent_aliases_preserve_candidate_cardinality(tmp_path):
    path = tmp_path / "candidate-concurrent.db"
    sources = repositories(path)
    close(sources)

    def execute(number):
        command = replace(
            issuance_command(),
            issuance_command_id=f"issuance-command-{number}",
        )
        sources, candidates, entry = production_entry(
            path,
            candidate_id_generator=Counter(f"candidate-{number}"),
            issuance_clock=Counter(ISSUED_AT + timedelta(seconds=number)),
            receipt_clock=Counter(ISSUED_AT + timedelta(seconds=number)),
        )
        try:
            return entry.execute(command)
        finally:
            close(sources)
            candidates.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = tuple(pool.map(execute, (1, 2)))

    assert len(
        {response.issuance.candidate_identity.candidate_id for response in responses}
    ) == 1
    with SQLiteCandidateIssuanceRepository(path) as candidates:
        assert counts(candidates._connection) == (1, 1, 2)


def test_production_entry_is_composition_only():
    source = inspect.getsource(CandidateIssuanceProductionEntry).lower()
    for forbidden in (
        "sqlite",
        "productobservationsnapshot",
        "captureproductsnapshots",
        "promoteopportunitycandidate",
        "addtovalidationqueuecommand",
        "opportunitylifecycle",
        "uuid",
        "hashlib",
        "fingerprint",
    ):
        assert forbidden not in source
