from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from app.domain.decision_engine.models import (
    DecisionDimension,
    DecisionEvidenceAvailability,
    DecisionFreshness,
    DecisionOutcome,
    DecisionReasonCode,
)


class ExplanationCode(StrEnum):
    INVEST_READY = "invest_ready"
    REVIEW_MORE_EVIDENCE = "review_more_evidence"
    REVIEW_MARKET_RISK = "review_market_risk"
    REJECT_SAFETY = "reject_safety"
    INSUFFICIENT_VERIFIED_EVIDENCE = "insufficient_verified_evidence"


class Severity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


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
class DecisionSummary:
    outcome: DecisionOutcome
    aggregate_confidence: Decimal
    supporting_dimension_count: int
    missing_dimension_count: int
    summary_code: ExplanationCode
    default_text: str

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, DecisionOutcome):
            raise TypeError("outcome must be DecisionOutcome")
        if not isinstance(self.aggregate_confidence, Decimal):
            raise TypeError("aggregate_confidence must be Decimal")
        if (
            not self.aggregate_confidence.is_finite()
            or not Decimal("0") <= self.aggregate_confidence <= Decimal("1")
        ):
            raise ValueError("aggregate_confidence must be between 0 and 1")
        for name in ("supporting_dimension_count", "missing_dimension_count"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if not isinstance(self.summary_code, ExplanationCode):
            raise TypeError("summary_code must be ExplanationCode")
        object.__setattr__(
            self,
            "default_text",
            _required_text(self.default_text, "default_text"),
        )


@dataclass(frozen=True, slots=True)
class DecisionExplanationItem:
    reason_code: DecisionReasonCode
    dimension: DecisionDimension
    severity: Severity
    default_text: str
    display_order: int

    def __post_init__(self) -> None:
        if not isinstance(self.reason_code, DecisionReasonCode):
            raise TypeError("reason_code must be DecisionReasonCode")
        if not isinstance(self.dimension, DecisionDimension):
            raise TypeError("dimension must be DecisionDimension")
        if not isinstance(self.severity, Severity):
            raise TypeError("severity must be Severity")
        if (
            isinstance(self.display_order, bool)
            or not isinstance(self.display_order, int)
            or self.display_order < 1
        ):
            raise ValueError("display_order must be a positive integer")
        object.__setattr__(
            self,
            "default_text",
            _required_text(self.default_text, "default_text"),
        )


@dataclass(frozen=True, slots=True)
class DecisionExplanationSection:
    title: str
    display_order: int
    items: tuple[DecisionExplanationItem, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "title", _required_text(self.title, "title"))
        if (
            isinstance(self.display_order, bool)
            or not isinstance(self.display_order, int)
            or self.display_order < 1
        ):
            raise ValueError("display_order must be a positive integer")
        if not isinstance(self.items, tuple):
            raise TypeError("items must be a tuple")
        if any(not isinstance(value, DecisionExplanationItem) for value in self.items):
            raise TypeError("items must contain DecisionExplanationItem values")
        if tuple(value.display_order for value in self.items) != tuple(
            range(1, len(self.items) + 1)
        ):
            raise ValueError("item display_order must be consecutive from 1")
        keys = tuple((value.reason_code, value.dimension) for value in self.items)
        if len(set(keys)) != len(keys):
            raise ValueError("items cannot contain duplicate reason and dimension pairs")


@dataclass(frozen=True, slots=True)
class DecisionEvidenceSummary:
    dimension: DecisionDimension
    availability: DecisionEvidenceAvailability
    confidence: Decimal | None
    freshness: DecisionFreshness

    def __post_init__(self) -> None:
        if not isinstance(self.dimension, DecisionDimension):
            raise TypeError("dimension must be DecisionDimension")
        if not isinstance(self.availability, DecisionEvidenceAvailability):
            raise TypeError("availability must be DecisionEvidenceAvailability")
        if not isinstance(self.freshness, DecisionFreshness):
            raise TypeError("freshness must be DecisionFreshness")
        if self.availability is DecisionEvidenceAvailability.UNAVAILABLE:
            if self.confidence is not None:
                raise ValueError("unavailable evidence confidence must be None")
        elif not isinstance(self.confidence, Decimal):
            raise TypeError("available evidence confidence must be Decimal")
        elif (
            not self.confidence.is_finite()
            or not Decimal("0") <= self.confidence <= Decimal("1")
        ):
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class DecisionExplanation:
    summary: DecisionSummary
    sections: tuple[DecisionExplanationSection, ...]
    evidence_summary: tuple[DecisionEvidenceSummary, ...]
    missing_evidence: tuple[DecisionDimension, ...]
    generated_at: datetime
    schema_version: str
    policy_version: str
    explanation_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.summary, DecisionSummary):
            raise TypeError("summary must be DecisionSummary")
        if not isinstance(self.sections, tuple):
            raise TypeError("sections must be a tuple")
        if any(not isinstance(value, DecisionExplanationSection) for value in self.sections):
            raise TypeError("sections must contain DecisionExplanationSection values")
        expected_sections = (
            ("Summary", 1),
            ("Strengths", 2),
            ("Warnings", 3),
            ("Missing Evidence", 4),
        )
        if tuple((value.title, value.display_order) for value in self.sections) != expected_sections:
            raise ValueError("sections must use the fixed explanation order")
        if self.sections[0].items:
            raise ValueError("Summary section cannot contain reason items")
        all_item_keys = tuple(
            (item.reason_code, item.dimension)
            for section in self.sections
            for item in section.items
        )
        if len(set(all_item_keys)) != len(all_item_keys):
            raise ValueError("explanation items cannot be duplicated across sections")

        if not isinstance(self.evidence_summary, tuple):
            raise TypeError("evidence_summary must be a tuple")
        if any(not isinstance(value, DecisionEvidenceSummary) for value in self.evidence_summary):
            raise TypeError("evidence_summary must contain DecisionEvidenceSummary values")
        if tuple(value.dimension for value in self.evidence_summary) != tuple(DecisionDimension):
            raise ValueError("evidence_summary must use the fixed dimension order")

        if not isinstance(self.missing_evidence, tuple):
            raise TypeError("missing_evidence must be a tuple")
        if any(not isinstance(value, DecisionDimension) for value in self.missing_evidence):
            raise TypeError("missing_evidence must contain DecisionDimension values")
        if len(set(self.missing_evidence)) != len(self.missing_evidence):
            raise ValueError("missing_evidence cannot contain duplicates")
        expected_missing = tuple(
            value.dimension
            for value in self.evidence_summary
            if value.availability is DecisionEvidenceAvailability.UNAVAILABLE
        )
        if self.missing_evidence != expected_missing:
            raise ValueError("missing_evidence must match unavailable evidence")
        if self.summary.missing_dimension_count != len(self.missing_evidence):
            raise ValueError("summary missing_dimension_count does not match evidence")
        supporting_dimensions = {
            item.dimension for item in self.sections[1].items
        }
        if self.summary.supporting_dimension_count != len(supporting_dimensions):
            raise ValueError(
                "summary supporting_dimension_count does not match strengths"
            )
        if tuple(item.dimension for item in self.sections[3].items) != self.missing_evidence:
            raise ValueError("Missing Evidence items must match missing_evidence")

        object.__setattr__(self, "generated_at", _aware(self.generated_at, "generated_at"))
        for name in ("schema_version", "policy_version", "explanation_version"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
