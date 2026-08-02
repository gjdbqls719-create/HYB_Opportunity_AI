from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.domain.market_intelligence.demand import DemandObservation


class DemandLevel(StrEnum):
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class PopularityLevel(StrEnum):
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class ReviewQuality(StrEnum):
    POOR = "poor"
    FAIR = "fair"
    GOOD = "good"
    EXCELLENT = "excellent"
    UNKNOWN = "unknown"


class DemandAssessmentAvailability(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


SEARCH_VOLUME_VERY_LOW_MAX = 100
SEARCH_VOLUME_LOW_MAX = 500
SEARCH_VOLUME_MEDIUM_MAX = 2_000
SEARCH_VOLUME_HIGH_MAX = 10_000

REVIEW_COUNT_VERY_LOW_MAX = 0
REVIEW_COUNT_LOW_MAX = 30
REVIEW_COUNT_MEDIUM_MAX = 200
REVIEW_COUNT_HIGH_MAX = 1_000

RATING_POOR_MAX = Decimal("2.5")
RATING_FAIR_MAX = Decimal("3.5")
RATING_GOOD_MAX = Decimal("4.5")

CORE_DEMAND_METRICS = (
    "search_volume",
    "review_count",
    "rating",
    "coupang_popularity_rank",
    "itemscout_popularity_rank",
)


class DemandEvidenceUnavailableError(ValueError):
    def __init__(self, missing_metrics: tuple[str, ...]) -> None:
        self.missing_metrics = missing_metrics
        super().__init__(f"demand evidence unavailable: {', '.join(missing_metrics)}")


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class DemandAssessment:
    """Demand-only assessment with no recommendation or decision semantics.

    Popularity ranks remain independent demand proxies. They contribute their
    evidence confidence but are not averaged into a synthetic rank because the
    two sources do not share a defined rank population. Competition and demand
    combination remains outside this contract.
    """

    demand_level: DemandLevel | None
    popularity_level: PopularityLevel | None
    review_quality: ReviewQuality
    availability: DemandAssessmentAvailability
    available_metrics: tuple[str, ...]
    missing_metrics: tuple[str, ...]
    reasons: tuple[str, ...]
    confidence: Decimal
    summary: str
    generated_at: datetime
    schema_version: str

    def __post_init__(self) -> None:
        for name, enum_type in (
            ("demand_level", DemandLevel),
            ("popularity_level", PopularityLevel),
        ):
            value = getattr(self, name)
            if value is not None and not isinstance(value, enum_type):
                object.__setattr__(self, name, enum_type(value))
        if not isinstance(self.review_quality, ReviewQuality):
            object.__setattr__(self, "review_quality", ReviewQuality(self.review_quality))
        if not isinstance(self.availability, DemandAssessmentAvailability):
            object.__setattr__(
                self, "availability", DemandAssessmentAvailability(self.availability)
            )
        available = tuple(self.available_metrics)
        missing = tuple(self.missing_metrics)
        reasons = tuple(self.reasons)
        if not available:
            raise ValueError("DemandAssessment requires at least one available metric")
        if set(available).intersection(missing):
            raise ValueError("available_metrics and missing_metrics cannot overlap")
        if set(available).union(missing) != set(CORE_DEMAND_METRICS):
            raise ValueError("availability metadata must cover every core demand metric")
        expected_availability = (
            DemandAssessmentAvailability.COMPLETE
            if not missing
            else DemandAssessmentAvailability.PARTIAL
        )
        if self.availability is not expected_availability:
            raise ValueError("availability does not match available demand evidence")
        if self.demand_level is None and "search_volume" in available:
            raise ValueError("available search_volume requires demand_level")
        if self.demand_level is not None and "search_volume" not in available:
            raise ValueError("demand_level requires available search_volume")
        if self.popularity_level is None and "review_count" in available:
            raise ValueError("available review_count requires popularity_level")
        if self.popularity_level is not None and "review_count" not in available:
            raise ValueError("popularity_level requires available review_count")
        if (self.review_quality is ReviewQuality.UNKNOWN) == ("rating" in available):
            raise ValueError("review_quality must reflect rating availability")
        if not isinstance(self.confidence, Decimal):
            raise TypeError("confidence must be Decimal")
        if not self.confidence.is_finite() or not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("confidence must be between 0 and 1")
        object.__setattr__(self, "summary", _required_text(self.summary, "summary"))
        object.__setattr__(self, "generated_at", _aware(self.generated_at, "generated_at"))
        object.__setattr__(self, "schema_version", _required_text(self.schema_version, "schema_version"))
        object.__setattr__(self, "available_metrics", available)
        object.__setattr__(self, "missing_metrics", missing)
        object.__setattr__(self, "reasons", reasons)


def analyze_demand(
    observation: DemandObservation,
    *,
    generated_at: datetime,
    schema_version: str = "demand-assessment-v1",
) -> DemandAssessment:
    if not isinstance(observation, DemandObservation):
        raise TypeError("observation must be DemandObservation")
    _aware(generated_at, "generated_at")

    available = tuple(
        metric
        for metric in CORE_DEMAND_METRICS
        if metric in observation.evidence and observation.evidence[metric].value is not None
    )
    missing = tuple(
        metric
        for metric in CORE_DEMAND_METRICS
        if metric not in observation.evidence or observation.evidence[metric].value is None
    )
    if not available:
        raise DemandEvidenceUnavailableError(missing)

    demand_level = None
    if "search_volume" in available:
        search_volume = observation.evidence["search_volume"].value
        assert isinstance(search_volume, int) and not isinstance(search_volume, bool)
        demand_level = _demand_level(search_volume)
    popularity_level = None
    if "review_count" in available:
        review_count = observation.evidence["review_count"].value
        assert isinstance(review_count, int) and not isinstance(review_count, bool)
        popularity_level = _popularity_level(review_count)
    review_quality = ReviewQuality.UNKNOWN
    if "rating" in available:
        rating = observation.evidence["rating"].value
        assert isinstance(rating, Decimal)
        review_quality = _review_quality(rating)
    confidence = sum(
        (observation.evidence[metric].confidence for metric in available),
        Decimal("0"),
    ) / Decimal(len(available))
    summary = _summary(demand_level, popularity_level, review_quality, available, missing)
    return DemandAssessment(
        demand_level=demand_level,
        popularity_level=popularity_level,
        review_quality=review_quality,
        availability=(
            DemandAssessmentAvailability.COMPLETE
            if not missing
            else DemandAssessmentAvailability.PARTIAL
        ),
        available_metrics=available,
        missing_metrics=missing,
        reasons=tuple(f"{metric} evidence unavailable" for metric in missing),
        confidence=confidence,
        summary=summary,
        generated_at=generated_at,
        schema_version=schema_version,
    )


def _demand_level(search_volume: int) -> DemandLevel:
    if search_volume <= SEARCH_VOLUME_VERY_LOW_MAX:
        return DemandLevel.VERY_LOW
    if search_volume <= SEARCH_VOLUME_LOW_MAX:
        return DemandLevel.LOW
    if search_volume <= SEARCH_VOLUME_MEDIUM_MAX:
        return DemandLevel.MEDIUM
    if search_volume <= SEARCH_VOLUME_HIGH_MAX:
        return DemandLevel.HIGH
    return DemandLevel.VERY_HIGH


def _popularity_level(review_count: int) -> PopularityLevel:
    if review_count <= REVIEW_COUNT_VERY_LOW_MAX:
        return PopularityLevel.VERY_LOW
    if review_count <= REVIEW_COUNT_LOW_MAX:
        return PopularityLevel.LOW
    if review_count <= REVIEW_COUNT_MEDIUM_MAX:
        return PopularityLevel.MEDIUM
    if review_count <= REVIEW_COUNT_HIGH_MAX:
        return PopularityLevel.HIGH
    return PopularityLevel.VERY_HIGH


def _review_quality(rating: Decimal) -> ReviewQuality:
    if rating <= RATING_POOR_MAX:
        return ReviewQuality.POOR
    if rating <= RATING_FAIR_MAX:
        return ReviewQuality.FAIR
    if rating <= RATING_GOOD_MAX:
        return ReviewQuality.GOOD
    return ReviewQuality.EXCELLENT


def _summary(
    demand_level: DemandLevel | None,
    popularity_level: PopularityLevel | None,
    review_quality: ReviewQuality,
    available: tuple[str, ...],
    missing: tuple[str, ...],
) -> str:
    parts: list[str] = []
    if demand_level is not None:
        parts.append(f"{demand_level.value.replace('_', ' ').title()} demand")
    if popularity_level is not None:
        parts.append(
            f"{popularity_level.value.replace('_', ' ')} observed popularity"
        )
    if review_quality is not ReviewQuality.UNKNOWN:
        parts.append(f"{review_quality.value} review quality")
    for metric, label in (
        ("coupang_popularity_rank", "Coupang popularity-rank proxy"),
        ("itemscout_popularity_rank", "ItemScout popularity-rank proxy"),
    ):
        if metric in available:
            parts.append(f"{label} available")
    summary = " with ".join(parts[:2])
    if len(parts) > 2:
        summary += "; " + "; ".join(parts[2:])
    if missing:
        summary += "; " + "; ".join(
            f"{metric.replace('_', '-')} evidence unavailable" for metric in missing
        )
    return summary + "."
