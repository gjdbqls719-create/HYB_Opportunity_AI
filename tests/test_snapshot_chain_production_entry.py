from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import inspect
import sqlite3
from types import SimpleNamespace

import pytest

from app.application.snapshot_chain_binding import (
    CompleteSnapshotChainProductionEntry,
    CompleteSnapshotChainProductionRequest,
    SnapshotChainBindingCommandConflictError,
    SnapshotChainBindingNotFoundError,
    SnapshotChainBindingResult,
    SnapshotChainEconomicsSourceConflictError,
    SnapshotChainIncompleteError,
    SnapshotChainMarketIdentityConflictError,
    SnapshotChainPriceSourceConflictError,
    SnapshotChainProductSourceConflictError,
    SnapshotChainVerifiedSourceConflictError,
)
from app.infrastructure.economics_calculation import (
    SQLiteEconomicsCalculationOwnerRepository,
)
from app.infrastructure.opportunity_validation import (
    SQLiteCandidatePromotionRepository,
)
from app.infrastructure.price_intelligence import SQLitePriceAnalysisRepository
from app.infrastructure.product_observation import (
    SQLiteProductSnapshotCaptureRepository,
)
from app.infrastructure.snapshot_chain import SQLiteSnapshotChainBindingRepository
from test_candidate_issuance_foundation import Counter
from test_discovery_correlation_contract import NOW
from test_economics_snapshot_production_entry import (
    close_sources,
    prepare_persisted_sources,
    production_entry as economics_entry,
    request as economics_request,
)


BOUND_AT = NOW + timedelta(hours=1)
COMMITTED_AT = BOUND_AT + timedelta(seconds=1)


def request(**changes):
    values = {
        "command_id": "snapshot-chain-command-1",
        "opportunity_id": "opportunity-1",
        "product_snapshot_capture_command_id": "capture-command-1",
        "price_analysis_command_id": "price-analysis-command-1",
        "economics_calculation_command_id": "economics-command-1",
        "requested_at": NOW + timedelta(minutes=45),
    }
    values.update(changes)
    return CompleteSnapshotChainProductionRequest(**values)


def production_entry(
    sources,
    captures,
    prices,
    economics,
    chains,
    *,
    binding_id_generator=None,
    bound_clock=None,
    receipt_clock=None,
):
    return CompleteSnapshotChainProductionEntry(
        source_repository=sources,
        product_snapshot_capture_repository=captures,
        price_analysis_repository=prices,
        economics_repository=economics,
        snapshot_chain_repository=chains,
        binding_id_generator=binding_id_generator or Counter("snapshot-chain-1"),
        bound_clock=bound_clock or Counter(BOUND_AT),
        receipt_clock=receipt_clock or Counter(COMMITTED_AT),
    )


def prepare_complete_sources(path):
    prepared = prepare_persisted_sources(path)
    sources, candidates, captures, prices, promotions = prepared[:5]
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    economics_result = economics_entry(promotions, prices, economics).execute(
        economics_request()
    )
    return prepared, economics, economics_result


def close_prepared(prepared, economics, chains=None):
    sources, candidates, captures, prices, promotions = prepared[:5]
    if chains is not None:
        chains.close()
    close_sources(sources, candidates, captures, prices, promotions, economics)


def chain_counts(repository):
    return tuple(
        repository._connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in (
            "opportunity_snapshot_chain_binding_history",
            "opportunity_snapshot_chain_product_members",
            "opportunity_snapshot_chain_binding_receipts",
        )
    )


