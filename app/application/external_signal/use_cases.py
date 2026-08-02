from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.domain.market_intelligence import (
    ArtifactReference,
    ExternalSignalDirection,
    HumanVerification,
    MarketObservationIdentity,
    OCRCandidate,
    OCRField,
)


@dataclass(frozen=True, slots=True)
class CreateOCRCandidate:
    candidate_id: str
    artifact: ArtifactReference
    field_name: OCRField
    raw_text: str
    normalized_value: Any
    confidence: Decimal
    captured_at: datetime
    schema_version: str = "ocr-candidate-v1"


@dataclass(frozen=True, slots=True)
class VerifyOCRCandidate:
    verification_id: str
    candidate: OCRCandidate
    verified_value: Any
    operator_id: str
    verified_at: datetime
    comment: str | None = None
    schema_version: str = "human-verification-v1"


@dataclass(frozen=True, slots=True)
class CreateExternalSignal:
    signal_id: str
    identity: MarketObservationIdentity
    candidate: OCRCandidate
    verification: HumanVerification | None
    signal_name: str
    signal_direction: ExternalSignalDirection
    confidence: Decimal = Decimal("1")
    schema_version: str = "external-signal-v1"
