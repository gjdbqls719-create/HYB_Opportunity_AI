from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import inspect
import sqlite3

import pytest

from app.application.price_analysis import (
    CandidatePriceAnalysisProductionEntry,
    CandidatePriceAnalysisRequest,
    PriceAnalysisCandidateMismatchError,
    PriceAnalysisCommandConflictError,
    PriceAnalysisExecutionError,
    PriceAnalysisProductOrderConflictError,
    PriceAnalysisSourceNotFoundError,
)
from app.domain.discovery_identity import DiscoveryOpportunityContext
from app.infrastructure.discovery import SQLiteCandidateIssuanceRepository
from app.infrastructure.price_intelligence import SQLitePriceAnalysisRepository
from app.infrastructure.product_observation import (
    SQLiteProductSnapshotCaptureRepository,
)
from engine.price_intelligence import analyze_product_prices
from test_candidate_issuance_foundation import Counter, ISSUED_AT
from test_discovery_correlation_contract import NOW, market_identity
from test_product_snapshot_capture_production_entry import (
    capture_request,
    close_all,
    prepare,
    production_entry as capture_entry,
)


GENERATED_AT = ISSUED_AT + timedelta(minutes=10)
COMMITTED_AT = GENERATED_AT + timedelta(seconds=1)


def prepare_captured_cohort(path):
    sources, candidates, issuance, first, second = prepare(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)
    captured = capture_entry(
        candidates,
        sources[2],
        captures,
        Counter(ISSUED_AT),
    ).execute(capture_request(issuance))
    return sources, candidates, captures, issuance, captured, first, second


def request(issuance, **changes):
    values = {
        "command_id": "price-analysis-command-1",
        "candidate_id": issuance.candidate_identity.candidate_id,
        "finalized_group_id": issuance.finalized_group_id,
        "product_snapshot_capture_command_id": "capture-command-1",
        "fallback_multiplier": Decimal("1.50"),
        "analyzer_version": "price-analyzer-v1",
        "requested_at": NOW + timedelta(minutes=5),
    }
    values.update(changes)
    return CandidatePriceAnalysisRequest(**values)


def analysis_entry(
    candidates,
    captures,
    analyses,
    *,
    snapshot_id_generator=None,
    generated_clock=None,
    receipt_clock=None,
    analyzer=analyze_product_prices,
):
    return CandidatePriceAnalysisProductionEntry(
        candidate_repository=candidates,
        capture_repository=captures,
        analysis_repository=analyses,
        snapshot_id_generator=snapshot_id_generator or Counter("price-snapshot-1"),
        generated_clock=generated_clock or Counter(GENERATED_AT),
        receipt_clock=receipt_clock or Counter(COMMITTED_AT),
        analyzer=analyzer,
    )


def analysis_counts(repository):
    return tuple(
        repository._connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in (
            "price_intelligence_snapshot_history",
            "price_intelligence_analysis_receipts",
        )
    )


def test_persisted_capture_receipt_supplies_exact_ordered_analysis_cohort(tmp_path):
    path = tmp_path / "production.db"
    sources, candidates, captures, issuance, captured, first, second = (
        prepare_captured_cohort(path)
    )
    analyses = SQLitePriceAnalysisRepository(path)
    seen = []

    def analyzer(products, *, fallback_multiplier):
        seen.append((tuple(products), fallback_multiplier))
        return analyze_product_prices(
            products,
            fallback_multiplier=fallback_multiplier,
        )

    result = analysis_entry(
        candidates,
        captures,
        analyses,
        analyzer=analyzer,
    ).execute(request(issuance))

    assert len(seen) == 1
    assert seen[0][1] == Decimal("1.50")
    for runtime_product, snapshot in zip(
        seen[0][0], captured.snapshots, strict=True
    ):
        assert all(
            getattr(runtime_product, name) == getattr(snapshot.product, name)
            for name in snapshot.product.__dataclass_fields__
        )
    assert result.replayed is False
    assert result.snapshot.snapshot_id == "price-snapshot-1"
    assert result.snapshot.candidate_identity == issuance.candidate_identity
    assert (
        result.snapshot.market_observation_identity
        == issuance.discovery_context.market_observation_identity
    )
    assert result.snapshot.product_observation_snapshot_ids == (
        "product-snapshot-1",
        "product-snapshot-2",
    )
    assert tuple(value.product for value in captured.snapshots) == (
        first.product,
        second.product,
    )
    assert tuple(value.collected_observation_id for value in captured.bindings) == (
        "observation-1",
        "observation-2",
    )
    assert result.receipt.product_snapshot_ids == captured.receipt.product_snapshot_ids
    assert result.receipt.generated_at == GENERATED_AT
    assert result.receipt.committed_at == COMMITTED_AT
    assert analysis_counts(analyses) == (1, 1)
    analyses.close()
    captures.close()
    candidates.close()
    close_all(*sources)