def test_persisted_receipts_create_one_complete_exact_binding(tmp_path):
    path = tmp_path / "complete.db"
    prepared, economics, economics_result = prepare_complete_sources(path)
    captures, prices, promotions = prepared[2], prepared[3], prepared[4]
    captured, analyzed, promoted, verified = prepared[6:10]
    chains = SQLiteSnapshotChainBindingRepository(path)

    result = production_entry(
        promotions, captures, prices, economics, chains
    ).execute(request())

    assert isinstance(result, SnapshotChainBindingResult)
    assert result.replayed is False
    assert result.binding.candidate_opportunity_binding_id == promoted.binding.binding_id
    assert result.binding.candidate_id == promoted.binding.candidate_id
    assert result.binding.opportunity_id == promoted.binding.opportunity_id
    assert result.binding.product_snapshot_ids == captured.receipt.product_snapshot_ids
    assert result.binding.price_snapshot_id == analyzed.receipt.price_snapshot_id
    assert result.binding.economics_snapshot_id == economics_result.receipt.economics_snapshot_id
    assert result.binding.verified_economics_opportunity_id == verified.opportunity_id
    assert result.binding.market_observation_identity == promoted.binding.market_observation_identity
    assert result.receipt.product_snapshot_ids == captured.receipt.product_snapshot_ids
    assert chain_counts(chains) == (1, 2, 1)
    close_prepared(prepared, economics, chains)


def test_capture_order_is_authoritative_and_price_reordering_is_rejected(tmp_path):
    path = tmp_path / "order.db"
    prepared, economics, _ = prepare_complete_sources(path)
    captures, prices, promotions = prepared[2], prepared[3], prepared[4]
    captured, analyzed = prepared[6], prepared[7]
    chains = SQLiteSnapshotChainBindingRepository(path)

    class ReorderedPriceRepository:
        def get_receipt(self, command_id):
            return replace(
                analyzed.receipt,
                product_snapshot_ids=tuple(reversed(analyzed.receipt.product_snapshot_ids)),
            )

        def get_result(self, receipt):
            return replace(analyzed, receipt=receipt)

    with pytest.raises(SnapshotChainPriceSourceConflictError):
        production_entry(
            promotions, captures, ReorderedPriceRepository(), economics, chains
        ).execute(request())

    assert captured.receipt.product_snapshot_ids == (
        captured.snapshots[0].snapshot_id,
        captured.snapshots[1].snapshot_id,
    )
    assert chain_counts(chains) == (0, 0, 0)
    close_prepared(prepared, economics, chains)


@pytest.mark.parametrize(
    "product_ids",
    (
        ("product-snapshot-2", "product-snapshot-1"),
        ("product-snapshot-1",),
        ("product-snapshot-1", "product-snapshot-1"),
    ),
)
def test_tampered_capture_order_subset_or_duplicates_are_rejected(tmp_path, product_ids):
    path = tmp_path / "capture-cohort.db"
    prepared, economics, _ = prepare_complete_sources(path)
    captures, prices, promotions = prepared[2], prepared[3], prepared[4]
    captured = prepared[6]
    chains = SQLiteSnapshotChainBindingRepository(path)
    receipt = SimpleNamespace(
        command_id=captured.receipt.command_id,
        candidate_id=captured.receipt.candidate_id,
        product_snapshot_ids=product_ids,
    )

    class TamperedCaptures:
        def get_receipt(self, command_id):
            return receipt

        def get_result(self, value):
            return replace(captured, receipt=value)

    with pytest.raises(SnapshotChainProductSourceConflictError):
        production_entry(
            promotions, TamperedCaptures(), prices, economics, chains
        ).execute(request())
    assert chain_counts(chains) == (0, 0, 0)
    close_prepared(prepared, economics, chains)


