from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.decision_engine import (
    DecisionDimension,
    DecisionDimensionResult,
    DecisionEvidenceAvailability,
    DecisionExplanationItem,
    DecisionFreshness,
    DecisionOutcome,
    DecisionSummary,
    ExplanationCode,
    Severity,
)


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _display_order(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class DashboardSummaryCard:
    summary: DecisionSummary

    def __post_init__(self) -> None:
        if not isinstance(self.summary, DecisionSummary):
            raise TypeError("summary must be DecisionSummary")

    @property
    def outcome(self) -> DecisionOutcome:
        return self.summary.outcome

    @property
    def aggregate_confidence(self) -> Decimal:
        return self.summary.aggregate_confidence

    @property
    def summary_code(self) -> ExplanationCode:
        return self.summary.summary_code

    @property
    def summary_text(self) -> str:
        return self.summary.default_text


@dataclass(frozen=True, slots=True)
class DashboardActionCard:
    primary_action: str
    secondary_action: str | None
    outcome: DecisionOutcome

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "primary_action",
            _required_text(self.primary_action, "primary_action"),
        )
        if self.secondary_action is not None:
            object.__setattr__(
                self,
                "secondary_action",
                _required_text(self.secondary_action, "secondary_action"),
            )
        if not isinstance(self.outcome, DecisionOutcome):
            raise TypeError("outcome must be DecisionOutcome")


@dataclass(frozen=True, slots=True)
class DashboardWarningCard:
    item: DecisionExplanationItem
    display_order: int

    def __post_init__(self) -> None:
        if not isinstance(self.item, DecisionExplanationItem):
            raise TypeError("item must be DecisionExplanationItem")
        if self.item.severity not in {Severity.WARNING, Severity.CRITICAL}:
            raise ValueError("warning card requires WARNING or CRITICAL severity")
        object.__setattr__(
            self,
            "display_order",
            _display_order(self.display_order, "display_order"),
        )


@dataclass(frozen=True, slots=True)
class DashboardEvidenceCard:
    dimension_result: DecisionDimensionResult
    severity: Severity | None
    display_order: int

    def __post_init__(self) -> None:
        if not isinstance(self.dimension_result, DecisionDimensionResult):
            raise TypeError("dimension_result must be DecisionDimensionResult")
        if self.severity is not None and not isinstance(self.severity, Severity):
            raise TypeError("severity must be Severity or None")
        object.__setattr__(
            self,
            "display_order",
            _display_order(self.display_order, "display_order"),
        )

    @property
    def dimension(self) -> DecisionDimension:
        return self.dimension_result.dimension

    @property
    def availability(self) -> DecisionEvidenceAvailability:
        return self.dimension_result.availability

    @property
    def confidence(self) -> Decimal | None:
        return self.dimension_result.confidence

    @property
    def freshness(self) -> DecisionFreshness:
        return self.dimension_result.freshness


@dataclass(frozen=True, slots=True)
class DashboardReadModel:
    summary_card: DashboardSummaryCard
    action_card: DashboardActionCard
    warning_cards: tuple[DashboardWarningCard, ...]
    evidence_cards: tuple[DashboardEvidenceCard, ...]
    generated_at: datetime
    schema_version: str
    policy_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.summary_card, DashboardSummaryCard):
            raise TypeError("summary_card must be DashboardSummaryCard")
        if not isinstance(self.action_card, DashboardActionCard):
            raise TypeError("action_card must be DashboardActionCard")
        if self.action_card.outcome is not self.summary_card.outcome:
            raise ValueError("summary and action outcomes must match")
        if not isinstance(self.warning_cards, tuple):
            raise TypeError("warning_cards must be a tuple")
        if any(not isinstance(value, DashboardWarningCard) for value in self.warning_cards):
            raise TypeError("warning_cards must contain DashboardWarningCard values")
        if tuple(value.display_order for value in self.warning_cards) != tuple(
            range(1, len(self.warning_cards) + 1)
        ):
            raise ValueError("warning card display_order must be consecutive from 1")
        warning_keys = tuple(
            (value.item.reason_code, value.item.dimension)
            for value in self.warning_cards
        )
        if len(set(warning_keys)) != len(warning_keys):
            raise ValueError("warning_cards cannot contain duplicates")

        if not isinstance(self.evidence_cards, tuple):
            raise TypeError("evidence_cards must be a tuple")
        if any(not isinstance(value, DashboardEvidenceCard) for value in self.evidence_cards):
            raise TypeError("evidence_cards must contain DashboardEvidenceCard values")
        if tuple(value.dimension for value in self.evidence_cards) != tuple(DecisionDimension):
            raise ValueError("evidence_cards must use the fixed dimension order")
        if tuple(value.display_order for value in self.evidence_cards) != tuple(
            range(1, len(DecisionDimension) + 1)
        ):
            raise ValueError("evidence card display_order must match dimension order")

        if not isinstance(self.generated_at, datetime):
            raise TypeError("generated_at must be a datetime")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        object.__setattr__(
            self,
            "schema_version",
            _required_text(self.schema_version, "schema_version"),
        )
        object.__setattr__(
            self,
            "policy_version",
            _required_text(self.policy_version, "policy_version"),
        )
