"""File-backed operational Production Safety evaluation persistence."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.production_safety_evaluation import *
from app.application.production_safety_evaluation import (
    PRODUCTION_SAFETY_EVALUATION_RULE_VERSION,
    PRODUCTION_SAFETY_EVALUATION_SCHEMA_VERSION,
    PRODUCTION_SAFETY_PROVENANCE_SCHEMA_VERSION,
    PRODUCTION_SAFETY_RECEIPT_SCHEMA_VERSION,
)
from app.application.snapshot_chain_binding import (
    SnapshotChainBindingNotFoundError,
    SnapshotChainProductSourceConflictError,
)
from app.domain.opportunity import ProductionSafetyAssessment, ProductionSafetyStatus
from app.infrastructure.product_observation.capture_repository import _identity
from app.infrastructure.product_observation.sqlite_repository import _identity_dict
from app.infrastructure.snapshot_chain import SQLiteSnapshotChainBindingRepository


_HISTORY = """
CREATE TABLE IF NOT EXISTS production_safety_evaluation_history (
    evaluation_id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    evaluation_version INTEGER NOT NULL,
    status TEXT NOT NULL,
    missing_fields_json TEXT NOT NULL,
    failed_checks_json TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    evaluation_schema_version TEXT NOT NULL,
    subject_fingerprint TEXT NOT NULL,
    inserted_at TEXT NOT NULL,
    UNIQUE(opportunity_id, evaluation_version),
    UNIQUE(subject_fingerprint)
)
"""
_PROVENANCE = """
CREATE TABLE IF NOT EXISTS production_safety_evaluation_provenance (
    evaluation_id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    snapshot_chain_binding_id TEXT NOT NULL,
    candidate_opportunity_binding_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    selected_product_snapshot_id TEXT NOT NULL,
    price_intelligence_snapshot_id TEXT NOT NULL,
    economics_calculation_snapshot_id TEXT NOT NULL,
    verified_economics_opportunity_id TEXT NOT NULL,
    market_identity_payload_json TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    provenance_schema_version TEXT NOT NULL,
    inserted_at TEXT NOT NULL,
    FOREIGN KEY(evaluation_id) REFERENCES production_safety_evaluation_history(evaluation_id),
    FOREIGN KEY(snapshot_chain_binding_id) REFERENCES opportunity_snapshot_chain_binding_history(binding_id),
    FOREIGN KEY(selected_product_snapshot_id) REFERENCES product_observation_snapshot_history(snapshot_id)
)
"""
_CURRENT = """
CREATE TABLE IF NOT EXISTS production_safety_evaluation_current (
    opportunity_id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL,
    evaluation_version INTEGER NOT NULL,
    projected_at TEXT NOT NULL,
    FOREIGN KEY(evaluation_id) REFERENCES production_safety_evaluation_history(evaluation_id)
)
"""
_RECEIPTS = """
CREATE TABLE IF NOT EXISTS production_safety_evaluation_receipts (
    command_id TEXT PRIMARY KEY,
    evaluation_id TEXT NOT NULL,
    opportunity_id TEXT NOT NULL,
    snapshot_chain_binding_id TEXT NOT NULL,
    selected_product_snapshot_id TEXT NOT NULL,
    command_fingerprint TEXT NOT NULL,
    requested_at TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    committed_at TEXT NOT NULL,
    receipt_schema_version TEXT NOT NULL,
    inserted_at TEXT NOT NULL,
    FOREIGN KEY(evaluation_id) REFERENCES production_safety_evaluation_history(evaluation_id)
)
"""


def _dump(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _subject(binding_id: str, product_id: str, rule_version: str) -> str:
    payload = {"binding_id": binding_id, "product_id": product_id, "rule_version": rule_version}
    return hashlib.sha256(_dump(payload).encode()).hexdigest()


class SQLiteProductionSafetyEvaluationRepository:
    def __init__(self, database_path=None, *, connection=None) -> None:
        if (database_path is None) == (connection is None):
            raise ValueError("provide exactly one database_path or connection")
        self._owns_connection = connection is None
        if connection is None:
            path = Path(database_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self._connection = connection
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        self._chains = SQLiteSnapshotChainBindingRepository(connection=connection)
        with connection:
            for statement in (_HISTORY, _PROVENANCE, _CURRENT, _RECEIPTS):
                connection.execute(statement)
            for table in (
                "production_safety_evaluation_history",
                "production_safety_evaluation_provenance",
                "production_safety_evaluation_receipts",
            ):
                for operation in ("UPDATE", "DELETE"):
                    connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT, 'Production Safety evaluation facts are append-only'); END"""
                    )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_safety_evaluation_opportunity "
                "ON production_safety_evaluation_history(opportunity_id, evaluation_version)"
            )

    def get_context(self, binding_id, product_snapshot_id):
        try:
            return self._chains.build_evaluation_context(binding_id, product_snapshot_id)
        except SnapshotChainBindingNotFoundError as error:
            raise ProductionSafetyChainNotFoundError(binding_id) from error
        except SnapshotChainProductSourceConflictError as error:
            raise ProductionSafetySelectedProductConflictError(str(error)) from error
        except Exception as error:
            raise ProductionSafetySourceLineageError(str(error)) from error

    def get_bindings_by_opportunity(self, opportunity_id):
        return self._chains.get_by_opportunity(opportunity_id)

    def get_binding(self, binding_id):
        return self._chains.get_binding(binding_id)

    def get_product_snapshot(self, snapshot_id):
        return self._chains.get_product_snapshot(snapshot_id)

    @property
    def verified_economics_repository(self):
        return self._chains._owners._sources

    def persist(self, command, evaluation_id, assessment, rule_version, evaluated_at, committed_at):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:
            raise ProductionSafetyEvaluationCommitError("Safety transaction could not start") from error
        try:
            receipt = self.get_receipt(command.command_id)
            if receipt is not None:
                if receipt.command_fingerprint != command.fingerprint:
                    raise ProductionSafetyEvaluationCommandConflictError("Safety command conflicts")
                result = self._result(receipt, True)
                self._connection.rollback()
                return result
            context = self.get_context(
                command.snapshot_chain_binding_id,
                command.selected_product_snapshot_id,
            )
            binding = self._chains.get_binding(command.snapshot_chain_binding_id)
            if binding is None:
                raise ProductionSafetyChainNotFoundError(command.snapshot_chain_binding_id)
            if binding.opportunity_id != command.opportunity_id:
                raise ProductionSafetySourceLineageError("command Opportunity differs from chain")
            subject = _subject(binding.binding_id, command.selected_product_snapshot_id, rule_version)
            existing = self._connection.execute(
                "SELECT evaluation_id FROM production_safety_evaluation_history WHERE subject_fingerprint=?",
                (subject,),
            ).fetchone()
            if existing is not None:
                evaluation = self.get_evaluation(existing[0])
                provenance = self.get_provenance(existing[0])
                receipt = self._receipt(command, evaluation, provenance, committed_at)
                try:
                    self._insert_receipt(receipt)
                except sqlite3.Error as error:
                    raise ProductionSafetyReceiptPersistenceError("Safety receipt insert failed") from error
                try:
                    self._commit()
                except sqlite3.Error as error:
                    raise ProductionSafetyEvaluationCommitError("Safety commit failed") from error
                return ProductionSafetyEvaluationResult(evaluation, provenance, receipt, False)
            version = self._connection.execute(
                "SELECT COALESCE(MAX(evaluation_version),0)+1 FROM production_safety_evaluation_history WHERE opportunity_id=?",
                (command.opportunity_id,),
            ).fetchone()[0]
            evaluation = ProductionSafetyEvaluation(
                evaluation_id, command.opportunity_id, version, assessment,
                rule_version, evaluated_at,
            )
            provenance = ProductionSafetyEvaluationProvenance(
                evaluation_id=evaluation_id,
                opportunity_id=command.opportunity_id,
                snapshot_chain_binding_id=binding.binding_id,
                candidate_opportunity_binding_id=binding.candidate_opportunity_binding_id,
                candidate_id=binding.candidate_id,
                selected_product_snapshot_id=command.selected_product_snapshot_id,
                price_intelligence_snapshot_id=binding.price_snapshot_id,
                economics_calculation_snapshot_id=binding.economics_snapshot_id,
                verified_economics_opportunity_id=binding.verified_economics_opportunity_id,
                market_observation_identity=binding.market_observation_identity,
                rule_version=rule_version,
                evaluated_at=evaluated_at,
            )
            receipt = self._receipt(command, evaluation, provenance, committed_at)
            try:
                self._insert_history(evaluation, subject)
            except sqlite3.Error as error:
                raise ProductionSafetyEvaluationHistoryError("Safety history insert failed") from error
            try:
                self._insert_provenance(provenance)
            except sqlite3.Error as error:
                raise ProductionSafetyProvenancePersistenceError("Safety provenance insert failed") from error
            try:
                self._project_current(evaluation, committed_at)
            except sqlite3.Error as error:
                raise ProductionSafetyCurrentProjectionError("Safety current projection failed") from error
            try:
                self._insert_receipt(receipt)
            except sqlite3.Error as error:
                raise ProductionSafetyReceiptPersistenceError("Safety receipt insert failed") from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise ProductionSafetyEvaluationCommitError("Safety commit failed") from error
            return ProductionSafetyEvaluationResult(evaluation, provenance, receipt, False)
        except Exception:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise

    @staticmethod
    def _receipt(command, evaluation, provenance, committed_at):
        return ProductionSafetyEvaluationReceipt(
            command.command_id, evaluation.evaluation_id, evaluation.opportunity_id,
            provenance.snapshot_chain_binding_id, provenance.selected_product_snapshot_id,
            command.fingerprint, command.requested_at, evaluation.evaluated_at, committed_at,
        )

    def _insert_history(self, value, fingerprint):
        self._connection.execute(
            "INSERT INTO production_safety_evaluation_history VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                value.evaluation_id, value.opportunity_id, value.evaluation_version,
                value.assessment.status.value, _dump(value.assessment.missing_fields),
                _dump(value.assessment.failed_checks), value.rule_version,
                value.evaluated_at.isoformat(), value.schema_version, fingerprint,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    def _insert_provenance(self, value):
        self._connection.execute(
            "INSERT INTO production_safety_evaluation_provenance VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                value.evaluation_id, value.opportunity_id, value.snapshot_chain_binding_id,
                value.candidate_opportunity_binding_id, value.candidate_id,
                value.selected_product_snapshot_id, value.price_intelligence_snapshot_id,
                value.economics_calculation_snapshot_id, value.verified_economics_opportunity_id,
                _dump(_identity_dict(value.market_observation_identity)), value.rule_version,
                value.evaluated_at.isoformat(), value.schema_version,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    def _project_current(self, value, projected_at):
        self._connection.execute(
            """INSERT INTO production_safety_evaluation_current VALUES(?,?,?,?)
            ON CONFLICT(opportunity_id) DO UPDATE SET
            evaluation_id=excluded.evaluation_id,
            evaluation_version=excluded.evaluation_version,
            projected_at=excluded.projected_at""",
            (value.opportunity_id, value.evaluation_id, value.evaluation_version, projected_at.isoformat()),
        )

    def _insert_receipt(self, value):
        self._connection.execute(
            "INSERT INTO production_safety_evaluation_receipts VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                value.command_id, value.evaluation_id, value.opportunity_id,
                value.snapshot_chain_binding_id, value.selected_product_snapshot_id,
                value.command_fingerprint, value.requested_at.isoformat(),
                value.evaluated_at.isoformat(), value.committed_at.isoformat(),
                value.schema_version, datetime.now(timezone.utc).isoformat(),
            ),
        )

    def _commit(self):
        self._connection.commit()

    def get_evaluation(self, evaluation_id):
        row = self._connection.execute(
            "SELECT * FROM production_safety_evaluation_history WHERE evaluation_id=?",
            (evaluation_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            if row["evaluation_schema_version"] != PRODUCTION_SAFETY_EVALUATION_SCHEMA_VERSION:
                raise UnsupportedProductionSafetyEvaluationVersionError("unsupported persisted Safety evaluation")
            value = ProductionSafetyEvaluation(
                row["evaluation_id"], row["opportunity_id"], row["evaluation_version"],
                ProductionSafetyAssessment(
                    ProductionSafetyStatus(row["status"]),
                    tuple(json.loads(row["missing_fields_json"])),
                    tuple(json.loads(row["failed_checks_json"])),
                ),
                row["rule_version"], datetime.fromisoformat(row["evaluated_at"]),
                row["evaluation_schema_version"],
            )
            provenance = self.get_provenance(evaluation_id, validate_evaluation=False)
            expected = _subject(
                provenance.snapshot_chain_binding_id,
                provenance.selected_product_snapshot_id,
                value.rule_version,
            )
            if row["subject_fingerprint"] != expected:
                raise ValueError("Safety subject fingerprint mismatch")
            return value
        except UnsupportedProductionSafetyEvaluationVersionError:
            raise
        except Exception as error:
            raise MalformedProductionSafetyEvaluationPersistenceError("persisted Safety evaluation is malformed") from error

    def get_provenance(self, evaluation_id, *, validate_evaluation=True):
        row = self._connection.execute(
            "SELECT * FROM production_safety_evaluation_provenance WHERE evaluation_id=?",
            (evaluation_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            if row["provenance_schema_version"] != PRODUCTION_SAFETY_PROVENANCE_SCHEMA_VERSION:
                raise UnsupportedProductionSafetyEvaluationVersionError("unsupported persisted Safety provenance")
            value = ProductionSafetyEvaluationProvenance(
                row["evaluation_id"], row["opportunity_id"], row["snapshot_chain_binding_id"],
                row["candidate_opportunity_binding_id"], row["candidate_id"],
                row["selected_product_snapshot_id"], row["price_intelligence_snapshot_id"],
                row["economics_calculation_snapshot_id"], row["verified_economics_opportunity_id"],
                _identity(row["market_identity_payload_json"]), row["rule_version"],
                datetime.fromisoformat(row["evaluated_at"]), row["provenance_schema_version"],
            )
            if validate_evaluation and self._connection.execute(
                "SELECT 1 FROM production_safety_evaluation_history WHERE evaluation_id=?",
                (evaluation_id,),
            ).fetchone() is None:
                raise ValueError("Safety provenance evaluation is missing")
            return value
        except UnsupportedProductionSafetyEvaluationVersionError:
            raise
        except Exception as error:
            raise MalformedProductionSafetyEvaluationPersistenceError("persisted Safety provenance is malformed") from error

    def get_receipt(self, command_id):
        row = self._connection.execute(
            "SELECT * FROM production_safety_evaluation_receipts WHERE command_id=?",
            (command_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            if row["receipt_schema_version"] != PRODUCTION_SAFETY_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedProductionSafetyEvaluationVersionError("unsupported persisted Safety receipt")
            receipt = ProductionSafetyEvaluationReceipt(
                row["command_id"], row["evaluation_id"], row["opportunity_id"],
                row["snapshot_chain_binding_id"], row["selected_product_snapshot_id"],
                row["command_fingerprint"], datetime.fromisoformat(row["requested_at"]),
                datetime.fromisoformat(row["evaluated_at"]), datetime.fromisoformat(row["committed_at"]),
                row["receipt_schema_version"],
            )
            command = EvaluateAndPersistProductionSafetyCommand(
                receipt.command_id, receipt.opportunity_id,
                receipt.snapshot_chain_binding_id, receipt.selected_product_snapshot_id,
                receipt.requested_at,
            )
            if receipt.command_fingerprint != command.fingerprint:
                raise ValueError("Safety receipt fingerprint mismatch")
            return receipt
        except UnsupportedProductionSafetyEvaluationVersionError:
            raise
        except Exception as error:
            raise MalformedProductionSafetyEvaluationPersistenceError("persisted Safety receipt is malformed") from error

    def _result(self, receipt, replayed):
        evaluation = self.get_evaluation(receipt.evaluation_id)
        provenance = self.get_provenance(receipt.evaluation_id)
        if evaluation is None or provenance is None:
            raise MalformedProductionSafetyEvaluationPersistenceError("Safety receipt references missing facts")
        return ProductionSafetyEvaluationResult(evaluation, provenance, receipt, replayed)

    def get_by_command(self, command_id):
        receipt = self.get_receipt(command_id)
        return None if receipt is None else self._result(receipt, False)

    def get_by_opportunity(self, opportunity_id):
        rows = self._connection.execute(
            "SELECT evaluation_id FROM production_safety_evaluation_history WHERE opportunity_id=? ORDER BY evaluation_version,evaluation_id",
            (opportunity_id,),
        ).fetchall()
        return tuple(self.get_evaluation(row[0]) for row in rows)

    def get_by_subject(self, binding_id, product_snapshot_id, rule_version=PRODUCTION_SAFETY_EVALUATION_RULE_VERSION):
        row = self._connection.execute(
            "SELECT evaluation_id FROM production_safety_evaluation_history WHERE subject_fingerprint=?",
            (_subject(binding_id, product_snapshot_id, rule_version),),
        ).fetchone()
        return None if row is None else self.get_evaluation(row[0])

    def get_current_production_safety_evaluation(self, opportunity_id):
        row = self._connection.execute(
            "SELECT evaluation_id FROM production_safety_evaluation_current WHERE opportunity_id=?",
            (opportunity_id,),
        ).fetchone()
        return None if row is None else self.get_evaluation(row[0])

    def get_current_decision_source(self, opportunity_id):
        row = self._connection.execute(
            "SELECT evaluation_id,evaluation_version FROM production_safety_evaluation_current WHERE opportunity_id=?",
            (opportunity_id,),
        ).fetchone()
        if row is None:
            return None
        evaluation = self.get_evaluation(row["evaluation_id"])
        provenance = self.get_provenance(row["evaluation_id"])
        if evaluation is None or provenance is None:
            raise MalformedProductionSafetyEvaluationPersistenceError("Safety current references incomplete facts")
        if (
            evaluation.opportunity_id != opportunity_id
            or provenance.opportunity_id != opportunity_id
            or provenance.evaluation_id != evaluation.evaluation_id
            or provenance.rule_version != evaluation.rule_version
            or row["evaluation_version"] != evaluation.evaluation_version
        ):
            raise MalformedProductionSafetyEvaluationPersistenceError("Safety current identity conflicts with history/provenance")
        if (
            evaluation.schema_version != PRODUCTION_SAFETY_EVALUATION_SCHEMA_VERSION
            or provenance.schema_version != PRODUCTION_SAFETY_PROVENANCE_SCHEMA_VERSION
            or evaluation.rule_version != PRODUCTION_SAFETY_EVALUATION_RULE_VERSION
        ):
            raise UnsupportedProductionSafetyEvaluationVersionError("unsupported operational Safety decision source")
        return OperationalProductionSafetyDecisionSource(
            evaluation.evaluation_id, opportunity_id, evaluation.assessment,
            provenance.snapshot_chain_binding_id, provenance.selected_product_snapshot_id,
            evaluation.rule_version, evaluation.schema_version, provenance.schema_version,
            evaluation.evaluated_at,
        )

    def get_decision_source(self, evaluation_id):
        evaluation = self.get_evaluation(evaluation_id)
        provenance = self.get_provenance(evaluation_id)
        if evaluation is None or provenance is None:
            return None
        if (
            provenance.opportunity_id != evaluation.opportunity_id
            or provenance.rule_version != evaluation.rule_version
            or evaluation.schema_version != PRODUCTION_SAFETY_EVALUATION_SCHEMA_VERSION
            or provenance.schema_version != PRODUCTION_SAFETY_PROVENANCE_SCHEMA_VERSION
            or evaluation.rule_version != PRODUCTION_SAFETY_EVALUATION_RULE_VERSION
        ):
            raise MalformedProductionSafetyEvaluationPersistenceError("Safety decision source is inconsistent")
        return OperationalProductionSafetyDecisionSource(
            evaluation.evaluation_id, evaluation.opportunity_id, evaluation.assessment,
            provenance.snapshot_chain_binding_id, provenance.selected_product_snapshot_id,
            evaluation.rule_version, evaluation.schema_version, provenance.schema_version,
            evaluation.evaluated_at,
        )

    def get_receipts_by_evaluation(self, evaluation_id):
        rows = self._connection.execute(
            "SELECT command_id FROM production_safety_evaluation_receipts WHERE evaluation_id=? ORDER BY committed_at,command_id",
            (evaluation_id,),
        ).fetchall()
        return tuple(self.get_receipt(row[0]) for row in rows)

    def close(self):
        if self._owns_connection:
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


__all__ = ["SQLiteProductionSafetyEvaluationRepository"]
