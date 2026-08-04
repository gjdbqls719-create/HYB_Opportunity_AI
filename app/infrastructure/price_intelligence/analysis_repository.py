"""SQLite persistence coordinator for authoritative Price analysis ownership."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
import sqlite3

from app.application.price_analysis import (
    AnalyzeAndPersistPriceIntelligenceCommand,
    PRICE_ANALYSIS_RECEIPT_SCHEMA_VERSION,
    MalformedPriceAnalysisReceiptError,
    PriceAnalysisCandidateMismatchError,
    PriceAnalysisCommandConflictError,
    PriceAnalysisCommitError,
    PriceAnalysisGroupMismatchError,
    PriceAnalysisMarketIdentityConflictError,
    PriceAnalysisProductOrderConflictError,
    PriceAnalysisReceiptPersistenceError,
    PriceAnalysisResult,
    PriceAnalysisSourceNotFoundError,
    PriceIntelligenceAnalysisReceipt,
    UnsupportedPriceAnalysisReceiptVersionError,
)
from app.application.price_intelligence_snapshot import PriceIntelligenceSnapshotHistoryError
from app.infrastructure.price_intelligence.sqlite_repository import (
    SQLitePriceIntelligenceSnapshotRepository,
    price_snapshot_fingerprint,
)
from app.infrastructure.product_observation import SQLiteProductSnapshotCaptureRepository


_TABLE="""CREATE TABLE IF NOT EXISTS price_intelligence_analysis_receipts(
 command_id TEXT PRIMARY KEY,candidate_id TEXT NOT NULL,finalized_group_id TEXT NOT NULL,
 price_snapshot_id TEXT NOT NULL,command_fingerprint TEXT NOT NULL,
 ordered_product_snapshot_ids_json TEXT NOT NULL,analyzer_version TEXT NOT NULL,
 fallback_multiplier TEXT NOT NULL,requested_at TEXT NOT NULL,generated_at TEXT NOT NULL,
 committed_at TEXT NOT NULL,receipt_schema_version TEXT NOT NULL,inserted_at TEXT NOT NULL,
 FOREIGN KEY(candidate_id) REFERENCES opportunity_candidate_history(candidate_id),
 FOREIGN KEY(finalized_group_id) REFERENCES discovery_finalized_group_history(finalized_group_id),
 FOREIGN KEY(price_snapshot_id) REFERENCES price_intelligence_snapshot_history(snapshot_id))"""


class SQLitePriceAnalysisRepository:
    def __init__(self,database_path=None,*,connection=None):
        if (database_path is None)==(connection is None): raise ValueError("provide exactly one database_path or connection")
        self._owns_connection=connection is None
        if connection is None:
            path=Path(database_path);path.parent.mkdir(parents=True,exist_ok=True)
            connection=sqlite3.connect(path,timeout=30,check_same_thread=False)
        self._connection=connection;connection.row_factory=sqlite3.Row;connection.execute("PRAGMA foreign_keys = ON")
        self._prices=SQLitePriceIntelligenceSnapshotRepository(connection=connection)
        self._products=SQLiteProductSnapshotCaptureRepository(connection=connection)
        with connection:
            connection.execute(_TABLE)
            for operation in ("UPDATE","DELETE"):
                connection.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_price_analysis_receipt_no_{operation.lower()}
                BEFORE {operation} ON price_intelligence_analysis_receipts
                BEGIN SELECT RAISE(ABORT,'price analysis receipts are append-only'); END""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_price_analysis_candidate_group ON price_intelligence_analysis_receipts(candidate_id,finalized_group_id,generated_at,command_id)")

    def get_receipt(self,command_id):
        try:row=self._connection.execute("SELECT * FROM price_intelligence_analysis_receipts WHERE command_id=?",(command_id,)).fetchone()
        except sqlite3.Error as error:raise PriceAnalysisReceiptPersistenceError("Price analysis receipt query failed") from error
        return None if row is None else self._receipt(row)

    def _receipt(self,row):
        try:
            if row["receipt_schema_version"]!=PRICE_ANALYSIS_RECEIPT_SCHEMA_VERSION: raise UnsupportedPriceAnalysisReceiptVersionError("unsupported persisted Price analysis receipt version")
            ids=json.loads(row["ordered_product_snapshot_ids_json"])
            if not isinstance(ids,list):raise ValueError("ordered Product Snapshot IDs must be a list")
            return PriceIntelligenceAnalysisReceipt(row["command_id"],row["candidate_id"],row["finalized_group_id"],row["price_snapshot_id"],row["command_fingerprint"],tuple(ids),row["analyzer_version"],Decimal(row["fallback_multiplier"]),datetime.fromisoformat(row["requested_at"]),datetime.fromisoformat(row["generated_at"]),datetime.fromisoformat(row["committed_at"]),row["receipt_schema_version"])
        except UnsupportedPriceAnalysisReceiptVersionError:raise
        except (ValueError,TypeError,KeyError,json.JSONDecodeError,InvalidOperation) as error:raise MalformedPriceAnalysisReceiptError("persisted Price analysis receipt is malformed") from error

    def get_result(self,receipt):
        snapshot=self._prices.get_snapshot(receipt.price_snapshot_id)
        if snapshot is None:raise MalformedPriceAnalysisReceiptError("Price analysis receipt references missing Snapshot")
        if (snapshot.candidate_identity.candidate_id!=receipt.candidate_id or snapshot.product_observation_snapshot_ids!=receipt.product_snapshot_ids or snapshot.analyzer_version!=receipt.analyzer_version or snapshot.generated_at!=receipt.generated_at):
            raise MalformedPriceAnalysisReceiptError("Price analysis receipt and Snapshot lineage differ")
        command=AnalyzeAndPersistPriceIntelligenceCommand(receipt.command_id,snapshot.candidate_identity,
            receipt.finalized_group_id,receipt.product_snapshot_ids,snapshot.market_observation_identity,
            receipt.fallback_multiplier,receipt.analyzer_version,receipt.requested_at)
        if command.fingerprint!=receipt.command_fingerprint:
            raise MalformedPriceAnalysisReceiptError("receipt command fingerprint is inconsistent")
        self.load_sources(command)
        return PriceAnalysisResult(snapshot,receipt,False)

    def load_sources(self,command):
        lineage=self._products.get_candidate_lineage(command.candidate_identity.candidate_id)
        if lineage is None:raise PriceAnalysisSourceNotFoundError("Candidate/Context is missing")
        discovery_reference,group_id,market_identity=lineage
        if discovery_reference!=command.candidate_identity.discovery_reference:raise PriceAnalysisCandidateMismatchError("Candidate discovery reference differs")
        if group_id!=command.finalized_group_id:raise PriceAnalysisGroupMismatchError("Candidate finalized group differs")
        if market_identity!=command.market_observation_identity:raise PriceAnalysisMarketIdentityConflictError("Candidate Market identity differs")
        group=self._products.get_group(command.finalized_group_id)
        if group is None:raise PriceAnalysisSourceNotFoundError("Finalized ProductGroup is missing")
        if len(group.observation_ids)!=len(command.product_snapshot_ids):raise PriceAnalysisProductOrderConflictError("Product Snapshot count differs from group membership")
        result=[];source_observation_ids=[]
        for snapshot_id in command.product_snapshot_ids:
            snapshot=self._products._snapshots.get_snapshot(snapshot_id)
            binding=self._products._binding(snapshot_id)
            if snapshot is None or binding is None:raise PriceAnalysisSourceNotFoundError("Product Snapshot or source binding is missing")
            if snapshot.candidate_identity!=command.candidate_identity:raise PriceAnalysisCandidateMismatchError("Product Snapshot Candidate differs")
            if snapshot.market_observation_identity!=command.market_observation_identity:raise PriceAnalysisMarketIdentityConflictError("Product Snapshot Market identity differs")
            source_observation_ids.append(binding.collected_observation_id);result.append(snapshot)
        if tuple(source_observation_ids)!=group.observation_ids:raise PriceAnalysisProductOrderConflictError("Product Snapshot source order differs from finalized group")
        return tuple(result)

    def save_analysis_result(self,command,snapshot,receipt):
        try:self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:raise PriceAnalysisCommitError("Price analysis transaction could not start") from error
        try:
            existing=self.get_receipt(command.command_id)
            if existing is not None:
                if existing.command_fingerprint!=command.fingerprint:raise PriceAnalysisCommandConflictError("Price analysis command payload conflicts")
                result=self.get_result(existing);self._connection.rollback();return PriceAnalysisResult(result.snapshot,result.receipt,True)
            sources=self.load_sources(command)
            if tuple(value.snapshot_id for value in sources)!=snapshot.product_observation_snapshot_ids:raise PriceAnalysisProductOrderConflictError("Snapshot ordered sources differ")
            if receipt.command_fingerprint!=command.fingerprint or receipt.price_snapshot_id!=snapshot.snapshot_id:raise PriceAnalysisCommandConflictError("Price analysis result does not match command")
            self._prices._validate_lineage(snapshot)
            try:self._prices._insert(snapshot,price_snapshot_fingerprint(snapshot))
            except sqlite3.Error as error:raise PriceIntelligenceSnapshotHistoryError("Price Snapshot history insert failed") from error
            try:self._insert_receipt(receipt)
            except sqlite3.Error as error:raise PriceAnalysisReceiptPersistenceError("Price analysis receipt insert failed") from error
            try:self._commit()
            except sqlite3.Error as error:raise PriceAnalysisCommitError("Price analysis commit failed") from error
            return PriceAnalysisResult(snapshot,receipt,False)
        except Exception:
            if self._connection.in_transaction:self._connection.rollback()
            raise

    def _insert_receipt(self,r):
        self._connection.execute("INSERT INTO price_intelligence_analysis_receipts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(r.command_id,r.candidate_id,r.finalized_group_id,r.price_snapshot_id,r.command_fingerprint,json.dumps(r.product_snapshot_ids,separators=(",", ":")),r.analyzer_version,str(r.fallback_multiplier),r.requested_at.isoformat(),r.generated_at.isoformat(),r.committed_at.isoformat(),r.schema_version,datetime.now(timezone.utc).isoformat()))
    def _commit(self):self._connection.commit()

    def get_by_candidate_group(self,candidate_id,finalized_group_id):
        try:rows=self._connection.execute("SELECT * FROM price_intelligence_analysis_receipts WHERE candidate_id=? AND finalized_group_id=? ORDER BY generated_at,command_id",(candidate_id,finalized_group_id)).fetchall()
        except sqlite3.Error as error:raise PriceAnalysisReceiptPersistenceError("Price analysis query failed") from error
        return tuple(self.get_result(self._receipt(row)) for row in rows)

    def close(self):
        if self._owns_connection:self._connection.close()
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
