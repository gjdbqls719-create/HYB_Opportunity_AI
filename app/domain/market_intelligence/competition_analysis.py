from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.domain.market_intelligence.competition import CompetitionObservation


class CompetitionLevel(StrEnum):
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class PricePressure(StrEnum):
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class RocketCompetitionLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


COMPETITOR_VERY_LOW_MAX = 5
COMPETITOR_LOW_MAX = 15
COMPETITOR_MEDIUM_MAX = 30
COMPETITOR_HIGH_MAX = 60

ROCKET_NONE_MAX = 0
ROCKET_LOW_MAX = 3
ROCKET_MEDIUM_MAX = 10

PRICE_SPREAD_VERY_HIGH_PRESSURE_MAX = Decimal("0.05")
PRICE_SPREAD_HIGH_PRESSURE_MAX = Decimal("0.15")
PRICE_SPREAD_MEDIUM_PRESSURE_MAX = Decimal("0.30")
PRICE_SPREAD_LOW_PRESSURE_MAX = Decimal("0.60")

CORE_COMPETITION_METRICS = (
    "competitor_count",
    "rocket_seller_count",
    "price_spread",
    "median_price",
)


class CompetitionEvidenceUnavailableError(ValueError):
    def __init__(self, missing_metrics: tuple[str, ...]) -> None:
        self.missing_metrics = missing_metrics
        super().__init__(f"competition evidence unavailable: {', '.join(missing_metrics)}")


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
class CompetitionAssessment:
    """Competition-only assessment with no recommendation semantics.

    ``market_concentration`` is the observed rocket-seller share among
    competitors, not HHI or verified seller market share concentration.
    """

    competition_level: CompetitionLevel
    price_pressure: PricePressure
    rocket_competition: RocketCompetitionLevel
    market_concentration: Decimal
    confidence: Decimal
    summary: str
    generated_at: datetime
    schema_version: str

    def __post_init__(self) -> None:
        for name, enum_type in (
            ("competition_level", CompetitionLevel),
            ("price_pressure", PricePressure),
            ("rocket_competition", RocketCompetitionLevel),
        ):
            value = getattr(self, name)
            if not isinstance(value, enum_type):
                object.__setattr__(self, name, enum_type(value))
        for name in ("market_concentration", "confidence"):
            value = getattr(self, name)
            if not isinstance(value, Decimal):
                raise TypeError(f"{name} must be Decimal")
            if not value.is_finite() or not Decimal("0") <= value <= Decimal("1"):
                raise ValueError(f"{name} must be between 0 and 1")
        object.__setattr__(self, "summary", _required_text(self.summary, "summary"))
        object.__setattr__(self, "generated_at", _aware(self.generated_at, "generated_at"))
        object.__setattr__(self, "schema_version", _required_text(self.schema_version, "schema_version"))


def analyze_competition(
    observation: CompetitionObservation,
    *,
    generated_at: datetime,
    schema_version: str = "competition-assessment-v1",
) -> CompetitionAssessment:
    if not isinstance(observation, CompetitionObservation):
        raise TypeError("observation must be CompetitionObservation")
    _aware(generated_at, "generated_at")

    missing = tuple(
        metric
        for metric in CORE_COMPETITION_METRICS
        if metric not in observation.evidence
        or observation.evidence[metric].value is None
    )
    if missing:
        raise CompetitionEvidenceUnavailableError(missing)

    competitor_count = observation.evidence["competitor_count"].value
    rocket_seller_count = observation.evidence["rocket_seller_count"].value
    price_spread = observation.evidence["price_spread"].value
    median_price = observation.evidence["median_price"].value
    assert isinstance(competitor_count, int) and not isinstance(competitor_count, bool)
    assert isinstance(rocket_seller_count, int) and not isinstance(rocket_seller_count, bool)
    assert isinstance(price_spread, Decimal)
    assert isinstance(median_price, Decimal)

    if rocket_seller_count > competitor_count:
        raise ValueError("rocket_seller_count cannot exceed competitor_count")
    if median_price == 0 and price_spread != 0:
        raise CompetitionEvidenceUnavailableError(("price_pressure",))

    spread_ratio = Decimal("0") if median_price == 0 else price_spread / median_price
    competition_level = _competition_level(competitor_count)
    rocket_level = _rocket_level(rocket_seller_count)
    pressure = _price_pressure(spread_ratio)
    concentration = (
        Decimal("0")
        if competitor_count == 0
        else Decimal(rocket_seller_count) / Decimal(competitor_count)
    )
    confidence = sum(
        (observation.evidence[metric].confidence for metric in CORE_COMPETITION_METRICS),
        Decimal("0"),
    ) / Decimal(len(CORE_COMPETITION_METRICS))
    summary = (
        f"{competition_level.value.replace('_', ' ').title()} competition "
        f"with {rocket_level.value.replace('_', ' ')} rocket seller presence."
    )
    return CompetitionAssessment(
        competition_level=competition_level,
        price_pressure=pressure,
        rocket_competition=rocket_level,
        market_concentration=concentration,
        confidence=confidence,
        summary=summary,
        generated_at=generated_at,
        schema_version=schema_version,
    )


def _competition_level(count: int) -> CompetitionLevel:
    if count <= COMPETITOR_VERY_LOW_MAX:
        return CompetitionLevel.VERY_LOW
    if count <= COMPETITOR_LOW_MAX:
        return CompetitionLevel.LOW
    if count <= COMPETITOR_MEDIUM_MAX:
        return CompetitionLevel.MEDIUM
    if count <= COMPETITOR_HIGH_MAX:
        return CompetitionLevel.HIGH
    return CompetitionLevel.VERY_HIGH


def _rocket_level(count: int) -> RocketCompetitionLevel:
    if count <= ROCKET_NONE_MAX:
        return RocketCompetitionLevel.NONE
    if count <= ROCKET_LOW_MAX:
        return RocketCompetitionLevel.LOW
    if count <= ROCKET_MEDIUM_MAX:
        return RocketCompetitionLevel.MEDIUM
    return RocketCompetitionLevel.HIGH


def _price_pressure(spread_ratio: Decimal) -> PricePressure:
    if spread_ratio <= PRICE_SPREAD_VERY_HIGH_PRESSURE_MAX:
        return PricePressure.VERY_HIGH
    if spread_ratio <= PRICE_SPREAD_HIGH_PRESSURE_MAX:
        return PricePressure.HIGH
    if spread_ratio <= PRICE_SPREAD_MEDIUM_PRESSURE_MAX:
        return PricePressure.MEDIUM
    if spread_ratio <= PRICE_SPREAD_LOW_PRESSURE_MAX:
        return PricePressure.LOW
    return PricePressure.VERY_LOW
