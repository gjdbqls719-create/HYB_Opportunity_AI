from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
import re

from app.domain.market_intelligence.assessment_subject import (
    AssessmentSubject,
    assessment_subject_kind,
    is_new_to_market_target_subject,
)
from app.domain.market_intelligence.competition_v2 import subject_to_data


DEMAND_V2_POLICY_VERSION = "demand-policy-v2"
DEMAND_V2_OBSERVATION_VERSION = "demand-observation-v2"
DEMAND_V2_ASSESSMENT_VERSION = "demand-assessment-v2"
DEMAND_COMPARABLE_COHORT_VERSION = "demand-comparable-cohort-v1"
DEMAND_PROVIDER_EVIDENCE_VERSION = "demand-provider-evidence-v1"
DEMAND_ARTIFACT_REFERENCE_VERSION = "demand-artifact-reference-v1"

_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


class DemandEvidenceOutcome(StrEnum):
    OBSERVED_VALUE = "observed_value"
    OBSERVED_ZERO = "observed_zero"
    NOT_OBSERVED = "not_observed"
    SEMANTICS_UNSUPPORTED = "semantics_unsupported"
    EXTRACTION_FAILED = "extraction_failed"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    NOT_APPLICABLE = "not_applicable"
    TARGET_LISTING_ABSENT = "target_listing_absent"


class ProviderFieldKind(StrEnum):
    QUERY_COUNT = "query_count"


class QueryMatchSemantics(StrEnum):
    EXACT = "exact"
    RELATED = "related"
    BROAD = "broad"
    PROVIDER_SPECIFIC = "provider_specific"


class DemandResultPlacement(StrEnum):
    ORGANIC = "organic"
    SPONSORED = "sponsored"


class DemandFamilyStatus(StrEnum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class DemandV2Availability(StrEnum):
    COMPLETE_CORE = "complete_core"
    PARTIAL_CORE = "partial_core"
    UNAVAILABLE = "unavailable"


class DemandV2Conclusion(StrEnum):
    SUPPORTS_DEEPER_COMMERCIAL_VALIDATION = "supports_deeper_commercial_validation"
    DOES_NOT_SUPPORT_DEEPER_COMMERCIAL_VALIDATION = "does_not_support_deeper_commercial_validation"
    INCONCLUSIVE = "inconclusive"


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


def _observed(outcome: DemandEvidenceOutcome) -> bool:
    return outcome in {
        DemandEvidenceOutcome.OBSERVED_VALUE,
        DemandEvidenceOutcome.OBSERVED_ZERO,
    }


def _validate_count(value: int | None, outcome: DemandEvidenceOutcome, name: str) -> None:
    if _observed(outcome):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer for observed evidence")
        if outcome is DemandEvidenceOutcome.OBSERVED_VALUE and value == 0:
            raise ValueError(f"{name} OBSERVED_VALUE must be greater than zero")
        if outcome is DemandEvidenceOutcome.OBSERVED_ZERO and value != 0:
            raise ValueError(f"{name} OBSERVED_ZERO requires zero")
    elif value is not None:
        raise ValueError(f"{name} non-value outcome requires no value")


def _evidence_reason(outcome: DemandEvidenceOutcome, reason: str | None) -> str | None:
    reason = _optional(reason, "reason")
    if _observed(outcome) and reason is not None:
        raise ValueError("observed evidence must not have a non-value reason")
    if not _observed(outcome) and reason is None:
        raise ValueError("non-value evidence requires a reason")
    return reason


@dataclass(frozen=True, slots=True)
class DemandArtifactReference:
    reference: str
    sha256: str
    schema_version: str = DEMAND_ARTIFACT_REFERENCE_VERSION

    def __post_init__(self) -> None:
        sha = _text(self.sha256, "sha256")
        if not _SHA256.fullmatch(sha):
            raise ValueError("sha256 must be 64 hexadecimal characters")
        object.__setattr__(self, "reference", _text(self.reference, "reference"))
        object.__setattr__(self, "sha256", sha.lower())
        if self.schema_version != DEMAND_ARTIFACT_REFERENCE_VERSION:
            raise ValueError("unsupported Demand artifact reference version")


@dataclass(frozen=True, slots=True)
class MarketIntentEvidence:
    provider: str
    provider_field_name: str
    provider_schema_version: str
    provider_field_kind: ProviderFieldKind
    query: str
    market: str
    geography: str
    locale: str
    match_semantics: QueryMatchSemantics
    period_started_at: datetime
    period_ended_at: datetime
    unit: str
    value: int | None
    source: str
    reference: str
    artifact: DemandArtifactReference
    collection_method: str
    observed_at: datetime
    outcome: DemandEvidenceOutcome
    confidence: Decimal
    reason: str | None = None
    collector_name: str | None = None
    collector_version: str | None = None
    category: str | None = None
    device_scope: str | None = None
    result_surface: str | None = None
    schema_version: str = DEMAND_PROVIDER_EVIDENCE_VERSION

    def __post_init__(self) -> None:
        outcome = DemandEvidenceOutcome(self.outcome)
        kind = ProviderFieldKind(self.provider_field_kind)
        if kind is not ProviderFieldKind.QUERY_COUNT:
            raise ValueError("Market Intent requires an explicit provider query-count field")
        started = _aware(self.period_started_at, "period_started_at")
        ended = _aware(self.period_ended_at, "period_ended_at")
        observed = _aware(self.observed_at, "observed_at")
        if ended < started:
            raise ValueError("period_ended_at cannot precede period_started_at")
        if observed < started:
            raise ValueError("observed_at cannot precede the observation period")
        _validate_count(self.value, outcome, "market intent value")
        if not isinstance(self.artifact, DemandArtifactReference):
            raise TypeError("artifact must be DemandArtifactReference")
        for name in (
            "provider", "provider_field_name", "provider_schema_version", "query",
            "geography", "locale", "unit", "source", "reference", "collection_method",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "market", _text(self.market, "market").upper())
        object.__setattr__(self, "provider_field_kind", kind)
        object.__setattr__(self, "match_semantics", QueryMatchSemantics(self.match_semantics))
        object.__setattr__(self, "period_started_at", started)
        object.__setattr__(self, "period_ended_at", ended)
        object.__setattr__(self, "observed_at", observed)
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "confidence", _confidence(self.confidence, "confidence"))
        object.__setattr__(self, "reason", _evidence_reason(outcome, self.reason))
        for name in ("collector_name", "collector_version", "category", "device_scope", "result_surface"):
            object.__setattr__(self, name, _optional(getattr(self, name), name))
        if self.schema_version != DEMAND_PROVIDER_EVIDENCE_VERSION:
            raise ValueError("unsupported Demand provider evidence version")


