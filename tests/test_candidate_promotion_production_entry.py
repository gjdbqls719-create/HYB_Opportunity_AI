from datetime import timedelta
import inspect
import sqlite3

import pytest

from app.application.candidate_promotion import (
    CandidateForPromotionNotFoundError,
    CandidatePromotionCommandConflictError,
    CandidatePromotionContextNotFoundError,
    CandidatePromotionProductionEntry,
    CandidatePromotionReceiptError,
)
from app.domain.opportunity import OpportunityLifecycleStatus
from app.infrastructure.discovery import SQLiteCandidateIssuanceRepository
from app.infrastructure.opportunity_validation import (
    SQLiteCandidatePromotionRepository,
)
from test_candidate_issuance_foundation import Counter, ISSUED_AT
from test_candidate_opportunity_promotion import command
from test_product_snapshot_capture_production_entry import close_all, prepare


def production_entry(
    candidates,
    promotions,
    *,
    opportunity_id_generator=None,
    binding_id_generator=None,
    clock=None,
):
    return CandidatePromotionProductionEntry(
        candidate_repository=candidates,
        promotion_repository=promotions,
        opportunity_id_generator=(
            opportunity_id_generator or Counter("opportunity-1")
        ),
        binding_id_generator=binding_id_generator or Counter("binding-1"),
        clock=clock or Counter(ISSUED_AT),
    )


def promotion_counts(repository):
    return tuple(
        repository._connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in (
            "opportunity_lifecycles",
            "opportunity_lifecycle_transitions",
            "validation_queue_admission_snapshots",
            "opportunity_market_identity_bindings",
            "opportunity_candidate_promotion_history",
            "opportunity_candidate_promotion_receipts",
        )
    )


def test_persisted_candidate_and_context_are_promoted_through_existing_owner(tmp_path):
    path = tmp_path / "production.db"
    sources, candidates, issuance, _, _ = prepare(path)
    promotions = SQLiteCandidatePromotionRepository(path)

    promoted = production_entry(candidates, promotions).execute(command())
    context = candidates.get_context(issuance.candidate_identity.candidate_id)

    assert promoted.replayed is False
    assert promoted.item.opportunity_id == "opportunity-1"
    assert promoted.item.discovery_reference == issuance.candidate_identity.discovery_reference
    assert promoted.item.marketplace == context.market_observation_identity.marketplace
    assert promoted.item.lifecycle_status is OpportunityLifecycleStatus.DISCOVERED
    assert promoted.item.lifecycle_version == 1
    assert promoted.binding.binding_id == "binding-1"
    assert promoted.binding.candidate_id == issuance.candidate_identity.candidate_id
    assert promoted.binding.discovery_reference == issuance.candidate_identity.discovery_reference
    assert promoted.binding.market_observation_identity == context.market_observation_identity
    assert promoted.binding.discovery_command_id == context.command_id
    assert promoted.binding.discovery_execution_id == context.discovery_execution_id
    assert promoted.binding.finalized_group_id == issuance.finalized_group_id
    assert promoted.receipt.opportunity_id == promoted.item.opportunity_id
    assert promotions.get_promotion_by_candidate("candidate-1") == promoted.binding
    assert promotions.get_promotion_by_opportunity("opportunity-1") == promoted.binding
    assert promotions.get_market_identity_binding("opportunity-1").market_observation_identity == context.market_observation_identity
    assert promotions.get("opportunity-1").status is OpportunityLifecycleStatus.DISCOVERED
    assert len(promotions.list_transitions("opportunity-1")) == 1
    assert promotion_counts(promotions) == (1, 1, 1, 1, 1, 1)
    promotions.close()
    candidates.close()
    close_all(*sources)


def test_explicit_opportunity_id_is_preserved_without_generator_inference(tmp_path):
    path = tmp_path / "explicit.db"
    sources, candidates, _, _, _ = prepare(path)
    promotions = SQLiteCandidatePromotionRepository(path)

    class FailOpportunityId:
        def __call__(self):
            raise AssertionError("explicit Opportunity ID must be authoritative")

    promoted = production_entry(
        candidates,
        promotions,
        opportunity_id_generator=FailOpportunityId(),
    ).execute(command(opportunity_id="caller-opportunity"))

    assert promoted.item.opportunity_id == "caller-opportunity"
    assert promoted.binding.opportunity_id == "caller-opportunity"
    assert promoted.receipt.opportunity_id == "caller-opportunity"
    promotions.close()
    candidates.close()
    close_all(*sources)