@pytest.mark.parametrize(
    "missing",
    ("opportunity", "promotion", "capture", "price", "economics", "verified", "market"),
)
def test_missing_authoritative_source_never_creates_partial_binding(tmp_path, missing):
    path = tmp_path / f"missing-{missing}.db"
    prepared, economics, _ = prepare_complete_sources(path)
    captures, prices, promotions = prepared[2], prepared[3], prepared[4]
    chains = SQLiteSnapshotChainBindingRepository(path)

    class Sources:
        def get_queue_item(self, opportunity_id):
            return None if missing == "opportunity" else promotions.get_queue_item(opportunity_id)

        def get_promotion_by_opportunity(self, opportunity_id):
            return None if missing == "promotion" else promotions.get_promotion_by_opportunity(opportunity_id)

        def get_verified_economics_snapshot(self, opportunity_id):
            return None if missing == "verified" else promotions.get_verified_economics_snapshot(opportunity_id)

        def get_market_identity_binding(self, opportunity_id):
            return None if missing == "market" else promotions.get_market_identity_binding(opportunity_id)

    class Captures:
        def get_receipt(self, command_id):
            return None if missing == "capture" else captures.get_receipt(command_id)

        def get_result(self, receipt):
            return captures.get_result(receipt)

    class Prices:
        def get_receipt(self, command_id):
            return None if missing == "price" else prices.get_receipt(command_id)

        def get_result(self, receipt):
            return prices.get_result(receipt)

    class Economics:
        def get_receipt(self, command_id):
            return None if missing == "economics" else economics.get_receipt(command_id)

        def get_result(self, receipt):
            return economics.get_result(receipt)

    expected = {
        "opportunity": SnapshotChainBindingNotFoundError,
        "promotion": SnapshotChainBindingNotFoundError,
        "capture": SnapshotChainIncompleteError,
        "price": SnapshotChainIncompleteError,
        "economics": SnapshotChainIncompleteError,
        "verified": SnapshotChainVerifiedSourceConflictError,
        "market": SnapshotChainMarketIdentityConflictError,
    }[missing]
    with pytest.raises(expected):
        production_entry(
            Sources(), Captures(), Prices(), Economics(), chains
        ).execute(request())
    assert chain_counts(chains) == (0, 0, 0)
    close_prepared(prepared, economics, chains)


@pytest.mark.parametrize(
    "conflict,error",
    (
        ("capture-candidate", SnapshotChainProductSourceConflictError),
        ("price-candidate", SnapshotChainPriceSourceConflictError),
        ("price-group", SnapshotChainPriceSourceConflictError),
        ("economics-opportunity", SnapshotChainEconomicsSourceConflictError),
        ("economics-binding", SnapshotChainEconomicsSourceConflictError),
        ("economics-price", SnapshotChainEconomicsSourceConflictError),
        ("verified-opportunity", SnapshotChainVerifiedSourceConflictError),
        ("market", SnapshotChainMarketIdentityConflictError),
    ),
)
def test_cross_stage_lineage_conflicts_stop_before_chain_persistence(
    tmp_path, conflict, error
):
    path = tmp_path / f"conflict-{conflict}.db"
    prepared, economics, economics_result = prepare_complete_sources(path)
    captures, prices, promotions = prepared[2], prepared[3], prepared[4]
    captured, analyzed = prepared[6], prepared[7]
    chains = SQLiteSnapshotChainBindingRepository(path)

    class Sources:
        def get_queue_item(self, opportunity_id):
            return promotions.get_queue_item(opportunity_id)

        def get_promotion_by_opportunity(self, opportunity_id):
            return promotions.get_promotion_by_opportunity(opportunity_id)

        def get_verified_economics_snapshot(self, opportunity_id):
            value = promotions.get_verified_economics_snapshot(opportunity_id)
            return replace(value, opportunity_id="other") if conflict == "verified-opportunity" else value

        def get_market_identity_binding(self, opportunity_id):
            value = promotions.get_market_identity_binding(opportunity_id)
            return replace(value, opportunity_id="other") if conflict == "market" else value

    class Captures:
        def get_receipt(self, command_id):
            value = captured.receipt
            return replace(value, candidate_id="other") if conflict == "capture-candidate" else value

        def get_result(self, receipt):
            return replace(captured, receipt=receipt)

    class Prices:
        def get_receipt(self, command_id):
            value = analyzed.receipt
            if conflict == "price-candidate":
                return replace(value, candidate_id="other")
            if conflict == "price-group":
                return replace(value, finalized_group_id="other")
            return value

        def get_result(self, receipt):
            return replace(analyzed, receipt=receipt)

    class Economics:
        def get_receipt(self, command_id):
            value = economics_result.receipt
            if conflict == "economics-opportunity":
                return replace(value, opportunity_id="other")
            if conflict == "economics-binding":
                return replace(value, candidate_opportunity_binding_id="other")
            if conflict == "economics-price":
                return replace(value, price_intelligence_snapshot_id="other")
            return value

        def get_result(self, receipt):
            return replace(economics_result, receipt=receipt)

    with pytest.raises(error):
        production_entry(
            Sources(), Captures(), Prices(), Economics(), chains
        ).execute(request())
    assert chain_counts(chains) == (0, 0, 0)
    close_prepared(prepared, economics, chains)


