from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from app.application.external_signal_ledger import (
    DuplicateExternalSignalLedgerError,
    ExternalSignalLedgerRepository,
)
from app.application.ocr.admission import (
    ARTIFACT_ADMISSION_SCHEMA_VERSION,
    OCR_EXECUTION_RECEIPT_SCHEMA_VERSION,
    ArtifactAdmissionConflictError,
    ArtifactAdmissionRecord,
    ExternalOCRAdmissionResult,
    FreshOCRAdmissionFactory,
    OCRAdmissionWriteSet,
    OCRExecutionConflictError,
    OCRExecutionPersistenceError,
    OCRExecutionReceipt,
    OCRExecutionReconstructionError,
    OCRExecutionRecord,
)
from app.domain.market_intelligence import (
    ArtifactOrigin,
    ArtifactReference,
    ArtifactType,
    ExternalSignalSourceType,
    HumanVerification,
    OCRCandidate,
    OCRField,
    OCRFieldResult,
    OCRProvider,
    OCRResult,
)


_ARTIFACT_ADMISSION_HISTORY = """
CREATE TABLE IF NOT EXISTS ocr_artifact_admission_history (
    artifact_id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    admitted_at TEXT NOT NULL,
    admission_schema_version TEXT NOT NULL,
    inserted_at TEXT NOT NULL
)
"""


_CANDIDATE_HISTORY = """
CREATE TABLE IF NOT EXISTS ocr_candidate_history (
    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    candidate_id TEXT NOT NULL UNIQUE,
    artifact_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    captured_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    inserted_at TEXT NOT NULL
)
"""

_EXECUTION_HISTORY = """
CREATE TABLE IF NOT EXISTS ocr_execution_history (
    provider TEXT NOT NULL,
    request_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    inserted_at TEXT NOT NULL,
    PRIMARY KEY (provider, request_id, artifact_id),
    FOREIGN KEY (artifact_id) REFERENCES ocr_artifact_admission_history(artifact_id)
)
"""

_EXECUTION_RECEIPTS = """
CREATE TABLE IF NOT EXISTS ocr_execution_receipts (
    provider TEXT NOT NULL,
    request_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL,
    ordered_candidate_ids_json TEXT NOT NULL,
    candidate_schema_version TEXT NOT NULL,
    committed_at TEXT NOT NULL,
    receipt_schema_version TEXT NOT NULL,
    inserted_at TEXT NOT NULL,
    PRIMARY KEY (provider, request_id, artifact_id),
    FOREIGN KEY (provider, request_id, artifact_id)
      REFERENCES ocr_execution_history(provider, request_id, artifact_id)
)
"""

_CANDIDATE_CURRENT = """
CREATE TABLE IF NOT EXISTS ocr_candidate_current (
    artifact_id TEXT NOT NULL,
    field_name TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    projected_at TEXT NOT NULL,
    PRIMARY KEY (artifact_id, field_name),
    FOREIGN KEY (fingerprint) REFERENCES ocr_candidate_history(fingerprint)
)
"""

_VERIFICATION_HISTORY = """
CREATE TABLE IF NOT EXISTS human_verification_history (
    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    verification_id TEXT NOT NULL UNIQUE,
    candidate_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    verified_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    inserted_at TEXT NOT NULL,
    FOREIGN KEY (candidate_id) REFERENCES ocr_candidate_history(candidate_id)
)
"""

_VERIFICATION_CURRENT = """
CREATE TABLE IF NOT EXISTS human_verification_current (
    candidate_id TEXT PRIMARY KEY,
    verification_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    verified_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    projected_at TEXT NOT NULL,
    FOREIGN KEY (fingerprint) REFERENCES human_verification_history(fingerprint)
)
"""


