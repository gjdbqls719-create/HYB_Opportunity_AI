"""Immutable evidence-readiness facts for future Capital Gate evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.decision_engine import OpportunityIdentity


CAPITAL_READINESS_SCHEMA_VERSION = "capital-readiness-v1"
CAPITAL_READINESS_SOURCE_MANIFEST_SCHEMA_VERSION = "capital-readiness-source-manifest-v1"
CAPITAL_READINESS_POLICY_NAME = "domestic-commerce-capital-readiness"
CAPITAL_READINESS_POLICY_VERSION = "1.0.0"


class CapitalReadinessState(StrEnum):
    READY_FOR_CAPITAL_REVIEW = "ready_for_capital_review"
    BLOCKED = "blocked"


class CapitalReadinessReasonCode(StrEnum):
    CONSERVATIVE_ECONOMICS_BLOCKED = "conservative_economics_blocked"
    DOMESTIC_MARKET_NOT_VALIDATED = "domestic_market_not_validated"
    CRITICAL_COST_INCOMPLETE = "critical_cost_incomplete"
    SOURCE_OPPORTUNITY_MISMATCH = "source_opportunity_mismatch"
    SOURCING_LINEAGE_MISMATCH = "sourcing_lineage_mismatch"
    PRODUCT_MATCH_NOT_VERIFIED = "product_match_not_verified"
    QUOTE_VALIDITY_MISSING = "quote_validity_missing"
    QUOTE_EXPIRED = "quote_expired"
    SOURCE_POLICY_UNSUPPORTED = "source_policy_unsupported"

    @property
    def order(self) -> int:
        return tuple(CapitalReadinessReasonCode).index(self)


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _positive(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class CapitalReadinessSourceManifest:
    opportunity_identity: OpportunityIdentity
    conservative_economics_result_id: str
    economics_source_composition_id: str
    acquisition_normalization_id: str
    landed_cost_composition_id: str
    domestic_market_validation_assessment_id: str
    critical_cost_assessment_id: str
    sourcing_binding_id: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    quote_id: str
    quote_revision: int
    product_match_verification_id: str
    quote_valid_until: datetime | None
    schema_version: str = CAPITAL_READINESS_SOURCE_MANIFEST_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        for name in (
            "conservative_economics_result_id",
            "economics_source_composition_id",
            "acquisition_normalization_id",
            "landed_cost_composition_id",
            "domestic_market_validation_assessment_id",
            "critical_cost_assessment_id",
            "sourcing_binding_id",
            "sourcing_admission_id",
            "quote_id",
            "product_match_verification_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        _positive(self.sourcing_admission_revision, "sourcing_admission_revision")
        _positive(self.quote_revision, "quote_revision")
        if self.sourcing_admission_revision != self.quote_revision:
            raise ValueError("Sourcing Admission and Quote revisions must match")
        if self.quote_valid_until is not None:
            object.__setattr__(
                self,
                "quote_valid_until",
                _aware(self.quote_valid_until, "quote_valid_until"),
            )
        if self.schema_version != CAPITAL_READINESS_SOURCE_MANIFEST_SCHEMA_VERSION:
            raise ValueError("unsupported Capital Readiness source manifest schema")


@dataclass(frozen=True, slots=True)
class CapitalReadinessReason:
    code: CapitalReadinessReasonCode

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", CapitalReadinessReasonCode(self.code))


@dataclass(frozen=True, slots=True)
class CapitalReadinessAssessment:
    assessment_id: str
    source_manifest: CapitalReadinessSourceManifest
    state: CapitalReadinessState
    blocking_reasons: tuple[CapitalReadinessReason, ...]
    policy_name: str
    policy_version: str
    requested_at: datetime
    evaluated_at: datetime
    schema_version: str = CAPITAL_READINESS_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "assessment_id", _text(self.assessment_id, "assessment_id"))
        if not isinstance(self.source_manifest, CapitalReadinessSourceManifest):
            raise TypeError("source_manifest must be CapitalReadinessSourceManifest")
        state = CapitalReadinessState(self.state)
        object.__setattr__(self, "state", state)
        if not isinstance(self.blocking_reasons, tuple) or any(
            not isinstance(reason, CapitalReadinessReason)
            for reason in self.blocking_reasons
        ):
            raise TypeError("blocking_reasons must be a CapitalReadinessReason tuple")
        codes = tuple(reason.code for reason in self.blocking_reasons)
        if len(set(codes)) != len(codes):
            raise ValueError("blocking reasons must be unique")
        if codes != tuple(sorted(codes, key=lambda value: value.order)):
            raise ValueError("blocking reasons must use deterministic order")
        if state is CapitalReadinessState.READY_FOR_CAPITAL_REVIEW and codes:
            raise ValueError("READY_FOR_CAPITAL_REVIEW cannot carry blockers")
        if state is CapitalReadinessState.BLOCKED and not codes:
            raise ValueError("BLOCKED assessment requires blockers")
        object.__setattr__(self, "policy_name", _text(self.policy_name, "policy_name"))
        object.__setattr__(self, "policy_version", _text(self.policy_version, "policy_version"))
        if (
            self.policy_name != CAPITAL_READINESS_POLICY_NAME
            or self.policy_version != CAPITAL_READINESS_POLICY_VERSION
        ):
            raise ValueError("unsupported Capital Readiness policy")
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        object.__setattr__(self, "evaluated_at", _aware(self.evaluated_at, "evaluated_at"))
        if self.schema_version != CAPITAL_READINESS_SCHEMA_VERSION:
            raise ValueError("unsupported Capital Readiness schema")

    @property
    def reason_codes(self) -> tuple[CapitalReadinessReasonCode, ...]:
        return tuple(reason.code for reason in self.blocking_reasons)


__all__ = [name for name in globals() if name.startswith("Capital") or name.startswith("CAPITAL")]