@dataclass(frozen=True, slots=True)
class DemandComparableCard:
    result_ordinal: int
    placement: DemandResultPlacement
    included: bool
    is_comparable: bool
    exclusion_reason: str | None
    marketplace_item_id: str | None
    observation_reference: str
    raw_title: str
    visible_variant_count: int = 1

    def __post_init__(self) -> None:
        if isinstance(self.result_ordinal, bool) or not isinstance(self.result_ordinal, int) or self.result_ordinal < 1:
            raise ValueError("result_ordinal must be a positive integer")
        placement = DemandResultPlacement(self.placement)
        reason = _optional(self.exclusion_reason, "exclusion_reason")
        if not isinstance(self.included, bool) or not isinstance(self.is_comparable, bool):
            raise TypeError("included and is_comparable must be bool")
        if self.included and (placement is not DemandResultPlacement.ORGANIC or not self.is_comparable or reason is not None):
            raise ValueError("only comparable organic cards without exclusion reason may be included")
        if not self.included and reason is None:
            raise ValueError("excluded card requires exclusion_reason")
        if placement is DemandResultPlacement.SPONSORED and reason != "sponsored":
            raise ValueError("sponsored card requires sponsored exclusion_reason")
        if isinstance(self.visible_variant_count, bool) or not isinstance(self.visible_variant_count, int) or self.visible_variant_count < 1:
            raise ValueError("visible_variant_count must be a positive integer")
        object.__setattr__(self, "placement", placement)
        object.__setattr__(self, "exclusion_reason", reason)
        object.__setattr__(self, "marketplace_item_id", _optional(self.marketplace_item_id, "marketplace_item_id"))
        object.__setattr__(self, "observation_reference", _text(self.observation_reference, "observation_reference"))
        object.__setattr__(self, "raw_title", _text(self.raw_title, "raw_title"))


