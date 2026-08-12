from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Callable

from app.application.operational_opportunity_eligibility import (
    OperationalOpportunityBindingConflictError,
    OperationalOpportunityBindingUnavailableError,
    get_operational_opportunity_eligibility,
)
from app.domain.market_intelligence.competition_v2 import (
    CompetitionV2Assessment,
    CompetitionV2Cohort,
    analyze_competition_v2,
    cohort_to_data,
)


class CompetitionV2AdmissionNotFoundError(LookupError): pass
class CompetitionV2AdmissionConflictError(ValueError): pass
class CompetitionV2AdmissionUnavailableError(RuntimeError): pass


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class FinalizeCompetitionV2AdmissionCommand:
    opportunity_id: str
    command_id: str
    operator_id: str
    submitted_at: datetime
    cohort: CompetitionV2Cohort

    def __post_init__(self) -> None:
        for name in ("opportunity_id", "command_id", "operator_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
            object.__setattr__(self, name, value.strip())
        if not isinstance(self.cohort, CompetitionV2Cohort):
            raise TypeError("cohort must be CompetitionV2Cohort")
        if self.cohort.operator_id != self.operator_id:
            raise ValueError("cohort operator must match command operator")
        if self.submitted_at.tzinfo is None or self.submitted_at.utcoffset() is None:
            raise ValueError("submitted_at must be timezone-aware")

    def authority_fingerprint(self) -> str:
        return _hash(cohort_to_data(self.cohort))

    def fingerprint(self) -> str:
        return _hash({"namespace": "competition-v2-admission", "opportunity_id": self.opportunity_id,
            "command_id": self.command_id, "operator_id": self.operator_id,
            "submitted_at": self.submitted_at.isoformat(), "cohort": cohort_to_data(self.cohort)})


@dataclass(frozen=True, slots=True)
class CompetitionV2Publication:
    opportunity_id: str
    cohort: CompetitionV2Cohort
    assessment: CompetitionV2Assessment
    committed_at: datetime


@dataclass(frozen=True, slots=True)
class CompetitionV2AdmissionResult:
    publication: CompetitionV2Publication
    replayed: bool
    aliased: bool = False


class FinalizeCompetitionV2Admission:
    def __init__(self, opportunities, repository, *, clock: Callable[[], datetime] | None = None):
        self._opportunities, self._repository = opportunities, repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def execute(self, command: FinalizeCompetitionV2AdmissionCommand) -> CompetitionV2AdmissionResult:
        fingerprint = command.fingerprint()
        receipt = self._repository.get_receipt(command.command_id)
        if receipt is not None:
            if receipt["command_fingerprint"] != fingerprint:
                raise CompetitionV2AdmissionConflictError("Competition v2 command conflicts with committed receipt")
            publication = self._repository.get_publication(receipt["cohort_id"])
            if publication is None:
                raise CompetitionV2AdmissionUnavailableError("committed Competition v2 publication is unavailable")
            return CompetitionV2AdmissionResult(publication, True)
        try:
            eligibility = get_operational_opportunity_eligibility(self._opportunities, command.opportunity_id)
        except OperationalOpportunityBindingConflictError as error:
            raise CompetitionV2AdmissionConflictError(str(error)) from error
        except OperationalOpportunityBindingUnavailableError as error:
            raise CompetitionV2AdmissionUnavailableError(str(error)) from error
        if eligibility is None:
            raise CompetitionV2AdmissionNotFoundError(command.opportunity_id)
        subject = eligibility.market_binding.market_observation_identity if eligibility.market_binding else (
            eligibility.target_binding.target_identity if eligibility.target_binding else None)
        if subject is None:
            raise CompetitionV2AdmissionConflictError("Opportunity has no operational assessment subject")
        if subject != command.cohort.subject:
            raise CompetitionV2AdmissionConflictError("Competition v2 subject conflicts with Opportunity")
        authority_fingerprint = command.authority_fingerprint()
        existing = self._repository.get_publication(command.cohort.cohort_id)
        if existing is not None:
            if existing.opportunity_id != command.opportunity_id or self._repository.get_authority_fingerprint(command.cohort.cohort_id) != authority_fingerprint:
                raise CompetitionV2AdmissionConflictError("Competition v2 cohort conflicts with committed authority")
            self._repository.save_alias_receipt(command.command_id, fingerprint, command.cohort.cohort_id,
                command.opportunity_id, command.operator_id, self._clock())
            return CompetitionV2AdmissionResult(existing, False, True)
        committed_at = self._clock()
        publication = CompetitionV2Publication(command.opportunity_id, command.cohort,
            analyze_competition_v2(command.cohort, generated_at=committed_at), committed_at)
        try:
            self._repository.finalize(publication, command.command_id, fingerprint,
                authority_fingerprint, command.operator_id)
        except CompetitionV2AdmissionConflictError:
            raise
        except Exception as error:
            raise CompetitionV2AdmissionUnavailableError("Competition v2 persistence unavailable") from error
        return CompetitionV2AdmissionResult(publication, False)
