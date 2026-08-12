from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping
import re

from app.domain.market_intelligence.assessment_subject import (
    AssessmentSubject,
    assessment_subject_kind,
    is_new_to_market_target_subject,
)
from app.domain.market_intelligence.competition_analysis import CompetitionLevel, PricePressure


COMPETITION_V2_POLICY_VERSION = "competition-policy-v2"
COMPETITION_V2_OBSERVATION_VERSION = "competition-observation-v2"
COMPETITION_V2_ASSESSMENT_VERSION = "competition-assessment-v2"
COUPANG_ROCKET_SIGNAL_VERSION = "coupang-rocket-signal-v1"
COUPANG_ROCKET_TAXONOMY_VERSION = "coupang-rocket-taxonomy-v1"
BOUNDED_COHORT_POLICY_VERSION = "bounded-comparable-cohort-v1"

_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")
_LABELS = {
    "\ud310\ub9e4\uc790\ub85c\ucf13": "seller_rocket",
    "\ub85c\ucf13\ubc30\uc1a1": "rocket_delivery",
    "\ub85c\ucf13\uadf8\ub85c\uc2a4": "rocket_growth",
}


class ResultPlacement(StrEnum):
    ORGANIC = "organic"
    SPONSORED = "sponsored"


class RocketObservationOutcome(StrEnum):
    OBSERVED = "observed"
    STATUS_NOT_OBSERVED = "status_not_observed"
    SEMANTICS_UNSUPPORTED = "semantics_unsupported"
    EXTRACTION_FAILED = "extraction_failed"


class CoupangRocketLabelState(StrEnum):
    SELLER_ROCKET = "seller_rocket"
    ROCKET_DELIVERY = "rocket_delivery"
    ROCKET_GROWTH = "rocket_growth"
    OTHER_EXPLICIT_ROCKET_LABEL = "other_explicit_rocket_label"
    NO_EXPLICIT_ROCKET_LABEL = "no_explicit_rocket_label"


EXPLICIT_ROCKET_STATES = tuple(CoupangRocketLabelState(value) for value in (
    "seller_rocket", "rocket_delivery", "rocket_growth", "other_explicit_rocket_label",
))


