from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import inspect
from threading import Lock
from uuid import UUID

import pytest

from app.application.candidate_promotion import (
    CandidatePromotionCommandConflictError,
    CandidatePromotionProductionEntry,
)
from app.infrastructure.discovery import SQLiteCandidateIssuanceRepository
from app.infrastructure.opportunity_validation import (
    ProductionCandidateOpportunityBindingIdentityGenerator,
    ProductionOpportunityIdentityGenerator,
    SQLiteCandidatePromotionRepository,
)
import app.infrastructure.opportunity_validation.identity_suppliers as suppliers
from test_candidate_issuance_foundation import Counter, ISSUED_AT
from test_candidate_opportunity_promotion import command
from test_product_snapshot_capture_production_entry import close_all, prepare


class RecordingGenerator:
    def __init__(self, generator):
        self.generator = generator
        self.calls = 0
        self.values = []

    def __call__(self):
        self.calls += 1
        value = self.generator()
        self.values.append(value)
        return value


class Fail:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        raise AssertionError("identity supplier must not run")


def production_entry(candidates, promotions, opportunity, binding, clock=None):
    return CandidatePromotionProductionEntry(
        candidate_repository=candidates,
        promotion_repository=promotions,
        opportunity_id_generator=opportunity,
        binding_id_generator=binding,
        clock=clock or Counter(ISSUED_AT),
    )


def test_promotion_identity_suppliers_are_stateless_callable_infrastructure():
    values = (
        ProductionOpportunityIdentityGenerator(),
        ProductionCandidateOpportunityBindingIdentityGenerator(),
    )

    assert all(callable(value) for value in values)
    assert all(type(value).__slots__ == () for value in values)
    assert all(not hasattr(value, "__dict__") for value in values)
    assert all(inspect.signature(value).parameters == {} for value in values)
    source = inspect.getsource(suppliers).lower()
    for forbidden in (
        "hashlib",
        "fingerprint",
        "repository",
        "candidate_id",
        "command_id",
        "market_identity",
    ):
        assert forbidden not in source


def test_promotion_identity_suppliers_return_uuid4_hex_without_transform(
    monkeypatch,
):
    issued = iter(
        (
            UUID("12345678-1234-4abc-8def-1234567890ab"),
            UUID("abcdefab-cdef-4abc-8def-abcdefabcdef"),
        )
    )
    monkeypatch.setattr(suppliers, "uuid4", lambda: next(issued))

    opportunity = ProductionOpportunityIdentityGenerator()()
    binding = ProductionCandidateOpportunityBindingIdentityGenerator()()

    assert opportunity == "1234567812344abc8def1234567890ab"
    assert binding == "abcdefabcdef4abc8defabcdefabcdef"


def test_each_supplier_call_returns_unique_lowercase_uuid_hex():
    opportunity = ProductionOpportunityIdentityGenerator()
    binding = ProductionCandidateOpportunityBindingIdentityGenerator()

    values = [opportunity() for _ in range(64)] + [binding() for _ in range(64)]

    assert len(values) == len(set(values))
    assert all(len(value) == 32 for value in values)
    assert all(value == value.lower() for value in values)
    assert all(set(value) <= set("0123456789abcdef") for value in values)


def test_promotion_identity_suppliers_remain_unique_under_concurrency():
    opportunity = ProductionOpportunityIdentityGenerator()
    binding = ProductionCandidateOpportunityBindingIdentityGenerator()

    with ThreadPoolExecutor(max_workers=16) as pool:
        values = tuple(
            pool.map(
                lambda index: opportunity() if index % 2 else binding(),
                range(256),
            )
        )

    assert len(values) == len(set(values))


def test_concrete_suppliers_promote_and_preserve_generated_identities(tmp_path):
    path = tmp_path / "promotion-suppliers.db"
    sources, candidates, _, _, _ = prepare(path)
    promotions = SQLiteCandidatePromotionRepository(path)
    opportunity = RecordingGenerator(ProductionOpportunityIdentityGenerator())
    binding = RecordingGenerator(
        ProductionCandidateOpportunityBindingIdentityGenerator()
    )
    try:
        result = production_entry(
            candidates, promotions, opportunity, binding
        ).execute(command())

        assert opportunity.calls == binding.calls == 1
        assert result.item.opportunity_id == opportunity.values[0]
        assert result.binding.opportunity_id == opportunity.values[0]
        assert result.binding.binding_id == binding.values[0]
        assert result.receipt.opportunity_id == opportunity.values[0]
        assert promotions.get_promotion_by_candidate("candidate-1") == result.binding
    finally:
        promotions.close()
        candidates.close()
        close_all(*sources)


