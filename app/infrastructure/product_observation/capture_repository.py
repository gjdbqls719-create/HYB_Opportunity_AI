"""Atomic SQLite owner persistence for collector-sourced Product snapshots."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import sqlite3

from app.application.product_snapshot_capture import (
    MalformedProductSnapshotCapturePersistenceError,
    ProductSnapshotCaptureHistoryError,
    ProductSnapshotCaptureResult,
    ProductSnapshotSourceConflictError,
    SnapshotOwnerCommandConflictError,
    SnapshotOwnerCommitError,
    UnsupportedProductSnapshotCaptureVersionError,
)
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.application.product_snapshot_capture import (
    PRODUCT_SNAPSHOT_CAPTURE_RECEIPT_SCHEMA_VERSION,
    PRODUCT_SNAPSHOT_SOURCE_BINDING_SCHEMA_VERSION,
    ProductSnapshotCaptureReceipt,
    ProductSnapshotSourceBinding,
)
from app.infrastructure.discovery.sqlite_observation_group_repository import (
    SQLiteDiscoveryGroupRepository,
    SQLiteDiscoveryObservationRepository,
)
from app.infrastructure.product_observation.sqlite_repository import (
    SQLiteProductObservationSnapshotRepository,
    product_snapshot_fingerprint,
)


_BINDING_TABLE = """CREATE TABLE IF NOT EXISTS product_snapshot_source_binding_history(
 product_snapshot_id TEXT PRIMARY KEY, collected_observation_id TEXT NOT NULL,
 candidate_id TEXT NOT NULL, capture_command_id TEXT NOT NULL, bound_at TEXT NOT NULL,
 binding_schema_version TEXT NOT NULL, UNIQUE(candidate_id,collected_observation_id),
 FOREIGN KEY(product_snapshot_id) REFERENCES product_observation_snapshot_history(snapshot_id),
 FOREIGN KEY(collected_observation_id) REFERENCES discovery_collected_observation_history(observation_id),
 FOREIGN KEY(candidate_id) REFERENCES opportunity_candidate_history(candidate_id))"""
_RECEIPT_TABLE = """CREATE TABLE IF NOT EXISTS product_snapshot_capture_receipts(
 command_id TEXT PRIMARY KEY, command_fingerprint TEXT NOT NULL, candidate_id TEXT NOT NULL,
 ordered_product_snapshot_ids_json TEXT NOT NULL, committed_at TEXT NOT NULL,
 receipt_schema_version TEXT NOT NULL,
 FOREIGN KEY(candidate_id) REFERENCES opportunity_candidate_history(candidate_id))"""


def _identity(payload: str) -> MarketObservationIdentity:
    value = json.loads(payload)
    return MarketObservationIdentity(
        scope=MarketObservationScope(value["scope"]), market=value["market"],
        marketplace=value["marketplace"], canonical_product_id=value["canonical_product_id"],
        marketplace_item_id=value["marketplace_item_id"], normalized_query=value["normalized_query"],
        category=value["category"], variant_identity=value["variant_identity"],
        condition=value["condition"], window_started_at=datetime.fromisoformat(value["window_started_at"]),
        window_ended_at=datetime.fromisoformat(value["window_ended_at"]),
    )


class SQLiteProductSnapshotCaptureRepository:
    def __init__(self, database_path=None, *, connection=None):
        if (database_path is None) == (connection is None):
            raise ValueError("provide exactly one database_path or connection")
        self._owns_connection = connection is None
        if connection is None:
            path = Path(database_path); path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self._connection = connection; connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        self._snapshots = SQLiteProductObservationSnapshotRepository(connection=connection)
        self._groups = SQLiteDiscoveryGroupRepository(connection=connection)
        self._observations = SQLiteDiscoveryObservationRepository(connection=connection)
        with connection:
            connection.execute(_BINDING_TABLE); connection.execute(_RECEIPT_TABLE)
            for table in ("product_snapshot_source_binding_history", "product_snapshot_capture_receipts"):
                for operation in ("UPDATE", "DELETE"):
                    connection.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()}
                    BEFORE {operation} ON {table}
                    BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END""")

    def get_candidate_lineage(self, candidate_id):
        try:
            row = self._connection.execute("""SELECT h.discovery_reference,h.finalized_group_id,c.market_identity_payload_json
                FROM opportunity_candidate_history h JOIN opportunity_candidate_context_history c
                ON c.candidate_id=h.candidate_id WHERE h.candidate_id=?""", (candidate_id,)).fetchone()
        except sqlite3.Error as error:
            raise ProductSnapshotCaptureHistoryError("Candidate lineage query failed") from error
        if row is None: return None
        try: return row[0], row[1], _identity(row[2])
        except Exception as error:
            raise MalformedProductSnapshotCapturePersistenceError("persisted Candidate lineage is malformed") from error

    def get_group(self, finalized_group_id): return self._groups.get_group(finalized_group_id)
    def get_observation(self, observation_id): return self._observations.get_observation(observation_id)

    def get_receipt(self, command_id):
        try:
            row = self._connection.execute("SELECT * FROM product_snapshot_capture_receipts WHERE command_id=?", (command_id,)).fetchone()
        except sqlite3.Error as error:
            raise ProductSnapshotCaptureHistoryError("capture receipt query failed") from error
        if row is None: return None
        try:
            if row["receipt_schema_version"] != PRODUCT_SNAPSHOT_CAPTURE_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedProductSnapshotCaptureVersionError("unsupported persisted capture receipt version")
            ids = json.loads(row["ordered_product_snapshot_ids_json"])
            if not isinstance(ids, list): raise ValueError("snapshot IDs must be a JSON list")
            return ProductSnapshotCaptureReceipt(row["command_id"], row["command_fingerprint"],
                row["candidate_id"], tuple(ids), datetime.fromisoformat(row["committed_at"]),
                row["receipt_schema_version"])
        except UnsupportedProductSnapshotCaptureVersionError: raise
        except Exception as error:
            raise MalformedProductSnapshotCapturePersistenceError("persisted capture receipt is malformed") from error

    def _binding(self, snapshot_id):
        try:
            row = self._connection.execute("SELECT * FROM product_snapshot_source_binding_history WHERE product_snapshot_id=?", (snapshot_id,)).fetchone()
        except sqlite3.Error as error:
            raise ProductSnapshotCaptureHistoryError("source binding query failed") from error
        if row is None: return None
        if row["binding_schema_version"] != PRODUCT_SNAPSHOT_SOURCE_BINDING_SCHEMA_VERSION:
            raise UnsupportedProductSnapshotCaptureVersionError("unsupported persisted source binding version")
        try:
            return ProductSnapshotSourceBinding(row["product_snapshot_id"], row["collected_observation_id"],
                row["candidate_id"], row["capture_command_id"], datetime.fromisoformat(row["bound_at"]),
                row["binding_schema_version"])
        except Exception as error:
            raise MalformedProductSnapshotCapturePersistenceError("persisted source binding is malformed") from error

    def get_result(self, receipt):
        snapshots = tuple(self._snapshots.get_snapshot(value) for value in receipt.product_snapshot_ids)
        bindings = tuple(self._binding(value) for value in receipt.product_snapshot_ids)
        if any(value is None for value in snapshots + bindings):
            raise MalformedProductSnapshotCapturePersistenceError("receipt references missing immutable facts")
        return ProductSnapshotCaptureResult(snapshots, bindings, receipt, False)

    def persist_capture(self, command, snapshots, bindings, receipt):
        try: self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error: raise SnapshotOwnerCommitError("capture transaction could not start") from error
        try:
            existing = self.get_receipt(command.command_id)
            if existing is not None:
                if existing.command_fingerprint != command.fingerprint:
                    raise SnapshotOwnerCommandConflictError("capture command payload conflicts")
                result = self.get_result(existing); self._connection.rollback()
                return ProductSnapshotCaptureResult(result.snapshots, result.bindings, result.receipt, True)
            for snapshot, binding in zip(snapshots, bindings, strict=True):
                self._snapshots._validate_lineage(snapshot)
                observation = self.get_observation(binding.collected_observation_id)
                if observation is None or (observation.product != snapshot.product
                    or observation.collector_provenance != snapshot.collector_provenance
                    or observation.observed_at != snapshot.observed_at):
                    raise ProductSnapshotSourceConflictError("Snapshot differs from exact collector observation")
                source_row = self._connection.execute(
                    """SELECT product_snapshot_id FROM product_snapshot_source_binding_history
                    WHERE candidate_id=? AND collected_observation_id=?""",
                    (binding.candidate_id, binding.collected_observation_id),
                ).fetchone()
                if source_row is not None and source_row[0] != snapshot.snapshot_id:
                    raise ProductSnapshotSourceConflictError(
                        "collector observation is already published for this Candidate"
                    )
                fingerprint = product_snapshot_fingerprint(snapshot)
                row = self._connection.execute("SELECT payload_fingerprint FROM product_observation_snapshot_history WHERE snapshot_id=?", (snapshot.snapshot_id,)).fetchone()
                if row is None: self._snapshots._insert(snapshot, fingerprint)
                elif row[0] != fingerprint: raise ProductSnapshotSourceConflictError("Product Snapshot ID conflicts")
                current = self._binding(snapshot.snapshot_id)
                if current is None:
                    self._connection.execute("INSERT INTO product_snapshot_source_binding_history VALUES(?,?,?,?,?,?)",
                        (binding.product_snapshot_id, binding.collected_observation_id, binding.candidate_id,
                         binding.capture_command_id, binding.bound_at.isoformat(), binding.schema_version))
                elif current.collected_observation_id != binding.collected_observation_id or current.candidate_id != binding.candidate_id:
                    raise ProductSnapshotSourceConflictError("Product Snapshot source binding conflicts")
            self._connection.execute("INSERT INTO product_snapshot_capture_receipts VALUES(?,?,?,?,?,?)",
                (receipt.command_id, receipt.command_fingerprint, receipt.candidate_id,
                 json.dumps(receipt.product_snapshot_ids, separators=(",", ":")),
                 receipt.committed_at.isoformat(), receipt.schema_version))
            try: self._commit()
            except sqlite3.Error as error: raise SnapshotOwnerCommitError("capture transaction commit failed") from error
            committed = self.get_result(receipt)
            return ProductSnapshotCaptureResult(
                committed.snapshots, committed.bindings, committed.receipt, False
            )
        except (SnapshotOwnerCommandConflictError, ProductSnapshotSourceConflictError, SnapshotOwnerCommitError):
            if self._connection.in_transaction: self._connection.rollback()
            raise
        except sqlite3.Error as error:
            if self._connection.in_transaction: self._connection.rollback()
            raise ProductSnapshotCaptureHistoryError("capture history write failed") from error
        except Exception:
            if self._connection.in_transaction: self._connection.rollback()
            raise

    def close(self):
        if self._owns_connection: self._connection.close()
    def _commit(self): self._connection.commit()
    def __enter__(self): return self
    def __exit__(self, *_): self.close()