class CompetitionV2Availability(StrEnum):
    COMPLETE_WITH_MARKETPLACE_SIGNAL = "complete_with_marketplace_signal"
    COMPLETE_CORE_WITH_PARTIAL_MARKETPLACE_SIGNAL = "complete_core_with_partial_marketplace_signal"
    COMPLETE_CORE_ONLY = "complete_core_only"
    UNAVAILABLE = "unavailable"


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _optional(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text or None")
    return value.strip() or None


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _confidence(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal")
    if not value.is_finite() or not Decimal("0") <= value <= Decimal("1"):
        raise ValueError(f"{name} must be between 0 and 1")
    return value


def normalize_coupang_rocket_labels(
    raw_labels: tuple[str, ...], outcome: RocketObservationOutcome,
) -> frozenset[CoupangRocketLabelState]:
    if outcome is not RocketObservationOutcome.OBSERVED:
        return frozenset()
    states: set[CoupangRocketLabelState] = set()
    for raw in raw_labels:
        label = _text(raw, "raw_rocket_label")
        mapped = _LABELS.get(label)
        if mapped:
            states.add(CoupangRocketLabelState(mapped))
        elif "\ub85c\ucf13" in label:
            states.add(CoupangRocketLabelState.OTHER_EXPLICIT_ROCKET_LABEL)
    if not states:
        states.add(CoupangRocketLabelState.NO_EXPLICIT_ROCKET_LABEL)
    return frozenset(states)


@dataclass(frozen=True, slots=True)
class CompetitionV2Card:
    result_ordinal: int
    placement: ResultPlacement
    included: bool
    is_comparable: bool
    exclusion_reason: str | None
    marketplace_item_id: str | None
    raw_title: str
    displayed_price: Decimal | None
    currency: str | None
    price_unit: str | None
    raw_rocket_labels: tuple[str, ...] = ()
    delivery_promise_text: str | None = None
    rocket_outcome: RocketObservationOutcome | None = None
    comparability_confidence: Decimal = Decimal("1")
    price_confidence: Decimal = Decimal("1")
    rocket_label_confidence: Decimal | None = None
    visible_seller_text: str | None = None
    visible_variant_count: int = 1
    raw_payload_reference: str | None = None
    badge_color: str | None = None
    badge_icon: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.result_ordinal, bool) or not isinstance(self.result_ordinal, int) or self.result_ordinal < 1:
            raise ValueError("result_ordinal must be a positive integer")
        placement = ResultPlacement(self.placement)
        reason = _optional(self.exclusion_reason, "exclusion_reason")
        if not isinstance(self.included, bool) or not isinstance(self.is_comparable, bool):
            raise TypeError("included and is_comparable must be bool")
        if self.included and (placement is not ResultPlacement.ORGANIC or not self.is_comparable or reason is not None):
            raise ValueError("only comparable organic cards without exclusion reason may be included")
        if not self.included and reason is None:
            raise ValueError("excluded card requires exclusion_reason")
        if placement is ResultPlacement.SPONSORED and reason != "sponsored":
            raise ValueError("sponsored card requires sponsored exclusion_reason")
        price = self.displayed_price
        if price is not None and (not isinstance(price, Decimal) or not price.is_finite() or price < 0):
            raise ValueError("displayed_price must be finite non-negative Decimal or None")
        outcome = None if self.rocket_outcome is None else RocketObservationOutcome(self.rocket_outcome)
        label_confidence = self.rocket_label_confidence
        if outcome is RocketObservationOutcome.OBSERVED and label_confidence is None:
            raise ValueError("observed Rocket label region requires confidence")
        if label_confidence is not None:
            label_confidence = _confidence(label_confidence, "rocket_label_confidence")
        if isinstance(self.visible_variant_count, bool) or not isinstance(self.visible_variant_count, int) or self.visible_variant_count < 1:
            raise ValueError("visible_variant_count must be a positive integer")
        object.__setattr__(self, "placement", placement)
        object.__setattr__(self, "exclusion_reason", reason)
        object.__setattr__(self, "marketplace_item_id", _optional(self.marketplace_item_id, "marketplace_item_id"))
        object.__setattr__(self, "raw_title", _text(self.raw_title, "raw_title"))
        object.__setattr__(self, "currency", _optional(self.currency, "currency"))
        object.__setattr__(self, "price_unit", _optional(self.price_unit, "price_unit"))
        object.__setattr__(self, "raw_rocket_labels", tuple(_text(v, "raw_rocket_label") for v in self.raw_rocket_labels))
        object.__setattr__(self, "delivery_promise_text", _optional(self.delivery_promise_text, "delivery_promise_text"))
        object.__setattr__(self, "rocket_outcome", outcome)
        object.__setattr__(self, "comparability_confidence", _confidence(self.comparability_confidence, "comparability_confidence"))
        object.__setattr__(self, "price_confidence", _confidence(self.price_confidence, "price_confidence"))
        object.__setattr__(self, "rocket_label_confidence", label_confidence)
        for name in ("visible_seller_text", "raw_payload_reference", "badge_color", "badge_icon"):
            object.__setattr__(self, name, _optional(getattr(self, name), name))

    @property
    def normalized_rocket_states(self) -> frozenset[CoupangRocketLabelState]:
        return frozenset() if self.rocket_outcome is None else normalize_coupang_rocket_labels(self.raw_rocket_labels, self.rocket_outcome)


@dataclass(frozen=True, slots=True)
class CompetitionV2Cohort:
    cohort_id: str
    subject: AssessmentSubject
    market: str
    marketplace: str
    query: str | None
    category: str | None
    product_use: str
    category_form_factor: str
    condition: str
    locale: str
    result_surface: str
    window_started_at: datetime
    window_ended_at: datetime
    artifact_reference: str
    artifact_sha256: str
    bound_start: int
    bound_end: int
    operator_id: str
    cards: tuple[CompetitionV2Card, ...]
    cohort_policy_version: str = BOUNDED_COHORT_POLICY_VERSION
    observation_schema_version: str = COMPETITION_V2_OBSERVATION_VERSION
    collector_name: str | None = None
    collector_version: str | None = None
    source_schema_version: str | None = None

    def __post_init__(self) -> None:
        assessment_subject_kind(self.subject)
        market, marketplace = _text(self.market, "market").upper(), _text(self.marketplace, "marketplace").lower()
        if market != self.subject.market.upper():
            raise ValueError("cohort market must match assessment subject")
        if not is_new_to_market_target_subject(self.subject) and marketplace != self.subject.marketplace:
            raise ValueError("cohort marketplace must match assessment subject")
        query, category = _optional(self.query, "query"), _optional(self.category, "category")
        if query is None and category is None:
            raise ValueError("cohort requires query or category")
        started, ended = _aware(self.window_started_at, "window_started_at"), _aware(self.window_ended_at, "window_ended_at")
        if ended < started:
            raise ValueError("window_ended_at cannot precede window_started_at")
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (self.bound_start, self.bound_end)) or self.bound_start < 1 or self.bound_end < self.bound_start:
            raise ValueError("finite bounds are invalid")
        cards = tuple(self.cards)
        if tuple(card.result_ordinal for card in cards) != tuple(range(self.bound_start, self.bound_end + 1)):
            raise ValueError("card ordering must exactly reconcile to finite bounds")
        seen: set[str] = set()
        for card in cards:
            if not isinstance(card, CompetitionV2Card):
                raise TypeError("cards must contain CompetitionV2Card")
            if card.marketplace_item_id in seen and (card.included or card.exclusion_reason != "duplicate_marketplace_item_id"):
                raise ValueError("later duplicate item ID must be retained as duplicate exclusion")
            if card.marketplace_item_id is not None:
                seen.add(card.marketplace_item_id)
            if marketplace != "coupang" and card.rocket_outcome is not None:
                raise ValueError("Coupang signal is only supported for coupang marketplace")
        sha = _text(self.artifact_sha256, "artifact_sha256")
        if not _SHA256.fullmatch(sha):
            raise ValueError("artifact_sha256 must be 64 hexadecimal characters")
        if self.cohort_policy_version != BOUNDED_COHORT_POLICY_VERSION or self.observation_schema_version != COMPETITION_V2_OBSERVATION_VERSION:
            raise ValueError("unsupported Competition v2 cohort version")
        object.__setattr__(self, "cohort_id", _text(self.cohort_id, "cohort_id"))
        object.__setattr__(self, "market", market)
        object.__setattr__(self, "marketplace", marketplace)
        object.__setattr__(self, "query", query)
        object.__setattr__(self, "category", category)
        for name in ("product_use", "category_form_factor", "condition", "locale", "result_surface", "artifact_reference", "operator_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "window_started_at", started)
        object.__setattr__(self, "window_ended_at", ended)
        object.__setattr__(self, "artifact_sha256", sha.lower())
        object.__setattr__(self, "cards", cards)
        for name in ("collector_name", "collector_version", "source_schema_version"):
            object.__setattr__(self, name, _optional(getattr(self, name), name))

    @property
    def included_cards(self) -> tuple[CompetitionV2Card, ...]:
        return tuple(card for card in self.cards if card.included)

    @property
    def sponsored_cards(self) -> tuple[CompetitionV2Card, ...]:
        return tuple(card for card in self.cards if card.placement is ResultPlacement.SPONSORED)

    def listing_reference(self, card: CompetitionV2Card) -> str:
        return card.marketplace_item_id or f"{self.artifact_reference}#result:{card.result_ordinal}"


@dataclass(frozen=True, slots=True)
class CompetitionV2CoreMetrics:
    comparable_listing_count: int
    median_price: Decimal | None
    price_spread: Decimal | None
    currency: str | None
    price_unit: str | None
    sponsored_listing_count: int


@dataclass(frozen=True, slots=True)
class CoupangRocketSignal:
    observable_listing_count: int
    explicit_label_counts: Mapping[CoupangRocketLabelState, int | None]
    explicit_label_shares: Mapping[CoupangRocketLabelState, Decimal | None]
    no_explicit_rocket_label_count: int
    status_not_observed_count: int
    semantics_unsupported_count: int
    extraction_failed_count: int
    schema_version: str = COUPANG_ROCKET_SIGNAL_VERSION
    taxonomy_version: str = COUPANG_ROCKET_TAXONOMY_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != COUPANG_ROCKET_SIGNAL_VERSION or self.taxonomy_version != COUPANG_ROCKET_TAXONOMY_VERSION:
            raise ValueError("unsupported Coupang signal/taxonomy version")
        counts, shares = dict(self.explicit_label_counts), dict(self.explicit_label_shares)
        if set(counts) != set(EXPLICIT_ROCKET_STATES) or set(shares) != set(EXPLICIT_ROCKET_STATES):
            raise ValueError("Coupang signal states are incomplete")
        object.__setattr__(self, "explicit_label_counts", MappingProxyType(counts))
        object.__setattr__(self, "explicit_label_shares", MappingProxyType(shares))


@dataclass(frozen=True, slots=True)
class CompetitionV2Assessment:
    source_cohort_id: str
    subject: AssessmentSubject
    core_metrics: CompetitionV2CoreMetrics
    competition_level: CompetitionLevel | None
    price_pressure: PricePressure | None
    availability: CompetitionV2Availability
    core_confidence: Decimal
    marketplace_signal_coverage: Decimal | None
    marketplace_signal_confidence: Decimal | None
    coupang_signal: CoupangRocketSignal | None
    generated_at: datetime
    schema_version: str = COMPETITION_V2_ASSESSMENT_VERSION
    policy_version: str = COMPETITION_V2_POLICY_VERSION

    def __post_init__(self) -> None:
        assessment_subject_kind(self.subject)
        object.__setattr__(self, "source_cohort_id", _text(self.source_cohort_id, "source_cohort_id"))
        object.__setattr__(self, "availability", CompetitionV2Availability(self.availability))
        object.__setattr__(self, "core_confidence", _confidence(self.core_confidence, "core_confidence"))
        for name in ("marketplace_signal_coverage", "marketplace_signal_confidence"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _confidence(value, name))
        object.__setattr__(self, "generated_at", _aware(self.generated_at, "generated_at"))
        if self.schema_version != COMPETITION_V2_ASSESSMENT_VERSION or self.policy_version != COMPETITION_V2_POLICY_VERSION:
            raise ValueError("unsupported Competition v2 assessment/policy version")
        if self.availability is CompetitionV2Availability.UNAVAILABLE:
            if self.competition_level is not None or self.price_pressure is not None:
                raise ValueError("unavailable assessment cannot expose levels")
        elif self.competition_level is None or self.price_pressure is None:
            raise ValueError("complete core assessment requires levels")


def _competition_level(count: int) -> CompetitionLevel:
    return (CompetitionLevel.VERY_LOW if count <= 5 else CompetitionLevel.LOW if count <= 15 else
            CompetitionLevel.MEDIUM if count <= 30 else CompetitionLevel.HIGH if count <= 60 else CompetitionLevel.VERY_HIGH)


def _price_pressure(ratio: Decimal) -> PricePressure:
    return (PricePressure.VERY_HIGH if ratio <= Decimal("0.05") else PricePressure.HIGH if ratio <= Decimal("0.15") else
            PricePressure.MEDIUM if ratio <= Decimal("0.30") else PricePressure.LOW if ratio <= Decimal("0.60") else PricePressure.VERY_LOW)


def _median(values: tuple[Decimal, ...]) -> Decimal:
    values = tuple(sorted(values)); middle = len(values) // 2
    return values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / Decimal("2")


def analyze_competition_v2(cohort: CompetitionV2Cohort, *, generated_at: datetime) -> CompetitionV2Assessment:
    generated_at = _aware(generated_at, "generated_at")
    included, count = cohort.included_cards, len(cohort.included_cards)
    currencies, units = {c.currency for c in included}, {c.price_unit for c in included}
    price_complete = count > 0 and all(c.displayed_price is not None and c.currency and c.price_unit for c in included) and len(currencies) == 1 and len(units) == 1
    median_price = price_spread = None
    if price_complete:
        prices = tuple(c.displayed_price for c in included if c.displayed_price is not None)
        median_price, price_spread = _median(prices), max(prices) - min(prices)
        if median_price == 0 and price_spread != 0:
            price_complete, median_price, price_spread = False, None, None
    core_complete = count > 0 and price_complete
    core = CompetitionV2CoreMetrics(count, median_price, price_spread,
        next(iter(currencies)) if price_complete else None, next(iter(units)) if price_complete else None, len(cohort.sponsored_cards))
    core_confidence = min(min(c.comparability_confidence for c in cohort.cards), min(c.price_confidence for c in included)) if core_complete else Decimal("0")
    signal_cards = tuple(c for c in included if c.rocket_outcome is not None)
    signal = None; coverage = None; signal_confidence = None
    if cohort.marketplace == "coupang" and signal_cards:
        observable = tuple(c for c in included if c.rocket_outcome is RocketObservationOutcome.OBSERVED)
        coverage = Decimal(len(observable)) / Decimal(count) if count else Decimal("0")
        if observable:
            signal_confidence = min(c.rocket_label_confidence for c in observable if c.rocket_label_confidence is not None) * coverage
        complete_signal = len(observable) == count
        counts, shares = {}, {}
        for state in EXPLICIT_ROCKET_STATES:
            observed_count = sum(state in c.normalized_rocket_states for c in observable)
            counts[state] = observed_count if observed_count or complete_signal else None
            shares[state] = Decimal(observed_count) / Decimal(len(observable)) if observable and counts[state] is not None else None
        signal = CoupangRocketSignal(len(observable), counts, shares,
            sum(CoupangRocketLabelState.NO_EXPLICIT_ROCKET_LABEL in c.normalized_rocket_states for c in observable),
            sum(c.rocket_outcome is RocketObservationOutcome.STATUS_NOT_OBSERVED for c in included),
            sum(c.rocket_outcome is RocketObservationOutcome.SEMANTICS_UNSUPPORTED for c in included),
            sum(c.rocket_outcome is RocketObservationOutcome.EXTRACTION_FAILED for c in included))
    if not core_complete:
        availability, level, pressure = CompetitionV2Availability.UNAVAILABLE, None, None
    else:
        level = _competition_level(count)
        pressure = _price_pressure(Decimal("0") if median_price == 0 else price_spread / median_price)
        availability = (CompetitionV2Availability.COMPLETE_CORE_ONLY if signal is None or signal.observable_listing_count == 0 else
            CompetitionV2Availability.COMPLETE_WITH_MARKETPLACE_SIGNAL if signal.observable_listing_count == count else
            CompetitionV2Availability.COMPLETE_CORE_WITH_PARTIAL_MARKETPLACE_SIGNAL)
    return CompetitionV2Assessment(cohort.cohort_id, cohort.subject, core, level, pressure, availability,
        core_confidence, coverage, signal_confidence, signal, generated_at)


def subject_to_data(subject: AssessmentSubject) -> dict[str, object]:
    if is_new_to_market_target_subject(subject):
        return {"kind": "new_to_market_domestic_selling_target", "domestic_selling_target_id": subject.domestic_selling_target_id}
    return {"kind": "market_observation", "scope": subject.scope.value, "market": subject.market,
        "marketplace": subject.marketplace, "canonical_product_id": subject.canonical_product_id,
        "marketplace_item_id": subject.marketplace_item_id, "normalized_query": subject.normalized_query,
        "category": subject.category, "variant_identity": subject.variant_identity, "condition": subject.condition,
        "window_started_at": subject.window_started_at.isoformat(), "window_ended_at": subject.window_ended_at.isoformat()}


def cohort_to_data(cohort: CompetitionV2Cohort) -> dict[str, object]:
    return {"cohort_id": cohort.cohort_id, "subject": subject_to_data(cohort.subject), "market": cohort.market,
        "marketplace": cohort.marketplace, "query": cohort.query, "category": cohort.category, "product_use": cohort.product_use,
        "category_form_factor": cohort.category_form_factor, "condition": cohort.condition, "locale": cohort.locale,
        "result_surface": cohort.result_surface, "window_started_at": cohort.window_started_at.isoformat(),
        "window_ended_at": cohort.window_ended_at.isoformat(), "artifact_reference": cohort.artifact_reference,
        "artifact_sha256": cohort.artifact_sha256, "bound_start": cohort.bound_start, "bound_end": cohort.bound_end,
        "operator_id": cohort.operator_id, "cohort_policy_version": cohort.cohort_policy_version,
        "observation_schema_version": cohort.observation_schema_version, "collector_name": cohort.collector_name,
        "collector_version": cohort.collector_version, "source_schema_version": cohort.source_schema_version,
        "cards": [{"result_ordinal": c.result_ordinal, "placement": c.placement.value, "included": c.included,
            "is_comparable": c.is_comparable, "exclusion_reason": c.exclusion_reason,
            "marketplace_item_id": c.marketplace_item_id, "observation_reference": cohort.listing_reference(c),
            "raw_title": c.raw_title, "displayed_price": None if c.displayed_price is None else str(c.displayed_price),
            "currency": c.currency, "price_unit": c.price_unit, "raw_rocket_labels": list(c.raw_rocket_labels),
            "normalized_rocket_states": sorted(v.value for v in c.normalized_rocket_states),
            "delivery_promise_text": c.delivery_promise_text, "rocket_outcome": None if c.rocket_outcome is None else c.rocket_outcome.value,
            "comparability_confidence": str(c.comparability_confidence), "price_confidence": str(c.price_confidence),
            "rocket_label_confidence": None if c.rocket_label_confidence is None else str(c.rocket_label_confidence),
            "visible_seller_text": c.visible_seller_text, "visible_variant_count": c.visible_variant_count,
            "raw_payload_reference": c.raw_payload_reference, "badge_color": c.badge_color, "badge_icon": c.badge_icon} for c in cohort.cards]}


def signal_to_data(signal: CoupangRocketSignal | None):
    if signal is None:
        return None
    return {"observable_listing_count": signal.observable_listing_count,
        "explicit_label_counts": {s.value: signal.explicit_label_counts[s] for s in EXPLICIT_ROCKET_STATES},
        "explicit_label_shares": {s.value: None if signal.explicit_label_shares[s] is None else str(signal.explicit_label_shares[s]) for s in EXPLICIT_ROCKET_STATES},
        "no_explicit_rocket_label_count": signal.no_explicit_rocket_label_count,
        "status_not_observed_count": signal.status_not_observed_count,
        "semantics_unsupported_count": signal.semantics_unsupported_count,
        "extraction_failed_count": signal.extraction_failed_count,
        "schema_version": signal.schema_version, "taxonomy_version": signal.taxonomy_version}


def assessment_to_data(a: CompetitionV2Assessment) -> dict[str, object]:
    c = a.core_metrics
    return {"source_cohort_id": a.source_cohort_id, "subject": subject_to_data(a.subject),
        "core_metrics": {"comparable_listing_count": c.comparable_listing_count,
            "median_price": None if c.median_price is None else str(c.median_price),
            "price_spread": None if c.price_spread is None else str(c.price_spread), "currency": c.currency,
            "price_unit": c.price_unit, "sponsored_listing_count": c.sponsored_listing_count},
        "competition_level": None if a.competition_level is None else a.competition_level.value,
        "price_pressure": None if a.price_pressure is None else a.price_pressure.value, "availability": a.availability.value,
        "core_confidence": str(a.core_confidence),
        "marketplace_signal_coverage": None if a.marketplace_signal_coverage is None else str(a.marketplace_signal_coverage),
        "marketplace_signal_confidence": None if a.marketplace_signal_confidence is None else str(a.marketplace_signal_confidence),
        "coupang_signal": signal_to_data(a.coupang_signal), "generated_at": a.generated_at.isoformat(),
        "schema_version": a.schema_version, "policy_version": a.policy_version}
