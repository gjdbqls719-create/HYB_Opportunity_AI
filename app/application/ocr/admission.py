"""Application contracts for authoritative external OCR admission."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Protocol, runtime_checkable

from app.domain.market_intelligence import (
    ArtifactReference,
    OCRCandidate,
    OCRProvider,
    OCRResult,
)


ARTIFACT_ADMISSION_SCHEMA_VERSION = "ocr-artifact-admission-v1"
OCR_CANDIDATE_SCHEMA_VERSION = "ocr-candidate-v1"
OCR_EXECUTION_RECEIPT_SCHEMA_VERSION = "ocr-execution-receipt-v1"


class OCRAdmissionError(RuntimeError):
    pass


class ArtifactAdmissionConflictError(OCRAdmissionError):
    pass


class OCRExecutionConflictError(OCRAdmissionError):
    pass


class OCRExecutionPersistenceError(OCRAdmissionError):
    pass


class OCRExecutionReconstructionError(OCRExecutionPersistenceError):
    pass


class OCRAdmissionDependencyError(OCRAdmissionError):
    pass


class OCRAdmissionValidationError(ValueError):
    pass


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class AdmitExternalOCRExecution:
    artifact: ArtifactReference
    result: OCRResult
    candidate_schema_version: str = OCR_CANDIDATE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, ArtifactReference):
            raise TypeError("artifact must be ArtifactReference")
        if not isinstance(self.result, OCRResult):
            raise TypeError("result must be OCRResult")
        if self.result.artifact_id != self.artifact.artifact_id:
            raise ValueError("OCR result artifact_id must match ArtifactReference")
        if self.result.executed_at < self.artifact.captured_at:
            raise OCRAdmissionValidationError(
                "OCR execution cannot precede Artifact capture"
            )
        if any(not field.raw_text.strip() for field in self.result.fields):
            raise OCRAdmissionValidationError(
                "OCR field raw_text must be non-empty for Candidate admission"
            )
        object.__setattr__(
            self,
            "candidate_schema_version",
            _text(self.candidate_schema_version, "candidate_schema_version"),
        )


@dataclass(frozen=True, slots=True)
class ArtifactAdmissionRecord:
    artifact: ArtifactReference
    admitted_at: datetime
    schema_version: str = ARTIFACT_ADMISSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, ArtifactReference):
            raise TypeError("artifact must be ArtifactReference")
        object.__setattr__(self, "admitted_at", _aware(self.admitted_at, "admitted_at"))
        object.__setattr__(
            self, "schema_version", _text(self.schema_version, "schema_version")
        )

    @property
    def replay_key(self) -> tuple[str, str]:
        return self.artifact.artifact_id, self.artifact.sha256


@dataclass(frozen=True, slots=True)
class OCRExecutionRecord:
    artifact: ArtifactReference
    result: OCRResult

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, ArtifactReference):
            raise TypeError("artifact must be ArtifactReference")
        if not isinstance(self.result, OCRResult):
            raise TypeError("result must be OCRResult")
        if self.result.artifact_id != self.artifact.artifact_id:
            raise ValueError("OCR result artifact_id must match execution artifact")

    @property
    def replay_key(self) -> tuple[OCRProvider, str, str]:
        return self.result.provider, self.result.request_id, self.artifact.artifact_id


@dataclass(frozen=True, slots=True)
class OCRExecutionReceipt:
    provider: OCRProvider
    request_id: str
    artifact_id: str
    artifact_sha256: str
    ordered_candidate_ids: tuple[str, ...]
    candidate_schema_version: str
    committed_at: datetime
    schema_version: str = OCR_EXECUTION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        try:
            provider = OCRProvider(self.provider)
        except ValueError as error:
            raise ValueError("unsupported OCR provider") from error
        candidate_ids = tuple(
            _text(candidate_id, "candidate_id")
            for candidate_id in self.ordered_candidate_ids
        )
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("ordered_candidate_ids cannot contain duplicates")
        object.__setattr__(self, "provider", provider)
        object.__setattr__(self, "request_id", _text(self.request_id, "request_id"))
        object.__setattr__(self, "artifact_id", _text(self.artifact_id, "artifact_id"))
        object.__setattr__(
            self, "artifact_sha256", _text(self.artifact_sha256, "artifact_sha256")
        )
        object.__setattr__(self, "ordered_candidate_ids", candidate_ids)
        object.__setattr__(
            self,
            "candidate_schema_version",
            _text(self.candidate_schema_version, "candidate_schema_version"),
        )
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        object.__setattr__(
            self, "schema_version", _text(self.schema_version, "schema_version")
        )

    @property
    def replay_key(self) -> tuple[OCRProvider, str, str]:
        return self.provider, self.request_id, self.artifact_id


@dataclass(frozen=True, slots=True)
class OCRAdmissionWriteSet:
    artifact_admission: ArtifactAdmissionRecord | None
    candidates: tuple[OCRCandidate, ...]
    receipt: OCRExecutionReceipt

    def __post_init__(self) -> None:
        if self.artifact_admission is not None and not isinstance(
            self.artifact_admission, ArtifactAdmissionRecord
        ):
            raise TypeError("artifact_admission must be ArtifactAdmissionRecord or None")
        candidates = tuple(self.candidates)
        if any(not isinstance(candidate, OCRCandidate) for candidate in candidates):
            raise TypeError("candidates must contain OCRCandidate values")
        if not isinstance(self.receipt, OCRExecutionReceipt):
            raise TypeError("receipt must be OCRExecutionReceipt")
        object.__setattr__(self, "candidates", candidates)


@dataclass(frozen=True, slots=True)
class ExternalOCRAdmissionResult:
    artifact_admission: ArtifactAdmissionRecord
    execution: OCRExecutionRecord
    receipt: OCRExecutionReceipt
    candidates: tuple[OCRCandidate, ...]
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.artifact_admission, ArtifactAdmissionRecord):
            raise TypeError("artifact_admission must be ArtifactAdmissionRecord")
        if not isinstance(self.execution, OCRExecutionRecord):
            raise TypeError("execution must be OCRExecutionRecord")
        if not isinstance(self.receipt, OCRExecutionReceipt):
            raise TypeError("receipt must be OCRExecutionReceipt")
        candidates = tuple(self.candidates)
        if any(not isinstance(candidate, OCRCandidate) for candidate in candidates):
            raise TypeError("candidates must contain OCRCandidate values")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")
        object.__setattr__(self, "candidates", candidates)


FreshOCRAdmissionFactory = Callable[[bool], OCRAdmissionWriteSet]


@runtime_checkable
class OCRExecutionPersistence(Protocol):
    def admit_external_execution(
        self,
        execution: OCRExecutionRecord,
        prepare_fresh: FreshOCRAdmissionFactory,
    ) -> ExternalOCRAdmissionResult: ...


class ExternalOCRCandidateAdmission:
    def __init__(
        self,
        *,
        persistence: OCRExecutionPersistence,
        candidate_identity_supplier: Callable[[], str],
        artifact_admission_clock: Callable[[], datetime],
        receipt_clock: Callable[[], datetime],
    ) -> None:
        if not isinstance(persistence, OCRExecutionPersistence):
            raise TypeError("persistence must implement OCRExecutionPersistence")
        for value, name in (
            (candidate_identity_supplier, "candidate_identity_supplier"),
            (artifact_admission_clock, "artifact_admission_clock"),
            (receipt_clock, "receipt_clock"),
        ):
            if not callable(value):
                raise TypeError(f"{name} must be callable")
        self._persistence = persistence
        self._candidate_identity_supplier = candidate_identity_supplier
        self._artifact_admission_clock = artifact_admission_clock
        self._receipt_clock = receipt_clock

    def execute(self, command: AdmitExternalOCRExecution) -> ExternalOCRAdmissionResult:
        if not isinstance(command, AdmitExternalOCRExecution):
            raise TypeError("command must be AdmitExternalOCRExecution")
        execution = OCRExecutionRecord(command.artifact, command.result)

        def prepare_fresh(is_new_artifact: bool) -> OCRAdmissionWriteSet:
            try:
                candidate_ids = tuple(
                    _text(self._candidate_identity_supplier(), "candidate_id")
                    for _ in command.result.fields
                )
                if len(candidate_ids) != len(set(candidate_ids)):
                    raise ValueError("candidate identity supplier returned duplicates")
                candidates = tuple(
                    OCRCandidate(
                        candidate_id=candidate_id,
                        artifact=command.artifact,
                        field_name=field.field_name,
                        raw_text=field.raw_text,
                        normalized_value=field.normalized_value,
                        confidence=field.confidence,
                        captured_at=command.result.executed_at,
                        schema_version=command.candidate_schema_version,
                    )
                    for candidate_id, field in zip(
                        candidate_ids, command.result.fields, strict=True
                    )
                )
                artifact_admission = (
                    ArtifactAdmissionRecord(
                        command.artifact,
                        _aware(self._artifact_admission_clock(), "artifact_admitted_at"),
                    )
                    if is_new_artifact
                    else None
                )
                receipt = OCRExecutionReceipt(
                    provider=command.result.provider,
                    request_id=command.result.request_id,
                    artifact_id=command.artifact.artifact_id,
                    artifact_sha256=command.artifact.sha256,
                    ordered_candidate_ids=candidate_ids,
                    candidate_schema_version=command.candidate_schema_version,
                    committed_at=_aware(self._receipt_clock(), "receipt_committed_at"),
                )
                return OCRAdmissionWriteSet(artifact_admission, candidates, receipt)
            except OCRAdmissionError:
                raise
            except Exception as error:
                raise OCRAdmissionDependencyError(
                    "external OCR admission dependency failed"
                ) from error

        return self._persistence.admit_external_execution(execution, prepare_fresh)


__all__ = [
    "ARTIFACT_ADMISSION_SCHEMA_VERSION",
    "OCR_CANDIDATE_SCHEMA_VERSION",
    "OCR_EXECUTION_RECEIPT_SCHEMA_VERSION",
    "AdmitExternalOCRExecution",
    "ArtifactAdmissionConflictError",
    "ArtifactAdmissionRecord",
    "ExternalOCRAdmissionResult",
    "ExternalOCRCandidateAdmission",
    "FreshOCRAdmissionFactory",
    "OCRAdmissionDependencyError",
    "OCRAdmissionError",
    "OCRAdmissionWriteSet",
    "OCRAdmissionValidationError",
    "OCRExecutionConflictError",
    "OCRExecutionPersistence",
    "OCRExecutionPersistenceError",
    "OCRExecutionReceipt",
    "OCRExecutionReconstructionError",
    "OCRExecutionRecord",
]
