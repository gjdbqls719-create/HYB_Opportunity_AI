from concurrent.futures import ThreadPoolExecutor
import re
from types import SimpleNamespace

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
from app.infrastructure.snapshot_chain_identity import (
    ProductionSnapshotChainBindingIdentityGenerator,
)
from app.infrastructure import snapshot_chain_identity
from test_candidate_issuance_foundation import Counter
from test_snapshot_chain_production_entry import (
    BOUND_AT,
    COMMITTED_AT,
    chain_counts,
    close_prepared,
    prepare_complete_sources,
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


def test_snapshot_chain_binding_generator_is_callable_stateless_and_opaque():
    generator = ProductionSnapshotChainBindingIdentityGenerator()

    binding_id = generator()

    assert callable(generator)
    assert generator.__slots__ == ()
    assert not hasattr(generator, "__dict__")
    assert OPAQUE_ID.fullmatch(binding_id)


def test_snapshot_chain_binding_generator_uses_uuid4_hex_without_transform(
    monkeypatch,
):
    monkeypatch.setattr(
        snapshot_chain_identity,
        "uuid4",
        lambda: SimpleNamespace(hex="authoritative-snapshot-chain-binding-id"),
    )

    assert (
        ProductionSnapshotChainBindingIdentityGenerator()()
        == "authoritative-snapshot-chain-binding-id"
    )


def test_snapshot_chain_binding_generator_is_unique_under_concurrency():
    generator = ProductionSnapshotChainBindingIdentityGenerator()

    with ThreadPoolExecutor(max_workers=16) as pool:
        binding_ids = tuple(pool.map(lambda _: generator(), range(512)))

    assert len(set(binding_ids)) == len(binding_ids)
    assert all(OPAQUE_ID.fullmatch(binding_id) for binding_id in binding_ids)


def test_snapshot_chain_owner_persists_generated_binding_identity_unchanged(
    tmp_path,
):
    path = tmp_path / "snapshot-chain-binding-generator.db"
    prepared, economics, _ = prepare_complete_sources(path)
    captures, prices, promotions = prepared[2], prepared[3], prepared[4]
    chains = SQLiteSnapshotChainBindingRepository(path)
    try:
        result = production_entry(
            promotions,
            captures,
            prices,
            economics,
            chains,
            binding_id_generator=(
                ProductionSnapshotChainBindingIdentityGenerator()
            ),
            bound_clock=Counter(BOUND_AT),
            receipt_clock=Counter(COMMITTED_AT),
        ).execute(request())

        binding_id = result.binding.binding_id
        assert OPAQUE_ID.fullmatch(binding_id)
        assert result.receipt.binding_id == binding_id
        assert chains.get_binding(binding_id) == result.binding
        assert chain_counts(chains) == (1, 2, 1)
    finally:
        close_prepared(prepared, economics, chains)


def test_exact_and_restart_replay_do_not_call_production_generator(
    tmp_path, monkeypatch
):
    path = tmp_path / "snapshot-chain-binding-generator-replay.db"
    prepared, economics, _ = prepare_complete_sources(path)
    captures, prices, promotions = prepared[2], prepared[3], prepared[4]
    chains = SQLiteSnapshotChainBindingRepository(path)
    first = production_entry(
        promotions,
        captures,
        prices,
        economics,
        chains,
        binding_id_generator=ProductionSnapshotChainBindingIdentityGenerator(),
        bound_clock=Counter(BOUND_AT),
        receipt_clock=Counter(COMMITTED_AT),
    ).execute(request())

    uuid_calls = 0

    def fail_uuid4():
        nonlocal uuid_calls
        uuid_calls += 1
        raise AssertionError("Snapshot Chain binding generator must not run")

    monkeypatch.setattr(snapshot_chain_identity, "uuid4", fail_uuid4)
    clocks = (Fail(), Fail())
    replay = production_entry(
        promotions,
        captures,
        prices,
        economics,
        chains,
        binding_id_generator=ProductionSnapshotChainBindingIdentityGenerator(),
        bound_clock=clocks[0],
        receipt_clock=clocks[1],
    ).execute(request())
    close_prepared(prepared, economics, chains)

    promotions = SQLiteCandidatePromotionRepository(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)
    prices = SQLitePriceAnalysisRepository(path)
    economics = SQLiteEconomicsCalculationOwnerRepository(path)
    chains = SQLiteSnapshotChainBindingRepository(path)
    restarted_clocks = (Fail(), Fail())
    try:
        restarted = production_entry(
            promotions,
            captures,
            prices,
            economics,
            chains,
            binding_id_generator=(
                ProductionSnapshotChainBindingIdentityGenerator()
            ),
            bound_clock=restarted_clocks[0],
            receipt_clock=restarted_clocks[1],
        ).execute(request())

        assert replay.replayed is True
        assert restarted.replayed is True
        assert replay.binding == restarted.binding == first.binding
        assert replay.receipt == restarted.receipt == first.receipt
        assert uuid_calls == 0
        assert all(value.calls == 0 for value in clocks)
        assert all(value.calls == 0 for value in restarted_clocks)
        assert chain_counts(chains) == (1, 2, 1)
    finally:
        chains.close()
        economics.close()
        prices.close()
        captures.close()
        promotions.close()
