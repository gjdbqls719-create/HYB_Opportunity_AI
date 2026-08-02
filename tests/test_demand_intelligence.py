from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.demand_intelligence import (
    AnalyzeDemand,
    DemandIntelligenceService,
    DemandIntelligenceStatus,
)
from app.domain.market_intelligence import (
    DemandAssessment,
    DemandAssessmentAvailability,
    DemandEvidenceUnavailableError,
    DemandLevel,
    DemandObservation,
    MarketEvidence,
    MarketEvidenceStatus,
    MarketObservationIdentity,
    MarketObservationScope,
    PopularityLevel,
    ReviewQuality,
    analyze_demand,
)
from app.infrastructure.market_observation import SQLiteMarketObservationRepository


NOW = datetime(2026, 8, 9, 9, tzinfo=timezone.utc)


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
    search_volume=2_001,
    review_count=201,
    rating="4.6",
    coupang_rank=3,
    itemscout_rank=7,
    confidences=("1", "1", "1", "1", "1"),
    evidence_overrides=None,
) -> DemandObservation:
    values = {
        "search_volume": evidence(search_volume, confidence=confidences[0]),
        "review_count": evidence(review_count, confidence=confidences[1]),
        "rating": evidence(Decimal(rating), confidence=confidences[2], unit="stars"),
        "coupang_popularity_rank": evidence(coupang_rank, confidence=confidences[3], unit="rank"),
        "itemscout_popularity_rank": evidence(itemscout_rank, confidence=confidences[4], unit="rank"),
    }
    if evidence_overrides:
        values.update(evidence_overrides)
    return DemandObservation(
        observation_id="demand-1",
        identity=identity(),
        observed_at=NOW,
        schema_version="demand-v1",
        evidence=values,
    )


def assess(item=None) -> DemandAssessment:
    return analyze_demand(item or observation(), generated_at=NOW)


@pytest.mark.parametrize(
    ("volume", "expected"),
    (
        (0, DemandLevel.VERY_LOW), (100, DemandLevel.VERY_LOW),
        (101, DemandLevel.LOW), (500, DemandLevel.LOW),
        (501, DemandLevel.MEDIUM), (2_000, DemandLevel.MEDIUM),
        (2_001, DemandLevel.HIGH), (10_000, DemandLevel.HIGH),
        (10_001, DemandLevel.VERY_HIGH),
    ),
)
def test_search_volume_demand_thresholds(volume: int, expected: DemandLevel) -> None:
    assert assess(observation(search_volume=volume)).demand_level is expected


@pytest.mark.parametrize(
    ("count", "expected"),
    (
        (0, PopularityLevel.VERY_LOW),
        (1, PopularityLevel.LOW), (30, PopularityLevel.LOW),
        (31, PopularityLevel.MEDIUM), (200, PopularityLevel.MEDIUM),
        (201, PopularityLevel.HIGH), (1_000, PopularityLevel.HIGH),
        (1_001, PopularityLevel.VERY_HIGH),
    ),
)
def test_review_count_popularity_thresholds(count: int, expected: PopularityLevel) -> None:
    assert assess(observation(review_count=count)).popularity_level is expected


@pytest.mark.parametrize(
    ("rating", "expected"),
    (
        ("0", ReviewQuality.POOR), ("2.5", ReviewQuality.POOR),
        ("2.5001", ReviewQuality.FAIR), ("3.5", ReviewQuality.FAIR),
        ("3.5001", ReviewQuality.GOOD), ("4.5", ReviewQuality.GOOD),
        ("4.5001", ReviewQuality.EXCELLENT), ("5", ReviewQuality.EXCELLENT),
    ),
)
def test_rating_quality_thresholds(rating: str, expected: ReviewQuality) -> None:
    assert assess(observation(rating=rating)).review_quality is expected


def test_confidence_is_exact_decimal_average() -> None:
    result = assess(observation(confidences=("0.8", "0.6", "1", "0.4", "0.7")))
    assert result.confidence == Decimal("0.7")
    assert isinstance(result.confidence, Decimal)


def test_rankings_remain_independent_proxies_and_no_competition_balance_exists() -> None:
    first = assess(observation(coupang_rank=1, itemscout_rank=999))
    second = assess(observation(coupang_rank=999, itemscout_rank=1))
    assert first.demand_level is second.demand_level
    assert not hasattr(first, "demand_confetition_balance")
    assert not hasattr(first, "demand_competition_balance")


def test_missing_and_unknown_core_evidence_produce_partial_assessment() -> None:
    item = observation()
    missing = DemandObservation(
        observation_id=item.observation_id,
        identity=item.identity,
        observed_at=item.observed_at,
        schema_version=item.schema_version,
        evidence={key: value for key, value in item.evidence.items() if key != "search_volume"},
    )
    result = assess(missing)
    assert result.availability is DemandAssessmentAvailability.PARTIAL
    assert result.demand_level is None
    assert result.missing_metrics == ("search_volume",)

    unknown = evidence(None, confidence="0", status=MarketEvidenceStatus.UNKNOWN)
    result = assess(observation(evidence_overrides={"itemscout_popularity_rank": unknown}))
    assert result.availability is DemandAssessmentAvailability.PARTIAL
    assert result.missing_metrics == ("itemscout_popularity_rank",)