def test_exact_replay_after_restart_skips_identity_and_clock_dependencies(tmp_path):
    path = tmp_path / "replay.db"
    sources, candidates, _, _, _ = prepare(path)
    promotions = SQLiteCandidatePromotionRepository(path)
    first = production_entry(candidates, promotions).execute(command())
    promotions.close()
    candidates.close()
    close_all(*sources)

    class Fail:
        def __init__(self):
            self.calls = 0

        def __call__(self):
            self.calls += 1
            raise AssertionError("replay dependency must not run")

    opportunity = Fail()
    binding = Fail()
    clock = Fail()
    candidates = SQLiteCandidateIssuanceRepository(path)
    promotions = SQLiteCandidatePromotionRepository(path)
    replay = production_entry(
        candidates,
        promotions,
        opportunity_id_generator=opportunity,
        binding_id_generator=binding,
        clock=clock,
    ).execute(command())

    assert replay.replayed is True
    assert replay.item == first.item
    assert replay.binding == first.binding
    assert replay.receipt == first.receipt
    assert (opportunity.calls, binding.calls, clock.calls) == (0, 0, 0)
    assert promotion_counts(promotions) == (1, 1, 1, 1, 1, 1)
    with pytest.raises(CandidatePromotionCommandConflictError):
        production_entry(candidates, promotions).execute(command(title="Changed"))
    promotions.close()
    candidates.close()


@pytest.mark.parametrize("missing", ("candidate", "context"))
def test_missing_persisted_candidate_fact_stops_before_validation(missing):
    class Candidates:
        def get_candidate(self, candidate_id):
            if missing == "candidate":
                return None
            from app.domain.discovery_identity import OpportunityCandidateIdentity

            return OpportunityCandidateIdentity("candidate-1", "discovery-1")

        def get_context(self, candidate_id):
            assert missing == "context"
            return None

    class Promotions:
        def validate_promotion_replay(self, command_id, fingerprint):
            return None

        def __getattr__(self, name):
            raise AssertionError(f"{name} must not be called")

    expected = (
        CandidateForPromotionNotFoundError
        if missing == "candidate"
        else CandidatePromotionContextNotFoundError
    )
    with pytest.raises(expected):
        production_entry(Candidates(), Promotions()).execute(command())


def test_receipt_failure_rolls_back_complete_production_admission(tmp_path):
    path = tmp_path / "rollback.db"
    sources, candidates, _, _, _ = prepare(path)
    promotions = SQLiteCandidatePromotionRepository(path)
    candidate_before = candidates.get_candidate("candidate-1")
    context_before = candidates.get_context("candidate-1")

    def fail_receipt(value):
        raise sqlite3.OperationalError("forced receipt failure")

    promotions._insert_receipt = fail_receipt
    with pytest.raises(CandidatePromotionReceiptError):
        production_entry(candidates, promotions).execute(command())

    assert promotion_counts(promotions) == (0, 0, 0, 0, 0, 0)
    assert not promotions._connection.in_transaction
    assert candidates.get_candidate("candidate-1") == candidate_before
    assert candidates.get_context("candidate-1") == context_before
    promotions.close()
    candidates.close()
    close_all(*sources)


def test_restart_reconstruction_and_append_only_binding_receipt(tmp_path):
    path = tmp_path / "append-only.db"
    sources, candidates, _, _, _ = prepare(path)
    promotions = SQLiteCandidatePromotionRepository(path)
    committed = production_entry(candidates, promotions).execute(command())
    promotions.close()
    candidates.close()
    close_all(*sources)

    promotions = SQLiteCandidatePromotionRepository(path)
    assert promotions.get_queue_item(committed.item.opportunity_id) == committed.item
    assert promotions.get_promotion_by_candidate("candidate-1") == committed.binding
    assert promotions.get_promotion_receipt("promotion-1") == committed.receipt
    for table in (
        "opportunity_candidate_promotion_history",
        "opportunity_candidate_promotion_receipts",
    ):
        for statement in (
            f"UPDATE {table} SET rowid=rowid",
            f"DELETE FROM {table}",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                promotions._connection.execute(statement)
            promotions._connection.rollback()
    promotions.close()


def test_production_entry_is_composition_only():
    source = inspect.getsource(CandidatePromotionProductionEntry).lower()
    for forbidden in (
        "economics",
        "snapshotchain",
        "decision",
        "dashboard",
        "discoveryruntime",
        "productobservationsnapshot",
        "priceintelligence",
        "engine",
        "uuid",
        "hashlib",
    ):
        assert forbidden not in source