def test_exact_replay_after_restart_skips_owner_dependencies(tmp_path):
    path = tmp_path / "replay.db"
    sources, candidates, captures, issuance, _, _, _ = prepare_captured_cohort(path)
    analyses = SQLitePriceAnalysisRepository(path)
    first = analysis_entry(candidates, captures, analyses).execute(request(issuance))
    analyses.close()
    captures.close()
    candidates.close()
    close_all(*sources)

    class Fail:
        def __init__(self):
            self.calls = 0

        def __call__(self, *args, **kwargs):
            self.calls += 1
            raise AssertionError("replay owner dependency must not run")

    snapshot_id_generator = Fail()
    generated_clock = Fail()
    receipt_clock = Fail()
    analyzer = Fail()
    candidates = SQLiteCandidateIssuanceRepository(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)
    analyses = SQLitePriceAnalysisRepository(path)
    replay = analysis_entry(
        candidates,
        captures,
        analyses,
        snapshot_id_generator=snapshot_id_generator,
        generated_clock=generated_clock,
        receipt_clock=receipt_clock,
        analyzer=analyzer,
    ).execute(request(issuance))

    assert replay.replayed is True
    assert replay.snapshot == first.snapshot
    assert replay.receipt == first.receipt
    assert tuple(
        value.calls
        for value in (
            snapshot_id_generator,
            generated_clock,
            receipt_clock,
            analyzer,
        )
    ) == (0, 0, 0, 0)
    assert analysis_counts(analyses) == (1, 1)
    with pytest.raises(PriceAnalysisCommandConflictError):
        analysis_entry(candidates, captures, analyses).execute(
            request(
                issuance,
                fallback_multiplier=Decimal("1.75"),
            )
        )
    analyses.close()
    captures.close()
    candidates.close()


@pytest.mark.parametrize("missing", ("candidate", "context", "capture"))
def test_missing_persisted_source_stops_before_analysis(missing):
    class Candidates:
        def get_candidate(self, candidate_id):
            if missing == "candidate":
                return None
            return candidate_identity()

        def get_context(self, candidate_id):
            if missing == "context":
                return None
            if missing == "capture":
                return DiscoveryOpportunityContext(
                    candidate_identity(),
                    market_identity(),
                    "execution-1",
                    "command-1",
                    NOW,
                )
            raise AssertionError("Context must not be read after missing Candidate")

    class Captures:
        def get_receipt(self, command_id):
            assert missing == "capture"
            return None

    class NeverCalled:
        def __getattr__(self, name):
            raise AssertionError(f"{name} must not be called")

    entry = analysis_entry(
        Candidates(),
        Captures() if missing == "capture" else NeverCalled(),
        NeverCalled(),
    )
    with pytest.raises(PriceAnalysisSourceNotFoundError):
        entry.execute(
            CandidatePriceAnalysisRequest(
                "analysis-command-1",
                "candidate-1",
                "group-opaque-1",
                "capture-command-1",
                Decimal("1.50"),
                "price-analyzer-v1",
                NOW,
            )
        )


def candidate_identity():
    from app.domain.discovery_identity import OpportunityCandidateIdentity

    return OpportunityCandidateIdentity("candidate-1", "collector:ebay:item-1")


