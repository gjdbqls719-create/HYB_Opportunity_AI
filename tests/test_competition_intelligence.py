from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.competition_intelligence import (
    AnalyzeCompetition,
    CompetitionIntelligenceService,
    CompetitionIntelligenceStatus,
)
from app.domain.market_intelligence import (
    CompetitionAssessment,
    CompetitionEvidenceUnavailableError,
    CompetitionLevel,
    CompetitionObservation,
    MarketEvidence,
    MarketEvidenceStatus,
    MarketObservationIdentity,
    MarketObservationScope,
    PricePressure,
    RocketCompetitionLevel,
    analyze_competition,
)
from app.infrastructure.market_observation import SQLiteMarketObservationRepository


NOW = datetime(2026, 8, 8, 9, tzinfo=timezone.utc)


def identity() -> MarketObservationIdentity:
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
        window_started_at=NOW,
        window_ended_at=NOW + timedelta(minutes=5),
    )


def evidence(value, *, confidence="1", unit="count", status=MarketEvidenceStatus.OBSERVED):
    absent = value is None
    return MarketEvidence(
        value=value,
        source=None if absent else "coupang-capture",
        reference=None if absent else "capture:1",
        observed_at=None if absent else NOW,
        status=status,
        confidence=Decimal(confidence),
        market="KR",
        marketplace="coupang",
        collection_method="capture",
        schema_version="market-evidence-v1",
        unit=unit,
    )


def observation(
    *,
    competitor_count=20,
    rocket_seller_count=4,
    price_spread="20",
    median_price="100",
    confidences=("1", "1", "1", "1"),
    evidence_overrides=None,
) -> CompetitionObservation:
    values = {
        "competitor_count": evidence(competitor_count, confidence=confidences[0]),
        "rocket_seller_count": evidence(rocket_seller_count, confidence=confidences[1]),
        "price_spread": evidence(Decimal(price_spread), confidence=confidences[2], unit="KRW"),
        "median_price": evidence(Decimal(median_price), confidence=confidences[3], unit="KRW"),
    }
    if evidence_overrides:
        values.update(evidence_overrides)
    return CompetitionObservation(
        observation_id="competition-1",
        identity=identity(),
        observed_at=NOW,
        schema_version="competition-v1",
        evidence=values,
    )


def assess(item=None) -> CompetitionAssessment:
    return analyze_competition(item or observation(), generated_at=NOW)


@pytest.mark.parametrize(
    ("count", "expected"),
    (
        (0, CompetitionLevel.VERY_LOW),
        (5, CompetitionLevel.VERY_LOW),
        (6, CompetitionLevel.LOW),
        (15, CompetitionLevel.LOW),
        (16, CompetitionLevel.MEDIUM),
        (30, CompetitionLevel.MEDIUM),
        (31, CompetitionLevel.HIGH),
        (60, CompetitionLevel.HIGH),
        (61, CompetitionLevel.VERY_HIGH),
    ),
)
def test_competitor_thresholds(count: int, expected: CompetitionLevel) -> None:
    rocket = min(count, 4)
    assert assess(observation(competitor_count=count, rocket_seller_count=rocket)).competition_level is expected


@pytest.mark.parametrize(
    ("count", "expected"),
    (
        (0, RocketCompetitionLevel.NONE),
        (1, RocketCompetitionLevel.LOW),
        (3, RocketCompetitionLevel.LOW),
        (4, RocketCompetitionLevel.MEDIUM),
        (10, RocketCompetitionLevel.MEDIUM),
        (11, RocketCompetitionLevel.HIGH),
    ),
)
def test_rocket_seller_thresholds(count: int, expected: RocketCompetitionLevel) -> None:
    assert assess(observation(competitor_count=100, rocket_seller_count=count)).rocket_competition is expected


@pytest.mark.parametrize(
    ("spread", "expected"),
    (
        ("5", PricePressure.VERY_HIGH),
        ("15", PricePressure.HIGH),
        ("30", PricePressure.MEDIUM),
        ("60", PricePressure.LOW),
        ("60.01", PricePressure.VERY_LOW),
    ),
)
def test_price_pressure_uses_spread_to_median_ratio(spread: str, expected: PricePressure) -> None:
    assert assess(observation(price_spread=spread, median_price="100")).price_pressure is expected


def test_confidence_is_exact_decimal_average_of_core_evidence() -> None:
    result = assess(observation(confidences=("0.8", "0.6", "1", "0.4")))
    assert result.confidence == Decimal("0.7")
    assert isinstance(result.confidence, Decimal)


def test_market_concentration_is_decimal_rocket_share_proxy() -> None:
    result = assess(observation(competitor_count=20, rocket_seller_count=5))
    assert result.market_concentration == Decimal("0.25")
    assert isinstance(result.market_concentration, Decimal)


def test_missing_and_unknown_core_evidence_are_unavailable() -> None:
    missing = observation()
    without_spread = CompetitionObservation(
        observation_id=missing.observation_id,
        identity=missing.identity,
        observed_at=missing.observed_at,
        schema_version=missing.schema_version,
        evidence={key: value for key, value in missing.evidence.items() if key != "price_spread"},
    )
    with pytest.raises(CompetitionEvidenceUnavailableError) as missing_error:
        assess(without_spread)
    assert missing_error.value.missing_metrics == ("price_spread",)

    unknown = evidence(None, confidence="0", status=MarketEvidenceStatus.UNKNOWN)
    with pytest.raises(CompetitionEvidenceUnavailableError) as unknown_error:
        assess(observation(evidence_overrides={"rocket_seller_count": unknown}))
    assert unknown_error.value.missing_metrics == ("rocket_seller_count",)


def test_summary_is_competition_only() -> None:
    result = assess(observation(competitor_count=61, rocket_seller_count=4))
    assert result.summary == "Very High competition with medium rocket seller presence."
    assert not hasattr(result, "recommendation")
    assert not hasattr(result, "score")


def test_assessment_is_immutable_and_has_value_equality() -> None:
    left = assess()
    right = assess()
    assert left == right
    with pytest.raises(FrozenInstanceError):
        left.confidence = Decimal("0")  # type: ignore[misc]


def test_application_reuses_market_observation_repository() -> None:
    repository = SQLiteMarketObservationRepository(":memory:")
    repository.save(observation())
    service = CompetitionIntelligenceService(repository)

    result = service.analyze(AnalyzeCompetition(identity(), NOW))
    assert result.status is CompetitionIntelligenceStatus.ASSESSED
    assert result.assessment == assess()


def test_application_returns_unavailable_for_missing_observation_or_metric() -> None:
    repository = SQLiteMarketObservationRepository(":memory:")
    service = CompetitionIntelligenceService(repository)
    result = service.analyze(AnalyzeCompetition(identity(), NOW))
    assert result.status is CompetitionIntelligenceStatus.UNAVAILABLE
    assert result.missing_metrics == ("competition_observation",)

    incomplete = observation()
    incomplete = CompetitionObservation(
        observation_id=incomplete.observation_id,
        identity=incomplete.identity,
        observed_at=incomplete.observed_at,
        schema_version=incomplete.schema_version,
        evidence={
            key: value
            for key, value in incomplete.evidence.items()
            if key != "median_price"
        },
    )
    repository.save(incomplete)
    result = service.analyze(AnalyzeCompetition(identity(), NOW))
    assert result.status is CompetitionIntelligenceStatus.UNAVAILABLE
    assert result.missing_metrics == ("median_price",)
