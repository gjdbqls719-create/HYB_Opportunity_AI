from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from app.application.assessment_snapshot import DemandAssessmentSnapshot
from app.application.decision_composition import ASSESSMENT_SCHEMA_VERSION, DEMAND_POLICY_VERSION, FRESHNESS_WINDOW
from app.domain.decision_engine import DecisionEvidenceAvailability, DecisionFreshness
from app.domain.market_intelligence import DemandAssessmentAvailability, DemandObservation, analyze_demand


class DemandAdmissionNotFoundError(LookupError): pass
class DemandAdmissionConflictError(ValueError): pass
class DemandAdmissionUnavailableError(RuntimeError): pass


@dataclass(frozen=True, slots=True)
class FinalizeDemandObservationAdmissionCommand:
    opportunity_id: str
    command_id: str
    operator_id: str
    observation: DemandObservation
    generated_at: datetime

    def __post_init__(self):
        for name in ("opportunity_id", "command_id", "operator_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip(): raise ValueError(f"{name} must be non-empty text")
            object.__setattr__(self, name, value.strip())
        if not isinstance(self.observation, DemandObservation): raise TypeError("observation must be DemandObservation")
        if self.generated_at.tzinfo is None or self.generated_at.utcoffset() is None: raise ValueError("generated_at must be timezone-aware")

    def fingerprint(self):
        evidence = {name: {"value": str(item.value) if item.value is not None else None,
            "value_type": type(item.value).__name__, "source": item.source, "reference": item.reference,
            "observed_at": item.observed_at.isoformat() if item.observed_at else None, "status": item.status.value,
            "confidence": str(item.confidence), "market": item.market, "marketplace": item.marketplace,
            "collection_method": item.collection_method, "keyword": item.keyword, "category": item.category,
            "marketplace_item_id": item.marketplace_item_id, "canonical_product_id": item.canonical_product_id,
            "unit": item.unit} for name, item in sorted(self.observation.evidence.items())}
        payload = {"opportunity_id": self.opportunity_id, "command_id": self.command_id,
            "operator_id": self.operator_id, "generated_at": self.generated_at.isoformat(),
            "observation_id": self.observation.observation_id, "observed_at": self.observation.observed_at.isoformat(),
            "identity": repr(self.observation.identity), "evidence": evidence}
        return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class DemandAdmissionResult:
    observation: DemandObservation
    snapshot: DemandAssessmentSnapshot
    replayed: bool


class FinalizeDemandObservationAdmission:
    def __init__(self, opportunities, observations): self._opportunities, self._observations = opportunities, observations
    def execute(self, command):
        fingerprint = command.fingerprint(); receipt = self._observations.get_demand_admission_receipt(command.command_id)
        if receipt:
            if receipt["fingerprint"] != fingerprint: raise DemandAdmissionConflictError("demand command payload conflicts with committed receipt")
            observation = self._observations.get_observation_by_id(receipt["observation_id"])
            snapshot = self._observations.get_demand_assessment_snapshot(receipt["snapshot_id"])
            if observation is None or snapshot is None: raise DemandAdmissionUnavailableError("committed demand admission is unavailable")
            return DemandAdmissionResult(observation, snapshot, True)
        if self._opportunities.get_queue_item(command.opportunity_id) is None: raise DemandAdmissionNotFoundError(command.opportunity_id)
        binding = self._opportunities.get_market_identity_binding(command.opportunity_id)
        if binding is None or binding.market_observation_identity != command.observation.identity:
            raise DemandAdmissionConflictError("demand observation identity conflicts with Opportunity")
        assessment = analyze_demand(command.observation, generated_at=command.generated_at)
        availability = (DecisionEvidenceAvailability.COMPLETE if assessment.availability is DemandAssessmentAvailability.COMPLETE
                        else DecisionEvidenceAvailability.PARTIAL)
        freshness = DecisionFreshness.FRESH if command.generated_at - command.observation.observed_at <= FRESHNESS_WINDOW else DecisionFreshness.STALE
        snapshot = DemandAssessmentSnapshot(f"demand-assessment:{command.observation.observation_id}",
            command.observation.identity, command.observation.observation_id, assessment, availability,
            assessment.confidence, freshness, command.generated_at, ASSESSMENT_SCHEMA_VERSION, DEMAND_POLICY_VERSION)
        self._observations.finalize_demand_admission(command.observation, snapshot, command.opportunity_id,
            command.command_id, fingerprint, command.operator_id)
        return DemandAdmissionResult(command.observation, snapshot, False)
