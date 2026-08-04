"""Immutable Candidate-scoped Product Observation Snapshot persistence."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.product_observation import (
    MalformedProductObservationSnapshotPersistenceError,
    ProductObservationSnapshotCandidateMismatchError,
    ProductObservationSnapshotCandidateNotFoundError,
    ProductObservationSnapshotCommitError,
    ProductObservationSnapshotConflictError,
    ProductObservationSnapshotHistoryError,
    ProductObservationSnapshotMarketIdentityConflictError,
    UnsupportedProductObservationSnapshotVersionError,
)
from app.domain.discovery_identity import OpportunityCandidateIdentity
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.domain.product_observation import (
    PRODUCT_OBSERVATION_SNAPSHOT_SCHEMA_VERSION, CollectorProvenance,
    ObservedProductSnapshot, ProductObservationSnapshot,
)
from app.models import ProductDataSource


_TABLE="""CREATE TABLE IF NOT EXISTS product_observation_snapshot_history(
 snapshot_id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL,
 candidate_discovery_reference TEXT NOT NULL, market_identity_payload_json TEXT NOT NULL,
 observed_product_payload_json TEXT NOT NULL, collector_provenance_payload_json TEXT NOT NULL,
 observed_at TEXT NOT NULL, snapshot_schema_version TEXT NOT NULL,
 payload_fingerprint TEXT NOT NULL, inserted_at TEXT NOT NULL,
 FOREIGN KEY(candidate_id) REFERENCES opportunity_candidate_history(candidate_id))"""


def _identity_dict(value):
    return {"scope":value.scope.value,"market":value.market,"marketplace":value.marketplace,
        "canonical_product_id":value.canonical_product_id,"marketplace_item_id":value.marketplace_item_id,
        "normalized_query":value.normalized_query,"category":value.category,
        "variant_identity":value.variant_identity,"condition":value.condition,
        "window_started_at":value.window_started_at.isoformat(),"window_ended_at":value.window_ended_at.isoformat()}


def _dump(value):return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True)


def _payload(snapshot):
    product=snapshot.product
    return {"snapshot_id":snapshot.snapshot_id,"candidate":{"candidate_id":snapshot.candidate_identity.candidate_id,
        "discovery_reference":snapshot.candidate_identity.discovery_reference},
        "market_identity":_identity_dict(snapshot.market_observation_identity),
        "product":{name:(getattr(product,name).value if name=="data_source" else getattr(product,name)) for name in product.__dataclass_fields__},
        "collector":{name:getattr(snapshot.collector_provenance,name) for name in snapshot.collector_provenance.__dataclass_fields__},
        "observed_at":snapshot.observed_at.isoformat(),"schema_version":snapshot.schema_version}


def product_snapshot_fingerprint(snapshot):
    return hashlib.sha256(_dump(_payload(snapshot)).encode("utf-8")).hexdigest()


class SQLiteProductObservationSnapshotRepository:
    def __init__(self,database_path=None,*,connection=None):
        if (database_path is None)==(connection is None):raise ValueError("provide exactly one database_path or connection")
        self._owns_connection=connection is None
        if connection is None:
            path=Path(database_path);path.parent.mkdir(parents=True,exist_ok=True)
            connection=sqlite3.connect(path,timeout=30,check_same_thread=False)
        self._connection=connection;connection.row_factory=sqlite3.Row;connection.execute("PRAGMA foreign_keys = ON")
        with connection:
            connection.execute(_TABLE)
            for operation in ("UPDATE","DELETE"):
                connection.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_product_observation_snapshot_no_{operation.lower()}
                BEFORE {operation} ON product_observation_snapshot_history
                BEGIN SELECT RAISE(ABORT,'product observation snapshot history is append-only'); END""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_product_snapshot_candidate ON product_observation_snapshot_history(candidate_id,observed_at,snapshot_id)")

    def _begin(self):
        try:self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:raise ProductObservationSnapshotCommitError("Product Snapshot transaction could not start") from error
    def _commit(self):self._connection.commit()
    def _rollback(self):
        if self._connection.in_transaction:self._connection.rollback()

    def save_snapshot(self,snapshot):
        if not isinstance(snapshot,ProductObservationSnapshot):raise TypeError("snapshot must be ProductObservationSnapshot")
        if snapshot.schema_version!=PRODUCT_OBSERVATION_SNAPSHOT_SCHEMA_VERSION:
            raise UnsupportedProductObservationSnapshotVersionError("unsupported Product Snapshot version")
        fingerprint=product_snapshot_fingerprint(snapshot);self._begin()
        try:
            row=self._connection.execute("SELECT payload_fingerprint FROM product_observation_snapshot_history WHERE snapshot_id=?",(snapshot.snapshot_id,)).fetchone()
            if row:
                if row[0]!=fingerprint:raise ProductObservationSnapshotConflictError("snapshot ID payload conflicts")
                result=self.get_snapshot(snapshot.snapshot_id);self._rollback();return result
            self._validate_lineage(snapshot)
            try:self._insert(snapshot,fingerprint)
            except sqlite3.Error as error:raise ProductObservationSnapshotHistoryError("Product Snapshot history insert failed") from error
            try:self._commit()
            except sqlite3.Error as error:raise ProductObservationSnapshotCommitError("Product Snapshot commit failed") from error
            return snapshot
        except Exception:self._rollback();raise

    def _validate_lineage(self,snapshot):
        try:
            candidate=self._connection.execute("SELECT discovery_reference FROM opportunity_candidate_history WHERE candidate_id=?",(snapshot.candidate_identity.candidate_id,)).fetchone()
            context=self._connection.execute("SELECT market_identity_payload_json FROM opportunity_candidate_context_history WHERE candidate_id=?",(snapshot.candidate_identity.candidate_id,)).fetchone()
        except sqlite3.Error as error:raise ProductObservationSnapshotHistoryError("Candidate lineage query failed") from error
        if candidate is None or context is None:raise ProductObservationSnapshotCandidateNotFoundError("persisted Candidate and Context are required")
        if candidate[0]!=snapshot.candidate_identity.discovery_reference:
            raise ProductObservationSnapshotCandidateMismatchError("Candidate discovery reference differs")
        try:persisted=json.loads(context[0])
        except (TypeError,ValueError) as error:raise MalformedProductObservationSnapshotPersistenceError("persisted Candidate context is malformed") from error
        if persisted!=_identity_dict(snapshot.market_observation_identity):
            raise ProductObservationSnapshotMarketIdentityConflictError("Snapshot Market identity differs from Candidate Context")
        identity=snapshot.market_observation_identity;product=snapshot.product
        if product.marketplace!=identity.marketplace:
            raise ProductObservationSnapshotMarketIdentityConflictError("Product marketplace differs from Market identity")
        if identity.scope is MarketObservationScope.LISTING and product.item_id!=identity.marketplace_item_id:
            raise ProductObservationSnapshotMarketIdentityConflictError("Product item differs from listing identity")

    def _insert(self,s,fingerprint):
        p=_payload(s)
        self._connection.execute("INSERT INTO product_observation_snapshot_history VALUES(?,?,?,?,?,?,?,?,?,?)",
            (s.snapshot_id,s.candidate_identity.candidate_id,s.candidate_identity.discovery_reference,
             _dump(p["market_identity"]),_dump(p["product"]),_dump(p["collector"]),s.observed_at.isoformat(),
             s.schema_version,fingerprint,datetime.now(timezone.utc).isoformat()))

    def get_snapshot(self,snapshot_id):
        try:row=self._connection.execute("SELECT * FROM product_observation_snapshot_history WHERE snapshot_id=?",(snapshot_id,)).fetchone()
        except sqlite3.Error as error:raise ProductObservationSnapshotHistoryError("Product Snapshot query failed") from error
        return None if row is None else self._from_row(row)

    def get_by_candidate(self,candidate_identity):
        if not isinstance(candidate_identity,OpportunityCandidateIdentity):raise TypeError("candidate_identity must be OpportunityCandidateIdentity")
        try:rows=self._connection.execute("SELECT * FROM product_observation_snapshot_history WHERE candidate_id=? ORDER BY observed_at,snapshot_id",(candidate_identity.candidate_id,)).fetchall()
        except sqlite3.Error as error:raise ProductObservationSnapshotHistoryError("Product Snapshot Candidate query failed") from error
        values=tuple(self._from_row(row) for row in rows)
        if any(value.candidate_identity!=candidate_identity for value in values):raise ProductObservationSnapshotCandidateMismatchError("persisted Candidate subject differs")
        return values

    def get_by_market_identity(self,identity):
        if not isinstance(identity,MarketObservationIdentity):raise TypeError("market_observation_identity must be MarketObservationIdentity")
        payload=_dump(_identity_dict(identity))
        try:rows=self._connection.execute("SELECT * FROM product_observation_snapshot_history WHERE market_identity_payload_json=? ORDER BY observed_at,snapshot_id",(payload,)).fetchall()
        except sqlite3.Error as error:raise ProductObservationSnapshotHistoryError("Product Snapshot Market query failed") from error
        return tuple(self._from_row(row) for row in rows)

    def _from_row(self,row):
        try:
            if row["snapshot_schema_version"]!=PRODUCT_OBSERVATION_SNAPSHOT_SCHEMA_VERSION:raise UnsupportedProductObservationSnapshotVersionError("unsupported persisted Product Snapshot version")
            i=json.loads(row["market_identity_payload_json"]);p=json.loads(row["observed_product_payload_json"]);c=json.loads(row["collector_provenance_payload_json"])
            identity=MarketObservationIdentity(scope=MarketObservationScope(i["scope"]),market=i["market"],marketplace=i["marketplace"],canonical_product_id=i["canonical_product_id"],marketplace_item_id=i["marketplace_item_id"],normalized_query=i["normalized_query"],category=i["category"],variant_identity=i["variant_identity"],condition=i["condition"],window_started_at=datetime.fromisoformat(i["window_started_at"]),window_ended_at=datetime.fromisoformat(i["window_ended_at"]))
            product=ObservedProductSnapshot(**(p|{"data_source":ProductDataSource(p["data_source"])}))
            value=ProductObservationSnapshot(row["snapshot_id"],OpportunityCandidateIdentity(row["candidate_id"],row["candidate_discovery_reference"]),identity,product,CollectorProvenance(**c),datetime.fromisoformat(row["observed_at"]),row["snapshot_schema_version"])
            if product_snapshot_fingerprint(value)!=row["payload_fingerprint"]:raise ValueError("Product Snapshot fingerprint mismatch")
            return value
        except UnsupportedProductObservationSnapshotVersionError:raise
        except Exception as error:raise MalformedProductObservationSnapshotPersistenceError("persisted Product Snapshot is malformed") from error

    def close(self):
        if self._owns_connection:self._connection.close()
    def __enter__(self):return self
    def __exit__(self,*_):self.close()
