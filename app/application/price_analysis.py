"""Authoritative Price Analyzer owner boundary over persisted Product snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from typing import Callable, Protocol

from app.domain.discovery_identity import OpportunityCandidateIdentity
from app.domain.market_intelligence import MarketObservationIdentity
from app.domain.price_intelligence import PriceIntelligenceSnapshot
from app.domain.product_observation import ProductObservationSnapshot
from app.application.product_runtime import (
    ProductRuntimeReconstructionError,
    reconstruct_runtime_product,
)
from engine.price_intelligence import PriceIntelligence, analyze_product_prices


PRICE_ANALYSIS_COMMAND_SCHEMA_VERSION = "price-analysis-command-v1"
PRICE_ANALYSIS_RECEIPT_SCHEMA_VERSION = "price-analysis-receipt-v1"


class PriceAnalysisPersistenceError(RuntimeError): pass
class PriceAnalysisCommandConflictError(PriceAnalysisPersistenceError): pass
class PriceAnalysisSourceNotFoundError(PriceAnalysisPersistenceError): pass
class PriceAnalysisCandidateMismatchError(PriceAnalysisPersistenceError): pass
class PriceAnalysisGroupMismatchError(PriceAnalysisPersistenceError): pass
class PriceAnalysisProductOrderConflictError(PriceAnalysisPersistenceError): pass
class PriceAnalysisMarketIdentityConflictError(PriceAnalysisPersistenceError): pass
class PriceAnalysisExecutionError(RuntimeError): pass
class MalformedPriceAnalysisReceiptError(PriceAnalysisPersistenceError): pass
class UnsupportedPriceAnalysisReceiptVersionError(MalformedPriceAnalysisReceiptError): pass
class PriceAnalysisReceiptPersistenceError(PriceAnalysisPersistenceError): pass
class PriceAnalysisCommitError(PriceAnalysisPersistenceError): pass


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip(): raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class AnalyzeAndPersistPriceIntelligenceCommand:
    command_id: str
    candidate_identity: OpportunityCandidateIdentity
    finalized_group_id: str
    product_snapshot_ids: tuple[str, ...]
    market_observation_identity: MarketObservationIdentity
    fallback_multiplier: Decimal
    analyzer_version: str
    requested_at: datetime
    schema_version: str = PRICE_ANALYSIS_COMMAND_SCHEMA_VERSION

    def __post_init__(self):
        for name in ("command_id","finalized_group_id","analyzer_version"): _required(getattr(self,name),name)
        if not isinstance(self.candidate_identity,OpportunityCandidateIdentity): raise TypeError("candidate_identity must be OpportunityCandidateIdentity")
        if not isinstance(self.market_observation_identity,MarketObservationIdentity): raise TypeError("market_observation_identity must be MarketObservationIdentity")
        if not isinstance(self.product_snapshot_ids,tuple) or not self.product_snapshot_ids: raise ValueError("product_snapshot_ids must be a non-empty tuple")
        if any(not isinstance(value,str) or not value.strip() for value in self.product_snapshot_ids): raise ValueError("product_snapshot_ids must contain non-empty text")
        if len(set(self.product_snapshot_ids))!=len(self.product_snapshot_ids): raise ValueError("product_snapshot_ids must be unique")
        if not isinstance(self.fallback_multiplier,Decimal): raise TypeError("fallback_multiplier must be Decimal")
        if not self.fallback_multiplier.is_finite() or self.fallback_multiplier<=0: raise ValueError("fallback_multiplier must be finite and positive")
        _aware(self.requested_at,"requested_at")
        if self.schema_version!=PRICE_ANALYSIS_COMMAND_SCHEMA_VERSION: raise ValueError("unsupported Price analysis command version")

    @property
    def fingerprint(self):
        payload={"candidate":repr(self.candidate_identity),"group":self.finalized_group_id,
            "product_snapshot_ids":self.product_snapshot_ids,"market":repr(self.market_observation_identity),
            "fallback_multiplier":str(self.fallback_multiplier),"analyzer_version":self.analyzer_version,
            "requested_at":self.requested_at.isoformat(),"schema_version":self.schema_version}
        return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class PriceIntelligenceAnalysisReceipt:
    command_id: str
    candidate_id: str
    finalized_group_id: str
    price_snapshot_id: str
    command_fingerprint: str
    product_snapshot_ids: tuple[str, ...]
    analyzer_version: str
    fallback_multiplier: Decimal
    requested_at: datetime
    generated_at: datetime
    committed_at: datetime
    schema_version: str = PRICE_ANALYSIS_RECEIPT_SCHEMA_VERSION

    def __post_init__(self):
        for name in ("command_id","candidate_id","finalized_group_id","price_snapshot_id","command_fingerprint","analyzer_version"): _required(getattr(self,name),name)
        if len(self.command_fingerprint)!=64 or any(v not in "0123456789abcdef" for v in self.command_fingerprint): raise ValueError("command_fingerprint must be SHA-256 text")
        if not isinstance(self.product_snapshot_ids,tuple) or not self.product_snapshot_ids: raise ValueError("product_snapshot_ids must be a non-empty tuple")
        if not isinstance(self.fallback_multiplier,Decimal) or not self.fallback_multiplier.is_finite() or self.fallback_multiplier<=0: raise ValueError("fallback_multiplier must be finite positive Decimal")
        for name in ("requested_at","generated_at","committed_at"): _aware(getattr(self,name),name)
        if self.schema_version!=PRICE_ANALYSIS_RECEIPT_SCHEMA_VERSION: raise UnsupportedPriceAnalysisReceiptVersionError("unsupported Price analysis receipt version")


@dataclass(frozen=True, slots=True)
class PriceAnalysisResult:
    snapshot: PriceIntelligenceSnapshot
    receipt: PriceIntelligenceAnalysisReceipt
    replayed: bool


class PriceAnalysisRepository(Protocol):
    def get_receipt(self,command_id:str)->PriceIntelligenceAnalysisReceipt|None: ...
    def get_result(self,receipt:PriceIntelligenceAnalysisReceipt)->PriceAnalysisResult: ...
    def load_sources(self,command:AnalyzeAndPersistPriceIntelligenceCommand)->tuple[ProductObservationSnapshot,...]: ...
    def save_analysis_result(self,command:AnalyzeAndPersistPriceIntelligenceCommand,snapshot:PriceIntelligenceSnapshot,receipt:PriceIntelligenceAnalysisReceipt)->PriceAnalysisResult: ...
    def get_by_candidate_group(self,candidate_id:str,finalized_group_id:str)->tuple[PriceAnalysisResult,...]: ...


class AnalyzeAndPersistPriceIntelligence:
    def __init__(self,repository:PriceAnalysisRepository,*,snapshot_id_generator:Callable[[],str],generated_clock:Callable[[],datetime],receipt_clock:Callable[[],datetime],analyzer:Callable[...,PriceIntelligence]=analyze_product_prices):
        for value,name in ((snapshot_id_generator,"snapshot_id_generator"),(generated_clock,"generated_clock"),(receipt_clock,"receipt_clock"),(analyzer,"analyzer")):
            if not callable(value): raise TypeError(f"{name} must be callable")
        self._repository=repository;self._snapshot_id_generator=snapshot_id_generator
        self._generated_clock=generated_clock;self._receipt_clock=receipt_clock;self._analyzer=analyzer

    def execute(self,command:AnalyzeAndPersistPriceIntelligenceCommand)->PriceAnalysisResult:
        if not isinstance(command,AnalyzeAndPersistPriceIntelligenceCommand): raise TypeError("command must be AnalyzeAndPersistPriceIntelligenceCommand")
        existing=self._repository.get_receipt(command.command_id)
        if existing is not None:
            if existing.command_fingerprint!=command.fingerprint: raise PriceAnalysisCommandConflictError("Price analysis command payload conflicts")
            result=self._repository.get_result(existing);return PriceAnalysisResult(result.snapshot,result.receipt,True)
        sources=self._repository.load_sources(command)
        try:products=[reconstruct_runtime_product(value) for value in sources]
        except ProductRuntimeReconstructionError as error: raise PriceAnalysisExecutionError("runtime Product reconstruction failed") from error
        try:analysis=self._analyzer(products,fallback_multiplier=command.fallback_multiplier)
        except Exception as error: raise PriceAnalysisExecutionError("Price Analyzer execution failed") from error
        if not isinstance(analysis,PriceIntelligence): raise PriceAnalysisExecutionError("Price Analyzer returned malformed result")
        snapshot_id=_required(self._snapshot_id_generator(),"snapshot_id")
        generated_at=self._generated_clock();committed_at=self._receipt_clock()
        _aware(generated_at,"generated_at");_aware(committed_at,"committed_at")
        snapshot=PriceIntelligenceSnapshot(snapshot_id,command.candidate_identity,command.market_observation_identity,
            command.product_snapshot_ids,analysis.currency,analysis.lowest_price,analysis.average_price,
            analysis.median_price,analysis.highest_price,analysis.price_range,analysis.price_variation_rate,
            analysis.price_stability_level,analysis.recommended_selling_price,analysis.sample_size,
            command.analyzer_version,generated_at)
        receipt=PriceIntelligenceAnalysisReceipt(command.command_id,command.candidate_identity.candidate_id,
            command.finalized_group_id,snapshot_id,command.fingerprint,command.product_snapshot_ids,
            command.analyzer_version,command.fallback_multiplier,command.requested_at,generated_at,committed_at)
        return self._repository.save_analysis_result(command,snapshot,receipt)


__all__=[name for name in globals() if name.startswith("PriceAnalysis") or name.startswith("AnalyzeAnd") or name.startswith("MalformedPriceAnalysis") or name.startswith("UnsupportedPriceAnalysis") or name in {"PriceIntelligenceAnalysisReceipt","PRICE_ANALYSIS_COMMAND_SCHEMA_VERSION","PRICE_ANALYSIS_RECEIPT_SCHEMA_VERSION"}]
