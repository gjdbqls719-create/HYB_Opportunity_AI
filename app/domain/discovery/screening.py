"""Versioned semantic contracts for production Discovery screening."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re


_SEMANTIC_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
_REASON_CODE = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text")
    if not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    if value != value.strip():
        raise ValueError(f"{name} must not contain surrounding whitespace")
    return value


def _policy_version(value: str) -> str:
    resolved = _required_text(value, "policy_version")
    if _SEMANTIC_VERSION.fullmatch(resolved) is None:
        raise ValueError("policy_version must use MAJOR.MINOR.PATCH")
    return resolved


def _ordered_text(values: tuple[str, ...], name: str) -> tuple[str, ...]:
    if not isinstance(values, tuple):
        raise TypeError(f"{name} must be a tuple")
    resolved = tuple(_required_text(value, name) for value in values)
    if not resolved:
        raise ValueError(f"{name} must not be empty")
    if len(set(resolved)) != len(resolved):
        raise ValueError(f"{name} must not contain duplicates")
    return resolved


@dataclass(frozen=True, slots=True)
class ScreeningScorePolicyDescriptor:
    """Identity and ordered semantics of the current screening score policy."""

    policy_name: str
    policy_version: str
    algorithm_id: str
    description: str
    ordered_rule_ids: tuple[str, ...]
    policy_assumption_inputs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("policy_name", "algorithm_id", "description"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        object.__setattr__(self, "policy_version", _policy_version(self.policy_version))
        for name in ("ordered_rule_ids", "policy_assumption_inputs"):
            object.__setattr__(self, name, _ordered_text(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class RecommendationPolicyDescriptor:
    """Identity and ordered semantics of recommendation construction."""

    policy_name: str
    policy_version: str
    algorithm_id: str
    description: str
    ordered_rule_ids: tuple[str, ...]
    reason_code_namespace: str

    def __post_init__(self) -> None:
        for name in (
            "policy_name",
            "algorithm_id",
            "description",
            "reason_code_namespace",
        ):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        object.__setattr__(self, "policy_version", _policy_version(self.policy_version))
        object.__setattr__(
            self,
            "ordered_rule_ids",
            _ordered_text(self.ordered_rule_ids, "ordered_rule_ids"),
        )


@dataclass(frozen=True, slots=True)
class ProductionSafetyPolicyDescriptor:
    """Identity and ordered semantics of the post-score production Safety Gate."""

    policy_name: str
    policy_version: str
    algorithm_id: str
    description: str
    ordered_rule_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in ("policy_name", "algorithm_id", "description"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        object.__setattr__(self, "policy_version", _policy_version(self.policy_version))
        object.__setattr__(
            self,
            "ordered_rule_ids",
            _ordered_text(self.ordered_rule_ids, "ordered_rule_ids"),
        )


@dataclass(frozen=True, slots=True)
class ScreeningRankingPolicyDescriptor:
    """Identity and exact key/tie semantics of production screening ranking."""

    policy_name: str
    policy_version: str
    algorithm_id: str
    description: str
    ordered_sort_keys: tuple[str, ...]
    equal_key_tie_behavior: str

    def __post_init__(self) -> None:
        for name in (
            "policy_name",
            "algorithm_id",
            "description",
            "equal_key_tie_behavior",
        ):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        object.__setattr__(self, "policy_version", _policy_version(self.policy_version))
        object.__setattr__(
            self,
            "ordered_sort_keys",
            _ordered_text(self.ordered_sort_keys, "ordered_sort_keys"),
        )


@dataclass(frozen=True, slots=True)
class ScreeningPolicyDescriptors:
    """The four exact policies used by one production screening result."""

    score: ScreeningScorePolicyDescriptor
    recommendation: RecommendationPolicyDescriptor
    production_safety: ProductionSafetyPolicyDescriptor
    ranking: ScreeningRankingPolicyDescriptor

    def __post_init__(self) -> None:
        expected = (
            ("score", ScreeningScorePolicyDescriptor),
            ("recommendation", RecommendationPolicyDescriptor),
            ("production_safety", ProductionSafetyPolicyDescriptor),
            ("ranking", ScreeningRankingPolicyDescriptor),
        )
        for name, value_type in expected:
            if not isinstance(getattr(self, name), value_type):
                raise TypeError(f"{name} must be {value_type.__name__}")


class ScreeningReasonCategory(str, Enum):
    PROFITABILITY = "PROFITABILITY"
    CONFIDENCE = "CONFIDENCE"
    PRICE_TREND = "PRICE_TREND"
    COMPETITION = "COMPETITION"
    RISK = "RISK"
    MARKET_ADJUSTMENT = "MARKET_ADJUSTMENT"
    RECOMMENDATION = "RECOMMENDATION"
    PRODUCTION_SAFETY = "PRODUCTION_SAFETY"


class ScreeningReasonPolarity(str, Enum):
    SUPPORTING = "SUPPORTING"
    BLOCKING = "BLOCKING"


SCREENING_REASON_CODE_NAMESPACE = "discovery.screening.reason.v1"


@dataclass(frozen=True, slots=True)
class StructuredScreeningReason:
    """Stable machine code paired with the original human explanation."""

    reason_code: str
    category: ScreeningReasonCategory
    polarity: ScreeningReasonPolarity
    source_component: str
    message: str

    def __post_init__(self) -> None:
        for name in ("reason_code", "source_component", "message"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        if _REASON_CODE.fullmatch(self.reason_code) is None:
            raise ValueError("reason_code must use a stable lowercase namespace")
        if not isinstance(self.category, ScreeningReasonCategory):
            raise TypeError("category must be ScreeningReasonCategory")
        if not isinstance(self.polarity, ScreeningReasonPolarity):
            raise TypeError("polarity must be ScreeningReasonPolarity")


def structured_screening_reason(
    suffix: str,
    *,
    category: ScreeningReasonCategory,
    polarity: ScreeningReasonPolarity,
    source_component: str,
    message: str,
) -> StructuredScreeningReason:
    """Create one v1 reason without deriving identity from its display text."""

    resolved_suffix = _required_text(suffix, "suffix")
    return StructuredScreeningReason(
        reason_code=f"{SCREENING_REASON_CODE_NAMESPACE}.{resolved_suffix}",
        category=category,
        polarity=polarity,
        source_component=source_component,
        message=message,
    )


def _unique_reasons(
    values: tuple[StructuredScreeningReason, ...],
) -> tuple[StructuredScreeningReason, ...]:
    if not isinstance(values, tuple):
        raise TypeError("structured_reasons must be a tuple")
    ordered: list[StructuredScreeningReason] = []
    by_code: dict[str, StructuredScreeningReason] = {}
    for value in values:
        if not isinstance(value, StructuredScreeningReason):
            raise TypeError("structured_reasons must contain StructuredScreeningReason")
        existing = by_code.get(value.reason_code)
        if existing is None:
            by_code[value.reason_code] = value
            ordered.append(value)
        elif existing != value:
            raise ValueError("one reason_code cannot have conflicting semantics")
    return tuple(ordered)


@dataclass(frozen=True, slots=True)
class ScreeningRecommendationValue:
    """The grade, action, and summary visible at one recommendation stage."""

    grade: str
    action: str
    summary: str

    def __post_init__(self) -> None:
        for name in ("grade", "action", "summary"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class ScreeningRecommendationSemantics:
    """Raw recommendation plus the effective post-Safety-Gate recommendation."""

    raw_recommendation: ScreeningRecommendationValue
    effective_recommendation: ScreeningRecommendationValue
    recommendation_score: int
    safety_intervention_occurred: bool
    safety_status: str
    structured_reasons: tuple[StructuredScreeningReason, ...]
    safety_reasons: tuple[StructuredScreeningReason, ...]
    safety_policy: ProductionSafetyPolicyDescriptor

    def __post_init__(self) -> None:
        if not isinstance(self.raw_recommendation, ScreeningRecommendationValue):
            raise TypeError("raw_recommendation must be ScreeningRecommendationValue")
        if not isinstance(self.effective_recommendation, ScreeningRecommendationValue):
            raise TypeError("effective_recommendation must be ScreeningRecommendationValue")
        if (
            isinstance(self.recommendation_score, bool)
            or not isinstance(self.recommendation_score, int)
            or not 0 <= self.recommendation_score <= 100
        ):
            raise ValueError("recommendation_score must be an integer from 0 to 100")
        if not isinstance(self.safety_intervention_occurred, bool):
            raise TypeError("safety_intervention_occurred must be bool")
        object.__setattr__(
            self,
            "safety_status",
            _required_text(self.safety_status, "safety_status"),
        )
        if not isinstance(self.safety_policy, ProductionSafetyPolicyDescriptor):
            raise TypeError("safety_policy must be ProductionSafetyPolicyDescriptor")
        structured = _unique_reasons(self.structured_reasons)
        safety = _unique_reasons(self.safety_reasons)
        object.__setattr__(self, "structured_reasons", structured)
        object.__setattr__(self, "safety_reasons", safety)
        if any(reason not in structured for reason in safety):
            raise ValueError("safety_reasons must be included in structured_reasons")
        changed = self.raw_recommendation != self.effective_recommendation
        if self.safety_intervention_occurred != changed:
            raise ValueError(
                "safety_intervention_occurred must match raw/effective recommendation change"
            )

    @property
    def raw_grade(self) -> str:
        return self.raw_recommendation.grade

    @property
    def effective_grade(self) -> str:
        return self.effective_recommendation.grade


PRODUCTION_SCREENING_SCORE_POLICY_V1 = ScreeningScorePolicyDescriptor(
    policy_name="production-discovery-screening-score",
    policy_version="1.0.0",
    algorithm_id="opportunity-explainable-screening-v1",
    description=(
        "Current Opportunity score, confidence, trend and market adjustments feed "
        "the explainable recommendation score; the market adjustment participates "
        "in both the final opportunity score and its explainable-score contribution."
    ),
    ordered_rule_ids=(
        "economics.roi_bucket",
        "economics.estimated_monthly_sales_bucket",
        "economics.competitor_count_bucket",
        "economics.risk_level_bucket",
        "economics.profitability_thresholds",
        "confidence.sample_size_multiplier",
        "trend.score_adjustment",
        "market_intelligence.score_adjustment",
        "final_opportunity_score.sum",
        "recommendation.explainable_contributions",
        "recommendation.score.clamp_round_integer",
    ),
    policy_assumption_inputs=(
        "selling_price_multiplier",
        "minimum_net_profit",
        "minimum_roi",
        "estimated_monthly_sales",
        "competitor_count",
        "risk_level",
    ),
)

PRODUCTION_RECOMMENDATION_POLICY_V1 = RecommendationPolicyDescriptor(
    policy_name="production-discovery-recommendation",
    policy_version="1.0.0",
    algorithm_id="score-grade-action-probability-v1",
    description=(
        "Maps the explainable integer score to stars, raw grade and action, then "
        "estimates success probability and builds the existing human summary."
    ),
    ordered_rule_ids=(
        "score_to_stars.thresholds",
        "score_to_grade.thresholds",
        "success_probability.confidence_and_profit",
        "reasons.default_when_empty",
        "summary.first_reason_first_warning",
    ),
    reason_code_namespace=SCREENING_REASON_CODE_NAMESPACE,
)

PRODUCTION_SAFETY_POLICY_V1 = ProductionSafetyPolicyDescriptor(
    policy_name="production-discovery-safety-gate",
    policy_version="1.0.0",
    algorithm_id="post-score-buy-family-safety-gate-v1",
    description=(
        "Checks production source, economics completeness and profitability; only "
        "BUY-family grades are downgraded to WATCH and their numeric score is kept."
    ),
    ordered_rule_ids=(
        "required.production_source",
        "required.purchase_price",
        "required.currency",
        "required.shipping_cost",
        "required.expected_selling_price",
        "required.fee_inputs",
        "required.net_profit_and_roi",
        "required.profitability_filter",
        "gate.non_buy_preserved",
        "gate.buy_family_downgraded_to_watch",
        "gate.recommendation_score_preserved",
    ),
)

PRODUCTION_SCREENING_RANKING_POLICY_V1 = ScreeningRankingPolicyDescriptor(
    policy_name="production-discovery-screening-ranking",
    policy_version="1.0.0",
    algorithm_id="python-stable-descending-tuple-sort-v1",
    description=(
        "Orders successful screening results by the current three numeric keys; "
        "complete equal-key ties retain their pre-sort input order."
    ),
    ordered_sort_keys=(
        "effective_recommendation_score:desc",
        "final_opportunity_score:desc",
        "per_unit_net_profit:desc",
    ),
    equal_key_tie_behavior="stable_input_order",
)

PRODUCTION_SCREENING_POLICY_DESCRIPTORS_V1 = ScreeningPolicyDescriptors(
    score=PRODUCTION_SCREENING_SCORE_POLICY_V1,
    recommendation=PRODUCTION_RECOMMENDATION_POLICY_V1,
    production_safety=PRODUCTION_SAFETY_POLICY_V1,
    ranking=PRODUCTION_SCREENING_RANKING_POLICY_V1,
)


__all__ = [
    "PRODUCTION_RECOMMENDATION_POLICY_V1",
    "PRODUCTION_SAFETY_POLICY_V1",
    "PRODUCTION_SCREENING_POLICY_DESCRIPTORS_V1",
    "PRODUCTION_SCREENING_RANKING_POLICY_V1",
    "PRODUCTION_SCREENING_SCORE_POLICY_V1",
    "RecommendationPolicyDescriptor",
    "SCREENING_REASON_CODE_NAMESPACE",
    "ScreeningPolicyDescriptors",
    "ScreeningRankingPolicyDescriptor",
    "ScreeningReasonCategory",
    "ScreeningReasonPolarity",
    "ScreeningRecommendationSemantics",
    "ScreeningRecommendationValue",
    "ScreeningScorePolicyDescriptor",
    "ProductionSafetyPolicyDescriptor",
    "StructuredScreeningReason",
    "structured_screening_reason",
]