def test_explicit_opportunity_id_skips_only_opportunity_supplier(tmp_path):
    path = tmp_path / "explicit-opportunity.db"
    sources, candidates, _, _, _ = prepare(path)
    promotions = SQLiteCandidatePromotionRepository(path)
    opportunity = Fail()
    binding = RecordingGenerator(
        ProductionCandidateOpportunityBindingIdentityGenerator()
    )
    try:
        result = production_entry(
            candidates, promotions, opportunity, binding
        ).execute(command(opportunity_id="caller-opportunity"))

        assert opportunity.calls == 0
        assert binding.calls == 1
        assert result.item.opportunity_id == "caller-opportunity"
        assert result.binding.opportunity_id == "caller-opportunity"
    finally:
        promotions.close()
        candidates.close()
        close_all(*sources)


def test_exact_replay_alias_and_conflict_skip_identity_suppliers(tmp_path):
    path = tmp_path / "promotion-replay.db"
    sources, candidates, _, _, _ = prepare(path)
    promotions = SQLiteCandidatePromotionRepository(path)
    first = production_entry(
        candidates,
        promotions,
        ProductionOpportunityIdentityGenerator(),
        ProductionCandidateOpportunityBindingIdentityGenerator(),
    ).execute(command())
    opportunity = Fail()
    binding = Fail()
    replay_entry = production_entry(
        candidates, promotions, opportunity, binding
    )
    try:
        replay = replay_entry.execute(command())
        alias = replay_entry.execute(
            replace(command(), promotion_command_id="promotion-alias")
        )
        with pytest.raises(CandidatePromotionCommandConflictError):
            replay_entry.execute(command(title="changed"))

        assert replay.replayed is True
        assert replay.item == first.item
        assert replay.binding == first.binding
        assert alias.replayed is True
        assert alias.item == first.item
        assert alias.binding == first.binding
        assert opportunity.calls == binding.calls == 0
    finally:
        promotions.close()
        candidates.close()
        close_all(*sources)


def test_concurrent_same_subject_keeps_only_winner_generated_identities(
    tmp_path, monkeypatch
):
    path = tmp_path / "promotion-race.db"
    sources, candidates, _, _, _ = prepare(path)
    candidates.close()
    close_all(*sources)
    generated = []
    lock = Lock()
    next_value = 1

    def uuid4():
        nonlocal next_value
        with lock:
            value = UUID(int=next_value)
            next_value += 1
            generated.append(value.hex)
            return value

    monkeypatch.setattr(suppliers, "uuid4", uuid4)

    def promote(_):
        candidate_repository = SQLiteCandidateIssuanceRepository(path)
        promotion_repository = SQLiteCandidatePromotionRepository(path)
        try:
            return production_entry(
                candidate_repository,
                promotion_repository,
                ProductionOpportunityIdentityGenerator(),
                ProductionCandidateOpportunityBindingIdentityGenerator(),
            ).execute(command())
        finally:
            promotion_repository.close()
            candidate_repository.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(promote, range(2)))

    repository = SQLiteCandidatePromotionRepository(path)
    try:
        persisted = repository.get_promotion_by_candidate("candidate-1")
        stored_ids = {persisted.opportunity_id, persisted.binding_id}
        assert all(result.binding == persisted for result in results)
        assert stored_ids <= set(generated)
        assert repository._connection.execute(
            "SELECT COUNT(*) FROM opportunity_candidate_promotion_history"
        ).fetchone()[0] == 1
        assert repository._connection.execute(
            "SELECT COUNT(*) FROM opportunity_candidate_promotion_receipts"
        ).fetchone()[0] == 1
        assert not repository._connection.in_transaction
    finally:
        repository.close()
