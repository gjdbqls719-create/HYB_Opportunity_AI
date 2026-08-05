from concurrent.futures import ThreadPoolExecutor
import re
from types import SimpleNamespace

from app.infrastructure.economics_calculation import (
    ProductionEconomicsSnapshotIdentityGenerator,
    SQLiteEconomicsCalculationOwnerRepository,
)
from app.infrastructure.economics_calculation import identity_suppliers
from app.infrastructure.opportunity_validation import (
    SQLiteCandidatePromotionRepository,
)
from app.infrastructure.price_intelligence import SQLitePriceAnalysisRepository
from test_candidate_issuance_foundation import Counter
from test_economics_snapshot_production_entry import (
    ECONOMICS_COMMITTED_AT,
    ECONOMICS_GENERATED_AT,
    close_sources,
    economics_counts,
    prepare_persisted_sources,
    production_entry,
    request,
)


OPAQUE_ID = re.compile(r"^[0-9a-f]{32}$")


class Fail:
    def __init__(self):
        self.calls = 0

    def __call__(self, *args, **kwargs):
        self.calls += 1
        raise AssertionError("replay owner dependency must not run")


def test_economics_snapshot_identity_generator_is_callable_stateless_and_opaque():
    generator = ProductionEconomicsSnapshotIdentityGenerator()

    snapshot_id = generator()

    assert callable(generator)
    assert generator.__slots__ == ()
    assert not hasattr(generator, "__dict__")
    assert OPAQUE_ID.fullmatch(snapshot_id)


def test_economics_snapshot_identity_generator_uses_uuid4_hex_without_transform(
    monkeypatch,
):
    monkeypatch.setattr(
        identity_suppliers,
        "uuid4",
        lambda: SimpleNamespace(hex="authoritative-economics-snapshot-id"),
    )

    assert (
        ProductionEconomicsSnapshotIdentityGenerator()()
        == "authoritative-economics-snapshot-id"
    )


def test_economics_snapshot_identity_generator_is_unique_under_concurrency():
    generator = ProductionEconomicsSnapshotIdentityGenerator()

    with ThreadPoolExecutor(max_workers=16) as pool:
        snapshot_ids = tuple(pool.map(lambda _: generator(), range(512)))

    assert len(set(snapshot_ids)) == len(snapshot_ids)
    assert all(OPAQUE_ID.fullmatch(snapshot_id) for snapshot_id in snapshot_ids)


def test_economics_owner_persists_generated_snapshot_identity_unchanged(tmp_path):
    path = tmp_path / "economics-snapshot-generator.db"
    prepared = prepare_persisted_sources(path)
    sources, candidates, captures, prices, promotions = prepared[:5]
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    try:
        result = production_entry(
            promotions,
            prices,
            economics,
            snapshot_id_generator=ProductionEconomicsSnapshotIdentityGenerator(),
            generated_clock=Counter(ECONOMICS_GENERATED_AT),
            receipt_clock=Counter(ECONOMICS_COMMITTED_AT),
        ).execute(request())

        snapshot_id = result.snapshot.snapshot_id
        assert OPAQUE_ID.fullmatch(snapshot_id)
        assert result.receipt.economics_snapshot_id == snapshot_id
        assert economics.get_result(result.receipt) == result
        assert economics_counts(economics) == (1, 1)
    finally:
        close_sources(
            sources, candidates, captures, prices, promotions, economics
        )


def test_exact_and_restart_replay_do_not_call_production_generator(
    tmp_path, monkeypatch
):
    path = tmp_path / "economics-snapshot-generator-replay.db"
    prepared = prepare_persisted_sources(path)
    sources, candidates, captures, prices, promotions = prepared[:5]
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    first = production_entry(
        promotions,
        prices,
        economics,
        snapshot_id_generator=ProductionEconomicsSnapshotIdentityGenerator(),
        generated_clock=Counter(ECONOMICS_GENERATED_AT),
        receipt_clock=Counter(ECONOMICS_COMMITTED_AT),
    ).execute(request())

    uuid_calls = 0

    def fail_uuid4():
        nonlocal uuid_calls
        uuid_calls += 1
        raise AssertionError("Economics Snapshot identity generator must not run")

    monkeypatch.setattr(identity_suppliers, "uuid4", fail_uuid4)
    dependencies = tuple(Fail() for _ in range(3))
    replay = production_entry(
        promotions,
        prices,
        economics,
        snapshot_id_generator=ProductionEconomicsSnapshotIdentityGenerator(),
        generated_clock=dependencies[0],
        receipt_clock=dependencies[1],
        calculator=dependencies[2],
    ).execute(request())
    close_sources(sources, candidates, captures, prices, promotions, economics)

    promotions = SQLiteCandidatePromotionRepository(path)
    prices = SQLitePriceAnalysisRepository(path)
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    restarted_dependencies = tuple(Fail() for _ in range(3))
    try:
        restarted = production_entry(
            promotions,
            prices,
            economics,
            snapshot_id_generator=ProductionEconomicsSnapshotIdentityGenerator(),
            generated_clock=restarted_dependencies[0],
            receipt_clock=restarted_dependencies[1],
            calculator=restarted_dependencies[2],
        ).execute(request())

        assert replay.replayed is True
        assert restarted.replayed is True
        assert replay.snapshot == restarted.snapshot == first.snapshot
        assert replay.receipt == restarted.receipt == first.receipt
        assert uuid_calls == 0
        assert all(value.calls == 0 for value in dependencies)
        assert all(value.calls == 0 for value in restarted_dependencies)
        assert economics_counts(economics) == (1, 1)
    finally:
        economics.close()
        prices.close()
        promotions.close()