@dataclass(frozen=True, slots=True)
class CompetitionCohortReference:
    competition_observation_id: str
    observation_identity_kind: str
    observation_identity_version: str
    cohort_id: str
    authority_fingerprint: str
    observation_schema_version: str
    cohort_policy_version: str
    artifact_reference: str
    artifact_sha256: str

    def __post_init__(self) -> None:
        for name in (
            "competition_observation_id", "observation_identity_kind",
            "observation_identity_version", "cohort_id", "observation_schema_version",
            "cohort_policy_version", "artifact_reference",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("authority_fingerprint", "artifact_sha256"):
            value = _text(getattr(self, name), name)
            if not _SHA256.fullmatch(value):
                raise ValueError(f"{name} must be 64 hexadecimal characters")
            object.__setattr__(self, name, value.lower())


@dataclass(frozen=True, slots=True)
class DemandComparableCohortManifest:
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
    artifact: DemandArtifactReference
    bound_start: int
    bound_end: int
    operator_id: str
    cards: tuple[DemandComparableCard, ...]
    source_competition_cohort: CompetitionCohortReference | None = None
    schema_version: str = DEMAND_COMPARABLE_COHORT_VERSION

    def __post_init__(self) -> None:
        assessment_subject_kind(self.subject)
        market = _text(self.market, "market").upper()
        marketplace = _text(self.marketplace, "marketplace").lower()
        if market != self.subject.market.upper():
            raise ValueError("cohort market must match assessment subject")
        if not is_new_to_market_target_subject(self.subject) and marketplace != self.subject.marketplace:
            raise ValueError("cohort marketplace must match assessment subject")
        query, category = _optional(self.query, "query"), _optional(self.category, "category")
        if query is None and category is None:
            raise ValueError("cohort requires query or category")
        started = _aware(self.window_started_at, "window_started_at")
        ended = _aware(self.window_ended_at, "window_ended_at")
        if ended < started:
            raise ValueError("window_ended_at cannot precede window_started_at")
        if any(isinstance(v, bool) or not isinstance(v, int) for v in (self.bound_start, self.bound_end)) or self.bound_start < 1 or self.bound_end < self.bound_start:
            raise ValueError("finite bounds are invalid")
        cards = tuple(self.cards)
        if tuple(card.result_ordinal for card in cards) != tuple(range(self.bound_start, self.bound_end + 1)):
            raise ValueError("card ordering must exactly reconcile to finite bounds")
        seen: set[str] = set()
        for card in cards:
            if not isinstance(card, DemandComparableCard):
                raise TypeError("cards must contain DemandComparableCard")
            if card.marketplace_item_id in seen and (card.included or card.exclusion_reason != "duplicate_marketplace_item_id"):
                raise ValueError("later duplicate item ID must be retained as duplicate exclusion")
            if card.marketplace_item_id is not None:
                seen.add(card.marketplace_item_id)
        if not isinstance(self.artifact, DemandArtifactReference):
            raise TypeError("artifact must be DemandArtifactReference")
        if self.source_competition_cohort is not None and not isinstance(self.source_competition_cohort, CompetitionCohortReference):
            raise TypeError("source_competition_cohort must be CompetitionCohortReference or None")
        object.__setattr__(self, "market", market)
        object.__setattr__(self, "marketplace", marketplace)
        object.__setattr__(self, "query", query)
        object.__setattr__(self, "category", category)
        for name in ("product_use", "category_form_factor", "condition", "locale", "result_surface", "operator_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "window_started_at", started)
        object.__setattr__(self, "window_ended_at", ended)
        object.__setattr__(self, "cards", cards)
        if self.schema_version != DEMAND_COMPARABLE_COHORT_VERSION:
            raise ValueError("unsupported Demand comparable cohort version")

    @property
    def included_cards(self) -> tuple[DemandComparableCard, ...]:
        return tuple(card for card in self.cards if card.included)


@dataclass(frozen=True, slots=True)
class DemandComparableCohort:
    cohort_id: str
    manifest: DemandComparableCohortManifest

    def __post_init__(self) -> None:
        object.__setattr__(self, "cohort_id", _text(self.cohort_id, "cohort_id"))
        if not isinstance(self.manifest, DemandComparableCohortManifest):
            raise TypeError("manifest must be DemandComparableCohortManifest")


@dataclass(frozen=True, slots=True)
class ListingReviewEvidence:
    result_ordinal: int
    listing_reference: str
    value: int | None
    outcome: DemandEvidenceOutcome
    confidence: Decimal
    source: str
    reference: str
    artifact: DemandArtifactReference
    collection_method: str
    observed_at: datetime
    reason: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.result_ordinal, bool) or not isinstance(self.result_ordinal, int) or self.result_ordinal < 1:
            raise ValueError("result_ordinal must be a positive integer")
        outcome = DemandEvidenceOutcome(self.outcome)
        _validate_count(self.value, outcome, "review count")
        if not isinstance(self.artifact, DemandArtifactReference):
            raise TypeError("artifact must be DemandArtifactReference")
        object.__setattr__(self, "listing_reference", _text(self.listing_reference, "listing_reference"))
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "confidence", _confidence(self.confidence, "confidence"))
        object.__setattr__(self, "source", _text(self.source, "source"))
        object.__setattr__(self, "reference", _text(self.reference, "reference"))
        object.__setattr__(self, "collection_method", _text(self.collection_method, "collection_method"))
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        object.__setattr__(self, "reason", _evidence_reason(outcome, self.reason))


