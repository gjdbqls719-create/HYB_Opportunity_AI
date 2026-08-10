from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
import inspect

import pytest

from app.application.candidate_issuance import (
    CANDIDATE_ISSUANCE_COMMAND_SCHEMA_VERSION,
    CandidateDiscoveryCommandNotFoundError,
    CandidateDiscoveryReferenceConflictError,
    CandidateDiscoveryResultNotFoundError,
    CandidateExecutionMismatchError,
    CandidateFinalizedGroupNotFoundError,
    CandidateGroupNotInResultError,
    CandidateIdentityGenerationError,
    CandidateIssuanceResult,
    CandidateMarketIdentityConflictError,
    IssueOpportunityCandidate,
    IssueOpportunityCandidateCommand,
    MalformedCandidateIssuanceCommandError,
    UnsupportedCandidateIssuanceCommandVersionError,
)
from app.domain.discovery_identity import OpportunityCandidateIdentity
from app.domain.market_intelligence import MarketObservationScope
from app.infrastructure.discovery import (
    SQLiteDiscoveryCommandRepository,
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
    SQLiteDiscoveryResultRepository,
)
from test_discovery_correlation_contract import NOW, group, market_identity
from test_discovery_execution_result_sqlite_persistence import prepare_group, result
from test_discovery_observation_group_sqlite_persistence import prepare, save_members


ISSUED_AT = NOW + timedelta(minutes=2)


class Counter:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.value if not callable(self.value) else self.value(self.calls)


def issuance_command(**changes):
    exact_handoff_identity = replace(
        market_identity(),
        window_started_at=NOW,
        window_ended_at=NOW,
    )
    values = {
        "issuance_command_id": "issuance-command-1",
        "discovery_command_id": "command-1",
        "discovery_execution_id": "execution-1",
        "finalized_group_id": "group-opaque-1",
        "discovery_reference": "collector:ebay:item-1",
        "market_observation_identity": exact_handoff_identity,
        "requested_at": NOW,
    }
    values.update(changes)
    return IssueOpportunityCandidateCommand(**values)


def repositories(path, *, completed=True):
    prepare_group(path)
    results = SQLiteDiscoveryResultRepository(path)
    if completed:
        results.save_result(result())
    return (
        SQLiteDiscoveryCommandRepository(path),
        results,
        SQLiteDiscoveryGroupRepository(path),
        SQLiteDiscoveryObservationRepository(path),
    )


def service(repositories, id_generator, clock):
    return IssueOpportunityCandidate(
        *repositories,
        candidate_id_generator=id_generator,
        clock=clock,
    )


def close(repositories):
    for repository in repositories:
        repository.close()


def database_state(connection):
    tables = tuple(
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
    )
    return tuple(
        (table, tuple(tuple(row) for row in connection.execute(f"SELECT * FROM {table} ORDER BY rowid")))
        for table in tables
    )


def test_command_is_immutable_versioned_equal_and_timezone_aware() -> None:
    value = issuance_command()
    assert value == issuance_command()
    assert value.schema_version == CANDIDATE_ISSUANCE_COMMAND_SCHEMA_VERSION
    with pytest.raises(FrozenInstanceError):
        value.finalized_group_id = "changed"
    with pytest.raises(MalformedCandidateIssuanceCommandError, match="timezone-aware"):
        replace(value, requested_at=NOW.replace(tzinfo=None))
    with pytest.raises(UnsupportedCandidateIssuanceCommandVersionError):
        replace(value, schema_version="future")


def test_issuance_reads_persisted_facts_and_returns_immutable_exact_context(tmp_path) -> None:
    repos = repositories(tmp_path / "discovery.db")
    generator = Counter("candidate-opaque-1")
    clock = Counter(ISSUED_AT)
    before = database_state(repos[0]._connection)
    issued = service(repos, generator, clock).execute(issuance_command())
    assert issued.candidate_identity == OpportunityCandidateIdentity(
        "candidate-opaque-1", "collector:ebay:item-1"
    )
    assert issued.discovery_context.candidate_identity == issued.candidate_identity
    assert (
        issued.discovery_context.market_observation_identity
        == issuance_command().market_observation_identity
    )
    assert issued.discovery_context.discovery_execution_id == "execution-1"
    assert issued.discovery_context.command_id == "command-1"
    assert issued.finalized_group_id == "group-opaque-1"
    assert issued.issued_at == ISSUED_AT
    assert generator.calls == 1 and clock.calls == 1
    assert database_state(repos[0]._connection) == before
    with pytest.raises(FrozenInstanceError):
        issued.finalized_group_id = "changed"
    close(repos)