def test_exact_replay_after_restart_returns_original_without_suppliers(tmp_path):
    path = tmp_path / "replay.db"
    prepared, economics, _ = prepare_complete_sources(path)
    captures, prices, promotions = prepared[2], prepared[3], prepared[4]
    chains = SQLiteSnapshotChainBindingRepository(path)
    first = production_entry(
        promotions, captures, prices, economics, chains
    ).execute(request())
    close_prepared(prepared, economics, chains)

    class Fail:
        def __init__(self):
            self.calls = 0

        def __call__(self):
            self.calls += 1
            raise AssertionError("replay supplier must not run")

    suppliers = (Fail(), Fail(), Fail())
    promotions = SQLiteCandidatePromotionRepository(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)
    prices = SQLitePriceAnalysisRepository(path)
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    chains = SQLiteSnapshotChainBindingRepository(path)
    replay = production_entry(
        promotions,
        captures,
        prices,
        economics,
        chains,
        binding_id_generator=suppliers[0],
        bound_clock=suppliers[1],
        receipt_clock=suppliers[2],
    ).execute(request())

    assert replay.replayed is True
    assert replay.binding == first.binding
    assert replay.receipt == first.receipt
    assert tuple(value.calls for value in suppliers) == (0, 0, 0)
    assert chain_counts(chains) == (1, 2, 1)
    chains.close(); economics.close(); prices.close(); captures.close(); promotions.close()


def test_changed_same_command_conflicts_and_alias_preserves_binding(tmp_path):
    path = tmp_path / "alias.db"
    prepared, economics, _ = prepare_complete_sources(path)
    captures, prices, promotions = prepared[2], prepared[3], prepared[4]
    chains = SQLiteSnapshotChainBindingRepository(path)
    first = production_entry(
        promotions, captures, prices, economics, chains
    ).execute(request())

    with pytest.raises(SnapshotChainBindingCommandConflictError):
        production_entry(
            promotions, captures, prices, economics, chains
        ).execute(request(requested_at=request().requested_at + timedelta(seconds=1)))

    alias = production_entry(
        promotions,
        captures,
        prices,
        economics,
        chains,
        binding_id_generator=Counter("must-not-win"),
    ).execute(request(command_id="snapshot-chain-command-2"))
    assert alias.binding == first.binding
    assert alias.receipt.binding_id == first.binding.binding_id
    assert chain_counts(chains) == (1, 2, 2)
    close_prepared(prepared, economics, chains)


def test_same_command_converges_across_connections(tmp_path):
    path = tmp_path / "concurrent.db"
    prepared, economics, _ = prepare_complete_sources(path)
    close_prepared(prepared, economics)

    def execute(index):
        promotions = SQLiteCandidatePromotionRepository(path)
        captures = SQLiteProductSnapshotCaptureRepository(path)
        prices = SQLitePriceAnalysisRepository(path)
        economics = SQLiteEconomicsCalculationOwnerRepository(path)
        chains = SQLiteSnapshotChainBindingRepository(path)
        try:
            return production_entry(
                promotions,
                captures,
                prices,
                economics,
                chains,
                binding_id_generator=Counter(f"snapshot-chain-{index}"),
            ).execute(request())
        finally:
            chains.close(); economics.close(); prices.close(); captures.close(); promotions.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = tuple(pool.map(execute, (1, 2)))
    assert results[0].binding == results[1].binding
    assert sum(value.replayed for value in results) == 1
    with SQLiteSnapshotChainBindingRepository(path) as chains:
        assert chain_counts(chains) == (1, 2, 1)


