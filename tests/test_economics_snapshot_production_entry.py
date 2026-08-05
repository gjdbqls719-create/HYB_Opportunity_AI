from dataclasses import replace
from datetime import timedelta
import inspect
import sqlite3

import pytest

from app.application.candidate_promotion import CandidatePromotionProductionEntry
from app.application.economics_calculation_owner import (
    EconomicsCalculationCommandConflictError,
    EconomicsCalculationExecutionError,
    EconomicsCalculationPriceSourceConflictError,
    EconomicsCalculationReceiptPersistenceError,
    EconomicsCalculationSourceNotFoundError,
    EconomicsSnapshotProductionEntry,
    EconomicsSnapshotProductionRequest,
)
from app.application.price_analysis import CandidatePriceAnalysisProductionEntry
from app.application.product_snapshot_capture import (
    CandidateProductSnapshotCaptureProductionEntry,
)
from app.application.verified_economics_admission import (
    FinalizeVerifiedEconomicsAdmission,
    FinalizeVerifiedEconomicsAdmissionCommand,
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
from engine.opportunity import calculate_verified_economics
from test_candidate_issuance_foundation import Counter, ISSUED_AT
from test_candidate_opportunity_promotion import command as promotion_command
from test_candidate_price_analysis_production_entry import (
    GENERATED_AT as PRICE_GENERATED_AT,
    request as price_request,
)
from test_discovery_correlation_contract import NOW
from test_economics_calculation_snapshot import inputs, parameters
from test_product_snapshot_capture_production_entry import (
    capture_request,
    close_all,
    prepare,
)


ECONOMICS_GENERATED_AT = PRICE_GENERATED_AT + timedelta(minutes=10)
ECONOMICS_COMMITTED_AT = ECONOMICS_GENERATED_AT + timedelta(seconds=1)


def prepare_persisted_sources(path, *, verified=True):
    sources, candidates, issuance, _, _ = prepare(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)
    captured = CandidateProductSnapshotCaptureProductionEntry(
        candidate_repository=candidates,
        group_repository=sources[2],
        capture_repository=captures,
        receipt_clock=Counter(ISSUED_AT),
    ).execute(capture_request(issuance))
    prices = SQLitePriceAnalysisRepository(path)
    analyzed = CandidatePriceAnalysisProductionEntry(
        candidate_repository=candidates,
        capture_repository=captures,
        analysis_repository=prices,
        snapshot_id_generator=Counter("price-snapshot-1"),
        generated_clock=Counter(PRICE_GENERATED_AT),
        receipt_clock=Counter(PRICE_GENERATED_AT + timedelta(seconds=1)),
    ).execute(price_request(issuance))
    promotions = SQLiteCandidatePromotionRepository(path)
    promoted = CandidatePromotionProductionEntry(
        candidate_repository=candidates,
        promotion_repository=promotions,
        opportunity_id_generator=Counter("opportunity-1"),
        binding_id_generator=Counter("binding-1"),
        clock=Counter(ISSUED_AT),
    ).execute(promotion_command())
    verified_snapshot = None
    if verified:
        verified_snapshot = FinalizeVerifiedEconomicsAdmission(promotions).execute(
            FinalizeVerifiedEconomicsAdmissionCommand(
                opportunity_id=promoted.item.opportunity_id,
                command_id="verified-command-1",
                operator_id="founder",
                inputs=inputs(),
                snapshot_at=NOW,
            )
        ).snapshot
    return (
        sources,
        candidates,
        captures,
        prices,
        promotions,
        issuance,
        captured,
        analyzed,
        promoted,
        verified_snapshot,
    )


def request(**changes):
    values = {
        "command_id": "economics-command-1",
        "opportunity_id": "opportunity-1",
        "price_analysis_command_id": "price-analysis-command-1",
        "calculation_parameters": parameters(),
        "calculation_version": "verified-economics-calculator-v1",
        "requested_at": NOW + timedelta(minutes=30),
    }
    values.update(changes)
    return EconomicsSnapshotProductionRequest(**values)


def production_entry(
    promotions,
    prices,
    economics,
    *,
    snapshot_id_generator=None,
    generated_clock=None,
    receipt_clock=None,
    calculator=calculate_verified_economics,
):
    return EconomicsSnapshotProductionEntry(
        promotion_repository=promotions,
        price_analysis_repository=prices,
        economics_repository=economics,
        snapshot_id_generator=(
            snapshot_id_generator or Counter("economics-snapshot-1")
        ),
        generated_clock=generated_clock or Counter(ECONOMICS_GENERATED_AT),
        receipt_clock=receipt_clock or Counter(ECONOMICS_COMMITTED_AT),
        calculator=calculator,
    )


def economics_counts(repository):
    return tuple(
        repository._connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in (
            "economics_calculation_snapshot_history",
            "economics_calculation_receipts",
        )
    )


def close_sources(sources, candidates, captures, prices, promotions, economics):
    economics.close()
    promotions.close()
    prices.close()
    captures.close()
    candidates.close()
    close_all(*sources)


def test_persisted_opportunity_price_and_verified_sources_drive_calculation(tmp_path):
    path = tmp_path / "production.db"
    prepared = prepare_persisted_sources(path)
    sources, candidates, captures, prices, promotions = prepared[:5]
    analyzed, promoted, verified = prepared[7], prepared[8], prepared[9]
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    seen = []

    def calculator(**kwargs):
        seen.append(kwargs)
        return calculate_verified_economics(**kwargs)

    result = production_entry(
        promotions,
        prices,
        economics,
        calculator=calculator,
    ).execute(request())

    assert len(seen) == 1
    assert seen[0]["economics"] == verified.inputs
    assert "price" not in seen[0]
    assert result.replayed is False
    assert result.snapshot.snapshot_id == "economics-snapshot-1"
    assert result.snapshot.opportunity_identity.opportunity_id == promoted.item.opportunity_id
    assert result.snapshot.candidate_opportunity_binding_id == promoted.binding.binding_id
    assert result.snapshot.candidate_id == promoted.binding.candidate_id
    assert result.snapshot.price_intelligence_snapshot_id == analyzed.snapshot.snapshot_id
    assert result.snapshot.verified_economics_opportunity_id == verified.opportunity_id
    assert result.snapshot.market_observation_identity == promoted.binding.market_observation_identity
    assert result.receipt.price_analysis_command_id == analyzed.receipt.command_id
    assert result.receipt.generated_at == ECONOMICS_GENERATED_AT
    assert result.receipt.committed_at == ECONOMICS_COMMITTED_AT
    assert economics_counts(economics) == (1, 1)
    close_sources(sources, candidates, captures, prices, promotions, economics)


def test_exact_replay_after_restart_skips_calculator_identity_and_clocks(tmp_path):
    path = tmp_path / "replay.db"
    prepared = prepare_persisted_sources(path)
    sources, candidates, captures, prices, promotions = prepared[:5]
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    first = production_entry(promotions, prices, economics).execute(request())
    close_sources(sources, candidates, captures, prices, promotions, economics)

    class Fail:
        def __init__(self):
            self.calls = 0

        def __call__(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("replay owner dependency must not run")

    snapshot_id = Fail()
    generated = Fail()
    committed = Fail()
    calculator = Fail()
    promotions = SQLiteCandidatePromotionRepository(path)
    prices = SQLitePriceAnalysisRepository(path)
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    replay = production_entry(
        promotions,
        prices,
        economics,
        snapshot_id_generator=snapshot_id,
        generated_clock=generated,
        receipt_clock=committed,
        calculator=calculator,
    ).execute(request())

    assert replay.replayed is True
    assert replay.snapshot == first.snapshot
    assert replay.receipt == first.receipt
    assert tuple(
        value.calls for value in (snapshot_id, generated, committed, calculator)
    ) == (0, 0, 0, 0)
    assert economics_counts(economics) == (1, 1)
    with pytest.raises(EconomicsCalculationCommandConflictError):
        production_entry(promotions, prices, economics).execute(
            request(calculation_version="changed")
        )
    economics.close()
    prices.close()
    promotions.close()


def test_missing_promotion_or_price_receipt_stops_before_economics_owner():
    class Promotions:
        def get_promotion_by_opportunity(self, opportunity_id):
            return None

    class Prices:
        def get_receipt(self, command_id):
            return None

    class NeverCalled:
        def __getattr__(self, name):
            raise AssertionError(f"{name} must not be called")

    with pytest.raises(EconomicsCalculationSourceNotFoundError):
        production_entry(Promotions(), NeverCalled(), NeverCalled()).execute(request())

    binding = type(
        "Binding",
        (),
        {
            "binding_id": "binding-1",
            "candidate_id": "candidate-1",
            "opportunity_id": "opportunity-1",
            "market_observation_identity": object(),
        },
    )()

    class BindingPromotions:
        def get_promotion_by_opportunity(self, opportunity_id):
            return binding

    with pytest.raises(EconomicsCalculationSourceNotFoundError):
        production_entry(BindingPromotions(), Prices(), NeverCalled()).execute(request())


def test_missing_verified_economics_is_rejected_without_writes(tmp_path):
    path = tmp_path / "missing-verified.db"
    prepared = prepare_persisted_sources(path, verified=False)
    sources, candidates, captures, prices, promotions = prepared[:5]
    economics = SQLiteEconomicsCalculationOwnerRepository(path)

    with pytest.raises(EconomicsCalculationSourceNotFoundError):
        production_entry(promotions, prices, economics).execute(request())

    assert economics_counts(economics) == (0, 0)
    close_sources(sources, candidates, captures, prices, promotions, economics)


def test_price_candidate_or_market_lineage_conflict_is_rejected(tmp_path):
    path = tmp_path / "price-conflict.db"
    prepared = prepare_persisted_sources(path)
    sources, candidates, captures, prices, promotions = prepared[:5]
    analyzed = prepared[7]
    economics = SQLiteEconomicsCalculationOwnerRepository(path)

    class ConflictingPrices:
        def get_receipt(self, command_id):
            return analyzed.receipt

        def get_result(self, receipt):
            from app.domain.discovery_identity import OpportunityCandidateIdentity

            snapshot = replace(
                analyzed.snapshot,
                candidate_identity=OpportunityCandidateIdentity(
                    "other-candidate",
                    analyzed.snapshot.candidate_identity.discovery_reference,
                ),
            )
            return replace(analyzed, snapshot=snapshot)

    with pytest.raises(EconomicsCalculationPriceSourceConflictError):
        production_entry(
            promotions,
            ConflictingPrices(),
            economics,
        ).execute(request())
    assert economics_counts(economics) == (0, 0)
    close_sources(sources, candidates, captures, prices, promotions, economics)


def test_calculator_and_receipt_failures_preserve_all_sources(tmp_path):
    path = tmp_path / "failure.db"
    prepared = prepare_persisted_sources(path)
    sources, candidates, captures, prices, promotions = prepared[:5]
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    source_counts = tuple(
        economics._connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in (
            "opportunity_lifecycles",
            "opportunity_candidate_promotion_history",
            "price_intelligence_snapshot_history",
            "verified_economics_snapshots",
        )
    )

    def fail_calculator(**kwargs):
        raise RuntimeError("calculator failed")

    with pytest.raises(EconomicsCalculationExecutionError):
        production_entry(
            promotions,
            prices,
            economics,
            calculator=fail_calculator,
        ).execute(request())
    assert economics_counts(economics) == (0, 0)

    def fail_receipt(value):
        raise sqlite3.OperationalError("forced receipt failure")

    economics._insert_receipt = fail_receipt
    with pytest.raises(EconomicsCalculationReceiptPersistenceError):
        production_entry(promotions, prices, economics).execute(request())
    assert economics_counts(economics) == (0, 0)
    assert not economics._connection.in_transaction
    assert source_counts == tuple(
        economics._connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in (
            "opportunity_lifecycles",
            "opportunity_candidate_promotion_history",
            "price_intelligence_snapshot_history",
            "verified_economics_snapshots",
        )
    )
    close_sources(sources, candidates, captures, prices, promotions, economics)


def test_restart_reconstruction_and_append_only_economics_facts(tmp_path):
    path = tmp_path / "append-only.db"
    prepared = prepare_persisted_sources(path)
    sources, candidates, captures, prices, promotions = prepared[:5]
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    committed = production_entry(promotions, prices, economics).execute(request())
    close_sources(sources, candidates, captures, prices, promotions, economics)

    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    assert economics.get_receipt(committed.receipt.command_id) == committed.receipt
    assert economics.get_result(committed.receipt).snapshot == committed.snapshot
    for table in (
        "economics_calculation_snapshot_history",
        "economics_calculation_receipts",
    ):
        for statement in (
            f"UPDATE {table} SET rowid=rowid",
            f"DELETE FROM {table}",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                economics._connection.execute(statement)
            economics._connection.rollback()
    economics.close()


def test_malformed_request_is_rejected_without_new_identity_rules():
    values = {
        "command_id": "economics-command-1",
        "opportunity_id": "opportunity-1",
        "price_analysis_command_id": "price-analysis-command-1",
        "calculation_parameters": parameters(),
        "calculation_version": "verified-economics-calculator-v1",
        "requested_at": NOW,
    }
    for changes, error in (
        ({"command_id": ""}, ValueError),
        ({"opportunity_id": ""}, ValueError),
        ({"price_analysis_command_id": ""}, ValueError),
        ({"calculation_parameters": object()}, TypeError),
        ({"calculation_version": ""}, ValueError),
        ({"requested_at": NOW.replace(tzinfo=None)}, ValueError),
    ):
        with pytest.raises(error):
            EconomicsSnapshotProductionRequest(**(values | changes))


def test_production_entry_is_composition_only():
    source = inspect.getsource(EconomicsSnapshotProductionEntry).lower()
    for forbidden in (
        "snapshotchain",
        "decision",
        "dashboard",
        "safety",
        "discoveryruntime",
        "promoteopportunitycandidate",
        "analyzeandpersistpriceintelligence",
        "engine",
        "uuid",
        "hashlib",
    ):
        assert forbidden not in source
