from dataclasses import FrozenInstanceError, replace
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import sqlite3

import pytest

from app.application.dashboard_api import (
    DashboardCompositionUnavailableError,
    MISSING_VERIFIED_ECONOMICS,
    ProductionOpportunityDecisionDashboardProvider,
)
from app.application.opportunity_market_identity import (
    GetOpportunityMarketIdentity,
    OpportunityMarketIdentityBinding,
    OpportunityMarketIdentityBindingNotFoundError,
    OpportunityMarketIdentityConflictError,
)
from app.application.opportunity_validation import (
    AddToValidationQueueCommand,
    DuplicateActiveValidationError,
    OpportunityValidationService,
)
from app.domain.market_intelligence import (
    MarketObservationIdentity,
    MarketObservationScope,
)
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from test_economics_variance import calculation


NOW = datetime(2026, 8, 5, tzinfo=timezone.utc)


def identity(scope=MarketObservationScope.LISTING):
    return MarketObservationIdentity(
        scope=scope,
        market="US",
        marketplace="ebay",
        canonical_product_id=("canon-1" if scope is MarketObservationScope.CANONICAL_PRODUCT else None),
        marketplace_item_id=("item-1" if scope is MarketObservationScope.LISTING else None),
        normalized_query=("camera" if scope is MarketObservationScope.SEARCH_QUERY else None),
        category=("cameras" if scope is MarketObservationScope.CATEGORY else None),
        variant_identity="black",
        condition="new",
        window_started_at=NOW - timedelta(days=1),
        window_ended_at=NOW,
    )


def command(market_identity=None):
    return AddToValidationQueueCommand(
        opportunity_id="opp-bound",
        discovery_reference="ebay:item-1",
        marketplace="ebay",
        title="Camera",
        admission_recommendation="WATCH",
        admission_score=70,
        admission_roi=25,
        currency="USD",
        admission_safety_status="READY",
        operator_id="founder",
        reason="selected",
        captured_at=NOW,
        market_observation_identity=market_identity,
    )


def service(repository):
    return OpportunityValidationService(
        queue_repository=repository,
        lifecycle_repository=repository,
    )


@pytest.mark.parametrize(
    "scope",
    (MarketObservationScope.LISTING, MarketObservationScope.CANONICAL_PRODUCT),
)
def test_allowed_binding_persists_and_round_trips(scope) -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    expected = identity(scope)
    service(repository).add(command(expected))

    binding = repository.get_market_identity_binding("opp-bound")

    assert binding.market_observation_identity == expected
    assert binding.bound_at == NOW
    assert binding.schema_version == "opportunity-market-identity-v1"
    assert GetOpportunityMarketIdentity(repository).execute("opp-bound") == expected
    repository.close()


@pytest.mark.parametrize(
    "scope",
    (MarketObservationScope.SEARCH_QUERY, MarketObservationScope.CATEGORY),
)
def test_non_decision_market_scopes_are_rejected_without_rows(scope) -> None:
    repository = SQLiteValidationQueueRepository(":memory:")

    with pytest.raises(ValueError, match="listing or canonical_product"):
        service(repository).add(command(identity(scope)))

    assert repository.get("opp-bound") is None
    assert repository.get_market_identity_binding("opp-bound") is None
    repository.close()


def test_binding_is_frozen_and_database_update_delete_are_blocked() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    service(repository).add(command(identity()))
    binding = repository.get_market_identity_binding("opp-bound")

    with pytest.raises(FrozenInstanceError):
        binding.opportunity_id = "changed"
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        repository._connection.execute(
            "UPDATE opportunity_market_identity_bindings SET market='CA'"
        )
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        repository._connection.execute(
            "DELETE FROM opportunity_market_identity_bindings"
        )
    assert repository.get_market_identity_binding("opp-bound") == binding
    repository.close()


def test_duplicate_opportunity_binding_is_rejected() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    service(repository).add(command(identity()))
    binding = repository.get_market_identity_binding("opp-bound")

    with pytest.raises(sqlite3.IntegrityError):
        repository._insert_market_identity_binding(binding)

    assert repository.get_market_identity_binding("opp-bound") == binding
    repository.close()


def test_binding_validates_opportunity_and_discovery_identity() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    lifecycle, transition, snapshot = service(repository)._build_admission(command())
    valid = OpportunityMarketIdentityBinding(
        "opp-bound", "ebay:item-1", identity(), NOW
    )

    with pytest.raises(OpportunityMarketIdentityConflictError, match="opportunity_id"):
        repository.admit_with_market_identity(
            lifecycle, transition, snapshot, replace(valid, opportunity_id="other")
        )
    with pytest.raises(OpportunityMarketIdentityConflictError, match="discovery_reference"):
        repository.admit_with_market_identity(
            lifecycle,
            transition,
            snapshot,
            replace(valid, discovery_reference="ebay:different"),
        )
    assert repository.get("opp-bound") is None
    repository.close()