def test_source_failure_and_supplier_failure_do_not_reach_chain_bind():
    class FailingSources:
        def get_queue_item(self, opportunity_id):
            raise RuntimeError("source read failed")

    class ChainSpy:
        def __init__(self):
            self.receipt_calls = 0
            self.bind_calls = 0

        def get_receipt(self, command_id):
            self.receipt_calls += 1
            return None

        def bind(self, *args):
            self.bind_calls += 1
            raise AssertionError("bind must not run")

    never = object()
    chain = ChainSpy()
    with pytest.raises(RuntimeError, match="source read failed"):
        production_entry(
            FailingSources(), never, never, never, chain
        ).execute(request())
    assert (chain.receipt_calls, chain.bind_calls) == (0, 0)


@pytest.mark.parametrize("failure", ("identity", "bound_clock", "receipt_clock"))
def test_identity_or_clock_failure_never_calls_chain_bind(tmp_path, failure):
    path = tmp_path / f"supplier-{failure}.db"
    prepared, economics, _ = prepare_complete_sources(path)
    captures, prices, promotions = prepared[2], prepared[3], prepared[4]

    class Fail:
        def __call__(self):
            raise RuntimeError(failure)

    class ChainSpy:
        def __init__(self):
            self.bind_calls = 0

        def get_receipt(self, command_id):
            return None

        def bind(self, *args):
            self.bind_calls += 1
            raise AssertionError("bind must not run")

    chain = ChainSpy()
    dependencies = {
        "binding_id_generator": Fail() if failure == "identity" else Counter("chain-1"),
        "bound_clock": Fail() if failure == "bound_clock" else Counter(BOUND_AT),
        "receipt_clock": Fail() if failure == "receipt_clock" else Counter(COMMITTED_AT),
    }
    with pytest.raises(RuntimeError, match=failure):
        production_entry(
            promotions, captures, prices, economics, chain, **dependencies
        ).execute(request())
    assert chain.bind_calls == 0
    close_prepared(prepared, economics)


def test_chain_repository_failure_propagates_without_source_mutation(tmp_path):
    path = tmp_path / "chain-failure.db"
    prepared, economics, _ = prepare_complete_sources(path)
    captures, prices, promotions = prepared[2], prepared[3], prepared[4]
    source_counts = tuple(
        economics._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "opportunity_candidate_promotion_history",
            "product_observation_snapshot_history",
            "price_intelligence_snapshot_history",
            "economics_calculation_snapshot_history",
        )
    )

    class ChainFailure(RuntimeError):
        pass

    class FailingChain:
        def get_receipt(self, command_id):
            raise ChainFailure("chain unavailable")

    with pytest.raises(ChainFailure, match="chain unavailable"):
        production_entry(
            promotions, captures, prices, economics, FailingChain()
        ).execute(request())
    assert source_counts == tuple(
        economics._connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "opportunity_candidate_promotion_history",
            "product_observation_snapshot_history",
            "price_intelligence_snapshot_history",
            "economics_calculation_snapshot_history",
        )
    )
    close_prepared(prepared, economics)


def test_malformed_request_and_forbidden_automation_are_absent():
    values = {
        "command_id": "snapshot-chain-command-1",
        "opportunity_id": "opportunity-1",
        "product_snapshot_capture_command_id": "capture-command-1",
        "price_analysis_command_id": "price-analysis-command-1",
        "economics_calculation_command_id": "economics-command-1",
        "requested_at": NOW,
    }
    for changes, error in (
        ({"command_id": ""}, ValueError),
        ({"opportunity_id": ""}, ValueError),
        ({"product_snapshot_capture_command_id": ""}, ValueError),
        ({"price_analysis_command_id": ""}, ValueError),
        ({"economics_calculation_command_id": ""}, ValueError),
        ({"requested_at": NOW.replace(tzinfo=None)}, ValueError),
    ):
        with pytest.raises(error):
            CompleteSnapshotChainProductionRequest(**(values | changes))

    source = inspect.getsource(CompleteSnapshotChainProductionEntry).lower()
    for forbidden in (
        "evaluateproductionSafety".lower(),
        "assess_production_safety",
        "finalizedecisioncomposition",
        "decisionmatrix",
        "dashboard",
        "analyze_product_prices",
        "calculate_verified_economics",
        "sqlite",
        "uuid",
        "latest",
    ):
        assert forbidden not in source
