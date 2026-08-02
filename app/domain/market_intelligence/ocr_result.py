from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from app.domain.market_intelligence.artifact import _aware, _required_text
from app.domain.market_intelligence.ocr_candidate import OCRField


class OCRProvider(StrEnum):
    UNKNOWN = "unknown"
    TESSERACT = "tesseract"
    EASYOCR = "easyocr"
    GOOGLE_VISION = "google_vision"
    AZURE_VISION = "azure_vision"
    OPENAI = "openai"
    CLAUDE = "claude"
    CUSTOM = "custom"


def _confidence(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be Decimal")
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    if not Decimal("0") <= value <= Decimal("1"):
        raise ValueError(f"{name} must be between 0 and 1")
    return value


@dataclass(frozen=True, slots=True)
class OCRFieldResult:
    field_name: OCRField
    raw_text: str
    normalized_value: Any
    confidence: Decimal
    bounding_box: tuple[int, int, int, int] | None = None

    def __post_init__(self) -> None:
        try:
            field_name = OCRField(self.field_name)
        except ValueError as error:
            raise ValueError("unsupported OCR field") from error
        if not isinstance(self.raw_text, str):
            raise TypeError("raw_text must be text")
        bounding_box = self.bounding_box
        if bounding_box is not None:
            if not isinstance(bounding_box, tuple) or len(bounding_box) != 4:
                raise TypeError("bounding_box must be a four-integer tuple or None")
            if any(isinstance(value, bool) or not isinstance(value, int) for value in bounding_box):
                raise TypeError("bounding_box must contain integers")
            if any(value < 0 for value in bounding_box):
                raise ValueError("bounding_box values cannot be negative")
        object.__setattr__(self, "field_name", field_name)
        object.__setattr__(self, "confidence", _confidence(self.confidence, "confidence"))


@dataclass(frozen=True, slots=True)
class OCRResult:
    """Provider-neutral immutable OCR response; it performs no OCR itself."""

    request_id: str
    artifact_id: str
    provider: OCRProvider
    provider_version: str
    executed_at: datetime
    fields: tuple[OCRFieldResult, ...]
    confidence: Decimal
    schema_version: str

    def __post_init__(self) -> None:
        try:
            provider = OCRProvider(self.provider)
        except ValueError as error:
            raise ValueError("unsupported OCR provider") from error
        fields = tuple(self.fields)
        if any(not isinstance(field, OCRFieldResult) for field in fields):
            raise TypeError("fields must contain OCRFieldResult values")
        object.__setattr__(self, "request_id", _required_text(self.request_id, "request_id"))
        object.__setattr__(self, "artifact_id", _required_text(self.artifact_id, "artifact_id"))
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "provider_version", _required_text(self.provider_version, "provider_version"))
        object.__setattr__(self, "executed_at", _aware(self.executed_at, "executed_at"))
        object.__setattr__(self, "fields", fields)
        object.__setattr__(self, "confidence", _confidence(self.confidence, "confidence"))
        object.__setattr__(self, "schema_version", _required_text(self.schema_version, "schema_version"))
