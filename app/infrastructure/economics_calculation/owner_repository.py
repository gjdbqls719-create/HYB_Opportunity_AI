"""Atomic SQLite coordinator for authoritative Economics calculator ownership."""
from __future__ import annotations
from datetime import datetime,timezone
from pathlib import Path
import sqlite3

from app.application.economics_calculation_owner import (
    ECONOMICS_CALCULATION_RECEIPT_SCHEMA_VERSION,CalculateAndPersistEconomicsCommand,
    EconomicsCalculationBindingConflictError,EconomicsCalculationCommandConflictError,
    EconomicsCalculationMarketIdentityConflictError,EconomicsCalculationOwnerCommitError,
    EconomicsCalculationPriceSourceConflictError,EconomicsCalculationReceipt,
    EconomicsCalculationReceiptPersistenceError,EconomicsCalculationSourceContext,
    EconomicsCalculationSourceNotFoundError,EconomicsCalculationVerifiedSourceConflictError,
    EconomicsOwnerResult,EconomicsOwnerSources,MalformedEconomicsCalculationReceiptError,
    UnsupportedEconomicsCalculationReceiptVersionError,
)
from app.application.economics_calculation_snapshot import EconomicsCalculationSnapshotHistoryError
from app.application.verified_economics_snapshot import VERIFIED_ECONOMICS_SNAPSHOT_SCHEMA_VERSION
from app.domain.price_intelligence import PRICE_INTELLIGENCE_SNAPSHOT_SCHEMA_VERSION
from app.infrastructure.economics_calculation.sqlite_repository import SQLiteEconomicsCalculationSnapshotRepository,economics_snapshot_fingerprint
from app.infrastructure.opportunity_validation import SQLiteCandidatePromotionRepository
from app.infrastructure.price_intelligence import SQLitePriceAnalysisRepository

_TABLE="""CREATE TABLE IF NOT EXISTS economics_calculation_receipts(
 command_id TEXT PRIMARY KEY,opportunity_id TEXT NOT NULL,candidate_id TEXT NOT NULL,
 candidate_opportunity_binding_id TEXT NOT NULL,price_intelligence_snapshot_id TEXT NOT NULL,
 price_analysis_command_id TEXT NOT NULL,verified_economics_opportunity_id TEXT NOT NULL,
 economics_snapshot_id TEXT NOT NULL,command_fingerprint TEXT NOT NULL,calculation_version TEXT NOT NULL,
 requested_at TEXT NOT NULL,generated_at TEXT NOT NULL,committed_at TEXT NOT NULL,
 receipt_schema_version TEXT NOT NULL,inserted_at TEXT NOT NULL,
 FOREIGN KEY(candidate_opportunity_binding_id) REFERENCES opportunity_candidate_promotion_history(binding_id),
 FOREIGN KEY(price_intelligence_snapshot_id) REFERENCES price_intelligence_snapshot_history(snapshot_id),
 FOREIGN KEY(economics_snapshot_id) REFERENCES economics_calculation_snapshot_history(snapshot_id))"""

