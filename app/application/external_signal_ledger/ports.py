from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.domain.market_intelligence import HumanVerification, OCRCandidate, OCRField


class DuplicateExternalSignalLedgerError(ValueError):
    pass


@runtime_checkable
class ExternalSignalLedgerRepository(Protocol):
    def save_candidate(self, candidate: OCRCandidate) -> None: ...
    def save_verification(self, verification: HumanVerification) -> None: ...
    def get_latest_candidate(
        self, artifact_id: str, field_name: OCRField
    ) -> OCRCandidate | None: ...
    def get_candidate_history(
        self, artifact_id: str, field_name: OCRField, *, limit: int | None = None
    ) -> tuple[OCRCandidate, ...]: ...
    def get_latest_verification(self, candidate_id: str) -> HumanVerification | None: ...
    def get_verification_history(
        self, candidate_id: str, *, limit: int | None = None
    ) -> tuple[HumanVerification, ...]: ...
