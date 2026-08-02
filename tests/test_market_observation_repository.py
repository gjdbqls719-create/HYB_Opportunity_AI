import sqlite3
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.market_observation import (
    DuplicateMarketObservationError,
    GetLatestObservation,
    GetObservationHistory,
    MarketObservationService,
    MarketObservationType,
    SaveMarketObservation,
)
from app.domain.market_intelligence import (
    CompetitionObservation,
    DemandObservation,
    ExternalMarketSignal,
    ExternalSignalDirection,
    ExternalSignalSourceType,
    MarketEvidence,
    MarketEvidenceStatus,
    MarketObservationIdentity,
    MarketObservationScope,
)
from app.infrastructure.market_observation import SQLiteMarketObservationRepository


NOW = datetime(2026, 8, 7, 9, tzinfo=timezone.utc)


def identity(at=NOW) -> MarketObservationIdentity:
    return MarketObservationIdentity(
        scope=MarketObservationScope.SEARCH_QUERY,
        market="KR",
        marketplace="coupang",
        canonical_product_id=None,
        marketplace_item_id=None,
        normalized_query="wireless mouse",
        category="electronics",
        variant_identity=None,
        condition="new",
        window_started_at=at,
        window_ended_at=at + timedelta(minutes=5),
    )


def evidence(value, at=NOW, *, reference="capture:1", unit="count") -> MarketEvidence:
    return MarketEvidence(
        value=value,
        source="coupang-capture",
        reference=reference,
        observed_at=at,
        status=MarketEvidenceStatus.OBSERVED,
        confidence=Decimal("0.9"),
        market="KR",
        marketplace="coupang",
        collection_method="capture",
        schema_version="market-evidence-v1",
        keyword="wireless mouse",
        category="electronics",
        unit=unit,
    )


def competition(number=10, at=NOW, *, observation_id="competition-1", reference="capture:1"):
    return CompetitionObservation(
        observation_id=observation_id,
        identity=identity(at),
        observed_at=at,
        schema_version="competition-v1",
        evidence={"competitor_count": evidence(number, at, reference=reference)},
    )


def demand(at=NOW):
    return DemandObservation(
        observation_id="demand-1",
        identity=identity(at),
        observed_at=at,
        schema_version="demand-v1",
        evidence={"rating": evidence(Decimal("4.75"), at, unit="stars")},
    )


def external(at=NOW):
    return ExternalMarketSignal(
        signal_id="signal-1",
        identity=identity(at),
        source_type=ExternalSignalSourceType.ITEMSCOUT_SCREENSHOT,
        signal_name="popularity momentum",
        signal_direction=ExternalSignalDirection.POSITIVE,
        evidence=evidence(Decimal("0.8"), at, unit="index"),
        captured_at=at,
        artifact_reference="artifact:1",
        schema_version="external-signal-v1",
    )


def history_count(repository) -> int:
    return repository._connection.execute(
        "SELECT COUNT(*) FROM market_observation_history"
    ).fetchone()[0]


def current_count(repository) -> int:
    return repository._connection.execute(
        "SELECT COUNT(*) FROM market_observation_current"
    ).fetchone()[0]


@pytest.mark.parametrize(
    ("item", "observation_type"),
    (
        (competition(), MarketObservationType.COMPETITION),
        (demand(), MarketObservationType.DEMAND),
        (external(), MarketObservationType.EXTERNAL_SIGNAL),
    ),
)
def test_all_observation_types_round_trip(item, observation_type) -> None:
    repository = SQLiteMarketObservationRepository(":memory:")
    repository.save(item)

    assert repository.get_latest(observation_type, item.identity) == item
    assert repository.get_history(observation_type, item.identity) == (item,)


def test_save_is_append_only_and_history_is_newest_first() -> None:
    repository = SQLiteMarketObservationRepository(":memory:")
    first = competition()
    second = competition(
        8,
        NOW + timedelta(hours=1),
        observation_id="competition-2",
        reference="capture:2",
    )
    repository.save(first)
    repository.save(second)

    assert repository.get_history(MarketObservationType.COMPETITION, first.identity) == (
        second,
        first,
    )
    assert history_count(repository) == 2
    assert current_count(repository) == 1


def test_current_projection_updates_to_latest_without_rewriting_history() -> None:
    repository = SQLiteMarketObservationRepository(":memory:")
    latest = competition(
        7,
        NOW + timedelta(hours=2),
        observation_id="competition-latest",
        reference="capture:latest",
    )
    older = competition(
        11,
        NOW + timedelta(hours=1),
        observation_id="competition-older",
        reference="capture:older",
    )
    repository.save(latest)
    repository.save(older)

    assert repository.get_latest(MarketObservationType.COMPETITION, older.identity) == latest
    assert history_count(repository) == 2


def test_duplicate_fingerprint_is_rejected_without_projection_change() -> None:
    repository = SQLiteMarketObservationRepository(":memory:")
    original = competition()
    duplicate = replace(original, observation_id="different-id")
    repository.save(original)

    with pytest.raises(DuplicateMarketObservationError):
        repository.save(duplicate)

    assert history_count(repository) == 1
    assert repository.get_latest(MarketObservationType.COMPETITION, original.identity) == original


def test_projection_failure_rolls_back_history_and_current() -> None:
    repository = SQLiteMarketObservationRepository(":memory:")
    repository._connection.execute(
        """CREATE TRIGGER fail_market_current_insert
        BEFORE INSERT ON market_observation_current
        BEGIN SELECT RAISE(ABORT, 'projection failure'); END"""
    )

    with pytest.raises(sqlite3.IntegrityError, match="projection failure"):
        repository.save(competition())

    assert history_count(repository) == 0
    assert current_count(repository) == 0


def test_history_table_rejects_update_and_delete() -> None:
    repository = SQLiteMarketObservationRepository(":memory:")
    repository.save(competition())

    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        repository._connection.execute(
            "UPDATE market_observation_history SET observation_id = 'changed'"
        )
    repository._connection.rollback()
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        repository._connection.execute("DELETE FROM market_observation_history")
    repository._connection.rollback()
    assert history_count(repository) == 1


def test_service_use_cases_save_query_history_and_calculate_freshness() -> None:
    repository = SQLiteMarketObservationRepository(":memory:")
    service = MarketObservationService(repository)
    item = competition()

    assert service.save(SaveMarketObservation(item)) == item
    latest = service.get_latest(GetLatestObservation(
        MarketObservationType.COMPETITION,
        item.identity,
        as_of=NOW + timedelta(hours=3),
        freshness_window=timedelta(hours=2),
    ))
    assert latest is not None
    assert latest.observation == item
    assert latest.age == timedelta(hours=3)
    assert latest.is_stale is True
    assert service.get_history(GetObservationHistory(
        MarketObservationType.COMPETITION,
        item.identity,
    )) == (item,)

    columns = {
        row["name"]
        for row in repository._connection.execute(
            "PRAGMA table_info(market_observation_history)"
        )
    }
    assert "freshness" not in columns
    assert "version" not in columns


def test_history_limit_is_applied_after_latest_ordering() -> None:
    repository = SQLiteMarketObservationRepository(":memory:")
    first = competition()
    second = competition(
        9,
        NOW + timedelta(hours=1),
        observation_id="competition-2",
        reference="capture:2",
    )
    repository.save(first)
    repository.save(second)

    assert repository.get_history(
        MarketObservationType.COMPETITION,
        first.identity,
        limit=1,
    ) == (second,)
