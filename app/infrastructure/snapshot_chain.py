"""File-backed complete Snapshot Chain binding and exact Safety source reads."""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import sqlite3
from app.application.snapshot_chain_binding import *
from app.application.snapshot_chain_binding import (
    SNAPSHOT_CHAIN_BINDING_SCHEMA_VERSION,
    SNAPSHOT_CHAIN_RECEIPT_SCHEMA_VERSION,
)
from app.application.production_safety_integration import ProductionSafetyEvaluationContext,ProductionSafetySourceNotFoundError
from app.infrastructure.economics_calculation import SQLiteEconomicsCalculationOwnerRepository
from app.infrastructure.product_observation.capture_repository import _identity

_HISTORY="""CREATE TABLE IF NOT EXISTS opportunity_snapshot_chain_binding_history(
 binding_id TEXT PRIMARY KEY,candidate_opportunity_binding_id TEXT NOT NULL,candidate_id TEXT NOT NULL,
 opportunity_id TEXT NOT NULL,chain_version INTEGER NOT NULL,ordered_product_snapshot_ids_json TEXT NOT NULL,
 price_snapshot_id TEXT NOT NULL,economics_snapshot_id TEXT NOT NULL,verified_economics_opportunity_id TEXT NOT NULL,
 market_identity_payload_json TEXT NOT NULL,bound_at TEXT NOT NULL,binding_schema_version TEXT NOT NULL,
 binding_command_id TEXT NOT NULL,payload_fingerprint TEXT NOT NULL,inserted_at TEXT NOT NULL,UNIQUE(opportunity_id,chain_version),
 UNIQUE(candidate_opportunity_binding_id,payload_fingerprint))"""
_MEMBERS="""CREATE TABLE IF NOT EXISTS opportunity_snapshot_chain_product_members(
 binding_id TEXT NOT NULL,position INTEGER NOT NULL,product_snapshot_id TEXT NOT NULL,
 PRIMARY KEY(binding_id,position),UNIQUE(binding_id,product_snapshot_id),
 FOREIGN KEY(binding_id) REFERENCES opportunity_snapshot_chain_binding_history(binding_id),
 FOREIGN KEY(product_snapshot_id) REFERENCES product_observation_snapshot_history(snapshot_id))"""
_RECEIPTS="""CREATE TABLE IF NOT EXISTS opportunity_snapshot_chain_binding_receipts(
 command_id TEXT PRIMARY KEY,binding_id TEXT NOT NULL,command_fingerprint TEXT NOT NULL,
 requested_at TEXT NOT NULL,committed_at TEXT NOT NULL,receipt_schema_version TEXT NOT NULL,inserted_at TEXT NOT NULL,
 FOREIGN KEY(binding_id) REFERENCES opportunity_snapshot_chain_binding_history(binding_id))"""
def _dump(v):return json.dumps(v,sort_keys=True,separators=(",", ":"))
def _market(v):
    from app.infrastructure.product_observation.sqlite_repository import _identity_dict
    return _dump(_identity_dict(v))
def _subject(command):return hashlib.sha256(_dump({"promotion":command.candidate_opportunity_binding_id,"products":command.product_snapshot_ids,"price":command.price_snapshot_id,"economics":command.economics_snapshot_id}).encode()).hexdigest()

