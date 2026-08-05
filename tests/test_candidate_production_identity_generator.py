from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
import re
from types import SimpleNamespace

from app.infrastructure.discovery import (
    ProductionCandidateIdentityGenerator,
)
from app.infrastructure.discovery import identity_suppliers
from test_candidate_issuance_foundation import Counter, ISSUED_AT, close, issuance_command
from test_candidate_issuance_persistence import counts
from test_candidate_issuance_production_entry import Fail, production_entry


OPAQUE_ID = re.compile(r"^[0-9a-f]{32}$")


def test_candidate_identity_generator_is_callable_stateless_and_opaque():
    generator = ProductionCandidateIdentityGenerator()

    candidate_id = generator()

    assert callable(generator)
    assert generator.__slots__ == ()
    assert not hasattr(generator, "__dict__")
    assert OPAQUE_ID.fullmatch(candidate_id)


def test_candidate_identity_generator_uses_uuid4_hex_without_transform(monkeypatch):
    monkeypatch.setattr(
        identity_suppliers,
        "uuid4",
        lambda: SimpleNamespace(hex="authoritative-opaque-id"),
    )

    assert ProductionCandidateIdentityGenerator()() == "authoritative-opaque-id"


def test_candidate_identity_generator_is_unique_across_concurrent_calls():
    generator = ProductionCandidateIdentityGenerator()

    with ThreadPoolExecutor(max_workers=16) as pool:
        candidate_ids = tuple(pool.map(lambda _: generator(), range(512)))

    assert len(set(candidate_ids)) == len(candidate_ids)
    assert all(OPAQUE_ID.fullmatch(candidate_id) for candidate_id in candidate_ids)


def test_candidate_production_entry_persists_generated_identity_unchanged(tmp_path):
    path = tmp_path / "candidate-generator.db"
    sources, candidates, entry = production_entry(
        path,
        candidate_id_generator=ProductionCandidateIdentityGenerator(),
        issuance_clock=Counter(ISSUED_AT),
        receipt_clock=Counter(ISSUED_AT + timedelta(seconds=1)),
    )
    try:
        response = entry.execute(issuance_command())

        candidate_id = response.issuance.candidate_identity.candidate_id
        assert OPAQUE_ID.fullmatch(candidate_id)
        assert response.receipt.candidate_id == candidate_id
        assert candidates.get_candidate(candidate_id) == response.issuance.candidate_identity
        assert counts(candidates._connection) == (1, 1, 1)
    finally:
        close(sources)
        candidates.close()


def test_candidate_replay_and_alias_do_not_call_production_generator(
    tmp_path, monkeypatch
):
    path = tmp_path / "candidate-generator-replay.db"
    sources, candidates, entry = production_entry(
        path,
        candidate_id_generator=ProductionCandidateIdentityGenerator(),
        issuance_clock=Counter(ISSUED_AT),
        receipt_clock=Counter(ISSUED_AT),
    )
    first = entry.execute(issuance_command())
    close(sources)
    candidates.close()

    uuid_calls = 0

    def fail_uuid4():
        nonlocal uuid_calls
        uuid_calls += 1
        raise AssertionError("Candidate identity generator must not be called")

    monkeypatch.setattr(identity_suppliers, "uuid4", fail_uuid4)

    sources, candidates, replay_entry = production_entry(
        path,
        candidate_id_generator=ProductionCandidateIdentityGenerator(),
        issuance_clock=Fail(),
        receipt_clock=Fail(),
    )
    replay = replay_entry.execute(issuance_command())
    close(sources)
    candidates.close()

    receipt_clock = Counter(ISSUED_AT + timedelta(seconds=1))
    sources, candidates, alias_entry = production_entry(
        path,
        candidate_id_generator=ProductionCandidateIdentityGenerator(),
        issuance_clock=Fail(),
        receipt_clock=receipt_clock,
    )
    try:
        alias = alias_entry.execute(
            replace(issuance_command(), issuance_command_id="issuance-command-2")
        )

        assert replay.replayed is True
        assert alias.replayed is True
        assert replay.issuance == alias.issuance == first.issuance
        assert uuid_calls == 0
        assert receipt_clock.calls == 1
        assert counts(candidates._connection) == (1, 1, 2)
    finally:
        close(sources)
        candidates.close()
