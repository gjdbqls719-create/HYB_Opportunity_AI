from concurrent.futures import ThreadPoolExecutor
import re
from types import SimpleNamespace

from app.infrastructure.discovery import SQLiteCandidateIssuanceRepository
from app.infrastructure.price_intelligence import (
    ProductionPriceSnapshotIdentityGenerator,
    SQLitePriceAnalysisRepository,
)
from app.infrastructure.price_intelligence import identity_suppliers
from app.infrastructure.product_observation import (
    SQLiteProductSnapshotCaptureRepository,
)
from test_candidate_issuance_foundation import Counter
from test_candidate_price_analysis_production_entry import (
    COMMITTED_AT,
    GENERATED_AT,
    analysis_counts,
    analysis_entry,
    prepare_captured_cohort,
    request,
)
from test_product_snapshot_capture_production_entry import close_all


OPAQUE_ID = re.compile(r"^[0-9a-f]{32}$")


class Fail:
    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("replay owner dependency must not run")


def test_price_snapshot_identity_generator_is_callable_stateless_and_opaque():
    generator = ProductionPriceSnapshotIdentityGenerator()

    snapshot_id = generator()

    assert callable(generator)
    assert generator.__slots__ == ()
    assert not hasattr(generator, "__dict__")
    assert OPAQUE_ID.fullmatch(snapshot_id)


def test_price_snapshot_identity_generator_uses_uuid4_hex_without_transform(
    monkeypatch,
):
    monkeypatch.setattr(
        identity_suppliers,
        "uuid4",
        lambda: SimpleNamespace(hex="authoritative-price-snapshot-id"),
    )

    assert (
        ProductionPriceSnapshotIdentityGenerator()()
        == "authoritative-price-snapshot-id"
    )


def test_price_snapshot_identity_generator_is_unique_across_concurrent_calls():
    generator = ProductionPriceSnapshotIdentityGenerator()

    with ThreadPoolExecutor(max_workers=16) as pool:
        snapshot_ids = tuple(pool.map(lambda _: generator(), range(512)))

    assert len(set(snapshot_ids)) == len(snapshot_ids)
    assert all(OPAQUE_ID.fullmatch(snapshot_id) for snapshot_id in snapshot_ids)


def test_price_analysis_persists_generated_snapshot_identity_unchanged(tmp_path):
    path = tmp_path / "price-snapshot-generator.db"
    sources, candidates, captures, issuance, _, _, _ = prepare_captured_cohort(path)
    analyses = SQLitePriceAnalysisRepository(path)
    try:
        analyzed = analysis_entry(
            candidates,
            captures,
            analyses,
            snapshot_id_generator=ProductionPriceSnapshotIdentityGenerator(),
            generated_clock=Counter(GENERATED_AT),
            receipt_clock=Counter(COMMITTED_AT),
        ).execute(request(issuance))

        snapshot_id = analyzed.snapshot.snapshot_id
        assert OPAQUE_ID.fullmatch(snapshot_id)
        assert analyzed.receipt.price_snapshot_id == snapshot_id
        assert analyses.get_result(analyzed.receipt) == analyzed
        assert analysis_counts(analyses) == (1, 1)
    finally:
        analyses.close()
        captures.close()
        candidates.close()
        close_all(*sources)


def test_exact_and_restart_replay_do_not_call_production_generator(
    tmp_path, monkeypatch
):
    path = tmp_path / "price-snapshot-generator-replay.db"
    sources, candidates, captures, issuance, _, _, _ = prepare_captured_cohort(path)
    analyses = SQLitePriceAnalysisRepository(path)
    first = analysis_entry(
        candidates,
        captures,
        analyses,
        snapshot_id_generator=ProductionPriceSnapshotIdentityGenerator(),
        generated_clock=Counter(GENERATED_AT),
        receipt_clock=Counter(COMMITTED_AT),
    ).execute(request(issuance))

    uuid_calls = 0

    def fail_uuid4():
        nonlocal uuid_calls
        uuid_calls += 1
        raise AssertionError("Price Snapshot identity generator must not run")

    monkeypatch.setattr(identity_suppliers, "uuid4", fail_uuid4)
    dependencies = tuple(Fail() for _ in range(3))
    replay = analysis_entry(
        candidates,
        captures,
        analyses,
        snapshot_id_generator=ProductionPriceSnapshotIdentityGenerator(),
        generated_clock=dependencies[0],
        receipt_clock=dependencies[1],
        analyzer=dependencies[2],
    ).execute(request(issuance))
    analyses.close()
    captures.close()
    candidates.close()
    close_all(*sources)

    candidates = SQLiteCandidateIssuanceRepository(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)
    analyses = SQLitePriceAnalysisRepository(path)
    restarted_dependencies = tuple(Fail() for _ in range(3))
    try:
        restarted = analysis_entry(
            candidates,
            captures,
            analyses,
            snapshot_id_generator=ProductionPriceSnapshotIdentityGenerator(),
            generated_clock=restarted_dependencies[0],
            receipt_clock=restarted_dependencies[1],
            analyzer=restarted_dependencies[2],
        ).execute(request(issuance))

        assert replay.replayed is True
        assert restarted.replayed is True
        assert replay.snapshot == restarted.snapshot == first.snapshot
        assert replay.receipt == restarted.receipt == first.receipt
        assert uuid_calls == 0
        assert all(value.calls == 0 for value in dependencies)
        assert all(value.calls == 0 for value in restarted_dependencies)
        assert analysis_counts(analyses) == (1, 1)
    finally:
        analyses.close()
        captures.close()
        candidates.close()