class SQLiteSnapshotChainBindingRepository:
    def __init__(self,database_path=None,*,connection=None):
        if (database_path is None)==(connection is None):raise ValueError("provide exactly one database_path or connection")
        self._owns_connection=connection is None
        if connection is None:path=Path(database_path);path.parent.mkdir(parents=True,exist_ok=True);connection=sqlite3.connect(path,timeout=30,check_same_thread=False)
        self._connection=connection;connection.row_factory=sqlite3.Row;connection.execute("PRAGMA foreign_keys = ON")
        self._owners=SQLiteEconomicsCalculationOwnerRepository(connection=connection)
        with connection:
            for table in (_HISTORY,_MEMBERS,_RECEIPTS):connection.execute(table)
            for table in ("opportunity_snapshot_chain_binding_history","opportunity_snapshot_chain_product_members","opportunity_snapshot_chain_binding_receipts"):
                for operation in ("UPDATE","DELETE"):connection.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'snapshot chain facts are append-only'); END""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_chain_opportunity ON opportunity_snapshot_chain_binding_history(opportunity_id,chain_version)")

    def _validate(self,c):
        row=self._connection.execute("SELECT * FROM opportunity_candidate_promotion_history WHERE binding_id=?",(c.candidate_opportunity_binding_id,)).fetchone()
        if row is None:raise SnapshotChainBindingNotFoundError("promotion binding not found")
        candidate_id,opportunity_id=row["candidate_id"],row["opportunity_id"]
        market=_identity(row["market_identity_payload_json"])
        products=[];observations=[]
        for sid in c.product_snapshot_ids:
            product=self._owners._prices._products._snapshots.get_snapshot(sid);binding=self._owners._prices._products._binding(sid)
            if product is None or binding is None:raise SnapshotChainIncompleteError("Product Snapshot/source binding is missing")
            if product.candidate_identity.candidate_id!=candidate_id:raise SnapshotChainCandidateMismatchError("Product Candidate differs")
            if product.market_observation_identity!=market:raise SnapshotChainMarketIdentityConflictError("Product Market differs")
            products.append(product);observations.append(binding.collected_observation_id)
        price=self._owners._prices._prices.get_snapshot(c.price_snapshot_id)
        if price is None:raise SnapshotChainIncompleteError("Price Snapshot is missing")
        if price.product_observation_snapshot_ids!=c.product_snapshot_ids:raise SnapshotChainProductSourceConflictError("Price cohort order differs")
        if price.candidate_identity.candidate_id!=candidate_id or price.market_observation_identity!=market:raise SnapshotChainPriceSourceConflictError("Price lineage differs")
        price_receipt=self._connection.execute("SELECT command_id FROM price_intelligence_analysis_receipts WHERE price_snapshot_id=?",(c.price_snapshot_id,)).fetchone()
        if price_receipt is None:raise SnapshotChainPriceSourceConflictError("Price analysis receipt is missing")
        self._owners._prices.get_result(self._owners._prices.get_receipt(price_receipt[0]))
        economics=self._owners._economics.get_snapshot(c.economics_snapshot_id)
        if economics is None:raise SnapshotChainIncompleteError("Economics Snapshot is missing")
        if economics.opportunity_identity.opportunity_id!=opportunity_id or economics.candidate_id!=candidate_id:raise SnapshotChainOpportunityMismatchError("Economics subject differs")
        if economics.candidate_opportunity_binding_id!=c.candidate_opportunity_binding_id or economics.price_intelligence_snapshot_id!=c.price_snapshot_id:raise SnapshotChainEconomicsSourceConflictError("Economics source lineage differs")
        if economics.market_observation_identity!=market:raise SnapshotChainMarketIdentityConflictError("Economics Market differs")
        econ_receipt=self._connection.execute("SELECT command_id FROM economics_calculation_receipts WHERE economics_snapshot_id=?",(c.economics_snapshot_id,)).fetchone()
        if econ_receipt is None:raise SnapshotChainEconomicsSourceConflictError("Economics owner receipt is missing")
        self._owners.get_result(self._owners.get_receipt(econ_receipt[0]))
        verified=self._owners._sources.get_verified_economics_snapshot(economics.verified_economics_opportunity_id)
        if verified is None or verified.opportunity_id!=opportunity_id:raise SnapshotChainVerifiedSourceConflictError("Verified Economics source differs")
        return candidate_id,opportunity_id,market,economics.verified_economics_opportunity_id

    def bind(self,c,binding_id,bound_at,committed_at):
        try:self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as e:raise SnapshotChainBindingCommitError("chain transaction could not start") from e
        try:
            receipt=self.get_receipt(c.command_id)
            if receipt:
                if receipt.command_fingerprint!=c.fingerprint:raise SnapshotChainBindingCommandConflictError("chain command conflicts")
                result=SnapshotChainBindingResult(self.get_binding(receipt.binding_id),receipt,True);self._connection.rollback();return result
            candidate,opportunity,market,verified=self._validate(c);subject=_subject(c)
            existing=self._connection.execute("SELECT binding_id FROM opportunity_snapshot_chain_binding_history WHERE candidate_opportunity_binding_id=? AND payload_fingerprint=?",(c.candidate_opportunity_binding_id,subject)).fetchone()
            if existing:
                binding=self.get_binding(existing[0]);receipt=self._receipt_value(c,binding,committed_at)
                try:self._insert_receipt(receipt)
                except sqlite3.Error as e:raise SnapshotChainReceiptPersistenceError("chain receipt insert failed") from e
                try:self._commit()
                except sqlite3.Error as e:raise SnapshotChainBindingCommitError("chain commit failed") from e
                return SnapshotChainBindingResult(binding,receipt,False)
            version=self._connection.execute("SELECT COALESCE(MAX(chain_version),0)+1 FROM opportunity_snapshot_chain_binding_history WHERE opportunity_id=?",(opportunity,)).fetchone()[0]
            binding=OpportunitySnapshotChainBinding(binding_id,c.candidate_opportunity_binding_id,candidate,opportunity,version,c.product_snapshot_ids,c.price_snapshot_id,c.economics_snapshot_id,verified,market,c.command_id,bound_at)
            try:self._insert_history(binding,subject)
            except sqlite3.Error as e:raise SnapshotChainBindingHistoryError("chain history insert failed") from e
            try:self._insert_members(binding)
            except sqlite3.Error as e:raise SnapshotChainMemberPersistenceError("chain members insert failed") from e
            receipt=self._receipt_value(c,binding,committed_at)
            try:self._insert_receipt(receipt)
            except sqlite3.Error as e:raise SnapshotChainReceiptPersistenceError("chain receipt insert failed") from e
            try:self._commit()
            except sqlite3.Error as e:raise SnapshotChainBindingCommitError("chain commit failed") from e
            return SnapshotChainBindingResult(binding,receipt,False)
        except Exception:
            if self._connection.in_transaction:self._connection.rollback()
            raise
    def _receipt_value(self,c,b,committed):return SnapshotChainBindingReceipt(c.command_id,b.binding_id,b.candidate_opportunity_binding_id,b.candidate_id,b.opportunity_id,b.product_snapshot_ids,b.price_snapshot_id,b.economics_snapshot_id,c.fingerprint,c.requested_at,b.bound_at,committed)
    def _insert_history(self,b,fp):self._connection.execute("INSERT INTO opportunity_snapshot_chain_binding_history VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(b.binding_id,b.candidate_opportunity_binding_id,b.candidate_id,b.opportunity_id,b.chain_version,json.dumps(b.product_snapshot_ids,separators=(",", ":")),b.price_snapshot_id,b.economics_snapshot_id,b.verified_economics_opportunity_id,_market(b.market_observation_identity),b.bound_at.isoformat(),b.schema_version,b.binding_command_id,fp,datetime.now(timezone.utc).isoformat()))
    def _insert_members(self,b):self._connection.executemany("INSERT INTO opportunity_snapshot_chain_product_members VALUES(?,?,?)",tuple((b.binding_id,i,v) for i,v in enumerate(b.product_snapshot_ids)))
    def _insert_receipt(self,r):self._connection.execute("INSERT INTO opportunity_snapshot_chain_binding_receipts VALUES(?,?,?,?,?,?,?)",(r.command_id,r.binding_id,r.command_fingerprint,r.requested_at.isoformat(),r.committed_at.isoformat(),r.schema_version,datetime.now(timezone.utc).isoformat()))
    def _commit(self):self._connection.commit()

    def get_binding(self,binding_id):
        row=self._connection.execute("SELECT * FROM opportunity_snapshot_chain_binding_history WHERE binding_id=?",(binding_id,)).fetchone()
        if row is None:return None
        try:
            if row["binding_schema_version"]!=SNAPSHOT_CHAIN_BINDING_SCHEMA_VERSION:raise UnsupportedSnapshotChainBindingVersionError("unsupported persisted chain version")
            members=self._connection.execute("SELECT position,product_snapshot_id FROM opportunity_snapshot_chain_product_members WHERE binding_id=? ORDER BY position",(binding_id,)).fetchall();ids=tuple(v[1] for v in members)
            if tuple(v[0] for v in members)!=tuple(range(len(members))) or ids!=tuple(json.loads(row["ordered_product_snapshot_ids_json"])):raise ValueError("chain members are malformed")
            value=OpportunitySnapshotChainBinding(row["binding_id"],row["candidate_opportunity_binding_id"],row["candidate_id"],row["opportunity_id"],row["chain_version"],ids,row["price_snapshot_id"],row["economics_snapshot_id"],row["verified_economics_opportunity_id"],_identity(row["market_identity_payload_json"]),row["binding_command_id"],datetime.fromisoformat(row["bound_at"]),row["binding_schema_version"])
            expected=hashlib.sha256(_dump({"promotion":value.candidate_opportunity_binding_id,"products":value.product_snapshot_ids,"price":value.price_snapshot_id,"economics":value.economics_snapshot_id}).encode()).hexdigest()
            if row["payload_fingerprint"]!=expected:raise ValueError("chain fingerprint mismatch")
            return value
        except UnsupportedSnapshotChainBindingVersionError:raise
        except Exception as e:raise MalformedSnapshotChainBindingPersistenceError("persisted chain is malformed") from e
    def get_receipt(self,command_id):
        row=self._connection.execute("SELECT * FROM opportunity_snapshot_chain_binding_receipts WHERE command_id=?",(command_id,)).fetchone()
        if row is None:return None
        binding=self.get_binding(row["binding_id"])
        if binding is None:raise MalformedSnapshotChainBindingPersistenceError("receipt binding missing")
        receipt=SnapshotChainBindingReceipt(row["command_id"],binding.binding_id,binding.candidate_opportunity_binding_id,binding.candidate_id,binding.opportunity_id,binding.product_snapshot_ids,binding.price_snapshot_id,binding.economics_snapshot_id,row["command_fingerprint"],datetime.fromisoformat(row["requested_at"]),binding.bound_at,datetime.fromisoformat(row["committed_at"]),row["receipt_schema_version"])
        reconstructed=BindOpportunitySnapshotChainCommand(receipt.command_id,receipt.candidate_opportunity_binding_id,receipt.product_snapshot_ids,receipt.price_snapshot_id,receipt.economics_snapshot_id,receipt.requested_at)
        if receipt.command_fingerprint!=reconstructed.fingerprint:raise MalformedSnapshotChainBindingPersistenceError("receipt fingerprint mismatch")
        return receipt
    def get_by_opportunity(self,opportunity_id):return self._query("opportunity_id",opportunity_id)
    def get_by_candidate(self,candidate_id):return self._query("candidate_id",candidate_id)
    def _query(self,col,val):return tuple(self.get_binding(r[0]) for r in self._connection.execute(f"SELECT binding_id FROM opportunity_snapshot_chain_binding_history WHERE {col}=? ORDER BY chain_version,binding_id",(val,)).fetchall())
    def get_receipts_by_binding(self,binding_id):return tuple(self.get_receipt(r[0]) for r in self._connection.execute("SELECT command_id FROM opportunity_snapshot_chain_binding_receipts WHERE binding_id=? ORDER BY committed_at,command_id",(binding_id,)).fetchall())
    def get_product_snapshot(self,snapshot_id):return self._owners._prices._products._snapshots.get_snapshot(snapshot_id)
    def get_price_snapshot(self,snapshot_id):return self._owners._prices._prices.get_snapshot(snapshot_id)
    def get_economics_snapshot(self,snapshot_id):return self._owners._economics.get_snapshot(snapshot_id)
    def get_candidate_opportunity_binding(self,candidate_id):return self._owners._sources.get_promotion_by_candidate(candidate_id)
    def validate_snapshot_lineage(self,context):
        if not isinstance(context,ProductionSafetyEvaluationContext):raise TypeError("context must be ProductionSafetyEvaluationContext")
        command=BindOpportunitySnapshotChainCommand("lineage-validation",context.candidate_opportunity_binding.binding_id,context.price_intelligence_snapshot.product_observation_snapshot_ids,context.price_intelligence_snapshot.snapshot_id,context.economics_calculation_snapshot.snapshot_id,context.economics_calculation_snapshot.generated_at)
        self._validate(command)
    def build_evaluation_context(self,binding_id,product_snapshot_id):
        binding=self.get_binding(binding_id)
        if binding is None:raise SnapshotChainBindingNotFoundError(binding_id)
        if product_snapshot_id not in binding.product_snapshot_ids:raise SnapshotChainProductSourceConflictError("Product is not in exact chain")
        self._validate(BindOpportunitySnapshotChainCommand("validation",binding.candidate_opportunity_binding_id,binding.product_snapshot_ids,binding.price_snapshot_id,binding.economics_snapshot_id,binding.bound_at))
        product=self._owners._prices._products._snapshots.get_snapshot(product_snapshot_id);price=self._owners._prices._prices.get_snapshot(binding.price_snapshot_id);economics=self._owners._economics.get_snapshot(binding.economics_snapshot_id);promotion=self._owners._sources.get_promotion_by_opportunity(binding.opportunity_id)
        return ProductionSafetyEvaluationContext(product,price,economics,promotion,binding.verified_economics_opportunity_id)
    def close(self):
        if self._owns_connection:self._connection.close()
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
