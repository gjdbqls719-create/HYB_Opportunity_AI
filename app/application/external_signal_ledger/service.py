from __future__ import annotations

from app.application.external_signal_ledger.ports import ExternalSignalLedgerRepository
from app.application.external_signal_ledger.use_cases import (
    GetLatestVerification,
    GetVerificationHistory,
    SaveHumanVerification,
    SaveOCRCandidate,
)
from app.domain.market_intelligence import HumanVerification, OCRCandidate


class ExternalSignalLedgerService:
    def __init__(self, repository: ExternalSignalLedgerRepository) -> None:
        if not isinstance(repository, ExternalSignalLedgerRepository):
            raise TypeError("repository must implement ExternalSignalLedgerRepository")
        self._repository = repository

    def save_candidate(self, command: SaveOCRCandidate) -> OCRCandidate:
        self._repository.save_candidate(command.candidate)
        return command.candidate

    def save_verification(self, command: SaveHumanVerification) -> HumanVerification:
        self._repository.save_verification(command.verification)
        return command.verification

    def get_latest_verification(
        self, query: GetLatestVerification
    ) -> HumanVerification | None:
        return self._repository.get_latest_verification(query.candidate_id)

    def get_verification_history(
        self, query: GetVerificationHistory
    ) -> tuple[HumanVerification, ...]:
        return self._repository.get_verification_history(
            query.candidate_id, limit=query.limit
        )