class SQLiteExternalSignalLedgerRepository(ExternalSignalLedgerRepository):
    """Append-only trust facts with independently replaceable latest projections."""

    def __init__(
        self,
        database_path: str | Path = "data/hyb_opportunity.db",
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        self._owns_connection = connection is None
        if connection is None:
            resolved = str(database_path)
            if resolved != ":memory:":
                Path(resolved).parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(resolved, timeout=30)
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        with self._connection:
            for statement in (
                _ARTIFACT_ADMISSION_HISTORY,
                _CANDIDATE_HISTORY,
                _CANDIDATE_CURRENT,
                _EXECUTION_HISTORY,
                _EXECUTION_RECEIPTS,
                _VERIFICATION_HISTORY,
                _VERIFICATION_CURRENT,
            ):
                self._connection.execute(statement)
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_ocr_candidate_history_lookup "
                "ON ocr_candidate_history(artifact_id, field_name, captured_at DESC, sequence_id DESC)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_human_verification_history_lookup "
                "ON human_verification_history(candidate_id, verified_at DESC, sequence_id DESC)"
            )
            for table in (
                "ocr_artifact_admission_history",
                "ocr_execution_history",
                "ocr_candidate_history",
                "ocr_execution_receipts",
                "human_verification_history",
            ):
                self._connection.execute(
                    f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_update
                    BEFORE UPDATE ON {table}
                    BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END"""
                )
                self._connection.execute(
                    f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_delete
                    BEFORE DELETE ON {table}
                    BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END"""
                )

    def save_candidate(self, candidate: OCRCandidate) -> None:
        if not isinstance(candidate, OCRCandidate):
            raise TypeError("candidate must be OCRCandidate")
        fingerprint = self._candidate_fingerprint(candidate)
        payload = self._candidate_payload(candidate)
        now = datetime.now(timezone.utc).isoformat()
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            self._insert_candidate_locked(candidate, fingerprint, payload, now)
            self._connection.commit()
        except sqlite3.IntegrityError as error:
            self._connection.rollback()
            if self._candidate_duplicate(candidate.candidate_id, fingerprint):
                raise DuplicateExternalSignalLedgerError(fingerprint) from error
            raise
        except Exception:
            self._connection.rollback()
            raise

    def admit_external_execution(
        self,
        execution: OCRExecutionRecord,
        prepare_fresh: FreshOCRAdmissionFactory,
    ) -> ExternalOCRAdmissionResult:
        if not isinstance(execution, OCRExecutionRecord):
            raise TypeError("execution must be OCRExecutionRecord")
        if not callable(prepare_fresh):
            raise TypeError("prepare_fresh must be callable")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:
            raise OCRExecutionPersistenceError(
                "OCR admission transaction could not start"
            ) from error
        try:
            artifact_admission = self._artifact_admission_locked(
                execution.artifact.artifact_id
            )
            is_new_artifact = artifact_admission is None
            if artifact_admission is not None and (
                artifact_admission.artifact != execution.artifact
            ):
                raise ArtifactAdmissionConflictError(
                    "Artifact admission payload conflicts with persisted Artifact"
                )

            persisted_execution = self._execution_locked(*execution.replay_key)
            persisted_receipt = self._execution_receipt_locked(*execution.replay_key)
            if persisted_execution is not None:
                if persisted_execution != execution:
                    raise OCRExecutionConflictError(
                        "OCR execution payload conflicts with persisted execution"
                    )
                if persisted_receipt is None or artifact_admission is None:
                    raise OCRExecutionReconstructionError(
                        "completed OCR execution receipt or Artifact is missing"
                    )
                replay = self._reconstruct_locked(
                    artifact_admission, persisted_execution, persisted_receipt
                )
                self._connection.rollback()
                return replay
            if persisted_receipt is not None:
                raise OCRExecutionReconstructionError(
                    "OCR execution receipt exists without execution history"
                )

            write_set = prepare_fresh(is_new_artifact)
            self._validate_write_set(execution, write_set, is_new_artifact)
            if write_set.artifact_admission is not None:
                try:
                    self._insert_artifact_admission_locked(write_set.artifact_admission)
                except sqlite3.Error as error:
                    raise OCRExecutionPersistenceError(
                        "artifact persistence failed"
                    ) from error
                artifact_admission = write_set.artifact_admission
            if artifact_admission is None:
                raise OCRExecutionReconstructionError(
                    "fresh OCR execution has no Artifact admission"
                )
            try:
                self._insert_execution_locked(execution, write_set.receipt.committed_at)
            except sqlite3.Error as error:
                raise OCRExecutionPersistenceError(
                    "execution persistence failed"
                ) from error
            for candidate in write_set.candidates:
                try:
                    self._insert_candidate_locked(
                        candidate,
                        self._admitted_candidate_fingerprint(candidate),
                        self._candidate_payload(candidate),
                        self._iso(write_set.receipt.committed_at),
                    )
                except sqlite3.Error as error:
                    raise OCRExecutionPersistenceError(
                        "candidate persistence failed"
                    ) from error
            try:
                self._insert_execution_receipt_locked(write_set.receipt)
            except sqlite3.Error as error:
                raise OCRExecutionPersistenceError(
                    "receipt persistence failed"
                ) from error
            try:
                self._connection.commit()
            except sqlite3.Error as error:
                raise OCRExecutionPersistenceError("OCR admission commit failed") from error
            return ExternalOCRAdmissionResult(
                artifact_admission,
                execution,
                write_set.receipt,
                write_set.candidates,
                False,
            )
        except Exception:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise

    def get_artifact_admission(
        self, artifact_id: str
    ) -> ArtifactAdmissionRecord | None:
        try:
            return self._artifact_admission_locked(artifact_id)
        except sqlite3.Error as error:
            raise OCRExecutionPersistenceError(
                "Artifact admission query failed"
            ) from error

    def get_execution(
        self, provider: OCRProvider, request_id: str, artifact_id: str
    ) -> OCRExecutionRecord | None:
        try:
            return self._execution_locked(provider, request_id, artifact_id)
        except sqlite3.Error as error:
            raise OCRExecutionPersistenceError("OCR execution query failed") from error

    def get_execution_receipt(
        self, provider: OCRProvider, request_id: str, artifact_id: str
    ) -> OCRExecutionReceipt | None:
        try:
            return self._execution_receipt_locked(provider, request_id, artifact_id)
        except sqlite3.Error as error:
            raise OCRExecutionPersistenceError("OCR receipt query failed") from error

    def save_verification(
        self,
        verification: HumanVerification,
        *,
        _manage_transaction: bool = True,
    ) -> None:
        if not isinstance(verification, HumanVerification):
            raise TypeError("verification must be HumanVerification")
        fingerprint = self._verification_fingerprint(verification)
        payload = self._verification_payload(verification)
        now = datetime.now(timezone.utc).isoformat()
        try:
            if _manage_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute(
                """INSERT INTO human_verification_history (
                verification_id, candidate_id, fingerprint, verified_at,
                payload_json, inserted_at
                ) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    verification.verification_id,
                    verification.candidate_id,
                    fingerprint,
                    self._iso(verification.verified_at),
                    payload,
                    now,
                ),
            )
            self._connection.execute(
                """INSERT INTO human_verification_current (
                candidate_id, verification_id, fingerprint, verified_at,
                payload_json, projected_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    verification_id=excluded.verification_id,
                    fingerprint=excluded.fingerprint,
                    verified_at=excluded.verified_at,
                    payload_json=excluded.payload_json,
                    projected_at=excluded.projected_at
                WHERE excluded.verified_at >= human_verification_current.verified_at""",
                (
                    verification.candidate_id,
                    verification.verification_id,
                    fingerprint,
                    self._iso(verification.verified_at),
                    payload,
                    now,
                ),
            )
            if _manage_transaction:
                self._connection.commit()
        except sqlite3.IntegrityError as error:
            if _manage_transaction:
                self._connection.rollback()
            if self._verification_duplicate(verification.verification_id, fingerprint):
                raise DuplicateExternalSignalLedgerError(fingerprint) from error
            raise
        except Exception:
            if _manage_transaction:
                self._connection.rollback()
            raise

    def get_latest_candidate(
        self, artifact_id: str, field_name: OCRField
    ) -> OCRCandidate | None:
        row = self._connection.execute(
            "SELECT payload_json FROM ocr_candidate_current WHERE artifact_id = ? AND field_name = ?",
            (artifact_id, OCRField(field_name).value),
        ).fetchone()
        return self._candidate_from_payload(row["payload_json"]) if row else None

    def get_candidate(self, candidate_id: str) -> OCRCandidate | None:
        row = self._connection.execute(
            "SELECT payload_json FROM ocr_candidate_history WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        return self._candidate_from_payload(row["payload_json"]) if row else None

    def list_candidates(self) -> tuple[OCRCandidate, ...]:
        rows = self._connection.execute(
            "SELECT payload_json FROM ocr_candidate_current ORDER BY captured_at, candidate_id"
        ).fetchall()
        return tuple(self._candidate_from_payload(row["payload_json"]) for row in rows)

    def get_candidate_history(
        self, artifact_id: str, field_name: OCRField, *, limit: int | None = None
    ) -> tuple[OCRCandidate, ...]:
        query = (
            "SELECT payload_json FROM ocr_candidate_history "
            "WHERE artifact_id = ? AND field_name = ? "
            "ORDER BY captured_at DESC, sequence_id DESC"
        )
        parameters: list[object] = [artifact_id, OCRField(field_name).value]
        self._append_limit(query, limit)
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)
        return tuple(
            self._candidate_from_payload(row["payload_json"])
            for row in self._connection.execute(query, tuple(parameters)).fetchall()
        )

    def get_latest_verification(self, candidate_id: str) -> HumanVerification | None:
        row = self._connection.execute(
            "SELECT payload_json FROM human_verification_current WHERE candidate_id = ?",
            (candidate_id,),
        ).fetchone()
        return self._verification_from_payload(row["payload_json"]) if row else None

    def get_verification_history(
        self, candidate_id: str, *, limit: int | None = None
    ) -> tuple[HumanVerification, ...]:
        query = (
            "SELECT payload_json FROM human_verification_history "
            "WHERE candidate_id = ? ORDER BY verified_at DESC, sequence_id DESC"
        )
        parameters: list[object] = [candidate_id]
        self._append_limit(query, limit)
        if limit is not None:
            query += " LIMIT ?"
            parameters.append(limit)
        return tuple(
            self._verification_from_payload(row["payload_json"])
            for row in self._connection.execute(query, tuple(parameters)).fetchall()
        )

    def _artifact_admission_locked(
        self, artifact_id: str
    ) -> ArtifactAdmissionRecord | None:
        row = self._connection.execute(
            "SELECT * FROM ocr_artifact_admission_history WHERE artifact_id = ?",
            (artifact_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            if row["admission_schema_version"] != ARTIFACT_ADMISSION_SCHEMA_VERSION:
                raise ValueError("unsupported Artifact admission version")
            artifact = self._artifact_from_data(json.loads(row["payload_json"]))
            if artifact.artifact_id != row["artifact_id"] or artifact.sha256 != row["sha256"]:
                raise ValueError("Artifact admission columns do not match payload")
            return ArtifactAdmissionRecord(
                artifact=artifact,
                admitted_at=self._datetime(row["admitted_at"]),
                schema_version=row["admission_schema_version"],
            )
        except OCRExecutionReconstructionError:
            raise
        except Exception as error:
            raise OCRExecutionReconstructionError(
                "malformed Artifact admission persistence"
            ) from error

    def _execution_locked(
        self, provider: OCRProvider, request_id: str, artifact_id: str
    ) -> OCRExecutionRecord | None:
        provider = OCRProvider(provider)
        row = self._connection.execute(
            """SELECT * FROM ocr_execution_history
            WHERE provider = ? AND request_id = ? AND artifact_id = ?""",
            (provider.value, request_id, artifact_id),
        ).fetchone()
        if row is None:
            return None
        artifact_admission = self._artifact_admission_locked(artifact_id)
        if artifact_admission is None:
            raise OCRExecutionReconstructionError(
                "OCR execution Artifact admission is missing"
            )
        try:
            data = json.loads(row["payload_json"])
            if (
                row["artifact_sha256"] != artifact_admission.artifact.sha256
                or data["artifact_id"] != artifact_id
                or data["artifact_sha256"] != artifact_admission.artifact.sha256
            ):
                raise ValueError("OCR execution Artifact lineage mismatch")
            result = self._ocr_result_from_data(data["result"])
            execution = OCRExecutionRecord(artifact_admission.artifact, result)
            if execution.replay_key != (provider, request_id, artifact_id):
                raise ValueError("OCR execution key does not match payload")
            return execution
        except OCRExecutionReconstructionError:
            raise
        except Exception as error:
            raise OCRExecutionReconstructionError(
                "malformed OCR execution persistence"
            ) from error

    def _execution_receipt_locked(
        self, provider: OCRProvider, request_id: str, artifact_id: str
    ) -> OCRExecutionReceipt | None:
        provider = OCRProvider(provider)
        row = self._connection.execute(
            """SELECT * FROM ocr_execution_receipts
            WHERE provider = ? AND request_id = ? AND artifact_id = ?""",
            (provider.value, request_id, artifact_id),
        ).fetchone()
        if row is None:
            return None
        try:
            if row["receipt_schema_version"] != OCR_EXECUTION_RECEIPT_SCHEMA_VERSION:
                raise ValueError("unsupported OCR receipt version")
            candidate_ids = json.loads(row["ordered_candidate_ids_json"])
            if not isinstance(candidate_ids, list):
                raise ValueError("ordered Candidate IDs must be a list")
            return OCRExecutionReceipt(
                provider=provider,
                request_id=row["request_id"],
                artifact_id=row["artifact_id"],
                artifact_sha256=row["artifact_sha256"],
                ordered_candidate_ids=tuple(candidate_ids),
                candidate_schema_version=row["candidate_schema_version"],
                committed_at=self._datetime(row["committed_at"]),
                schema_version=row["receipt_schema_version"],
            )
        except Exception as error:
            raise OCRExecutionReconstructionError(
                "malformed OCR execution receipt"
            ) from error

    def _reconstruct_locked(
        self,
        artifact_admission: ArtifactAdmissionRecord,
        execution: OCRExecutionRecord,
        receipt: OCRExecutionReceipt,
    ) -> ExternalOCRAdmissionResult:
        if (
            receipt.replay_key != execution.replay_key
            or receipt.artifact_sha256 != artifact_admission.artifact.sha256
            or receipt.candidate_schema_version == ""
        ):
            raise OCRExecutionReconstructionError(
                "OCR execution receipt lineage conflicts"
            )
        candidates: list[OCRCandidate] = []
        for candidate_id in receipt.ordered_candidate_ids:
            candidate = self.get_candidate(candidate_id)
            if candidate is None:
                raise OCRExecutionReconstructionError(
                    "OCR execution Candidate is missing"
                )
            candidates.append(candidate)
        result = ExternalOCRAdmissionResult(
            artifact_admission,
            execution,
            receipt,
            tuple(candidates),
            True,
        )
        self._validate_reconstruction(result)
        return result

    @staticmethod
    def _validate_reconstruction(result: ExternalOCRAdmissionResult) -> None:
        fields = result.execution.result.fields
        if len(result.candidates) != len(fields):
            raise OCRExecutionReconstructionError(
                "OCR execution Candidate membership length conflicts"
            )
        for candidate, field in zip(result.candidates, fields, strict=True):
            if (
                candidate.artifact != result.execution.artifact
                or candidate.field_name is not field.field_name
                or candidate.raw_text != field.raw_text
                or candidate.normalized_value != field.normalized_value
                or candidate.confidence != field.confidence
                or candidate.captured_at != result.execution.result.executed_at
                or candidate.schema_version
                != result.receipt.candidate_schema_version
            ):
                raise OCRExecutionReconstructionError(
                    "OCR execution Candidate facts conflict with provenance"
                )

    @classmethod
    def _validate_write_set(
        cls,
        execution: OCRExecutionRecord,
        write_set: OCRAdmissionWriteSet,
        is_new_artifact: bool,
    ) -> None:
        if not isinstance(write_set, OCRAdmissionWriteSet):
            raise TypeError("prepare_fresh must return OCRAdmissionWriteSet")
        if is_new_artifact != (write_set.artifact_admission is not None):
            raise OCRExecutionReconstructionError(
                "Artifact admission write set does not match persistence state"
            )
        if (
            write_set.artifact_admission is not None
            and write_set.artifact_admission.artifact != execution.artifact
        ):
            raise OCRExecutionReconstructionError(
                "Artifact admission write set conflicts with execution"
            )
        receipt = write_set.receipt
        if (
            receipt.replay_key != execution.replay_key
            or receipt.artifact_sha256 != execution.artifact.sha256
            or receipt.ordered_candidate_ids
            != tuple(candidate.candidate_id for candidate in write_set.candidates)
            or len(write_set.candidates) != len(execution.result.fields)
        ):
            raise OCRExecutionReconstructionError(
                "OCR admission write set lineage conflicts"
            )
        for candidate, field in zip(
            write_set.candidates, execution.result.fields, strict=True
        ):
            if (
                candidate.artifact != execution.artifact
                or candidate.field_name is not field.field_name
                or candidate.raw_text != field.raw_text
                or candidate.normalized_value != field.normalized_value
                or candidate.confidence != field.confidence
                or candidate.captured_at != execution.result.executed_at
                or candidate.schema_version != receipt.candidate_schema_version
            ):
                raise OCRExecutionReconstructionError(
                    "OCR Candidate write set conflicts with execution provenance"
                )

    def _insert_artifact_admission_locked(
        self, admission: ArtifactAdmissionRecord
    ) -> None:
        self._connection.execute(
            """INSERT INTO ocr_artifact_admission_history (
            artifact_id, sha256, payload_json, admitted_at,
            admission_schema_version, inserted_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                admission.artifact.artifact_id,
                admission.artifact.sha256,
                self._json(self._artifact_data(admission.artifact)),
                self._iso(admission.admitted_at),
                admission.schema_version,
                self._iso(admission.admitted_at),
            ),
        )

    def _insert_execution_locked(
        self, execution: OCRExecutionRecord, inserted_at: datetime
    ) -> None:
        self._connection.execute(
            """INSERT INTO ocr_execution_history (
            provider, request_id, artifact_id, artifact_sha256,
            payload_json, inserted_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (
                execution.result.provider.value,
                execution.result.request_id,
                execution.artifact.artifact_id,
                execution.artifact.sha256,
                self._execution_payload(execution),
                self._iso(inserted_at),
            ),
        )

    def _insert_execution_receipt_locked(
        self, receipt: OCRExecutionReceipt
    ) -> None:
        self._connection.execute(
            """INSERT INTO ocr_execution_receipts (
            provider, request_id, artifact_id, artifact_sha256,
            ordered_candidate_ids_json, candidate_schema_version,
            committed_at, receipt_schema_version, inserted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                receipt.provider.value,
                receipt.request_id,
                receipt.artifact_id,
                receipt.artifact_sha256,
                self._json(list(receipt.ordered_candidate_ids)),
                receipt.candidate_schema_version,
                self._iso(receipt.committed_at),
                receipt.schema_version,
                self._iso(receipt.committed_at),
            ),
        )

    def _insert_candidate_locked(
        self, candidate: OCRCandidate, fingerprint: str, payload: str, inserted_at: str
    ) -> None:
        self._connection.execute(
            """INSERT INTO ocr_candidate_history (
            candidate_id, artifact_id, field_name, fingerprint,
            captured_at, payload_json, inserted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                candidate.candidate_id,
                candidate.artifact.artifact_id,
                candidate.field_name.value,
                fingerprint,
                self._iso(candidate.captured_at),
                payload,
                inserted_at,
            ),
        )
        self._connection.execute(
            """INSERT INTO ocr_candidate_current (
            artifact_id, field_name, candidate_id, fingerprint,
            captured_at, payload_json, projected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(artifact_id, field_name) DO UPDATE SET
                candidate_id=excluded.candidate_id,
                fingerprint=excluded.fingerprint,
                captured_at=excluded.captured_at,
                payload_json=excluded.payload_json,
                projected_at=excluded.projected_at
            WHERE excluded.captured_at >= ocr_candidate_current.captured_at""",
            (
                candidate.artifact.artifact_id,
                candidate.field_name.value,
                candidate.candidate_id,
                fingerprint,
                self._iso(candidate.captured_at),
                payload,
                inserted_at,
            ),
        )

    def close(self) -> None:
        if self._owns_connection:
            self._connection.close()

    @staticmethod
    def _append_limit(query: str, limit: int | None) -> None:
        if limit is not None and (
            isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
        ):
            raise ValueError("limit must be a positive integer or None")

    def _candidate_duplicate(self, candidate_id: str, fingerprint: str) -> bool:
        return self._connection.execute(
            "SELECT 1 FROM ocr_candidate_history WHERE candidate_id = ? OR fingerprint = ?",
            (candidate_id, fingerprint),
        ).fetchone() is not None

    def _verification_duplicate(self, verification_id: str, fingerprint: str) -> bool:
        return self._connection.execute(
            "SELECT 1 FROM human_verification_history WHERE verification_id = ? OR fingerprint = ?",
            (verification_id, fingerprint),
        ).fetchone() is not None

    @classmethod
    def _candidate_fingerprint(cls, candidate: OCRCandidate) -> str:
        return cls._hash({
            "sha256": candidate.artifact.sha256,
            "artifact_id": candidate.artifact.artifact_id,
            "field_name": candidate.field_name.value,
            "captured_at": cls._iso(candidate.captured_at),
        })

    @classmethod
    def _admitted_candidate_fingerprint(cls, candidate: OCRCandidate) -> str:
        return cls._hash({
            "candidate_id": candidate.candidate_id,
            "sha256": candidate.artifact.sha256,
            "artifact_id": candidate.artifact.artifact_id,
            "field_name": candidate.field_name.value,
            "raw_text": candidate.raw_text,
            "normalized_value": cls._encode_value(candidate.normalized_value),
            "confidence": str(candidate.confidence),
            "captured_at": cls._iso(candidate.captured_at),
            "schema_version": candidate.schema_version,
        })

    @classmethod
    def _verification_fingerprint(cls, verification: HumanVerification) -> str:
        return cls._hash({
            "candidate_id": verification.candidate_id,
            "verified_value": cls._encode_value(verification.verified_value),
            "operator": verification.operator_id,
            "verified_at": cls._iso(verification.verified_at),
        })

    @classmethod
    def _candidate_payload(cls, candidate: OCRCandidate) -> str:
        artifact = candidate.artifact
        return cls._json({
            "candidate_id": candidate.candidate_id,
            "artifact": cls._artifact_data(artifact),
            "field_name": candidate.field_name.value,
            "raw_text": candidate.raw_text,
            "normalized_value": cls._encode_value(candidate.normalized_value),
            "confidence": str(candidate.confidence),
            "captured_at": cls._iso(candidate.captured_at),
            "schema_version": candidate.schema_version,
        })

    @classmethod
    def _candidate_from_payload(cls, payload: str) -> OCRCandidate:
        data = json.loads(payload)
        return OCRCandidate(
            candidate_id=data["candidate_id"],
            artifact=cls._artifact_from_data(data["artifact"]),
            field_name=OCRField(data["field_name"]),
            raw_text=data["raw_text"],
            normalized_value=cls._decode_value(data["normalized_value"]),
            confidence=Decimal(data["confidence"]),
            captured_at=cls._datetime(data["captured_at"]),
            schema_version=data["schema_version"],
        )

    @classmethod
    def _artifact_data(cls, artifact: ArtifactReference) -> dict[str, Any]:
        return {
            "artifact_id": artifact.artifact_id,
            "artifact_type": artifact.artifact_type.value,
            "artifact_origin": artifact.artifact_origin.value,
            "source_type": artifact.source_type.value,
            "sha256": artifact.sha256,
            "captured_at": cls._iso(artifact.captured_at),
            "width": artifact.width,
            "height": artifact.height,
            "mime_type": artifact.mime_type,
            "file_size": artifact.file_size,
            "schema_version": artifact.schema_version,
        }

    @classmethod
    def _artifact_from_data(cls, artifact: Mapping[str, Any]) -> ArtifactReference:
        return ArtifactReference(
            artifact_id=artifact["artifact_id"],
            artifact_type=ArtifactType(artifact["artifact_type"]),
            artifact_origin=ArtifactOrigin(artifact["artifact_origin"]),
            source_type=ExternalSignalSourceType(artifact["source_type"]),
            sha256=artifact["sha256"],
            captured_at=cls._datetime(artifact["captured_at"]),
            width=artifact["width"],
            height=artifact["height"],
            mime_type=artifact["mime_type"],
            file_size=artifact["file_size"],
            schema_version=artifact["schema_version"],
        )

    @classmethod
    def _execution_payload(cls, execution: OCRExecutionRecord) -> str:
        return cls._json({
            "artifact_id": execution.artifact.artifact_id,
            "artifact_sha256": execution.artifact.sha256,
            "result": cls._ocr_result_data(execution.result),
        })

    @classmethod
    def _ocr_result_data(cls, result: OCRResult) -> dict[str, Any]:
        return {
            "request_id": result.request_id,
            "artifact_id": result.artifact_id,
            "provider": result.provider.value,
            "provider_version": result.provider_version,
            "executed_at": cls._iso(result.executed_at),
            "confidence": str(result.confidence),
            "schema_version": result.schema_version,
            "fields": [
                {
                    "position": position,
                    "field_name": field.field_name.value,
                    "raw_text": field.raw_text,
                    "normalized_value": cls._encode_value(field.normalized_value),
                    "confidence": str(field.confidence),
                    "bounding_box": (
                        list(field.bounding_box)
                        if field.bounding_box is not None
                        else None
                    ),
                }
                for position, field in enumerate(result.fields)
            ],
        }

    @classmethod
    def _ocr_result_from_data(cls, data: Mapping[str, Any]) -> OCRResult:
        fields_data = data["fields"]
        if not isinstance(fields_data, list):
            raise TypeError("OCR execution fields must be a list")
        fields: list[OCRFieldResult] = []
        for position, field in enumerate(fields_data):
            if field["position"] != position:
                raise ValueError("OCR execution field positions are not ordered")
            bounding_box = field["bounding_box"]
            fields.append(
                OCRFieldResult(
                    field_name=OCRField(field["field_name"]),
                    raw_text=field["raw_text"],
                    normalized_value=cls._decode_value(field["normalized_value"]),
                    confidence=Decimal(field["confidence"]),
                    bounding_box=(
                        tuple(bounding_box) if bounding_box is not None else None
                    ),
                )
            )
        return OCRResult(
            request_id=data["request_id"],
            artifact_id=data["artifact_id"],
            provider=OCRProvider(data["provider"]),
            provider_version=data["provider_version"],
            executed_at=cls._datetime(data["executed_at"]),
            fields=tuple(fields),
            confidence=Decimal(data["confidence"]),
            schema_version=data["schema_version"],
        )

    @classmethod
    def _verification_payload(cls, verification: HumanVerification) -> str:
        return cls._json({
            "verification_id": verification.verification_id,
            "candidate_id": verification.candidate_id,
            "verified_value": cls._encode_value(verification.verified_value),
            "operator_id": verification.operator_id,
            "verified_at": cls._iso(verification.verified_at),
            "comment": verification.comment,
            "schema_version": verification.schema_version,
        })

    @classmethod
    def _verification_from_payload(cls, payload: str) -> HumanVerification:
        data = json.loads(payload)
        return HumanVerification(
            verification_id=data["verification_id"],
            candidate_id=data["candidate_id"],
            verified_value=cls._decode_value(data["verified_value"]),
            operator_id=data["operator_id"],
            verified_at=cls._datetime(data["verified_at"]),
            comment=data["comment"],
            schema_version=data["schema_version"],
        )

    @classmethod
    def _encode_value(cls, value: Any) -> dict[str, Any]:
        if isinstance(value, Decimal):
            return {"kind": "decimal", "value": str(value)}
        if isinstance(value, tuple):
            return {"kind": "tuple", "value": [cls._encode_value(item) for item in value]}
        if isinstance(value, list):
            return {"kind": "list", "value": [cls._encode_value(item) for item in value]}
        if isinstance(value, dict):
            if any(not isinstance(key, str) for key in value):
                raise TypeError("ledger mapping keys must be text")
            return {"kind": "mapping", "value": {key: cls._encode_value(item) for key, item in value.items()}}
        if value is None or isinstance(value, (str, int, float, bool)):
            return {"kind": "scalar", "value": value}
        raise TypeError("ledger value is not JSON serializable")

    @classmethod
    def _decode_value(cls, data: Mapping[str, Any]) -> Any:
        kind, value = data["kind"], data["value"]
        if kind == "decimal":
            return Decimal(value)
        if kind == "tuple":
            return tuple(cls._decode_value(item) for item in value)
        if kind == "list":
            return [cls._decode_value(item) for item in value]
        if kind == "mapping":
            return {key: cls._decode_value(item) for key, item in value.items()}
        if kind == "scalar":
            return value
        raise ValueError("unsupported ledger value encoding")

    @classmethod
    def _hash(cls, value: Any) -> str:
        return hashlib.sha256(cls._json(value).encode("utf-8")).hexdigest()

    @staticmethod
    def _json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _iso(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _datetime(value: str) -> datetime:
        return datetime.fromisoformat(value)
