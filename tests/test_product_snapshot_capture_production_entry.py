from dataclasses import replace
from datetime import timedelta
import inspect

import pytest

from app.application.candidate_issuance import CandidateIssuanceProductionEntry
from app.application.product_snapshot_capture import (
    CandidateProductSnapshotCaptureProductionEntry,
    CandidateProductSnapshotCaptureRequest,
    ProductSnapshotSourceConflictError,
    ProductSnapshotSourceObservationNotFoundError,
    SnapshotOwnerCommandConflictError,
)
from app.domain.discovery_identity import DiscoveryGroupMembershipConflictError
from app.domain.market_intelligence import MarketObservationScope
from app.infrastructure.discovery import (
    SQLiteCandidateIssuanceRepository,
    SQLiteDiscoveryCommandRepository,
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
    SQLiteDiscoveryResultRepository,
)
from app.infrastructure.product_observation import (
    SQLiteProductSnapshotCaptureRepository,
)
from test_candidate_issuance_foundation import Counter, ISSUED_AT, issuance_command
from test_discovery_command_sqlite_persistence import receipt
from test_discovery_correlation_contract import (
    NOW,
    command,
    group,
    market_identity,
    observation,
)
from test_discovery_execution_result_sqlite_persistence import result


def prepare(
    path,
    *,
    candidate_market_identity=None,
    observation_market_identity=None,
    second_item_id="item-2",
    second_marketplace="ebay",
):
    commands = SQLiteDiscoveryCommandRepository(path)
    commands.save_command(command(), receipt(command()))
    observations = SQLiteDiscoveryObservationRepository(path)
    first = replace(
        observation(),
        candidate_market_identity=observation_market_identity,
    )
    second_product = replace(
        first.product,
        marketplace=second_marketplace,
        item_id=second_item_id,
        url=f"https://example.com/{second_marketplace}/{second_item_id}",
    )
    second = replace(
        first,
        observation_id="observation-2",
        source_marketplace=second_marketplace,
        source_item_id=second_item_id,
        product=second_product,
        observed_at=NOW + timedelta(seconds=1),
    )
    observations.save_observation(first)
    observations.save_observation(second)
    groups = SQLiteDiscoveryGroupRepository(path)
    groups.save_group(group())
    results = SQLiteDiscoveryResultRepository(path)
    results.save_result(result())
    candidates = SQLiteCandidateIssuanceRepository(path)
    candidate_entry = CandidateIssuanceProductionEntry(
        command_repository=commands,
        result_repository=results,
        group_repository=groups,
        observation_repository=observations,
        candidate_repository=candidates,
        candidate_id_generator=Counter("candidate-1"),
        issuance_clock=Counter(ISSUED_AT),
        receipt_clock=Counter(ISSUED_AT),
    )
    issuance = candidate_entry.execute(
        issuance_command(
            market_observation_identity=(
                candidate_market_identity or market_identity()
            )
        )
    ).issuance
    return (
        (commands, results, groups, observations),
        candidates,
        issuance,
        first,
        second,
    )


def close_all(*repositories):
    for repository in repositories:
        repository.close()


def capture_counts(repository):
    return tuple(
        repository._connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in (
            "product_observation_snapshot_history",
            "product_snapshot_source_binding_history",
            "product_snapshot_capture_receipts",
        )
    )


def capture_request(issuance, **changes):
    values = {
        "command_id": "capture-command-1",
        "candidate_id": issuance.candidate_identity.candidate_id,
        "finalized_group_id": issuance.finalized_group_id,
        "product_snapshot_ids": ("product-snapshot-1", "product-snapshot-2"),
        "requested_at": NOW + timedelta(minutes=3),
    }
    values.update(changes)
    return CandidateProductSnapshotCaptureRequest(**values)


def production_entry(candidates, groups, captures, clock):
    return CandidateProductSnapshotCaptureProductionEntry(
        candidate_repository=candidates,
        group_repository=groups,
        capture_repository=captures,
        receipt_clock=clock,
    )


