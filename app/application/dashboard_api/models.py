from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.domain.decision_engine import (
    DecisionDimension,
    DecisionEvidenceAvailability,
    DecisionFreshness,
    DecisionOutcome,
    DecisionReasonCode,
    ExplanationCode,
    Severity,
)


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _confidence(value: Decimal | None, name: str) -> Decimal | None:
    if value is None:
        return None
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal or None")
    if not value.is_finite() or not Decimal("0") <= value <= Decimal("1"):
        raise ValueError(f"{name} must be between 0 and 1")
    return value


def _display_order(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


@dataclass(frozen=True, slots=True)
class DashboardSummaryDTO:
    outcome: DecisionOutcome
    confidence: Decimal
    summary_code: ExplanationCode
    summary_text: str

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, DecisionOutcome):
            raise TypeError("outcome must be DecisionOutcome")
        confidence = _confidence(self.confidence, "confidence")
        if confidence is None:
            raise ValueError("summary confidence is required")
        object.__setattr__(self, "confidence", confidence)
        if not isinstance(self.summary_code, ExplanationCode):
            raise TypeError("summary_code must be ExplanationCode")
        object.__setattr__(
            self,
            "summary_text",
            _required_text(self.summary_text, "summary_text"),
        )


@dataclass(frozen=True, slots=True)
class DashboardActionDTO:
    outcome: DecisionOutcome
    primary_action: str
    secondary_action: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, DecisionOutcome):
            raise TypeError("outcome must be DecisionOutcome")
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


@dataclass(frozen=True, slots=True)
class DashboardWarningDTO:
    dimension: DecisionDimension
    severity: Severity
    reason_code: DecisionReasonCode
    text: str
    display_order: int

    def __post_init__(self) -> None:
        if not isinstance(self.dimension, DecisionDimension):
            raise TypeError("dimension must be DecisionDimension")
        if self.severity not in {Severity.WARNING, Severity.CRITICAL}:
            raise ValueError("severity must be WARNING or CRITICAL")
        if not isinstance(self.reason_code, DecisionReasonCode):
            raise TypeError("reason_code must be DecisionReasonCode")
        object.__setattr__(self, "text", _required_text(self.text, "text"))
        object.__setattr__(
            self,
            "display_order",
            _display_order(self.display_order, "display_order"),
        )


@dataclass(frozen=True, slots=True)
class DashboardEvidenceDTO:
    dimension: DecisionDimension
    availability: DecisionEvidenceAvailability
    confidence: Decimal | None
    freshness: DecisionFreshness
    severity: Severity | None
    display_order: int

    def __post_init__(self) -> None:
        if not isinstance(self.dimension, DecisionDimension):
            raise TypeError("dimension must be DecisionDimension")
        if not isinstance(self.availability, DecisionEvidenceAvailability):
            raise TypeError("availability must be DecisionEvidenceAvailability")
        if not isinstance(self.freshness, DecisionFreshness):
            raise TypeError("freshness must be DecisionFreshness")
        if self.severity is not None and not isinstance(self.severity, Severity):
            raise TypeError("severity must be Severity or None")
        confidence = _confidence(self.confidence, "confidence")
        if self.availability is DecisionEvidenceAvailability.UNAVAILABLE:
            if confidence is not None:
                raise ValueError("unavailable evidence confidence must be None")
        object.__setattr__(self, "confidence", confidence)
        object.__setattr__(
            self,
            "display_order",
            _display_order(self.display_order, "display_order"),
        )


@dataclass(frozen=True, slots=True)
class DashboardMetadataDTO:
    generated_at: datetime
    schema_version: str
    policy_version: str
    read_model_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.generated_at, datetime):
            raise TypeError("generated_at must be a datetime")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")
        for name in ("schema_version", "policy_version", "read_model_version"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))


@dataclass(frozen=True, slots=True)
class DashboardResponseDTO:
    summary: DashboardSummaryDTO
    action: DashboardActionDTO
    warnings: tuple[DashboardWarningDTO, ...]
    evidence: tuple[DashboardEvidenceDTO, ...]
    metadata: DashboardMetadataDTO

    def __post_init__(self) -> None:
        if not isinstance(self.summary, DashboardSummaryDTO):
            raise TypeError("summary must be DashboardSummaryDTO")
        if not isinstance(self.action, DashboardActionDTO):
            raise TypeError("action must be DashboardActionDTO")
        if self.summary.outcome is not self.action.outcome:
            raise ValueError("summary and action outcomes must match")
        if not isinstance(self.warnings, tuple):
            raise TypeError("warnings must be a tuple")
        if any(not isinstance(value, DashboardWarningDTO) for value in self.warnings):
            raise TypeError("warnings must contain DashboardWarningDTO values")
        if tuple(value.display_order for value in self.warnings) != tuple(
            range(1, len(self.warnings) + 1)
        ):
            raise ValueError("warning display_order must be consecutive from 1")
        warning_keys = tuple(
            (value.dimension, value.reason_code) for value in self.warnings
        )
        if len(set(warning_keys)) != len(warning_keys):
            raise ValueError("warnings cannot contain duplicates")
        if not isinstance(self.evidence, tuple):
            raise TypeError("evidence must be a tuple")
        if any(not isinstance(value, DashboardEvidenceDTO) for value in self.evidence):
            raise TypeError("evidence must contain DashboardEvidenceDTO values")
        if tuple(value.dimension for value in self.evidence) != tuple(DecisionDimension):
            raise ValueError("evidence must preserve the fixed dimension order")
        if tuple(value.display_order for value in self.evidence) != tuple(
            range(1, len(DecisionDimension) + 1)
        ):
            raise ValueError("evidence display_order must match dimension order")
        if not isinstance(self.metadata, DashboardMetadataDTO):
            raise TypeError("metadata must be DashboardMetadataDTO")

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": {
                "outcome": self.summary.outcome.value,
                "confidence": str(self.summary.confidence),
                "summary_code": self.summary.summary_code.value,
                "summary_text": self.summary.summary_text,
            },
            "action": {
                "outcome": self.action.outcome.value,
                "primary_action": self.action.primary_action,
                "secondary_action": self.action.secondary_action,
            },
            "warnings": [
                {
                    "dimension": value.dimension.value,
                    "severity": value.severity.value,
                    "reason_code": value.reason_code.value,
                    "text": value.text,
                    "display_order": value.display_order,
                }
                for value in self.warnings
            ],
            "evidence": [
                {
                    "dimension": value.dimension.value,
                    "availability": value.availability.value,
                    "confidence": (
                        str(value.confidence)
                        if value.confidence is not None
                        else None
                    ),
                    "freshness": value.freshness.value,
                    "severity": (
                        value.severity.value if value.severity is not None else None
                    ),
                    "display_order": value.display_order,
                }
                for value in self.evidence
            ],
            "metadata": {
                "generated_at": self.metadata.generated_at.isoformat(),
                "schema_version": self.metadata.schema_version,
                "policy_version": self.metadata.policy_version,
                "read_model_version": self.metadata.read_model_version,
            },
        }
