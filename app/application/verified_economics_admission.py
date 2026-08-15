from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from app.application.operational_opportunity_eligibility import (
    OperationalDomesticSellingTargetSubject,
    OperationalMarketIdentitySubject,
    OperationalOpportunityBindingConflictError,
    OperationalOpportunityBindingUnavailableError,
    get_operational_opportunity_eligibility,
)
from app.application.verified_economics_snapshot import VerifiedEconomicsSnapshot
from app.domain.opportunity import VerifiedEconomicsInput


class VerifiedEconomicsAdmissionNotFoundError(LookupError): pass
class VerifiedEconomicsAdmissionConflictError(ValueError): pass
class VerifiedEconomicsAdmissionPersistenceError(RuntimeError): pass


@dataclass(frozen=True, slots=True)
class VerifiedEconomicsAdmissionResult:
    snapshot: VerifiedEconomicsSnapshot
    replayed: bool


@dataclass(frozen=True, slots=True)
class FinalizeVerifiedEconomicsAdmissionCommand:
    opportunity_id: str
    command_id: str
    operator_id: str
    inputs: VerifiedEconomicsInput
    snapshot_at: datetime

    def __post_init__(self):
        for name in ("opportunity_id","command_id","operator_id"):
            value=getattr(self,name)
            if not isinstance(value,str) or not value.strip(): raise ValueError(f"{name} must be non-empty text")
            object.__setattr__(self,name,value.strip())
        if not isinstance(self.inputs,VerifiedEconomicsInput): raise TypeError("inputs must be VerifiedEconomicsInput")
        if not isinstance(self.snapshot_at,datetime) or self.snapshot_at.tzinfo is None or self.snapshot_at.utcoffset() is None: raise ValueError("snapshot_at must be timezone-aware")

    def fingerprint(self) -> str:
        def evidence(value):
            return {"status":value.status.value,"source":value.source,"observed_at":value.observed_at.isoformat() if value.observed_at else None,"reference":value.reference}
        values={}
        for name in ("purchase_cost","shipping_cost","marketplace_fee_rate","payment_fee_rate","fixed_fee","tax_rate","duty_cost","other_cost","expected_sale_price"):
            item=getattr(self.inputs,name); number=getattr(item,"amount",getattr(item,"rate",None))
            values[name]={"value":str(number) if number is not None else None,"currency":getattr(item,"currency",None),"evidence":evidence(item.evidence)}
        payload={"opportunity_id":self.opportunity_id,"command_id":self.command_id,"operator_id":self.operator_id,"snapshot_at":self.snapshot_at.isoformat(),"inputs":values}
        return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",",":")).encode()).hexdigest()


class FinalizeVerifiedEconomicsAdmission:
    def __init__(self, repository): self._repository=repository
    def execute(self, command: FinalizeVerifiedEconomicsAdmissionCommand) -> VerifiedEconomicsAdmissionResult:
        fingerprint=command.fingerprint(); receipt=self._repository.get_verified_economics_admission_receipt(command.command_id)
        if receipt is not None:
            if receipt["fingerprint"] != fingerprint: raise VerifiedEconomicsAdmissionConflictError("verified economics command payload conflicts with committed receipt")
            snapshot=self._repository.get_verified_economics_snapshot(receipt["opportunity_id"])
            if snapshot is None: raise VerifiedEconomicsAdmissionPersistenceError("committed verified economics snapshot is unavailable")
            return VerifiedEconomicsAdmissionResult(snapshot, True)
        try:
            eligibility = get_operational_opportunity_eligibility(
                self._repository,
                command.opportunity_id,
            )
        except OperationalOpportunityBindingConflictError as error:
            raise VerifiedEconomicsAdmissionConflictError(str(error)) from error
        except OperationalOpportunityBindingUnavailableError as error:
            raise VerifiedEconomicsAdmissionPersistenceError(str(error)) from error
        if eligibility is None: raise VerifiedEconomicsAdmissionNotFoundError(command.opportunity_id)
        if not isinstance(
            eligibility.subject,
            (OperationalMarketIdentitySubject, OperationalDomesticSellingTargetSubject),
        ):
            raise VerifiedEconomicsAdmissionConflictError(
                "opportunity operational subject is missing or unsupported"
            )
        if self._repository.get_verified_economics_snapshot(command.opportunity_id) is not None: raise VerifiedEconomicsAdmissionConflictError("verified economics snapshot already exists")
        snapshot=VerifiedEconomicsSnapshot(command.opportunity_id,command.inputs,command.snapshot_at)
        saved = self._repository.finalize_verified_economics_admission(snapshot,command.command_id,fingerprint,command.operator_id)
        return VerifiedEconomicsAdmissionResult(saved, False)
