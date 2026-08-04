"""Complete-only immutable Snapshot Chain binding contracts."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
import hashlib,json
from typing import Callable,Protocol
from app.domain.market_intelligence import MarketObservationIdentity

SNAPSHOT_CHAIN_BINDING_SCHEMA_VERSION="opportunity-snapshot-chain-binding-v1"
SNAPSHOT_CHAIN_COMMAND_SCHEMA_VERSION="snapshot-chain-binding-command-v1"
SNAPSHOT_CHAIN_RECEIPT_SCHEMA_VERSION="snapshot-chain-binding-receipt-v1"

class SnapshotChainBindingPersistenceError(RuntimeError):pass
class SnapshotChainBindingNotFoundError(SnapshotChainBindingPersistenceError):pass
class SnapshotChainBindingCommandConflictError(SnapshotChainBindingPersistenceError):pass
class SnapshotChainBindingConflictError(SnapshotChainBindingPersistenceError):pass
class SnapshotChainIncompleteError(SnapshotChainBindingPersistenceError):pass
class SnapshotChainCandidateMismatchError(SnapshotChainBindingPersistenceError):pass
class SnapshotChainOpportunityMismatchError(SnapshotChainBindingPersistenceError):pass
class SnapshotChainMarketIdentityConflictError(SnapshotChainBindingPersistenceError):pass
class SnapshotChainProductSourceConflictError(SnapshotChainBindingPersistenceError):pass
class SnapshotChainPriceSourceConflictError(SnapshotChainBindingPersistenceError):pass
class SnapshotChainEconomicsSourceConflictError(SnapshotChainBindingPersistenceError):pass
class SnapshotChainVerifiedSourceConflictError(SnapshotChainBindingPersistenceError):pass
class MalformedSnapshotChainBindingPersistenceError(SnapshotChainBindingPersistenceError):pass
class UnsupportedSnapshotChainBindingVersionError(MalformedSnapshotChainBindingPersistenceError):pass
class SnapshotChainBindingHistoryError(SnapshotChainBindingPersistenceError):pass
class SnapshotChainMemberPersistenceError(SnapshotChainBindingPersistenceError):pass
class SnapshotChainCurrentProjectionError(SnapshotChainBindingPersistenceError):pass
class SnapshotChainReceiptPersistenceError(SnapshotChainBindingPersistenceError):pass
class SnapshotChainBindingCommitError(SnapshotChainBindingPersistenceError):pass

def _text(v,n):
    if not isinstance(v,str) or not v.strip():raise ValueError(f"{n} must be non-empty text")
    return v.strip()
def _aware(v,n):
    if not isinstance(v,datetime) or v.tzinfo is None or v.utcoffset() is None:raise ValueError(f"{n} must be timezone-aware")

@dataclass(frozen=True,slots=True)
class OpportunitySnapshotChainBinding:
    binding_id:str;candidate_opportunity_binding_id:str;candidate_id:str;opportunity_id:str
    chain_version:int;product_snapshot_ids:tuple[str,...];price_snapshot_id:str
    economics_snapshot_id:str;verified_economics_opportunity_id:str
    market_observation_identity:MarketObservationIdentity;binding_command_id:str;bound_at:datetime
    schema_version:str=SNAPSHOT_CHAIN_BINDING_SCHEMA_VERSION
    def __post_init__(self):
        for n in ("binding_id","candidate_opportunity_binding_id","candidate_id","opportunity_id","price_snapshot_id","economics_snapshot_id","verified_economics_opportunity_id","binding_command_id"):_text(getattr(self,n),n)
        if self.candidate_id==self.opportunity_id:raise ValueError("Candidate and Opportunity IDs must differ")
        if isinstance(self.chain_version,bool) or not isinstance(self.chain_version,int) or self.chain_version<1:raise ValueError("chain_version must be positive")
        if not isinstance(self.product_snapshot_ids,tuple) or not self.product_snapshot_ids:raise SnapshotChainIncompleteError("Product Snapshot IDs are required")
        if any(not isinstance(v,str) or not v.strip() for v in self.product_snapshot_ids) or len(set(self.product_snapshot_ids))!=len(self.product_snapshot_ids):raise ValueError("Product Snapshot IDs must be non-empty and unique")
        if not isinstance(self.market_observation_identity,MarketObservationIdentity):raise TypeError("market_observation_identity must be MarketObservationIdentity")
        _aware(self.bound_at,"bound_at")
        if self.schema_version!=SNAPSHOT_CHAIN_BINDING_SCHEMA_VERSION:raise UnsupportedSnapshotChainBindingVersionError("unsupported chain binding version")

@dataclass(frozen=True,slots=True)
class BindOpportunitySnapshotChainCommand:
    command_id:str;candidate_opportunity_binding_id:str;product_snapshot_ids:tuple[str,...]
    price_snapshot_id:str;economics_snapshot_id:str;requested_at:datetime
    schema_version:str=SNAPSHOT_CHAIN_COMMAND_SCHEMA_VERSION
    def __post_init__(self):
        for n in ("command_id","candidate_opportunity_binding_id","price_snapshot_id","economics_snapshot_id"):_text(getattr(self,n),n)
        if not isinstance(self.product_snapshot_ids,tuple) or not self.product_snapshot_ids:raise SnapshotChainIncompleteError("Product Snapshot IDs are required")
        if any(not isinstance(v,str) or not v.strip() for v in self.product_snapshot_ids) or len(set(self.product_snapshot_ids))!=len(self.product_snapshot_ids):raise ValueError("Product Snapshot IDs must be non-empty and unique")
        _aware(self.requested_at,"requested_at")
        if self.schema_version!=SNAPSHOT_CHAIN_COMMAND_SCHEMA_VERSION:raise ValueError("unsupported chain command version")
    @property
    def fingerprint(self):
        p={"promotion_binding":self.candidate_opportunity_binding_id,"products":self.product_snapshot_ids,"price":self.price_snapshot_id,"economics":self.economics_snapshot_id,"requested_at":self.requested_at.isoformat(),"schema_version":self.schema_version}
        return hashlib.sha256(json.dumps(p,sort_keys=True,separators=(",", ":")).encode()).hexdigest()

@dataclass(frozen=True,slots=True)
class SnapshotChainBindingReceipt:
    command_id:str;binding_id:str;candidate_opportunity_binding_id:str;candidate_id:str;opportunity_id:str
    product_snapshot_ids:tuple[str,...];price_snapshot_id:str;economics_snapshot_id:str
    command_fingerprint:str;requested_at:datetime;bound_at:datetime;committed_at:datetime
    schema_version:str=SNAPSHOT_CHAIN_RECEIPT_SCHEMA_VERSION
    def __post_init__(self):
        for n in ("command_id","binding_id","candidate_opportunity_binding_id","candidate_id","opportunity_id","price_snapshot_id","economics_snapshot_id","command_fingerprint"):_text(getattr(self,n),n)
        if len(self.command_fingerprint)!=64:raise ValueError("command_fingerprint must be SHA-256 text")
        if not isinstance(self.product_snapshot_ids,tuple) or not self.product_snapshot_ids:raise SnapshotChainIncompleteError("receipt Product IDs are required")
        for n in ("requested_at","bound_at","committed_at"):_aware(getattr(self,n),n)
        if self.schema_version!=SNAPSHOT_CHAIN_RECEIPT_SCHEMA_VERSION:raise UnsupportedSnapshotChainBindingVersionError("unsupported chain receipt version")

@dataclass(frozen=True,slots=True)
class SnapshotChainBindingResult:
    binding:OpportunitySnapshotChainBinding;receipt:SnapshotChainBindingReceipt;replayed:bool

class SnapshotChainBindingRepository(Protocol):
    def get_receipt(self,command_id:str)->SnapshotChainBindingReceipt|None:...
    def get_binding(self,binding_id:str)->OpportunitySnapshotChainBinding|None:...
    def bind(self,command:BindOpportunitySnapshotChainCommand,binding_id:str,bound_at:datetime,committed_at:datetime)->SnapshotChainBindingResult:...
    def get_by_opportunity(self,opportunity_id:str)->tuple[OpportunitySnapshotChainBinding,...]:...
    def get_by_candidate(self,candidate_id:str)->tuple[OpportunitySnapshotChainBinding,...]:...
    def get_receipts_by_binding(self,binding_id:str)->tuple[SnapshotChainBindingReceipt,...]:...
    def build_evaluation_context(self,binding_id:str,product_snapshot_id:str):...

class BindOpportunitySnapshotChain:
    def __init__(self,repository:SnapshotChainBindingRepository,*,binding_id_generator:Callable[[],str],bound_clock:Callable[[],datetime],receipt_clock:Callable[[],datetime]):self._repo=repository;self._id=binding_id_generator;self._bound=bound_clock;self._committed=receipt_clock
    def execute(self,command):
        if not isinstance(command,BindOpportunitySnapshotChainCommand):raise TypeError("command must be BindOpportunitySnapshotChainCommand")
        receipt=self._repo.get_receipt(command.command_id)
        if receipt is not None:
            if receipt.command_fingerprint!=command.fingerprint:raise SnapshotChainBindingCommandConflictError("chain command payload conflicts")
            binding=self._repo.get_binding(receipt.binding_id)
            if binding is None:raise MalformedSnapshotChainBindingPersistenceError("receipt references missing binding")
            return SnapshotChainBindingResult(binding,receipt,True)
        binding_id=_text(self._id(),"binding_id");bound=self._bound();committed=self._committed();_aware(bound,"bound_at");_aware(committed,"committed_at")
        return self._repo.bind(command,binding_id,bound,committed)

__all__=[name for name in globals() if name.startswith("SnapshotChain") or name.startswith("OpportunitySnapshot") or name.startswith("BindOpportunity") or name.startswith("MalformedSnapshot") or name.startswith("UnsupportedSnapshot")]