@dataclass(frozen=True, slots=True)
class ListingRatingEvidence:
    result_ordinal: int
    listing_reference: str
    value: Decimal | None
    scale_min: Decimal
    scale_max: Decimal
    outcome: DemandEvidenceOutcome
    confidence: Decimal
    source: str
    reference: str
    artifact: DemandArtifactReference
    collection_method: str
    observed_at: datetime
    reason: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.result_ordinal, bool) or not isinstance(self.result_ordinal, int) or self.result_ordinal < 1:
            raise ValueError("result_ordinal must be a positive integer")
        outcome = DemandEvidenceOutcome(self.outcome)
        for name in ("scale_min", "scale_max"):
            value = getattr(self, name)
            if not isinstance(value, Decimal) or not value.is_finite():
                raise ValueError(f"{name} must be finite Decimal")
        if self.scale_max <= self.scale_min:
            raise ValueError("rating scale maximum must exceed minimum")
        if _observed(outcome):
            if not isinstance(self.value, Decimal) or not self.value.is_finite() or not self.scale_min <= self.value <= self.scale_max:
                raise ValueError("observed rating must be a finite Decimal within its scale")
            if outcome is DemandEvidenceOutcome.OBSERVED_VALUE and self.value == 0:
                raise ValueError("rating OBSERVED_VALUE must be non-zero")
            if outcome is DemandEvidenceOutcome.OBSERVED_ZERO and self.value != 0:
                raise ValueError("rating OBSERVED_ZERO requires zero")
        elif self.value is not None:
            raise ValueError("non-value rating outcome requires no value")
        if not isinstance(self.artifact, DemandArtifactReference):
            raise TypeError("artifact must be DemandArtifactReference")
        object.__setattr__(self, "listing_reference", _text(self.listing_reference, "listing_reference"))
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "confidence", _confidence(self.confidence, "confidence"))
        object.__setattr__(self, "source", _text(self.source, "source"))
        object.__setattr__(self, "reference", _text(self.reference, "reference"))
        object.__setattr__(self, "collection_method", _text(self.collection_method, "collection_method"))
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        object.__setattr__(self, "reason", _evidence_reason(outcome, self.reason))


