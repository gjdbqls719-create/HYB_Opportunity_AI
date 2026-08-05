"""Economics calculator ownership with explicit cross-stage Price provenance."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Callable, Protocol

from app.application.candidate_promotion import (
    CandidateOpportunityBinding,
    CandidatePromotionRepository,
)
from app.application.price_analysis import PriceAnalysisRepository
from app.application.verified_economics_snapshot import VerifiedEconomicsSnapshot
from app.domain.decision_engine import OpportunityIdentity
from app.domain.economics_calculation_snapshot import (
    EconomicsAnalysisSnapshot, EconomicsCalculationParameters,
    EconomicsCalculationSnapshot, ProfitabilityResultSnapshot,
)
from app.domain.market_intelligence import MarketObservationIdentity
from app.domain.opportunity import EconomicEvidence, EconomicsCalculation, EvidenceStatus, MoneyInput
from app.domain.price_intelligence import PriceIntelligenceSnapshot
from engine.opportunity import calculate_verified_economics


ECONOMICS_SOURCE_CONTEXT_SCHEMA_VERSION="economics-calculation-source-v1"
ECONOMICS_OWNER_COMMAND_SCHEMA_VERSION="economics-owner-command-v1"
ECONOMICS_CALCULATION_RECEIPT_SCHEMA_VERSION="economics-calculation-receipt-v1"


class EconomicsCalculationOwnerPersistenceError(RuntimeError):pass
class EconomicsCalculationCommandConflictError(EconomicsCalculationOwnerPersistenceError):pass
class EconomicsCalculationSourceNotFoundError(EconomicsCalculationOwnerPersistenceError):pass
class EconomicsCalculationBindingConflictError(EconomicsCalculationOwnerPersistenceError):pass
class EconomicsCalculationPriceSourceConflictError(EconomicsCalculationOwnerPersistenceError):pass
class EconomicsCalculationVerifiedSourceConflictError(EconomicsCalculationOwnerPersistenceError):pass
class EconomicsCalculationMarketIdentityConflictError(EconomicsCalculationOwnerPersistenceError):pass
class EconomicsCalculationExecutionError(RuntimeError):pass
class MalformedEconomicsCalculationReceiptError(EconomicsCalculationOwnerPersistenceError):pass
class UnsupportedEconomicsCalculationReceiptVersionError(MalformedEconomicsCalculationReceiptError):pass
class EconomicsCalculationReceiptPersistenceError(EconomicsCalculationOwnerPersistenceError):pass
class EconomicsCalculationOwnerCommitError(EconomicsCalculationOwnerPersistenceError):pass


def _text(value,name):
    if not isinstance(value,str) or not value.strip():raise ValueError(f"{name} must be non-empty text")
    return value.strip()
def _aware(value,name):
    if not isinstance(value,datetime) or value.tzinfo is None or value.utcoffset() is None:raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True,slots=True)
class EconomicsCalculationSourceContext:
    opportunity_id:str
    candidate_opportunity_binding_id:str
    candidate_id:str
    price_intelligence_snapshot_id:str
    price_analysis_command_id:str
    verified_economics_opportunity_id:str
    market_observation_identity:MarketObservationIdentity
    economics_calculation_command_id:str
    requested_at:datetime
    schema_version:str=ECONOMICS_SOURCE_CONTEXT_SCHEMA_VERSION
    def __post_init__(self):
        for name in ("opportunity_id","candidate_opportunity_binding_id","candidate_id","price_intelligence_snapshot_id","price_analysis_command_id","verified_economics_opportunity_id","economics_calculation_command_id"): _text(getattr(self,name),name)
        if self.opportunity_id==self.candidate_id:raise ValueError("Candidate and Opportunity identities must remain separate")
        if not isinstance(self.market_observation_identity,MarketObservationIdentity):raise TypeError("market_observation_identity must be MarketObservationIdentity")
        _aware(self.requested_at,"requested_at")
        if self.schema_version!=ECONOMICS_SOURCE_CONTEXT_SCHEMA_VERSION:raise ValueError("unsupported Economics source context version")


@dataclass(frozen=True,slots=True)
class CalculateAndPersistEconomicsCommand:
    command_id:str
    source:EconomicsCalculationSourceContext
    calculation_parameters:EconomicsCalculationParameters
    calculation_version:str
    requested_at:datetime
    schema_version:str=ECONOMICS_OWNER_COMMAND_SCHEMA_VERSION
    def __post_init__(self):
        _text(self.command_id,"command_id");_text(self.calculation_version,"calculation_version")
        if not isinstance(self.source,EconomicsCalculationSourceContext):raise TypeError("source must be EconomicsCalculationSourceContext")
        if self.command_id!=self.source.economics_calculation_command_id:raise ValueError("source command identity differs")
        if not isinstance(self.calculation_parameters,EconomicsCalculationParameters):raise TypeError("calculation_parameters must be EconomicsCalculationParameters")
        _aware(self.requested_at,"requested_at")
        if self.requested_at!=self.source.requested_at:raise ValueError("source and command requested_at differ")
        if self.schema_version!=ECONOMICS_OWNER_COMMAND_SCHEMA_VERSION:raise ValueError("unsupported Economics owner command version")
    @property
    def fingerprint(self):
        p=self.calculation_parameters
        payload={"source":repr(self.source),"parameters":{"marketplace":p.marketplace,"minimum_net_profit":str(p.minimum_net_profit),"minimum_roi":str(p.minimum_roi),"estimated_monthly_sales":p.estimated_monthly_sales,"competitor_count":p.competitor_count,"risk_level":p.risk_level,"context":repr(p.context_items)},"calculation_version":self.calculation_version,"requested_at":self.requested_at.isoformat(),"schema_version":self.schema_version}
        return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True,slots=True)
class EconomicsSnapshotProductionRequest:
    command_id:str
    opportunity_id:str
    price_analysis_command_id:str
    calculation_parameters:EconomicsCalculationParameters
    calculation_version:str
    requested_at:datetime
    def __post_init__(self):
        for name in (
            "command_id",
            "opportunity_id",
            "price_analysis_command_id",
            "calculation_version",
        ):
            object.__setattr__(self,name,_text(getattr(self,name),name))
        if not isinstance(self.calculation_parameters,EconomicsCalculationParameters):
            raise TypeError("calculation_parameters must be EconomicsCalculationParameters")
        _aware(self.requested_at,"requested_at")


@dataclass(frozen=True,slots=True)
class EconomicsCalculationReceipt:
    command_id:str;opportunity_id:str;candidate_id:str;candidate_opportunity_binding_id:str
    price_intelligence_snapshot_id:str;verified_economics_opportunity_id:str
    price_analysis_command_id:str
    economics_snapshot_id:str;command_fingerprint:str;calculation_version:str
    requested_at:datetime;generated_at:datetime;committed_at:datetime
    schema_version:str=ECONOMICS_CALCULATION_RECEIPT_SCHEMA_VERSION
    def __post_init__(self):
        for name in ("command_id","opportunity_id","candidate_id","candidate_opportunity_binding_id","price_intelligence_snapshot_id","price_analysis_command_id","verified_economics_opportunity_id","economics_snapshot_id","command_fingerprint","calculation_version"):_text(getattr(self,name),name)
        if len(self.command_fingerprint)!=64 or any(v not in "0123456789abcdef" for v in self.command_fingerprint):raise ValueError("command_fingerprint must be SHA-256 text")
        for name in ("requested_at","generated_at","committed_at"):_aware(getattr(self,name),name)
        if self.schema_version!=ECONOMICS_CALCULATION_RECEIPT_SCHEMA_VERSION:raise UnsupportedEconomicsCalculationReceiptVersionError("unsupported Economics receipt version")


@dataclass(frozen=True,slots=True)
class EconomicsOwnerSources:
    binding:CandidateOpportunityBinding
    price_snapshot:PriceIntelligenceSnapshot
    verified_snapshot:VerifiedEconomicsSnapshot

@dataclass(frozen=True,slots=True)
class EconomicsOwnerResult:
    snapshot:EconomicsCalculationSnapshot;receipt:EconomicsCalculationReceipt;replayed:bool

class EconomicsOwnerRepository(Protocol):
    def get_receipt(self,command_id:str)->EconomicsCalculationReceipt|None:...
    def get_result(self,receipt:EconomicsCalculationReceipt)->EconomicsOwnerResult:...
    def load_sources(self,source:EconomicsCalculationSourceContext)->EconomicsOwnerSources:...
    def save_result(self,command:CalculateAndPersistEconomicsCommand,snapshot:EconomicsCalculationSnapshot,receipt:EconomicsCalculationReceipt)->EconomicsOwnerResult:...


class CalculateAndPersistEconomics:
    def __init__(self,repository:EconomicsOwnerRepository,*,snapshot_id_generator:Callable[[],str],generated_clock:Callable[[],datetime],receipt_clock:Callable[[],datetime],calculator:Callable[...,EconomicsCalculation]=calculate_verified_economics):
        self._repository=repository;self._id=snapshot_id_generator;self._generated=generated_clock;self._committed=receipt_clock;self._calculator=calculator
        if not all(callable(value) for value in (snapshot_id_generator,generated_clock,receipt_clock,calculator)):raise TypeError("owner dependencies must be callable")
    def execute(self,command):
        if not isinstance(command,CalculateAndPersistEconomicsCommand):raise TypeError("command must be CalculateAndPersistEconomicsCommand")
        existing=self._repository.get_receipt(command.command_id)
        if existing is not None:
            if existing.command_fingerprint!=command.fingerprint:raise EconomicsCalculationCommandConflictError("Economics command payload conflicts")
            result=self._repository.get_result(existing);return EconomicsOwnerResult(result.snapshot,result.receipt,True)
        sources=self._repository.load_sources(command.source);p=command.calculation_parameters
        try:
            result=self._calculator(marketplace=p.marketplace,economics=sources.verified_snapshot.inputs,minimum_net_profit=p.minimum_net_profit,minimum_roi=p.minimum_roi,estimated_monthly_sales=p.estimated_monthly_sales,competitor_count=p.competitor_count,risk_level=p.risk_level,context=dict(p.context_items))
        except Exception as error:raise EconomicsCalculationExecutionError("Economics calculator execution failed") from error
        if not isinstance(result,EconomicsCalculation):raise EconomicsCalculationExecutionError("Economics calculator returned malformed result")
        snapshot_id=_text(self._id(),"snapshot_id");generated_at=self._generated();committed_at=self._committed();_aware(generated_at,"generated_at");_aware(committed_at,"committed_at")
        evidence=EconomicEvidence(EvidenceStatus.UNSUPPORTED,"legacy_calculator")
        profitability=ProfitabilityResultSnapshot(p.minimum_net_profit,p.minimum_roi,result.analysis["passes_net_profit_filter"],result.analysis["passes_roi_filter"],result.analysis["passes_profitability_filter"])
        snapshot=EconomicsCalculationSnapshot(snapshot_id,OpportunityIdentity(command.source.opportunity_id,sources.binding.discovery_reference),command.source.market_observation_identity,command.source.candidate_opportunity_binding_id,command.source.candidate_id,command.source.price_intelligence_snapshot_id,command.source.verified_economics_opportunity_id,result.inputs.expected_sale_price,result.marketplace_fee,result.payment_fee,result.tax_cost,result.landed_cost,result.selling_cost,result.total_cost,result.net_profit,result.roi,result.landed_cost_roi,result.margin_rate,MoneyInput(None,result.inputs.currency,evidence),profitability,p,EconomicsAnalysisSnapshot.from_runtime(result.analysis),command.calculation_version,generated_at)
        receipt=EconomicsCalculationReceipt(command.command_id,command.source.opportunity_id,command.source.candidate_id,command.source.candidate_opportunity_binding_id,command.source.price_intelligence_snapshot_id,command.source.verified_economics_opportunity_id,command.source.price_analysis_command_id,snapshot_id,command.fingerprint,command.calculation_version,command.requested_at,generated_at,committed_at)
        return self._repository.save_result(command,snapshot,receipt)


class EconomicsSnapshotProductionEntry:
    """Composes persisted promotion and Price facts with the Economics owner."""

    def __init__(self,*,promotion_repository:CandidatePromotionRepository,
                 price_analysis_repository:PriceAnalysisRepository,
                 economics_repository:EconomicsOwnerRepository,
                 snapshot_id_generator:Callable[[],str],
                 generated_clock:Callable[[],datetime],
                 receipt_clock:Callable[[],datetime],
                 calculator:Callable[...,EconomicsCalculation]=calculate_verified_economics):
        self._promotions=promotion_repository
        self._prices=price_analysis_repository
        self._calculate=CalculateAndPersistEconomics(
            economics_repository,snapshot_id_generator=snapshot_id_generator,
            generated_clock=generated_clock,receipt_clock=receipt_clock,
            calculator=calculator)

    def execute(self,request:EconomicsSnapshotProductionRequest)->EconomicsOwnerResult:
        if not isinstance(request,EconomicsSnapshotProductionRequest):
            raise TypeError("request must be EconomicsSnapshotProductionRequest")
        binding=self._promotions.get_promotion_by_opportunity(request.opportunity_id)
        if binding is None:
            raise EconomicsCalculationSourceNotFoundError("persisted Opportunity promotion is missing")
        if binding.opportunity_id!=request.opportunity_id:
            raise EconomicsCalculationBindingConflictError("Opportunity promotion binding differs")
        price_receipt=self._prices.get_receipt(request.price_analysis_command_id)
        if price_receipt is None:
            raise EconomicsCalculationSourceNotFoundError("persisted Price analysis is missing")
        price_result=self._prices.get_result(price_receipt)
        price_snapshot=price_result.snapshot
        if price_snapshot.candidate_identity.candidate_id!=binding.candidate_id:
            raise EconomicsCalculationPriceSourceConflictError("Price source Candidate differs")
        if price_snapshot.market_observation_identity!=binding.market_observation_identity:
            raise EconomicsCalculationMarketIdentityConflictError("Price source Market identity differs")
        source=EconomicsCalculationSourceContext(
            opportunity_id=binding.opportunity_id,
            candidate_opportunity_binding_id=binding.binding_id,
            candidate_id=binding.candidate_id,
            price_intelligence_snapshot_id=price_snapshot.snapshot_id,
            price_analysis_command_id=price_receipt.command_id,
            verified_economics_opportunity_id=binding.opportunity_id,
            market_observation_identity=binding.market_observation_identity,
            economics_calculation_command_id=request.command_id,
            requested_at=request.requested_at)
        command=CalculateAndPersistEconomicsCommand(
            command_id=request.command_id,source=source,
            calculation_parameters=request.calculation_parameters,
            calculation_version=request.calculation_version,
            requested_at=request.requested_at)
        return self._calculate.execute(command)

__all__=[name for name in globals() if name.startswith("Economics") or name.startswith("CalculateAnd") or name.startswith("MalformedEconomics") or name.startswith("UnsupportedEconomics")]
