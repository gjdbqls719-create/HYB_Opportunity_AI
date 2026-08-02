from __future__ import annotations

from decimal import Decimal

from app.application.ocr.ports import ExtractText
from app.application.ocr.use_cases import ConvertOCRResultToCandidates, ExtractOCR
from app.domain.market_intelligence import (
    ArtifactReference,
    OCRCandidate,
    OCRField,
    OCRFieldResult,
    OCRProvider,
    OCRResult,
)


class OCRService:
    def __init__(self, adapter: ExtractText) -> None:
        if not isinstance(adapter, ExtractText):
            raise TypeError("adapter must implement ExtractText")
        self._adapter = adapter

    def extract(self, command: ExtractOCR) -> OCRResult:
        result = self._adapter.extract_text(command.artifact)
        if not isinstance(result, OCRResult):
            raise TypeError("OCR adapter must return OCRResult")
        if result.artifact_id != command.artifact.artifact_id:
            raise ValueError("OCR result artifact_id must match request artifact")
        return result

    def to_candidates(
        self, command: ConvertOCRResultToCandidates
    ) -> tuple[OCRCandidate, ...]:
        if command.result.artifact_id != command.artifact.artifact_id:
            raise ValueError("OCR result artifact_id must match candidate artifact")
        return tuple(
            OCRCandidate(
                candidate_id=f"{command.result.request_id}:{index}:{field.field_name.value}",
                artifact=command.artifact,
                field_name=field.field_name,
                raw_text=field.raw_text,
                normalized_value=field.normalized_value,
                confidence=field.confidence,
                captured_at=command.result.executed_at,
                schema_version=command.candidate_schema_version,
            )
            for index, field in enumerate(command.result.fields)
        )


class DummyOCRAdapter:
    """Deterministic test adapter; it performs no OCR or artifact access."""

    def extract_text(self, artifact: ArtifactReference) -> OCRResult:
        if not isinstance(artifact, ArtifactReference):
            raise TypeError("artifact must be ArtifactReference")
        return OCRResult(
            request_id=f"dummy:{artifact.artifact_id}",
            artifact_id=artifact.artifact_id,
            provider=OCRProvider.CUSTOM,
            provider_version="dummy-v1",
            executed_at=artifact.captured_at,
            fields=(
                OCRFieldResult(
                    field_name=OCRField.PRICE,
                    raw_text="19,900",
                    normalized_value=Decimal("19900"),
                    confidence=Decimal("0.90"),
                    bounding_box=(10, 10, 100, 20),
                ),
                OCRFieldResult(
                    field_name=OCRField.SEARCH_VOLUME,
                    raw_text="1,200",
                    normalized_value=1200,
                    confidence=Decimal("0.80"),
                    bounding_box=(10, 40, 100, 20),
                ),
                OCRFieldResult(
                    field_name=OCRField.POPULARITY,
                    raw_text="7",
                    normalized_value=7,
                    confidence=Decimal("0.70"),
                    bounding_box=None,
                ),
            ),
            confidence=Decimal("0.80"),
            schema_version="ocr-result-v1",
        )