def test_listing_candidate_captures_full_ordered_production_cohort(tmp_path):
    path = tmp_path / "listing.db"
    sources, candidates, issuance, first, second = prepare(
        path,
        second_marketplace="amazon",
    )
    assert first.candidate_market_identity is None
    assert second.candidate_market_identity is None
    captures = SQLiteProductSnapshotCaptureRepository(path)
    committed_at = ISSUED_AT + timedelta(minutes=1)
    clock = Counter(committed_at)

    captured = production_entry(
        candidates,
        sources[2],
        captures,
        clock,
    ).execute(capture_request(issuance))

    assert captured.replayed is False
    assert tuple(value.product for value in captured.snapshots) == (
        first.product,
        second.product,
    )
    assert tuple(value.product.item_id for value in captured.snapshots) == (
        "item-1",
        "item-2",
    )
    assert tuple(value.product.marketplace for value in captured.snapshots) == (
        "ebay",
        "amazon",
    )
    assert all(
        value.market_observation_identity
        == issuance.discovery_context.market_observation_identity
        for value in captured.snapshots
    )
    assert tuple(value.collected_observation_id for value in captured.bindings) == (
        "observation-1",
        "observation-2",
    )
    assert tuple(value.product_snapshot_id for value in captured.bindings) == (
        "product-snapshot-1",
        "product-snapshot-2",
    )
    assert all(value.bound_at == committed_at for value in captured.bindings)
    assert captured.receipt.committed_at == committed_at
    assert clock.calls == 1
    assert capture_counts(captures) == (2, 2, 1)
    captures.close()
    candidates.close()
    close_all(*sources)


def test_canonical_candidate_uses_persisted_context_without_inference(tmp_path):
    path = tmp_path / "canonical.db"
    identity = market_identity(MarketObservationScope.CANONICAL_PRODUCT)
    sources, candidates, issuance, first, second = prepare(
        path,
        candidate_market_identity=identity,
    )
    captures = SQLiteProductSnapshotCaptureRepository(path)

    captured = production_entry(
        candidates,
        sources[2],
        captures,
        Counter(ISSUED_AT),
    ).execute(capture_request(issuance))

    assert tuple(value.market_observation_identity for value in captured.snapshots) == (
        identity,
        identity,
    )
    assert tuple(value.product for value in captured.snapshots) == (
        first.product,
        second.product,
    )
    assert tuple(value.collected_observation_id for value in captured.bindings) == (
        "observation-1",
        "observation-2",
    )
    captures.close()
    candidates.close()
    close_all(*sources)


def test_explicit_observation_identity_match_and_conflict(tmp_path):
    identity = market_identity()
    path = tmp_path / "matching.db"
    sources, candidates, issuance, _, _ = prepare(
        path,
        candidate_market_identity=identity,
        observation_market_identity=identity,
        second_item_id="item-1",
    )
    captures = SQLiteProductSnapshotCaptureRepository(path)
    captured = production_entry(
        candidates, sources[2], captures, Counter(ISSUED_AT)
    ).execute(capture_request(issuance))
    assert len(captured.snapshots) == 2
    captures.close()
    candidates.close()
    close_all(*sources)

    path = tmp_path / "conflicting.db"
    sources, candidates, issuance, _, _ = prepare(
        path,
        candidate_market_identity=identity,
        observation_market_identity=replace(identity, condition="used"),
        second_item_id="item-1",
    )
    captures = SQLiteProductSnapshotCaptureRepository(path)
    with pytest.raises(ProductSnapshotSourceConflictError):
        production_entry(
            candidates, sources[2], captures, Counter(ISSUED_AT)
        ).execute(capture_request(issuance))
    assert capture_counts(captures) == (0, 0, 0)
    captures.close()
    candidates.close()
    close_all(*sources)