class SQLiteEconomicsCalculationOwnerRepository:
    def __init__(self,database_path=None,*,connection=None):
        if (database_path is None)==(connection is None):raise ValueError("provide exactly one database_path or connection")
        self._owns_connection=connection is None
        if connection is None:path=Path(database_path);path.parent.mkdir(parents=True,exist_ok=True);connection=sqlite3.connect(path,timeout=30,check_same_thread=False)
        self._connection=connection;connection.row_factory=sqlite3.Row;connection.execute("PRAGMA foreign_keys = ON")
        self._economics=SQLiteEconomicsCalculationSnapshotRepository(connection=connection)
        self._sources=SQLiteCandidatePromotionRepository(connection=connection)
        self._prices=SQLitePriceAnalysisRepository(connection=connection)
        with connection:
            connection.execute(_TABLE)
            for operation in ("UPDATE","DELETE"):connection.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_economics_owner_receipt_no_{operation.lower()} BEFORE {operation} ON economics_calculation_receipts BEGIN SELECT RAISE(ABORT,'economics calculation receipts are append-only'); END""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_economics_owner_opportunity ON economics_calculation_receipts(opportunity_id,generated_at,command_id)")

    def get_receipt(self,command_id):
        try:row=self._connection.execute("SELECT * FROM economics_calculation_receipts WHERE command_id=?",(command_id,)).fetchone()
        except sqlite3.Error as error:raise EconomicsCalculationReceiptPersistenceError("Economics receipt query failed") from error
        if row is None:return None
        try:
            if row["receipt_schema_version"]!=ECONOMICS_CALCULATION_RECEIPT_SCHEMA_VERSION:raise UnsupportedEconomicsCalculationReceiptVersionError("unsupported persisted Economics receipt version")
            return EconomicsCalculationReceipt(row["command_id"],row["opportunity_id"],row["candidate_id"],row["candidate_opportunity_binding_id"],row["price_intelligence_snapshot_id"],row["verified_economics_opportunity_id"],row["price_analysis_command_id"],row["economics_snapshot_id"],row["command_fingerprint"],row["calculation_version"],datetime.fromisoformat(row["requested_at"]),datetime.fromisoformat(row["generated_at"]),datetime.fromisoformat(row["committed_at"]),row["receipt_schema_version"])
        except UnsupportedEconomicsCalculationReceiptVersionError:raise
        except Exception as error:raise MalformedEconomicsCalculationReceiptError("persisted Economics receipt is malformed") from error

    def load_sources(self,source):
        binding=self._sources.get_promotion_by_opportunity(source.opportunity_id)
        if binding is None:raise EconomicsCalculationSourceNotFoundError("Candidate Opportunity binding is missing")
        if binding.binding_id!=source.candidate_opportunity_binding_id or binding.candidate_id!=source.candidate_id or binding.opportunity_id!=source.opportunity_id:raise EconomicsCalculationBindingConflictError("Candidate Opportunity binding differs")
        if binding.market_observation_identity!=source.market_observation_identity:raise EconomicsCalculationMarketIdentityConflictError("binding Market identity differs")
        price=self._prices._prices.get_snapshot(source.price_intelligence_snapshot_id)
        if price is None:raise EconomicsCalculationSourceNotFoundError("Price Snapshot is missing")
        price_receipt=self._prices.get_receipt(source.price_analysis_command_id)
        if price_receipt is None:raise EconomicsCalculationSourceNotFoundError("Price analysis receipt is missing")
        if price_receipt.price_snapshot_id!=price.snapshot_id or price.candidate_identity.candidate_id!=source.candidate_id:raise EconomicsCalculationPriceSourceConflictError("Price source Candidate/receipt differs")
        if price.market_observation_identity!=source.market_observation_identity or price.schema_version!=PRICE_INTELLIGENCE_SNAPSHOT_SCHEMA_VERSION:raise EconomicsCalculationPriceSourceConflictError("Price source Market/version differs")
        verified=self._sources.get_verified_economics_snapshot(source.verified_economics_opportunity_id)
        if verified is None:raise EconomicsCalculationSourceNotFoundError("Verified Economics source is missing")
        if verified.opportunity_id!=source.opportunity_id or verified.schema_version!=VERIFIED_ECONOMICS_SNAPSHOT_SCHEMA_VERSION:raise EconomicsCalculationVerifiedSourceConflictError("Verified Economics source differs")
        return EconomicsOwnerSources(binding,price,verified)

    def get_result(self,receipt):
        snapshot=self._economics.get_snapshot(receipt.economics_snapshot_id)
        if snapshot is None:raise MalformedEconomicsCalculationReceiptError("Economics receipt references missing Snapshot")
        if (snapshot.opportunity_identity.opportunity_id!=receipt.opportunity_id or snapshot.candidate_id!=receipt.candidate_id or snapshot.candidate_opportunity_binding_id!=receipt.candidate_opportunity_binding_id or snapshot.price_intelligence_snapshot_id!=receipt.price_intelligence_snapshot_id or snapshot.verified_economics_opportunity_id!=receipt.verified_economics_opportunity_id or snapshot.calculation_version!=receipt.calculation_version or snapshot.generated_at!=receipt.generated_at):raise MalformedEconomicsCalculationReceiptError("Economics receipt and Snapshot differ")
        source=EconomicsCalculationSourceContext(receipt.opportunity_id,receipt.candidate_opportunity_binding_id,receipt.candidate_id,receipt.price_intelligence_snapshot_id,receipt.price_analysis_command_id,receipt.verified_economics_opportunity_id,snapshot.market_observation_identity,receipt.command_id,receipt.requested_at)
        self.load_sources(source)
        return EconomicsOwnerResult(snapshot,receipt,False)

    def save_result(self,command,snapshot,receipt):
        try:self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:raise EconomicsCalculationOwnerCommitError("Economics owner transaction could not start") from error
        try:
            existing=self.get_receipt(command.command_id)
            if existing is not None:
                if existing.command_fingerprint!=command.fingerprint:raise EconomicsCalculationCommandConflictError("Economics command payload conflicts")
                result=self.get_result(existing);self._connection.rollback();return EconomicsOwnerResult(result.snapshot,result.receipt,True)
            self.load_sources(command.source);binding=self._economics._validate_lineage(snapshot)
            try:self._economics._insert(snapshot,binding.candidate_id,economics_snapshot_fingerprint(snapshot))
            except sqlite3.Error as error:raise EconomicsCalculationSnapshotHistoryError("Economics Snapshot history insert failed") from error
            try:self._insert_receipt(receipt)
            except sqlite3.Error as error:raise EconomicsCalculationReceiptPersistenceError("Economics receipt insert failed") from error
            try:self._commit()
            except sqlite3.Error as error:raise EconomicsCalculationOwnerCommitError("Economics owner commit failed") from error
            return EconomicsOwnerResult(snapshot,receipt,False)
        except Exception:
            if self._connection.in_transaction:self._connection.rollback()
            raise
    def _insert_receipt(self,r):self._connection.execute("INSERT INTO economics_calculation_receipts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(r.command_id,r.opportunity_id,r.candidate_id,r.candidate_opportunity_binding_id,r.price_intelligence_snapshot_id,r.price_analysis_command_id,r.verified_economics_opportunity_id,r.economics_snapshot_id,r.command_fingerprint,r.calculation_version,r.requested_at.isoformat(),r.generated_at.isoformat(),r.committed_at.isoformat(),r.schema_version,datetime.now(timezone.utc).isoformat()))
    def _commit(self):self._connection.commit()
    def get_by_opportunity(self,opportunity_id):
        try:rows=self._connection.execute("SELECT * FROM economics_calculation_receipts WHERE opportunity_id=? ORDER BY generated_at,command_id",(opportunity_id,)).fetchall()
        except sqlite3.Error as error:raise EconomicsCalculationReceiptPersistenceError("Economics owner query failed") from error
        return tuple(self.get_result(self.get_receipt(row["command_id"])) for row in rows)
    def get_by_price_snapshot(self,snapshot_id):
        try:rows=self._connection.execute("SELECT * FROM economics_calculation_receipts WHERE price_intelligence_snapshot_id=? ORDER BY generated_at,command_id",(snapshot_id,)).fetchall()
        except sqlite3.Error as error:raise EconomicsCalculationReceiptPersistenceError("Economics Price source query failed") from error
        return tuple(self.get_result(self.get_receipt(row["command_id"])) for row in rows)
    def close(self):
        if self._owns_connection:self._connection.close()
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
