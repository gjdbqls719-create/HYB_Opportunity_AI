from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from app.application.assessment_snapshot import CompetitionAssessmentSnapshot
from app.application.decision_composition import (
    ASSESSMENT_SCHEMA_VERSION,
    COMPETITION_POLICY_VERSION,
    FRESHNESS_WINDOW,
)
from app.application.operational_opportunity_eligibility import (
    OperationalOpportunityBindingConflictError,
    OperationalOpportunityBindingUnavailableError,
    get_operational_opportunity_eligibility,
)
from app.domain.decision_engine import DecisionEvidenceAvailability, DecisionFreshness
from app.domain.market_intelligence import (
    CompetitionObservation,
    analyze_competition,
    is_new_to_market_target_subject,
)


TARGET_ASSESSMENT_SCHEMA_VERSION = "market-assessment-target-v1"


class CompetitionAdmissionNotFoundError(LookupError): pass
class CompetitionAdmissionConflictError(ValueError): pass
class CompetitionAdmissionUnavailableError(RuntimeError): pass


@dataclass(frozen=True, slots=True)
class FinalizeCompetitionObservationAdmissionCommand:
    opportunity_id: str
    command_id: str
    operator_id: str
    observation: CompetitionObservation
    generated_at: datetime

    def __post_init__(self):
        for name in ("opportunity_id", "command_id", "operator_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
            object.__setattr__(self, name, value.strip())
        if not isinstance(self.observation, CompetitionObservation):
            raise TypeError("observation must be CompetitionObservation")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None:
            raise ValueError("generated_at must be timezone-aware")

    def fingerprint(self) -> str:
        evidence = {}
        for name, item in sorted(self.observation.evidence.items()):
            evidence[name] = {"value": str(item.value) if item.value is not None else None,
                "value_type": type(item.value).__name__, "source": item.source,
                "reference": item.reference, "observed_at": item.observed_at.isoformat() if item.observed_at else None,
                "status": item.status.value, "confidence": str(item.confidence), "market": item.market,
                "marketplace": item.marketplace, "collection_method": item.collection_method,
                "keyword": item.keyword, "category": item.category, "marketplace_item_id": item.marketplace_item_id,
                "canonical_product_id": item.canonical_product_id, "unit": item.unit}
        payload = {"opportunity_id": self.opportunity_id, "command_id": self.command_id,
            "operator_id": self.operator_id, "generated_at": self.generated_at.isoformat(),
            "observation_id": self.observation.observation_id, "observed_at": self.observation.observed_at.isoformat(),
            "identity": repr(self.observation.identity), "evidence": evidence}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class CompetitionAdmissionResult:
    observation: CompetitionObservation
    snapshot: CompetitionAssessmentSnapshot
    replayed: bool


class FinalizeCompetitionObservationAdmission:
    def __init__(self, opportunities, observations):
        self._opportunities, self._observations = opportunities, observations

    def execute(self, command: FinalizeCompetitionObservationAdmissionCommand) -> CompetitionAdmissionResult:
        fingerprint = command.fingerprint()
        receipt = self._observations.get_competition_admission_receipt(command.command_id)
        if receipt:
            if receipt["fingerprint"] != fingerprint:
                raise CompetitionAdmissionConflictError("competition command payload conflicts with committed receipt")
            observation = self._observations.get_observation_by_id(receipt["observation_id"])
            snapshot = self._observations.get_competition_assessment_snapshot(receipt["snapshot_id"])
            if observation is None or snapshot is None:
                raise CompetitionAdmissionUnavailableError("committed competition admission is unavailable")
            return CompetitionAdmissionResult(observation, snapshot, True)
        try:
            eligibility = get_operational_opportunity_eligibility(
                self._opportunities,
                command.opportunity_id,
            )
        except OperationalOpportunityBindingConflictError as error:
            raise CompetitionAdmissionConflictError(str(error)) from error
        except OperationalOpportunityBindingUnavailableError as error:
            raise CompetitionAdmissionUnavailableError(str(error)) from error
        if eligibility is None:
            raise CompetitionAdmissionNotFoundError(command.opportunity_id)
        subject = None
        if eligibility.market_binding is not None:
            subject = eligibility.market_binding.market_observation_identity
        elif eligibility.target_binding is not None:
            subject = eligibility.target_binding.target_identity
        if subject is None or subject != command.observation.identity:
            raise CompetitionAdmissionConflictError("competition observation identity conflicts with Opportunity")
        assessment = analyze_competition(command.observation, generated_at=command.generated_at)
        freshness = (DecisionFreshness.FRESH if command.generated_at - command.observation.observed_at <= FRESHNESS_WINDOW
                     else DecisionFreshness.STALE)
        snapshot_schema = (
            TARGET_ASSESSMENT_SCHEMA_VERSION
            if is_new_to_market_target_subject(command.observation.identity)
            else ASSESSMENT_SCHEMA_VERSION
        )
        snapshot = CompetitionAssessmentSnapshot(
            f"competition-assessment:{command.observation.observation_id}", command.observation.identity,
            command.observation.observation_id, assessment, DecisionEvidenceAvailability.COMPLETE,
            assessment.confidence, freshness, command.generated_at, snapshot_schema,
            COMPETITION_POLICY_VERSION)
        self._observations.finalize_competition_admission(
            command.observation, snapshot, command.opportunity_id, command.command_id,
            fingerprint, command.operator_id)
        return CompetitionAdmissionResult(command.observation, snapshot, False)