def test_exact_replay_after_restart_uses_no_clock_or_duplicate_rows(tmp_path):
    path = tmp_path / "replay.db"
    sources, candidates, issuance, _, _ = prepare(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)
    clock = Counter(ISSUED_AT)
    first = production_entry(
        candidates, sources[2], captures, clock
    ).execute(capture_request(issuance))
    captures.close()
    candidates.close()
    close_all(*sources)

    class FailClock:
        def __init__(self):
            self.calls = 0

        def __call__(self):
            self.calls += 1
            raise AssertionError("replay clock must not run")

    fail_clock = FailClock()
    candidates = SQLiteCandidateIssuanceRepository(path)
    groups = SQLiteDiscoveryGroupRepository(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)
    replay = production_entry(
        candidates, groups, captures, fail_clock
    ).execute(capture_request(issuance))
    assert replay.replayed is True
    assert replay.snapshots == first.snapshots
    assert replay.bindings == first.bindings
    assert replay.receipt == first.receipt
    assert fail_clock.calls == 0
    assert capture_counts(captures) == (2, 2, 1)
    with pytest.raises(SnapshotOwnerCommandConflictError):
        production_entry(
            candidates, groups, captures, fail_clock
        ).execute(
            capture_request(
                issuance,
                requested_at=NOW + timedelta(days=1),
            )
        )
    captures.close()
    groups.close()
    candidates.close()


@pytest.mark.parametrize("missing", ("candidate", "context"))
def test_missing_candidate_or_context_stops_before_group_and_capture(missing):
    candidate = issuance_command_identity()

    class Candidates:
        def get_candidate(self, value):
            return None if missing == "candidate" else candidate

        def get_context(self, value):
            return None

    class NeverCalled:
        def __getattr__(self, name):
            raise AssertionError(f"{name} must not be called")

    request = CandidateProductSnapshotCaptureRequest(
        "capture-command-1",
        "candidate-1",
        "group-opaque-1",
        ("product-snapshot-1", "product-snapshot-2"),
        NOW,
    )
    with pytest.raises(ProductSnapshotSourceConflictError):
        production_entry(
            Candidates(), NeverCalled(), NeverCalled(), Counter(ISSUED_AT)
        ).execute(request)


def issuance_command_identity():
    from app.domain.discovery_identity import OpportunityCandidateIdentity

    return OpportunityCandidateIdentity("candidate-1", "collector:ebay:item-1")


def test_wrong_group_order_missing_observation_and_execution_are_rejected(tmp_path):
    path = tmp_path / "lineage.db"
    sources, candidates, issuance, _, _ = prepare(path)
    groups = sources[2]
    groups.save_group(replace(group(), finalized_group_id="group-opaque-2"))
    captures = SQLiteProductSnapshotCaptureRepository(path)
    entry = production_entry(candidates, groups, captures, Counter(ISSUED_AT))
    with pytest.raises(ProductSnapshotSourceConflictError):
        entry.execute(
            capture_request(issuance, finalized_group_id="group-opaque-2")
        )

    class ReversedGroups:
        def get_group(self, value):
            persisted = groups.get_group(value)
            return replace(
                persisted,
                observation_ids=tuple(reversed(persisted.observation_ids)),
            )

    with pytest.raises(ProductSnapshotSourceConflictError):
        production_entry(
            candidates, ReversedGroups(), captures, Counter(ISSUED_AT)
        ).execute(capture_request(issuance))

    class ObservationFailure:
        def __init__(self, failure):
            self.failure = failure

        def __getattr__(self, name):
            return getattr(captures, name)

        def get_observation(self, observation_id):
            if self.failure == "missing":
                return None
            return replace(
                captures.get_observation(observation_id),
                discovery_execution_id="other-execution",
            )

    with pytest.raises(ProductSnapshotSourceObservationNotFoundError):
        production_entry(
            candidates,
            groups,
            ObservationFailure("missing"),
            Counter(ISSUED_AT),
        ).execute(capture_request(issuance))
    with pytest.raises(ProductSnapshotSourceConflictError):
        production_entry(
            candidates,
            groups,
            ObservationFailure("execution"),
            Counter(ISSUED_AT),
        ).execute(capture_request(issuance))
    assert capture_counts(captures) == (0, 0, 0)
    captures.close()
    candidates.close()
    close_all(*sources)


