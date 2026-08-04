"""Candidate-scoped immutable PriceIntelligence Snapshot persistence."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.price_intelligence_snapshot import (
    MalformedPriceIntelligenceSnapshotPersistenceError,
    PriceIntelligenceSnapshotCandidateMismatchError,
    PriceIntelligenceSnapshotCommitError, PriceIntelligenceSnapshotConflictError,
    PriceIntelligenceSnapshotHistoryError, PriceIntelligenceSnapshotMarketMismatchError,
    UnsupportedPriceIntelligenceSnapshotVersionError,
)
from app.domain.discovery_identity import OpportunityCandidateIdentity
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.domain.price_intelligence import PRICE_INTELLIGENCE_SNAPSHOT_SCHEMA_VERSION, PriceIntelligenceSnapshot
from app.domain.product_observation import PRODUCT_OBSERVATION_SNAPSHOT_SCHEMA_VERSION
from app.infrastructure.product_observation.sqlite_repository import (
    SQLiteProductObservationSnapshotRepository, _dump, _identity_dict,
)


_TABLE="""CREATE TABLE IF NOT EXISTS price_intelligence_snapshot_history(
 snapshot_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL, discovery_reference TEXT NOT NULL,
 market_identity_payload_json TEXT NOT NULL, ordered_product_snapshot_ids_json TEXT NOT NULL,
 analyzer_version TEXT NOT NULL, currency TEXT NOT NULL, lowest_price TEXT NOT NULL,
 average_price TEXT NOT NULL, median_price TEXT NOT NULL, highest_price TEXT NOT NULL,
 price_range TEXT NOT NULL, variation_rate TEXT NOT NULL, stability TEXT NOT NULL,
 recommended_price TEXT NOT NULL, sample_size INTEGER NOT NULL, generated_at TEXT NOT NULL,
 schema_version TEXT NOT NULL, payload_fingerprint TEXT NOT NULL, inserted_at TEXT NOT NULL,
 FOREIGN KEY(candidate_id) REFERENCES opportunity_candidate_history(candidate_id))"""


def _payload(value):
    return {"snapshot_id":value.snapshot_id,"candidate":{"candidate_id":value.candidate_identity.candidate_id,
        "discovery_reference":value.candidate_identity.discovery_reference},
        "market_identity":_identity_dict(value.market_observation_identity),
        "product_snapshot_ids":list(value.product_observation_snapshot_ids),"analyzer_version":value.analyzer_version,
        "currency":value.currency,"lowest_price":str(value.lowest_price),"average_price":str(value.average_price),
        "median_price":str(value.median_price),"highest_price":str(value.highest_price),"price_range":str(value.price_range),
        "variation_rate":str(value.price_variation_rate),"stability":value.price_stability_level,
        "recommended_price":str(value.recommended_selling_price),"sample_size":value.sample_size,
        "generated_at":value.generated_at.isoformat(),"schema_version":value.schema_version}


def price_snapshot_fingerprint(value):return hashlib.sha256(_dump(_payload(value)).encode("utf-8")).hexdigest()


class SQLitePriceIntelligenceSnapshotRepository:
    def __init__(self,database_path=None,*,connection=None):
        if (database_path is None)==(connection is None):raise ValueError("provide exactly one database_path or connection")
        self._owns_connection=connection is None
        if connection is None:
            path=Path(database_path);path.parent.mkdir(parents=True,exist_ok=True)
            connection=sqlite3.connect(path,timeout=30,check_same_thread=False)
        self._connection=connection;connection.row_factory=sqlite3.Row;connection.execute("PRAGMA foreign_keys = ON")
        self._products=SQLiteProductObservationSnapshotRepository(connection=connection)
        with connection:
            connection.execute(_TABLE)
            for operation in ("UPDATE","DELETE"):
                connection.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_price_intelligence_snapshot_no_{operation.lower()}
                BEFORE {operation} ON price_intelligence_snapshot_history
                BEGIN SELECT RAISE(ABORT,'price intelligence snapshot history is append-only'); END""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_price_snapshot_candidate ON price_intelligence_snapshot_history(candidate_id,generated_at,snapshot_id)")

    def _begin(self):
        try:self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:raise PriceIntelligenceSnapshotCommitError("Price Snapshot transaction could not start") from error
    def _commit(self):self._connection.commit()
    def _rollback(self):
        if self._connection.in_transaction:self._connection.rollback()

    def save_snapshot(self,snapshot):
        if not isinstance(snapshot,PriceIntelligenceSnapshot):raise TypeError("snapshot must be PriceIntelligenceSnapshot")
        if snapshot.schema_version!=PRICE_INTELLIGENCE_SNAPSHOT_SCHEMA_VERSION:
            raise UnsupportedPriceIntelligenceSnapshotVersionError("unsupported Price Snapshot version")
        fingerprint=price_snapshot_fingerprint(snapshot);self._begin()
        try:
            row=self._connection.execute("SELECT payload_fingerprint FROM price_intelligence_snapshot_history WHERE snapshot_id=?",(snapshot.snapshot_id,)).fetchone()
            if row:
                if row[0]!=fingerprint:raise PriceIntelligenceSnapshotConflictError("Price Snapshot ID payload conflicts")
                result=self.get_snapshot(snapshot.snapshot_id);self._rollback();return result
            self._validate_lineage(snapshot)
            try:self._insert(snapshot,fingerprint)
            except sqlite3.Error as error:raise PriceIntelligenceSnapshotHistoryError("Price Snapshot history insert failed") from error
            try:self._commit()
            except sqlite3.Error as error:raise PriceIntelligenceSnapshotCommitError("Price Snapshot commit failed") from error
            return snapshot
        except Exception:self._rollback();raise

    def _validate_lineage(self,snapshot):
        try:
            candidate=self._connection.execute("SELECT discovery_reference FROM opportunity_candidate_history WHERE candidate_id=?",(snapshot.candidate_identity.candidate_id,)).fetchone()
            context=self._connection.execute("SELECT market_identity_payload_json FROM opportunity_candidate_context_history WHERE candidate_id=?",(snapshot.candidate_identity.candidate_id,)).fetchone()
        except sqlite3.Error as error:raise PriceIntelligenceSnapshotHistoryError("Price Snapshot Candidate query failed") from error
        if candidate is None or context is None or candidate[0]!=snapshot.candidate_identity.discovery_reference:
            raise PriceIntelligenceSnapshotCandidateMismatchError("persisted Candidate/Context differs")
        try:persisted_identity=json.loads(context[0])
        except (TypeError,ValueError) as error:raise MalformedPriceIntelligenceSnapshotPersistenceError("Candidate Context is malformed") from error
        if persisted_identity!=_identity_dict(snapshot.market_observation_identity):
            raise PriceIntelligenceSnapshotMarketMismatchError("Price Snapshot Market identity differs from Candidate Context")
        if snapshot.sample_size!=len(snapshot.product_observation_snapshot_ids):
            raise PriceIntelligenceSnapshotHistoryError("Price Snapshot sample size differs from ordered cohort")
        for snapshot_id in snapshot.product_observation_snapshot_ids:
            try:product=self._products.get_snapshot(snapshot_id)
            except Exception as error:raise PriceIntelligenceSnapshotHistoryError("Product Snapshot lineage is malformed") from error
            if product is None:raise PriceIntelligenceSnapshotHistoryError("Product Snapshot lineage is missing")
            if product.schema_version!=PRODUCT_OBSERVATION_SNAPSHOT_SCHEMA_VERSION:
                raise PriceIntelligenceSnapshotHistoryError("unsupported Product Snapshot lineage")
            if product.candidate_identity!=snapshot.candidate_identity:
                raise PriceIntelligenceSnapshotCandidateMismatchError("Product Snapshot Candidate differs")
            if product.market_observation_identity!=snapshot.market_observation_identity:
                raise PriceIntelligenceSnapshotMarketMismatchError("Product Snapshot Market identity differs")

    def _insert(self,s,fingerprint):
        self._connection.execute("INSERT INTO price_intelligence_snapshot_history VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (s.snapshot_id,s.candidate_identity.candidate_id,s.candidate_identity.discovery_reference,
             _dump(_identity_dict(s.market_observation_identity)),_dump(list(s.product_observation_snapshot_ids)),s.analyzer_version,s.currency,
             str(s.lowest_price),str(s.average_price),str(s.median_price),str(s.highest_price),str(s.price_range),
             str(s.price_variation_rate),s.price_stability_level,str(s.recommended_selling_price),s.sample_size,
             s.generated_at.isoformat(),s.schema_version,fingerprint,datetime.now(timezone.utc).isoformat()))

    def get_snapshot(self,snapshot_id):
        try:row=self._connection.execute("SELECT * FROM price_intelligence_snapshot_history WHERE snapshot_id=?",(snapshot_id,)).fetchone()
        except sqlite3.Error as error:raise PriceIntelligenceSnapshotHistoryError("Price Snapshot query failed") from error
        return None if row is None else self._from_row(row)

    def get_by_candidate(self,candidate_identity):
        if not isinstance(candidate_identity,OpportunityCandidateIdentity):raise TypeError("candidate_identity must be OpportunityCandidateIdentity")
        try:rows=self._connection.execute("SELECT * FROM price_intelligence_snapshot_history WHERE candidate_id=? ORDER BY generated_at,snapshot_id",(candidate_identity.candidate_id,)).fetchall()
        except sqlite3.Error as error:raise PriceIntelligenceSnapshotHistoryError("Price Snapshot Candidate query failed") from error
        values=tuple(self._from_row(row) for row in rows)
        if any(value.candidate_identity!=candidate_identity for value in values):raise PriceIntelligenceSnapshotCandidateMismatchError("persisted Candidate differs")
        return values

    def get_by_market_identity(self,identity):
        if not isinstance(identity,MarketObservationIdentity):raise TypeError("market_observation_identity must be MarketObservationIdentity")
        try:rows=self._connection.execute("SELECT * FROM price_intelligence_snapshot_history WHERE market_identity_payload_json=? ORDER BY generated_at,snapshot_id",(_dump(_identity_dict(identity)),)).fetchall()
        except sqlite3.Error as error:raise PriceIntelligenceSnapshotHistoryError("Price Snapshot Market query failed") from error
        return tuple(self._from_row(row) for row in rows)

    def _from_row(self,row):
        try:
            if row["schema_version"]!=PRICE_INTELLIGENCE_SNAPSHOT_SCHEMA_VERSION:raise UnsupportedPriceIntelligenceSnapshotVersionError("unsupported persisted Price Snapshot version")
            i=json.loads(row["market_identity_payload_json"]);source_ids=json.loads(row["ordered_product_snapshot_ids_json"])
            identity=MarketObservationIdentity(scope=MarketObservationScope(i["scope"]),market=i["market"],marketplace=i["marketplace"],canonical_product_id=i["canonical_product_id"],marketplace_item_id=i["marketplace_item_id"],normalized_query=i["normalized_query"],category=i["category"],variant_identity=i["variant_identity"],condition=i["condition"],window_started_at=datetime.fromisoformat(i["window_started_at"]),window_ended_at=datetime.fromisoformat(i["window_ended_at"]))
            value=PriceIntelligenceSnapshot(row["snapshot_id"],OpportunityCandidateIdentity(row["candidate_id"],row["discovery_reference"]),identity,tuple(source_ids),row["currency"],Decimal(row["lowest_price"]),Decimal(row["average_price"]),Decimal(row["median_price"]),Decimal(row["highest_price"]),Decimal(row["price_range"]),Decimal(row["variation_rate"]),row["stability"],Decimal(row["recommended_price"]),row["sample_size"],row["analyzer_version"],datetime.fromisoformat(row["generated_at"]),row["schema_version"])
            if price_snapshot_fingerprint(value)!=row["payload_fingerprint"]:raise ValueError("Price Snapshot fingerprint mismatch")
            return value
        except UnsupportedPriceIntelligenceSnapshotVersionError:raise
        except (json.JSONDecodeError,KeyError,TypeError,ValueError,InvalidOperation) as error:
            raise MalformedPriceIntelligenceSnapshotPersistenceError("persisted Price Snapshot is malformed") from error

    def close(self):
        if self._owns_connection:self._connection.close()
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
