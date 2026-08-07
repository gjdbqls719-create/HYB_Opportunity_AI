"""Append-only SQLite persistence for exact Sourcing Economics bindings."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.sourcing.economics_binding import (
    BindSourcingEconomicsSourceCommand,
    MalformedSourcingEconomicsBindingError,
    SOURCING_ECONOMICS_BINDING_RECEIPT_SCHEMA_VERSION,
    SourcingEconomicsBindingOpportunityMismatchError,
    SourcingEconomicsBindingReceipt,
    SourcingEconomicsBindingReplayConflictError,
    SourcingEconomicsBindingResult,
    SourcingEconomicsExactRevisionError,
    UnsupportedSourcingEconomicsBindingVersionError,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing import (
    SOURCING_ECONOMICS_BINDING_SCHEMA_VERSION,
    SourcingEconomicsBinding,
    SourcingEconomicsSourceReference,
)
from app.infrastructure.sourcing.sqlite_repository import SQLiteSourcingAuthorityRepository


class SourcingEconomicsBindingPersistenceError(RuntimeError): pass
class SourcingEconomicsBindingHistoryError(SourcingEconomicsBindingPersistenceError): pass
class SourcingEconomicsBindingReceiptError(SourcingEconomicsBindingPersistenceError): pass
class SourcingEconomicsBindingCommitError(SourcingEconomicsBindingPersistenceError): pass


def _aware(value: str, name: str) -> datetime:
    try:
        result = datetime.fromisoformat(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} is malformed") from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return result


def _payload(binding: SourcingEconomicsBinding) -> str:
    source = binding.source_reference
    return json.dumps({
        "binding_id": binding.binding_id,
        "opportunity_identity": {
            "opportunity_id": binding.opportunity_identity.opportunity_id,
            "discovery_reference": binding.opportunity_identity.discovery_reference,
        },
        "source_reference": {
            "admission_id": source.admission_id,
            "admission_revision": source.admission_revision,
            "quote_id": source.quote_id,
            "quote_revision": source.quote_revision,
            "schema_version": source.schema_version,
        },
        "requested_at": binding.requested_at.isoformat(),
        "bound_at": binding.bound_at.isoformat(),
        "schema_version": binding.schema_version,
    }, sort_keys=True, separators=(",", ":"))


class SQLiteSourcingEconomicsBindingRepository:
    """Persists a selected exact source; it never selects or calculates one."""

    def __init__(self, database_path: str | Path | None = None, *, connection=None):
        if (database_path is None) == (connection is None):
            raise ValueError("provide exactly one database_path or connection")
        self._owns_connection = connection is None
        if connection is None:
            path = Path(database_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._source = SQLiteSourcingAuthorityRepository(connection=self._connection)
        self._initialize_schema()

    def _initialize_schema(self):
        with self._connection:
            self._connection.execute("""CREATE TABLE IF NOT EXISTS sourcing_economics_binding_history(
                binding_id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL,
                discovery_reference TEXT NOT NULL, admission_id TEXT NOT NULL,
                admission_revision INTEGER NOT NULL, quote_id TEXT NOT NULL,
                quote_revision INTEGER NOT NULL, requested_at TEXT NOT NULL,
                bound_at TEXT NOT NULL, schema_version TEXT NOT NULL,
                payload_fingerprint TEXT NOT NULL, inserted_at TEXT NOT NULL,
                FOREIGN KEY(admission_id,admission_revision) REFERENCES
                  founder_sourcing_admission_history(admission_id,revision))""")
            self._connection.execute("""CREATE TABLE IF NOT EXISTS sourcing_economics_binding_receipts(
                command_id TEXT PRIMARY KEY, binding_id TEXT NOT NULL,
                command_fingerprint TEXT NOT NULL, committed_at TEXT NOT NULL,
                schema_version TEXT NOT NULL, inserted_at TEXT NOT NULL,
                FOREIGN KEY(binding_id) REFERENCES sourcing_economics_binding_history(binding_id))""")
            for table in ("sourcing_economics_binding_history", "sourcing_economics_binding_receipts"):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END"""
                    )

    def _rollback(self):
        if self._connection.in_transaction:
            self._connection.rollback()

    def _commit(self):
        self._connection.commit()

    def get_source_admission(self, reference):
        return self._source.get_admission_revision(reference.admission_id, reference.admission_revision)

    def _binding_row(self, binding_id):
        try:
            return self._connection.execute(
                "SELECT * FROM sourcing_economics_binding_history WHERE binding_id=?", (binding_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise SourcingEconomicsBindingHistoryError("binding query failed") from error

    def _binding(self, row):
        try:
            if row["schema_version"] != SOURCING_ECONOMICS_BINDING_SCHEMA_VERSION:
                raise UnsupportedSourcingEconomicsBindingVersionError("unsupported binding version")
            source = SourcingEconomicsSourceReference(
                row["admission_id"], row["admission_revision"], row["quote_id"], row["quote_revision"]
            )
            value = SourcingEconomicsBinding(
                row["binding_id"], OpportunityIdentity(row["opportunity_id"], row["discovery_reference"]),
                source, _aware(row["requested_at"], "requested_at"),
                _aware(row["bound_at"], "bound_at"), row["schema_version"],
            )
            if hashlib.sha256(_payload(value).encode()).hexdigest() != row["payload_fingerprint"]:
                raise ValueError("binding fingerprint mismatch")
            return value
        except UnsupportedSourcingEconomicsBindingVersionError:
            raise
        except Exception as error:
            raise MalformedSourcingEconomicsBindingError("persisted binding is malformed") from error

    def get_binding(self, binding_id):
        row = self._binding_row(binding_id)
        return None if row is None else self._binding(row)

    def _receipt_row(self, command_id):
        try:
            return self._connection.execute(
                "SELECT * FROM sourcing_economics_binding_receipts WHERE command_id=?", (command_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise SourcingEconomicsBindingReceiptError("receipt query failed") from error

    def _receipt(self, row):
        try:
            return SourcingEconomicsBindingReceipt(
                row["command_id"], row["binding_id"], row["command_fingerprint"],
                _aware(row["committed_at"], "committed_at"), row["schema_version"],
            )
        except UnsupportedSourcingEconomicsBindingVersionError:
            raise
        except Exception as error:
            raise MalformedSourcingEconomicsBindingError("persisted receipt is malformed") from error

    def get_receipt(self, command_id):
        row = self._receipt_row(command_id)
        return None if row is None else self._receipt(row)

    def validate_replay(self, command_id, fingerprint):
        row = self._receipt_row(command_id)
        if row is None:
            return None
        receipt = self._receipt(row)
        if receipt.command_fingerprint != fingerprint:
            raise SourcingEconomicsBindingReplayConflictError("binding command payload conflicts")
        binding = self.get_binding(receipt.binding_id)
        if binding is None:
            raise MalformedSourcingEconomicsBindingError("receipt references missing binding")
        return SourcingEconomicsBindingResult(binding, receipt, True)

    def save_binding(self, command, binding, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            admission = self.get_source_admission(command.source_reference)
            if admission is None or admission.to_economics_source_reference() != command.source_reference:
                raise SourcingEconomicsExactRevisionError("exact persisted source differs")
            if admission.selling_product_lineage.opportunity_identity != command.opportunity_identity:
                raise SourcingEconomicsBindingOpportunityMismatchError("persisted Opportunity lineage differs")
            payload = _payload(binding)
            fingerprint = hashlib.sha256(payload.encode()).hexdigest()
            try:
                self._connection.execute(
                    "INSERT INTO sourcing_economics_binding_history VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                    (binding.binding_id, binding.opportunity_identity.opportunity_id,
                     binding.opportunity_identity.discovery_reference,
                     binding.source_reference.admission_id, binding.source_reference.admission_revision,
                     binding.source_reference.quote_id, binding.source_reference.quote_revision,
                     binding.requested_at.isoformat(), binding.bound_at.isoformat(),
                     binding.schema_version, fingerprint, receipt.committed_at.isoformat()),
                )
            except sqlite3.Error as error:
                raise SourcingEconomicsBindingHistoryError("binding insert failed") from error
            try:
                self._connection.execute(
                    "INSERT INTO sourcing_economics_binding_receipts VALUES(?,?,?,?,?,?)",
                    (receipt.command_id, receipt.binding_id, receipt.command_fingerprint,
                     receipt.committed_at.isoformat(), receipt.schema_version,
                     receipt.committed_at.isoformat()),
                )
            except sqlite3.Error as error:
                raise SourcingEconomicsBindingReceiptError("receipt insert failed") from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise SourcingEconomicsBindingCommitError("binding commit failed") from error
            return SourcingEconomicsBindingResult(binding, receipt, False)
        except Exception:
            self._rollback()
            raise

    def close(self):
        self._rollback()
        if self._owns_connection:
            self._connection.close()

    def __enter__(self): return self
    def __exit__(self, exc_type, exc, traceback): self.close()


__all__ = [name for name in globals() if name.startswith("SQLite") or name.startswith("Sourcing")]