def test_snapshot_count_duplicates_and_malformed_request_are_rejected(tmp_path):
    with pytest.raises(ValueError):
        CandidateProductSnapshotCaptureRequest(
            "capture-command-1",
            "candidate-1",
            "group-opaque-1",
            ("same", "same"),
            NOW,
        )
    with pytest.raises(ValueError):
        CandidateProductSnapshotCaptureRequest(
            "",
            "candidate-1",
            "group-opaque-1",
            ("product-snapshot-1",),
            NOW,
        )
    with pytest.raises(ValueError):
        CandidateProductSnapshotCaptureRequest(
            "capture-command-1",
            "candidate-1",
            "group-opaque-1",
            ("product-snapshot-1",),
            NOW.replace(tzinfo=None),
        )
    with pytest.raises(DiscoveryGroupMembershipConflictError):
        group(observation_ids=("observation-1", "observation-1"))

    path = tmp_path / "count.db"
    sources, candidates, issuance, _, _ = prepare(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)
    with pytest.raises(ProductSnapshotSourceConflictError):
        production_entry(
            candidates, sources[2], captures, Counter(ISSUED_AT)
        ).execute(
            capture_request(
                issuance,
                product_snapshot_ids=("product-snapshot-1",),
            )
        )
    assert capture_counts(captures) == (0, 0, 0)
    captures.close()
    candidates.close()
    close_all(*sources)


def test_clock_and_repository_failures_do_not_change_source_facts(tmp_path):
    path = tmp_path / "failure.db"
    sources, candidates, issuance, _, _ = prepare(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)
    before = tuple(
        tuple(row)
        for row in captures._connection.execute(
            "SELECT * FROM opportunity_candidate_history"
        )
    ), tuple(
        tuple(row)
        for row in captures._connection.execute(
            "SELECT * FROM discovery_finalized_group_history"
        )
    )

    def fail_clock():
        raise RuntimeError("capture clock failed")

    with pytest.raises(RuntimeError, match="capture clock failed"):
        production_entry(candidates, sources[2], captures, fail_clock).execute(
            capture_request(issuance)
        )
    assert capture_counts(captures) == (0, 0, 0)

    class FailingPersistence:
        def __getattr__(self, name):
            return getattr(captures, name)

        def persist_capture(self, *args):
            raise RuntimeError("capture persistence failed")

    with pytest.raises(RuntimeError, match="capture persistence failed"):
        production_entry(
            candidates,
            sources[2],
            FailingPersistence(),
            Counter(ISSUED_AT),
        ).execute(capture_request(issuance))
    after = tuple(
        tuple(row)
        for row in captures._connection.execute(
            "SELECT * FROM opportunity_candidate_history"
        )
    ), tuple(
        tuple(row)
        for row in captures._connection.execute(
            "SELECT * FROM discovery_finalized_group_history"
        )
    )
    assert after == before
    assert capture_counts(captures) == (0, 0, 0)
    captures.close()
    candidates.close()
    close_all(*sources)


@pytest.mark.parametrize("source", ("candidate", "group", "observation"))
def test_source_read_failure_stops_before_persistence(tmp_path, source):
    path = tmp_path / f"read-{source}.db"
    sources, candidates, issuance, _, _ = prepare(path)
    captures = SQLiteProductSnapshotCaptureRepository(path)

    class CandidateReads:
        def __getattr__(self, name):
            if source == "candidate" and name == "get_candidate":
                raise RuntimeError("candidate read failed")
            return getattr(candidates, name)

    class GroupReads:
        def get_group(self, value):
            if source == "group":
                raise RuntimeError("group read failed")
            return sources[2].get_group(value)

    class CaptureReads:
        def __getattr__(self, name):
            return getattr(captures, name)

        def get_observation(self, value):
            if source == "observation":
                raise RuntimeError("observation read failed")
            return captures.get_observation(value)

    clock = Counter(ISSUED_AT)
    with pytest.raises(RuntimeError, match=f"{source} read failed"):
        production_entry(
            CandidateReads(),
            GroupReads(),
            CaptureReads(),
            clock,
        ).execute(capture_request(issuance))
    assert clock.calls == 0
    assert capture_counts(captures) == (0, 0, 0)
    captures.close()
    candidates.close()
    close_all(*sources)


def test_production_entry_is_composition_only():
    source = inspect.getsource(
        CandidateProductSnapshotCaptureProductionEntry
    ).lower()
    for forbidden in (
        "analyzeandpersistpriceintelligence",
        "promoteopportunitycandidate",
        "addtovalidationqueuecommand",
        "opportunitylifecycle",
        "economicscalculationsnapshot",
        "snapshotchain",
        "engine",
        "marketplace",
        "uuid",
        "hashlib",
        "update",
    ):
        assert forbidden not in source
