from __future__ import annotations

from dataclasses import dataclass

from app.domain.market_intelligence import ArtifactReference, OCRResult


@dataclass(frozen=True, slots=True)
class ExtractOCR:
    artifact: ArtifactReference

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, ArtifactReference):
            raise TypeError("artifact must be ArtifactReference")


@dataclass(frozen=True, slots=True)
class ConvertOCRResultToCandidates:
    artifact: ArtifactReference
    result: OCRResult
    candidate_schema_version: str = "ocr-candidate-v1"

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, ArtifactReference):
            raise TypeError("artifact must be ArtifactReference")
        if not isinstance(self.result, OCRResult):
            raise TypeError("result must be OCRResult")
        if not isinstance(self.candidate_schema_version, str) or not self.candidate_schema_version.strip():
            raise ValueError("candidate_schema_version must be non-empty text")
        object.__setattr__(self, "candidate_schema_version", self.candidate_schema_version.strip())