@dataclass(frozen=True, slots=True)
class ProviderSignalEvidence:
    signal_name: str
    provider: str
    provider_field_name: str
    provider_schema_version: str
    population: str
    result_surface: str
    query: str | None
    category: str | None
    geography: str
    locale: str
    period_started_at: datetime
    period_ended_at: datetime
    directionality: str | None
    tie_semantics: str | None
    value: str | None
    unit: str
    outcome: DemandEvidenceOutcome
    confidence: Decimal
    source: str
    reference: str
    artifact: DemandArtifactReference
    collection_method: str
    observed_at: datetime
    reason: str | None = None
    collection_method_version: str | None = None

    def __post_init__(self) -> None:
        outcome = DemandEvidenceOutcome(self.outcome)
        if _observed(outcome):
            object.__setattr__(self, "value", _text(self.value, "value"))
        elif self.value is not None:
            raise ValueError("non-value provider signal outcome requires no value")
        started = _aware(self.period_started_at, "period_started_at")
        ended = _aware(self.period_ended_at, "period_ended_at")
        if ended < started:
            raise ValueError("period_ended_at cannot precede period_started_at")
        for name in (
            "signal_name", "provider", "provider_field_name", "provider_schema_version",
            "population", "result_surface", "geography", "locale", "unit", "source",
            "reference", "collection_method",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        for name in ("query", "category", "directionality", "tie_semantics", "collection_method_version"):
            object.__setattr__(self, name, _optional(getattr(self, name), name))
        if self.query is None and self.category is None:
            raise ValueError("provider signal requires query or category scope")
        if not isinstance(self.artifact, DemandArtifactReference):
            raise TypeError("artifact must be DemandArtifactReference")
        object.__setattr__(self, "outcome", outcome)
        object.__setattr__(self, "confidence", _confidence(self.confidence, "confidence"))
        object.__setattr__(self, "period_started_at", started)
        object.__setattr__(self, "period_ended_at", ended)
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        object.__setattr__(self, "reason", _evidence_reason(outcome, self.reason))


@dataclass(frozen=True, slots=True)
class DemandV2Observation:
    observation_id: str
    subject: AssessmentSubject
    market_intent: MarketIntentEvidence
    comparable_cohort: DemandComparableCohort
    reviews: tuple[ListingReviewEvidence, ...]
    ratings: tuple[ListingRatingEvidence, ...]
    provider_signals: tuple[ProviderSignalEvidence, ...]
    target_traction_outcome: DemandEvidenceOutcome
    observed_at: datetime
    schema_version: str = DEMAND_V2_OBSERVATION_VERSION

    def __post_init__(self) -> None:
        assessment_subject_kind(self.subject)
        if not isinstance(self.market_intent, MarketIntentEvidence):
            raise TypeError("market_intent must be MarketIntentEvidence")
        if not isinstance(self.comparable_cohort, DemandComparableCohort):
            raise TypeError("comparable_cohort must be DemandComparableCohort")
        if self.comparable_cohort.manifest.subject != self.subject:
            raise ValueError("comparable cohort subject must match observation subject")
        if self.market_intent.market != self.subject.market.upper():
            raise ValueError("Market Intent market must match observation subject")
        reviews = tuple(self.reviews)
        ratings = tuple(self.ratings)
        signals = tuple(self.provider_signals)
        included = {card.result_ordinal: card for card in self.comparable_cohort.manifest.included_cards}
        if set(included) != {item.result_ordinal for item in reviews} or len(reviews) != len(included):
            raise ValueError("reviews must contain exactly one fact for every included card")
        for item in (*reviews, *ratings):
            card = included.get(item.result_ordinal)
            if card is None or item.listing_reference != card.observation_reference:
                raise ValueError("listing evidence must match an included cohort card")
        if len({item.result_ordinal for item in ratings}) != len(ratings):
            raise ValueError("ratings cannot duplicate a cohort card")
        outcome = DemandEvidenceOutcome(self.target_traction_outcome)
        expected = (
            DemandEvidenceOutcome.TARGET_LISTING_ABSENT
            if is_new_to_market_target_subject(self.subject)
            else DemandEvidenceOutcome.NOT_APPLICABLE
        )
        if outcome is not expected:
            raise ValueError("target traction outcome must reflect the assessment subject")
        object.__setattr__(self, "observation_id", _text(self.observation_id, "observation_id"))
        object.__setattr__(self, "reviews", reviews)
        object.__setattr__(self, "ratings", ratings)
        object.__setattr__(self, "provider_signals", signals)
        object.__setattr__(self, "target_traction_outcome", outcome)
        object.__setattr__(self, "observed_at", _aware(self.observed_at, "observed_at"))
        if self.schema_version != DEMAND_V2_OBSERVATION_VERSION:
            raise ValueError("unsupported Demand v2 observation version")


@dataclass(frozen=True, slots=True)
class ReviewAggregates:
    comparable_listing_count: int
    review_observable_listing_count: int
    review_coverage: Decimal
    review_counts_sorted: tuple[int, ...]
    median_review_count: Decimal | None
    engaged_listing_count: int
    engaged_listing_share: Decimal | None


@dataclass(frozen=True, slots=True)
class RatingAggregates:
    rating_observable_listing_count: int
    rating_coverage: Decimal
    ratings_sorted: tuple[Decimal, ...]
    median_rating: Decimal
    scale_min: Decimal
    scale_max: Decimal
    confidence: Decimal


@dataclass(frozen=True, slots=True)
class DemandV2Assessment:
    assessment_id: str
    source_observation_id: str
    subject: AssessmentSubject
    market_intent_status: DemandFamilyStatus
    comparable_response_status: DemandFamilyStatus
    market_intent_confidence: Decimal | None
    comparable_response_confidence: Decimal | None
    review_aggregates: ReviewAggregates
    rating_aggregates: RatingAggregates | None
    availability: DemandV2Availability
    conclusion: DemandV2Conclusion
    reasons: tuple[str, ...]
    summary: str
    generated_at: datetime
    schema_version: str = DEMAND_V2_ASSESSMENT_VERSION
    policy_version: str = DEMAND_V2_POLICY_VERSION

    def __post_init__(self) -> None:
        assessment_subject_kind(self.subject)
        for name in ("assessment_id", "source_observation_id", "summary"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(self, "market_intent_status", DemandFamilyStatus(self.market_intent_status))
        object.__setattr__(self, "comparable_response_status", DemandFamilyStatus(self.comparable_response_status))
        object.__setattr__(self, "availability", DemandV2Availability(self.availability))
        object.__setattr__(self, "conclusion", DemandV2Conclusion(self.conclusion))
        for name in ("market_intent_confidence", "comparable_response_confidence"):
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _confidence(value, name))
        object.__setattr__(self, "reasons", tuple(_text(value, "reason") for value in self.reasons))
        object.__setattr__(self, "generated_at", _aware(self.generated_at, "generated_at"))
        if self.schema_version != DEMAND_V2_ASSESSMENT_VERSION or self.policy_version != DEMAND_V2_POLICY_VERSION:
            raise ValueError("unsupported Demand v2 assessment/policy version")


def _median(values: tuple[int, ...] | tuple[Decimal, ...]) -> Decimal:
    ordered = tuple(sorted(values))
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return Decimal(ordered[middle])
    return (Decimal(ordered[middle - 1]) + Decimal(ordered[middle])) / Decimal("2")


def analyze_demand_v2(
    observation: DemandV2Observation,
    *,
    assessment_id: str,
    generated_at: datetime,
) -> DemandV2Assessment:
    if not isinstance(observation, DemandV2Observation):
        raise TypeError("observation must be DemandV2Observation")
    generated_at = _aware(generated_at, "generated_at")
    intent_complete = _observed(observation.market_intent.outcome)
    intent_status = DemandFamilyStatus.COMPLETE if intent_complete else DemandFamilyStatus.UNAVAILABLE
    intent_confidence = observation.market_intent.confidence if intent_complete else None

    included_count = len(observation.comparable_cohort.manifest.included_cards)
    observable = tuple(item for item in observation.reviews if _observed(item.outcome))
    observable_count = len(observable)
    coverage = Decimal(observable_count) / Decimal(included_count) if included_count else Decimal("0")
    counts = tuple(sorted(item.value for item in observable if item.value is not None))
    median_count = _median(counts) if counts else None
    engaged_count = sum(value > 0 for value in counts)
    engaged_share = Decimal(engaged_count) / Decimal(observable_count) if observable_count else None
    review_aggregates = ReviewAggregates(
        included_count, observable_count, coverage, counts, median_count,
        engaged_count, engaged_share,
    )
    comparable_status = (
        DemandFamilyStatus.COMPLETE if included_count > 0 and observable_count == included_count
        else DemandFamilyStatus.PARTIAL if observable_count > 0
        else DemandFamilyStatus.UNAVAILABLE
    )
    comparable_confidence = (
        min(item.confidence for item in observable) * coverage if observable else None
    )

    rating_aggregates = None
    rating_scale_incompatible = False
    reviews_by_ordinal = {item.result_ordinal: item for item in observation.reviews}
    eligible_ratings = tuple(
        item for item in observation.ratings
        if _observed(item.outcome)
        and reviews_by_ordinal[item.result_ordinal].value is not None
        and reviews_by_ordinal[item.result_ordinal].value > 0
    )
    scales = {(item.scale_min, item.scale_max) for item in eligible_ratings}
    if eligible_ratings and len(scales) == 1:
        values = tuple(sorted(item.value for item in eligible_ratings if item.value is not None))
        scale_min, scale_max = next(iter(scales))
        rating_coverage = Decimal(len(values)) / Decimal(included_count)
        rating_aggregates = RatingAggregates(
            len(values), rating_coverage, values, _median(values), scale_min, scale_max,
            min(item.confidence for item in eligible_ratings) * rating_coverage,
        )
    elif len(scales) > 1:
        rating_scale_incompatible = True

    if intent_status is DemandFamilyStatus.COMPLETE and comparable_status is DemandFamilyStatus.COMPLETE:
        availability = DemandV2Availability.COMPLETE_CORE
    elif intent_complete or observable_count > 0:
        availability = DemandV2Availability.PARTIAL_CORE
    else:
        availability = DemandV2Availability.UNAVAILABLE
    if availability is DemandV2Availability.COMPLETE_CORE:
        assert observation.market_intent.value is not None and median_count is not None
        conclusion = (
            DemandV2Conclusion.SUPPORTS_DEEPER_COMMERCIAL_VALIDATION
            if observation.market_intent.value > 0 and median_count > 0
            else DemandV2Conclusion.DOES_NOT_SUPPORT_DEEPER_COMMERCIAL_VALIDATION
        )
    else:
        conclusion = DemandV2Conclusion.INCONCLUSIVE
    reasons: list[str] = []
    if not intent_complete:
        reasons.append("MARKET_INTENT_UNAVAILABLE")
    if comparable_status is DemandFamilyStatus.PARTIAL:
        reasons.append("COMPARABLE_RESPONSE_PARTIAL")
    elif comparable_status is DemandFamilyStatus.UNAVAILABLE:
        reasons.append("COMPARABLE_RESPONSE_UNAVAILABLE")
    if rating_scale_incompatible:
        reasons.append("RATING_SCALE_INCOMPATIBLE")
    summary = (
        f"Demand v2 {availability.value}; Market Intent {intent_status.value}; "
        f"Comparable Market Response {comparable_status.value}; conclusion {conclusion.value}."
    )
    return DemandV2Assessment(
        assessment_id, observation.observation_id, observation.subject, intent_status,
        comparable_status, intent_confidence, comparable_confidence, review_aggregates,
        rating_aggregates, availability, conclusion, tuple(reasons), summary, generated_at,
    )


def artifact_to_data(value: DemandArtifactReference) -> dict[str, object]:
    return {"reference": value.reference, "sha256": value.sha256, "schema_version": value.schema_version}


def market_intent_to_data(value: MarketIntentEvidence) -> dict[str, object]:
    return {
        "provider": value.provider, "provider_field_name": value.provider_field_name,
        "provider_schema_version": value.provider_schema_version,
        "provider_field_kind": value.provider_field_kind.value, "query": value.query,
        "market": value.market, "geography": value.geography, "locale": value.locale,
        "match_semantics": value.match_semantics.value,
        "period_started_at": value.period_started_at.isoformat(),
        "period_ended_at": value.period_ended_at.isoformat(), "unit": value.unit,
        "value": value.value, "source": value.source, "reference": value.reference,
        "artifact": artifact_to_data(value.artifact), "collection_method": value.collection_method,
        "observed_at": value.observed_at.isoformat(), "outcome": value.outcome.value,
        "confidence": str(value.confidence), "reason": value.reason,
        "collector_name": value.collector_name, "collector_version": value.collector_version,
        "category": value.category,
        "device_scope": value.device_scope, "result_surface": value.result_surface,
        "schema_version": value.schema_version,
    }


def competition_reference_to_data(value: CompetitionCohortReference | None):
    if value is None:
        return None
    return {
        "competition_observation_id": value.competition_observation_id,
        "observation_identity_kind": value.observation_identity_kind,
        "observation_identity_version": value.observation_identity_version,
        "cohort_id": value.cohort_id, "authority_fingerprint": value.authority_fingerprint,
        "observation_schema_version": value.observation_schema_version,
        "cohort_policy_version": value.cohort_policy_version,
        "artifact_reference": value.artifact_reference, "artifact_sha256": value.artifact_sha256,
    }


def cohort_manifest_to_data(value: DemandComparableCohortManifest) -> dict[str, object]:
    return {
        "subject": subject_to_data(value.subject), "market": value.market,
        "marketplace": value.marketplace, "query": value.query, "category": value.category,
        "product_use": value.product_use, "category_form_factor": value.category_form_factor,
        "condition": value.condition, "locale": value.locale, "result_surface": value.result_surface,
        "window_started_at": value.window_started_at.isoformat(),
        "window_ended_at": value.window_ended_at.isoformat(), "artifact": artifact_to_data(value.artifact),
        "bound_start": value.bound_start, "bound_end": value.bound_end,
        "operator_id": value.operator_id, "source_competition_cohort": competition_reference_to_data(value.source_competition_cohort),
        "schema_version": value.schema_version,
        "cards": [{"result_ordinal": card.result_ordinal, "placement": card.placement.value,
            "included": card.included, "is_comparable": card.is_comparable,
            "exclusion_reason": card.exclusion_reason, "marketplace_item_id": card.marketplace_item_id,
            "observation_reference": card.observation_reference, "raw_title": card.raw_title,
            "visible_variant_count": card.visible_variant_count} for card in value.cards],
    }


def review_to_data(value: ListingReviewEvidence) -> dict[str, object]:
    return {"result_ordinal": value.result_ordinal, "listing_reference": value.listing_reference,
        "value": value.value, "outcome": value.outcome.value, "confidence": str(value.confidence),
        "source": value.source, "reference": value.reference, "artifact": artifact_to_data(value.artifact),
        "collection_method": value.collection_method, "observed_at": value.observed_at.isoformat(),
        "reason": value.reason}


def rating_to_data(value: ListingRatingEvidence) -> dict[str, object]:
    return {"result_ordinal": value.result_ordinal, "listing_reference": value.listing_reference,
        "value": None if value.value is None else str(value.value), "scale_min": str(value.scale_min),
        "scale_max": str(value.scale_max), "outcome": value.outcome.value,
        "confidence": str(value.confidence), "source": value.source, "reference": value.reference,
        "artifact": artifact_to_data(value.artifact), "collection_method": value.collection_method,
        "observed_at": value.observed_at.isoformat(), "reason": value.reason}


def provider_signal_to_data(value: ProviderSignalEvidence) -> dict[str, object]:
    return {"signal_name": value.signal_name, "provider": value.provider,
        "provider_field_name": value.provider_field_name,
        "provider_schema_version": value.provider_schema_version, "population": value.population,
        "result_surface": value.result_surface, "query": value.query, "category": value.category,
        "geography": value.geography, "locale": value.locale,
        "period_started_at": value.period_started_at.isoformat(),
        "period_ended_at": value.period_ended_at.isoformat(),
        "directionality": value.directionality, "tie_semantics": value.tie_semantics,
        "value": value.value,
        "unit": value.unit, "outcome": value.outcome.value, "confidence": str(value.confidence),
        "source": value.source, "reference": value.reference, "artifact": artifact_to_data(value.artifact),
        "collection_method": value.collection_method,
        "collection_method_version": value.collection_method_version,
        "observed_at": value.observed_at.isoformat(), "reason": value.reason}


def observation_to_data(value: DemandV2Observation) -> dict[str, object]:
    return {"observation_id": value.observation_id, "subject": subject_to_data(value.subject),
        "market_intent": market_intent_to_data(value.market_intent),
        "comparable_cohort": {"cohort_id": value.comparable_cohort.cohort_id,
            "manifest": cohort_manifest_to_data(value.comparable_cohort.manifest)},
        "reviews": [review_to_data(item) for item in value.reviews],
        "ratings": [rating_to_data(item) for item in value.ratings],
        "provider_signals": [provider_signal_to_data(item) for item in value.provider_signals],
        "target_traction_outcome": value.target_traction_outcome.value,
        "observed_at": value.observed_at.isoformat(), "schema_version": value.schema_version}


def assessment_to_data(value: DemandV2Assessment) -> dict[str, object]:
    reviews = value.review_aggregates
    ratings = value.rating_aggregates
    return {"assessment_id": value.assessment_id, "source_observation_id": value.source_observation_id,
        "subject": subject_to_data(value.subject), "market_intent_status": value.market_intent_status.value,
        "comparable_response_status": value.comparable_response_status.value,
        "market_intent_confidence": None if value.market_intent_confidence is None else str(value.market_intent_confidence),
        "comparable_response_confidence": None if value.comparable_response_confidence is None else str(value.comparable_response_confidence),
        "review_aggregates": {"comparable_listing_count": reviews.comparable_listing_count,
            "review_observable_listing_count": reviews.review_observable_listing_count,
            "review_coverage": str(reviews.review_coverage), "review_counts_sorted": list(reviews.review_counts_sorted),
            "median_review_count": None if reviews.median_review_count is None else str(reviews.median_review_count),
            "engaged_listing_count": reviews.engaged_listing_count,
            "engaged_listing_share": None if reviews.engaged_listing_share is None else str(reviews.engaged_listing_share)},
        "rating_aggregates": None if ratings is None else {"rating_observable_listing_count": ratings.rating_observable_listing_count,
            "rating_coverage": str(ratings.rating_coverage), "ratings_sorted": [str(item) for item in ratings.ratings_sorted],
            "median_rating": str(ratings.median_rating), "scale_min": str(ratings.scale_min),
            "scale_max": str(ratings.scale_max), "confidence": str(ratings.confidence)},
        "availability": value.availability.value, "conclusion": value.conclusion.value,
        "reasons": list(value.reasons), "summary": value.summary,
        "generated_at": value.generated_at.isoformat(), "schema_version": value.schema_version,
        "policy_version": value.policy_version}