def test_canonical_product_identity_conflicts_with_listing_handoff(tmp_path) -> None:
    repos = repositories(tmp_path / "discovery.db")
    identity = market_identity(MarketObservationScope.CANONICAL_PRODUCT)
    with pytest.raises(CandidateMarketIdentityConflictError):
        service(
            repos, Counter("candidate-1"), Counter(ISSUED_AT)
        ).execute(issuance_command(market_observation_identity=identity))
    close(repos)


@pytest.mark.parametrize(
    "scope",
    (MarketObservationScope.SEARCH_QUERY, MarketObservationScope.CATEGORY),
)
def test_unresolved_market_scopes_are_rejected_before_generation(tmp_path, scope) -> None:
    repos = repositories(tmp_path / f"{scope}.db")
    generator, clock = Counter("candidate-1"), Counter(ISSUED_AT)
    with pytest.raises(CandidateMarketIdentityConflictError):
        service(repos, generator, clock).execute(
            issuance_command(market_observation_identity=market_identity(scope))
        )
    assert generator.calls == 0 and clock.calls == 0
    close(repos)


def test_marketplace_and_listing_item_mismatch_are_rejected(tmp_path) -> None:
    repos = repositories(tmp_path / "discovery.db")
    base = issuance_command().market_observation_identity
    for identity in (
        replace(base, marketplace="amazon"),
        replace(base, marketplace_item_id="other-item"),
        replace(base, market="KR"),
        replace(base, window_started_at=base.window_started_at - timedelta(seconds=1)),
    ):
        with pytest.raises(CandidateMarketIdentityConflictError):
            service(repos, Counter("candidate-1"), Counter(ISSUED_AT)).execute(
                issuance_command(market_observation_identity=identity)
            )
    close(repos)


def test_changed_discovery_reference_is_rejected(tmp_path) -> None:
    repos = repositories(tmp_path / "reference.db")
    with pytest.raises(CandidateDiscoveryReferenceConflictError):
        service(repos, Counter("candidate-1"), Counter(ISSUED_AT)).execute(
            issuance_command(discovery_reference="changed-reference")
        )
    close(repos)


def test_group_a_handoff_cannot_issue_candidate_for_group_b(tmp_path) -> None:
    repos = repositories(tmp_path / "cross-group.db", completed=False)
    repos[2].save_group(
        replace(
            group(),
            finalized_group_id="group-opaque-2",
            representative_observation_id="observation-2",
        )
    )
    repos[1].save_result(
        result(finalized_group_ids=("group-opaque-1", "group-opaque-2"))
    )
    with pytest.raises(CandidateMarketIdentityConflictError):
        service(repos, Counter("candidate-1"), Counter(ISSUED_AT)).execute(
            issuance_command(finalized_group_id="group-opaque-2")
        )
    close(repos)


def test_historical_group_without_handoff_cannot_issue_candidate(tmp_path) -> None:
    path = tmp_path / "historical.db"
    prepare(path)
    save_members(path)
    groups = SQLiteDiscoveryGroupRepository(path)
    groups.save_group(group())
    groups.close()
    results = SQLiteDiscoveryResultRepository(path)
    results.save_result(result())
    results.close()
    repos = (
        SQLiteDiscoveryCommandRepository(path),
        SQLiteDiscoveryResultRepository(path),
        SQLiteDiscoveryGroupRepository(path),
        SQLiteDiscoveryObservationRepository(path),
    )
    with pytest.raises(CandidateMarketIdentityConflictError, match="not Candidate-eligible"):
        service(repos, Counter("candidate-1"), Counter(ISSUED_AT)).execute(
            issuance_command()
        )
    close(repos)


def test_missing_result_and_zero_result_are_rejected_without_generation(tmp_path) -> None:
    repos = repositories(tmp_path / "missing.db", completed=False)
    generator, clock = Counter("candidate-1"), Counter(ISSUED_AT)
    with pytest.raises(CandidateDiscoveryResultNotFoundError):
        service(repos, generator, clock).execute(issuance_command())
    assert generator.calls == 0 and clock.calls == 0
    close(repos)

    repos = repositories(tmp_path / "zero.db", completed=False)
    repos[1].save_result(result(finalized_group_ids=()))
    generator, clock = Counter("candidate-1"), Counter(ISSUED_AT)
    with pytest.raises(CandidateGroupNotInResultError):
        service(repos, generator, clock).execute(issuance_command())
    assert generator.calls == 0 and clock.calls == 0
    close(repos)


