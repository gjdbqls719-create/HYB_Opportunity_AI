from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.domain.market_intelligence.artifact import ArtifactReference, _aware, _required_text


class OCRField(StrEnum):
    PRICE = "price"
    POPULARITY = "popularity"
    SEARCH_VOLUME = "search_volume"
    COMPETITOR_COUNT = "competitor_count"
    RATING = "rating"
    REVIEW_COUNT = "review_count"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class OCRCandidate:
    """Unverified extraction candidate; it is never a decision input."""

    candidate_id: str
    artifact: ArtifactReference
    field_name: OCRField
    raw_text: str
    normalized_value: Any
    confidence: Decimal
    captured_at: datetime
    schema_version: str

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, ArtifactReference):
            raise TypeError("artifact must be ArtifactReference")
        try:
            field_name = OCRField(self.field_name)
        except ValueError as error:
            raise ValueError("unsupported OCR field") from error
        if not isinstance(self.confidence, Decimal):
            raise TypeError("confidence must be Decimal")
        if not self.confidence.is_finite():
            raise ValueError("confidence must be finite")
        if not Decimal("0") <= self.confidence <= Decimal("1"):
            raise ValueError("confidence must be between 0 and 1")
        captured_at = _aware(self.captured_at, "captured_at")
        if captured_at < self.artifact.captured_at:
            raise ValueError("candidate captured_at cannot precede artifact captured_at")

        object.__setattr__(self, "candidate_id", _required_text(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "field_name", field_name)
        object.__setattr__(self, "raw_text", _required_text(self.raw_text, "raw_text"))
        object.__setattr__(self, "captured_at", captured_at)
        object.__setattr__(self, "schema_version", _required_text(self.schema_version, "schema_version"))