def test_summary_is_demand_only() -> None:
    result = assess()
    assert result.summary.startswith("High demand with high observed popularity")
    assert "excellent review quality" in result.summary
    for forbidden in ("recommendation", "score", "decision"):
        assert not hasattr(result, forbidden)


def test_assessment_is_immutable_and_has_value_equality() -> None:
    assert assess() == assess()
    with pytest.raises(FrozenInstanceError):
        assess().confidence = Decimal("0")  # type: ignore[misc]


def test_application_reuses_market_observation_repository() -> None:
    repository = SQLiteMarketObservationRepository(":memory:")
    repository.save(observation())
    result = DemandIntelligenceService(repository).analyze(AnalyzeDemand(identity(), NOW))
    assert result.status is DemandIntelligenceStatus.ASSESSED
    assert result.assessment == assess()


def test_application_returns_unavailable_only_without_any_usable_observation() -> None:
    repository = SQLiteMarketObservationRepository(":memory:")
    service = DemandIntelligenceService(repository)
    assert service.analyze(AnalyzeDemand(identity(), NOW)).missing_metrics == ("demand_observation",)

    item = observation()
    repository.save(DemandObservation(
        observation_id=item.observation_id,
        identity=item.identity,
        observed_at=item.observed_at,
        schema_version=item.schema_version,
        evidence={key: value for key, value in item.evidence.items() if key != "rating"},
    ))
    result = service.analyze(AnalyzeDemand(identity(), NOW))
    assert result.status is DemandIntelligenceStatus.ASSESSED
    assert result.assessment is not None
    assert result.assessment.availability is DemandAssessmentAvailability.PARTIAL
    assert result.assessment.missing_metrics == ("rating",)


def partial_observation(values) -> DemandObservation:
    return DemandObservation(
        observation_id="demand-partial",
        identity=identity(),
        observed_at=NOW,
        schema_version="demand-v1",
        evidence=values,
    )


def test_search_volume_only_creates_partial_assessment() -> None:
    result = assess(partial_observation({
        "search_volume": evidence(501, confidence="0.8"),
    }))
    assert result.availability is DemandAssessmentAvailability.PARTIAL
    assert result.demand_level is DemandLevel.MEDIUM
    assert result.popularity_level is None
    assert result.review_quality is ReviewQuality.UNKNOWN
    assert result.available_metrics == ("search_volume",)
    assert result.confidence == Decimal("0.8")


def test_review_count_and_rating_create_partial_assessment() -> None:
    result = assess(partial_observation({
        "review_count": evidence(50, confidence="0.6"),
        "rating": evidence(Decimal("4"), confidence="0.8", unit="stars"),
    }))
    assert result.popularity_level is PopularityLevel.MEDIUM
    assert result.review_quality is ReviewQuality.GOOD
    assert result.demand_level is None
    assert result.confidence == Decimal("0.7")
    assert "search-volume evidence unavailable" in result.summary


def test_coupang_rank_without_itemscout_rank_remains_assessable() -> None:
    result = assess(partial_observation({
        "coupang_popularity_rank": evidence(3, confidence="0.9", unit="rank"),
    }))
    assert result.availability is DemandAssessmentAvailability.PARTIAL
    assert result.available_metrics == ("coupang_popularity_rank",)
    assert "itemscout_popularity_rank" in result.missing_metrics
    assert result.confidence == Decimal("0.9")


def test_unknown_metric_does_not_remove_other_results() -> None:
    result = assess(partial_observation({
        "review_count": evidence(0, confidence="0.7"),
        "rating": evidence(
            None, confidence="0.2", status=MarketEvidenceStatus.UNKNOWN,
        ),
    }))
    assert result.popularity_level is PopularityLevel.VERY_LOW
    assert result.review_quality is ReviewQuality.UNKNOWN
    assert result.confidence == Decimal("0.7")
    assert result.available_metrics == ("review_count",)
    assert "rating" in result.missing_metrics


def test_all_metrics_unavailable_is_the_only_domain_unavailable_case() -> None:
    unknown = evidence(None, confidence="0", status=MarketEvidenceStatus.UNAVAILABLE)
    item = partial_observation({metric: unknown for metric in (
        "search_volume", "review_count", "rating",
        "coupang_popularity_rank", "itemscout_popularity_rank",
    )})
    with pytest.raises(DemandEvidenceUnavailableError) as error:
        assess(item)
    assert error.value.missing_metrics == (
        "search_volume", "review_count", "rating",
        "coupang_popularity_rank", "itemscout_popularity_rank",
    )


def test_confirmed_zero_is_available_not_missing() -> None:
    result = assess(partial_observation({
        "search_volume": evidence(0, confidence="1"),
        "review_count": evidence(0, confidence="1"),
        "rating": evidence(Decimal("0"), confidence="1", unit="stars"),
    }))
    assert result.demand_level is DemandLevel.VERY_LOW
    assert result.popularity_level is PopularityLevel.VERY_LOW
    assert result.review_quality is ReviewQuality.POOR
    assert result.available_metrics[:3] == ("search_volume", "review_count", "rating")


def test_complete_assessment_has_complete_metadata() -> None:
    result = assess()
    assert result.availability is DemandAssessmentAvailability.COMPLETE
    assert result.available_metrics == (
        "search_volume", "review_count", "rating",
        "coupang_popularity_rank", "itemscout_popularity_rank",
    )
    assert result.missing_metrics == ()
    assert result.reasons == ()