def test_missing_command_group_and_execution_mismatch_taxonomy() -> None:
    class Commands:
        def get_command(self, value):
            return None

    class Results:
        def get_by_execution(self, value):
            return result()

    class Groups:
        def get_group(self, value):
            return None

    class Observations:
        def get_observation(self, value):
            return None

    generator, clock = Counter("candidate-1"), Counter(ISSUED_AT)
    boundary = IssueOpportunityCandidate(
        Commands(), Results(), Groups(), Observations(),
        candidate_id_generator=generator, clock=clock,
    )
    with pytest.raises(CandidateDiscoveryCommandNotFoundError):
        boundary.execute(issuance_command())
    assert generator.calls == 0 and clock.calls == 0

    class ExistingCommands:
        def get_command(self, value):
            from test_discovery_correlation_contract import command
            return command()

    boundary = IssueOpportunityCandidate(
        ExistingCommands(), Results(), Groups(), Observations(),
        candidate_id_generator=generator, clock=clock,
    )
    with pytest.raises(CandidateFinalizedGroupNotFoundError):
        boundary.execute(issuance_command())
    with pytest.raises(CandidateExecutionMismatchError):
        boundary.execute(issuance_command(discovery_execution_id="other"))


def test_group_not_in_result_is_rejected() -> None:
    from test_discovery_correlation_contract import command

    class Commands:
        get_command = lambda self, value: command()

    class Results:
        get_by_execution = lambda self, value: result(finalized_group_ids=("other",))

    class Groups:
        get_group = lambda self, value: group()

    class Observations:
        get_observation = lambda self, value: pytest.fail("observation read must not occur")

    with pytest.raises(CandidateGroupNotInResultError):
        IssueOpportunityCandidate(
            Commands(), Results(), Groups(), Observations(),
            candidate_id_generator=lambda: "candidate-1", clock=lambda: ISSUED_AT,
        ).execute(issuance_command())


@pytest.mark.parametrize("generated", ("", "   ", None))
def test_invalid_generated_candidate_identity_is_explicit(tmp_path, generated) -> None:
    repos = repositories(tmp_path / f"{generated!r}.db")
    with pytest.raises(CandidateIdentityGenerationError):
        service(repos, Counter(generated), Counter(ISSUED_AT)).execute(
            issuance_command()
        )
    close(repos)


def test_naive_issuance_clock_is_rejected(tmp_path) -> None:
    repos = repositories(tmp_path / "discovery.db")
    with pytest.raises(CandidateIdentityGenerationError, match="timezone-aware"):
        service(
            repos, Counter("candidate-1"),
            Counter(ISSUED_AT.replace(tzinfo=None)),
        ).execute(issuance_command())
    close(repos)


def test_same_generated_values_have_value_equality_but_no_replay_claim(tmp_path) -> None:
    repos = repositories(tmp_path / "discovery.db")
    first = service(repos, Counter("candidate-1"), Counter(ISSUED_AT)).execute(
        issuance_command()
    )
    second = service(repos, Counter("candidate-1"), Counter(ISSUED_AT)).execute(
        issuance_command()
    )
    assert first == second
    assert isinstance(first, CandidateIssuanceResult)
    assert "replayed" not in CandidateIssuanceResult.__dataclass_fields__
    close(repos)


def test_repeated_call_has_no_cache_and_may_generate_another_identity(tmp_path) -> None:
    repos = repositories(tmp_path / "discovery.db")
    generator = Counter(lambda call: f"candidate-{call}")
    clock = Counter(lambda call: ISSUED_AT + timedelta(seconds=call))
    boundary = service(repos, generator, clock)
    first = boundary.execute(issuance_command())
    second = boundary.execute(issuance_command())
    assert first.candidate_identity != second.candidate_identity
    assert generator.calls == 2 and clock.calls == 2
    close(repos)


def test_boundary_has_no_write_or_forbidden_execution_dependencies() -> None:
    source = inspect.getsource(IssueOpportunityCandidate).lower()
    for forbidden in (
        "save_", "sqlite", "insert", "collector", "group_similar",
        "snapshot", "safety", "decision", "opportunitylifecycle",
    ):
        assert forbidden not in source
