from __future__ import annotations

from typing import Protocol

from app.application.sourcing.models import (
    AdmitFounderSourcingCommand,
    ReviseFounderSourcingQuoteCommand,
    SourcingAdmissionReceipt,
    SourcingAdmissionResult,
)
from app.domain.sourcing import FounderSourcingAdmission
from app.domain.opportunity import DomesticSellingOpportunityAdmission


class SourcingAuthorityRepository(Protocol):
    def get_domestic_selling_admission(
        self, admission_id: str
    ) -> DomesticSellingOpportunityAdmission | None: ...

    def save_admission(
        self,
        command: AdmitFounderSourcingCommand,
        admission: FounderSourcingAdmission,
        receipt: SourcingAdmissionReceipt,
    ) -> SourcingAdmissionResult: ...

    def save_quote_revision(
        self,
        command: ReviseFounderSourcingQuoteCommand,
        admission: FounderSourcingAdmission,
        receipt: SourcingAdmissionReceipt,
    ) -> SourcingAdmissionResult: ...

    def validate_replay(
        self, command_id: str, fingerprint: str
    ) -> SourcingAdmissionResult | None: ...

    def get_admission(self, admission_id: str) -> FounderSourcingAdmission | None: ...

    def get_admission_revision(
        self, admission_id: str, revision: int
    ) -> FounderSourcingAdmission | None: ...

    def get_receipt(self, command_id: str) -> SourcingAdmissionReceipt | None: ...
