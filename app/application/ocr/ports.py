from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.market_intelligence import ArtifactReference, OCRResult


@runtime_checkable
class ExtractText(Protocol):
    """Provider-neutral OCR adapter port."""

    def extract_text(self, artifact: ArtifactReference) -> OCRResult: ...


OCRAdapter = ExtractText

__all__ = ["ExtractText", "OCRAdapter"]
