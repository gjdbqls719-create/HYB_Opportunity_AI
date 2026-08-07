from __future__ import annotations

from dataclasses import dataclass

from app.application.sourcing.models import (
    AdmitFounderSourcingCommand,
    ReviseFounderSourcingQuoteCommand,
    SourcingAdmissionResult,
)
from app.application.sourcing.service import AdmitFounderSourcing, ReviseFounderSourcingQuote


@dataclass(frozen=True, slots=True)
class SourcingAuthorityProductionEntry:
    admission: AdmitFounderSourcing
    quote_revision: ReviseFounderSourcingQuote

    def admit(self, command: AdmitFounderSourcingCommand) -> SourcingAdmissionResult:
        return self.admission.execute(command)

    def revise(self, command: ReviseFounderSourcingQuoteCommand) -> SourcingAdmissionResult:
        return self.quote_revision.execute(command)


__all__ = ["SourcingAuthorityProductionEntry"]