@pytest.mark.parametrize(
    ("table", "message"),
    (
        ("opportunity_market_identity_bindings", "binding failure"),
        ("validation_queue_admission_snapshots", "snapshot failure"),
    ),
)
def test_admission_insert_failure_rolls_back_every_artifact(table, message) -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    repository._connection.execute(
        f"""CREATE TRIGGER injected_failure BEFORE INSERT ON {table}
        BEGIN SELECT RAISE(ABORT, '{message}'); END"""
    )

    with pytest.raises(sqlite3.IntegrityError, match=message):
        service(repository).add(command(identity()))

    assert repository.get("opp-bound") is None
    assert repository.list_transitions("opp-bound") == ()
    assert repository.get_queue_item("opp-bound") is None
    assert repository.get_market_identity_binding("opp-bound") is None
    repository.close()


def test_estimated_baseline_failure_leaves_no_binding_or_admission() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    repository._connection.execute(
        """CREATE TRIGGER fail_baseline BEFORE INSERT
        ON opportunity_estimated_economics_snapshots
        BEGIN SELECT RAISE(ABORT, 'baseline failure'); END"""
    )

    with pytest.raises(sqlite3.IntegrityError, match="baseline failure"):
        service(repository).add_with_economics(command(identity()), calculation())

    assert repository.get("opp-bound") is None
    assert repository.get_queue_item("opp-bound") is None
    assert repository._economics.get_admission_baseline("opp-bound") is None
    assert repository.get_market_identity_binding("opp-bound") is None
    repository.close()


def test_legacy_admission_has_explicit_binding_not_found() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    service(repository).add(command())

    with pytest.raises(OpportunityMarketIdentityBindingNotFoundError):
        GetOpportunityMarketIdentity(repository).execute("opp-bound")
    repository.close()


def test_dashboard_provider_uses_binding_and_advances_to_next_gap() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    service(repository).add(command(identity()))

    with pytest.raises(
        DashboardCompositionUnavailableError,
        match="no authoritative VerifiedEconomicsInput source",
    ) as error:
        ProductionOpportunityDecisionDashboardProvider(repository).get("opp-bound")

    assert str(error.value) == MISSING_VERIFIED_ECONOMICS
    repository.close()


def test_binding_query_is_read_only_and_preserves_timezone_and_scope() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    expected = identity(MarketObservationScope.CANONICAL_PRODUCT)
    service(repository).add(command(expected))
    before = {
        table: repository._connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in (
            "opportunity_lifecycles",
            "opportunity_lifecycle_transitions",
            "validation_queue_admission_snapshots",
            "opportunity_estimated_economics_snapshots",
            "opportunity_market_identity_bindings",
            "market_observation_history",
            "market_observation_current",
        )
        if repository._connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,),
        ).fetchone()
    }

    actual = GetOpportunityMarketIdentity(repository).execute("opp-bound")
    after = {
        table: repository._connection.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in before
    }

    assert actual == expected
    assert actual.scope is MarketObservationScope.CANONICAL_PRODUCT
    assert actual.window_started_at.utcoffset() is not None
    assert before == after
    repository.close()


def test_legacy_add_contract_remains_compatible() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")

    item = service(repository).add(command())

    assert item.opportunity_id == "opp-bound"
    assert repository.get_market_identity_binding("opp-bound") is None
    repository.close()


def test_concurrent_duplicate_admission_creates_exactly_one_binding(tmp_path) -> None:
    database = tmp_path / "market-binding.db"
    SQLiteValidationQueueRepository(database).close()

    def admit(opportunity_id):
        repository = SQLiteValidationQueueRepository(database)
        try:
            return service(repository).add(
                replace(command(identity()), opportunity_id=opportunity_id)
            ).opportunity_id
        finally:
            repository.close()

    outcomes = []
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(admit, value) for value in ("opp-a", "opp-b")]
        for future in futures:
            try:
                outcomes.append(("created", future.result()))
            except DuplicateActiveValidationError:
                outcomes.append(("duplicate", None))

    repository = SQLiteValidationQueueRepository(database)
    binding_count = repository._connection.execute(
        "SELECT COUNT(*) FROM opportunity_market_identity_bindings"
    ).fetchone()[0]
    repository.close()
    assert sorted(value for value, _ in outcomes) == ["created", "duplicate"]
    assert binding_count == 1
