from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.domain.market_intelligence.evidence import (
    MarketEvidence,
    MarketEvidenceStatus,
)
from app.domain.market_intelligence.identity import MarketObservationIdentity


class ExternalSignalSourceType(StrEnum):
    ITEMSCOUT_SCREENSHOT = "itemscout_screenshot"
    MANUAL_INPUT = "manual_input"
    HUMAN_REPORT = "human_report"
    OCR_CANDIDATE = "ocr_candidate"
    OTHER = "other"


class ExternalSignalDirection(StrEnum):
    POSITIVE = "positive"
    NEUTRAL = "neutral"
    NEGATIVE = "negative"
    UNKNOWN = "unknown"


_ARTIFACT_SOURCES = frozenset({
    ExternalSignalSourceType.ITEMSCOUT_SCREENSHOT,
    ExternalSignalSourceType.OCR_CANDIDATE,
})


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _optional_text(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be text or None")
    return value.strip() or None


def _aware_optional(value: datetime | None, name: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime or None")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class ExternalMarketSignal:
    """Immutable reference signal that cannot create a business decision."""

    signal_id: str
    identity: MarketObservationIdentity
    source_type: ExternalSignalSourceType
    signal_name: str
    signal_direction: ExternalSignalDirection
    evidence: MarketEvidence
    captured_at: datetime
    schema_version: str
    verified_at: datetime | None = None
    operator_id: str | None = None
    artifact_reference: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identity, MarketObservationIdentity):
            raise TypeError("identity must be MarketObservationIdentity")
        if not isinstance(self.evidence, MarketEvidence):
            raise TypeError("evidence must be MarketEvidence")
        try:
            source_type = ExternalSignalSourceType(self.source_type)
        except ValueError as error:
            raise ValueError("unsupported external signal source type") from error
        try:
            direction = ExternalSignalDirection(self.signal_direction)
        except ValueError as error:
            raise ValueError("unsupported external signal direction") from error

        captured_at = _aware_optional(self.captured_at, "captured_at")
        assert captured_at is not None
        verified_at = _aware_optional(self.verified_at, "verified_at")
        operator_id = _optional_text(self.operator_id, "operator_id")
        artifact_reference = _optional_text(self.artifact_reference, "artifact_reference")

        if self.evidence.market != self.identity.market:
            raise ValueError("evidence market must match observation identity")
        if self.evidence.marketplace != self.identity.marketplace:
            raise ValueError("evidence marketplace must match observation identity")
        if source_type is ExternalSignalSourceType.OCR_CANDIDATE and self.evidence.status is MarketEvidenceStatus.HUMAN_VERIFIED:
            raise ValueError("OCR candidate cannot be human verified")
        if self.evidence.status is MarketEvidenceStatus.HUMAN_VERIFIED:
            if verified_at is None:
                raise ValueError("human-verified evidence requires verified_at")
            if operator_id is None:
                raise ValueError("human-verified evidence requires operator_id")
        if source_type in _ARTIFACT_SOURCES and artifact_reference is None:
            raise ValueError(f"{source_type.value} requires artifact_reference")
        if verified_at is not None and verified_at < captured_at:
            raise ValueError("verified_at cannot precede captured_at")

        object.__setattr__(self, "signal_id", _required_text(self.signal_id, "signal_id"))
        object.__setattr__(self, "source_type", source_type)
        object.__setattr__(self, "signal_name", _required_text(self.signal_name, "signal_name"))
        object.__setattr__(self, "signal_direction", direction)
        object.__setattr__(self, "captured_at", captured_at)
        object.__setattr__(self, "schema_version", _required_text(self.schema_version, "schema_version"))
        object.__setattr__(self, "verified_at", verified_at)
        object.__setattr__(self, "operator_id", operator_id)
        object.__setattr__(self, "artifact_reference", artifact_reference)