def test_wrong_capture_candidate_and_changed_source_order_are_rejected(tmp_path):
    path = tmp_path / "lineage.db"
    sources, candidates, captures, issuance, captured, _, _ = prepare_captured_cohort(
        path
    )
    analyses = SQLitePriceAnalysisRepository(path)

    class WrongCandidateCapture:
        def get_receipt(self, command_id):
            return replace(captured.receipt, candidate_id="other-candidate")

    with pytest.raises(PriceAnalysisCandidateMismatchError):
        analysis_entry(
            candidates,
            WrongCandidateCapture(),
            analyses,
        ).execute(request(issuance))

    class ReversedCapture:
        def get_receipt(self, command_id):
            return replace(
                captured.receipt,
                product_snapshot_ids=tuple(
                    reversed(captured.receipt.product_snapshot_ids)
                ),
            )

    with pytest.raises(PriceAnalysisProductOrderConflictError):
        analysis_entry(candidates, ReversedCapture(), analyses).execute(
            request(issuance, command_id="analysis-command-2")
        )
    assert analysis_counts(analyses) == (0, 0)
    analyses.close()
    captures.close()
    candidates.close()
    close_all(*sources)


def test_malformed_request_is_rejected_without_new_identity_rules():
    values = {
        "command_id": "analysis-command-1",
        "candidate_id": "candidate-1",
        "finalized_group_id": "group-opaque-1",
        "product_snapshot_capture_command_id": "capture-command-1",
        "fallback_multiplier": Decimal("1.50"),
        "analyzer_version": "price-analyzer-v1",
        "requested_at": NOW,
    }
    for changes, error in (
        ({"command_id": ""}, ValueError),
        ({"product_snapshot_capture_command_id": ""}, ValueError),
        ({"fallback_multiplier": 1.5}, TypeError),
        ({"fallback_multiplier": Decimal("NaN")}, ValueError),
        ({"analyzer_version": ""}, ValueError),
        ({"requested_at": NOW.replace(tzinfo=None)}, ValueError),
    ):
        with pytest.raises(error):
            CandidatePriceAnalysisRequest(**(values | changes))


def test_analyzer_and_repository_failures_preserve_candidate_and_capture(tmp_path):
    path = tmp_path / "failure.db"
    sources, candidates, captures, issuance, captured, _, _ = prepare_captured_cohort(
        path
    )
    analyses = SQLitePriceAnalysisRepository(path)
    before_capture = tuple(captures._connection.iterdump())

    def fail_analyzer(*args, **kwargs):
        raise RuntimeError("analysis failed")

    with pytest.raises(PriceAnalysisExecutionError):
        analysis_entry(
            candidates,
            captures,
            analyses,
            analyzer=fail_analyzer,
        ).execute(request(issuance))
    assert analysis_counts(analyses) == (0, 0)

    class FailingPersistence:
        def __getattr__(self, name):
            return getattr(analyses, name)

        def save_analysis_result(self, *args):
            raise RuntimeError("analysis persistence failed")

    with pytest.raises(RuntimeError, match="analysis persistence failed"):
        analysis_entry(
            candidates,
            captures,
            FailingPersistence(),
        ).execute(request(issuance))
    assert tuple(captures._connection.iterdump()) == before_capture
    assert captures.get_result(captured.receipt) == captured
    assert analysis_counts(analyses) == (0, 0)
    analyses.close()
    captures.close()
    candidates.close()
    close_all(*sources)


def test_append_only_price_facts_survive_restart(tmp_path):
    path = tmp_path / "append-only.db"
    sources, candidates, captures, issuance, _, _, _ = prepare_captured_cohort(path)
    analyses = SQLitePriceAnalysisRepository(path)
    committed = analysis_entry(candidates, captures, analyses).execute(request(issuance))
    analyses.close()
    captures.close()
    candidates.close()
    close_all(*sources)

    analyses = SQLitePriceAnalysisRepository(path)
    assert analyses.get_receipt(committed.receipt.command_id) == committed.receipt
    assert analyses.get_result(committed.receipt).snapshot == committed.snapshot
    for table in (
        "price_intelligence_snapshot_history",
        "price_intelligence_analysis_receipts",
    ):
        for statement in (
            f"UPDATE {table} SET rowid=rowid",
            f"DELETE FROM {table}",
        ):
            with pytest.raises(sqlite3.IntegrityError, match="append-only"):
                analyses._connection.execute(statement)
            analyses._connection.rollback()
    analyses.close()


def test_production_entry_is_composition_only():
    source = inspect.getsource(CandidatePriceAnalysisProductionEntry).lower()
    for forbidden in (
        "promoteopportunitycandidate",
        "opportunitylifecycle",
        "economics",
        "snapshotchain",
        "decision",
        "dashboard",
        "discoveryruntime",
        "uuid",
        "hashlib",
        "update",
    ):
        assert forbidden not in source
