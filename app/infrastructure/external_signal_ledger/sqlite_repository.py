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
from app.domain.market_intelligence import (
    ArtifactOrigin,
    ArtifactReference,
    ArtifactType,
    ExternalSignalSourceType,
    HumanVerification,
    OCRCandidate,
    OCRField,
)


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
            connection = sqlite3.connect(resolved)
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        with self._connection:
            for statement in (
                _CANDIDATE_HISTORY,
                _CANDIDATE_CURRENT,
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
            for table in ("ocr_candidate_history", "human_verification_history"):
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
                    now,
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
                    now,
                ),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as error:
            self._connection.rollback()
            if self._candidate_duplicate(candidate.candidate_id, fingerprint):
                raise DuplicateExternalSignalLedgerError(fingerprint) from error
            raise
        except Exception:
            self._connection.rollback()
            raise

    def save_verification(self, verification: HumanVerification) -> None:
        if not isinstance(verification, HumanVerification):
            raise TypeError("verification must be HumanVerification")
        fingerprint = self._verification_fingerprint(verification)
        payload = self._verification_payload(verification)
        now = datetime.now(timezone.utc).isoformat()
        try:
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
            self._connection.commit()
        except sqlite3.IntegrityError as error:
            self._connection.rollback()
            if self._verification_duplicate(verification.verification_id, fingerprint):
                raise DuplicateExternalSignalLedgerError(fingerprint) from error
            raise
        except Exception:
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
            "artifact": {
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
            },
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
        artifact = data["artifact"]
        return OCRCandidate(
            candidate_id=data["candidate_id"],
            artifact=ArtifactReference(
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
            ),
            field_name=OCRField(data["field_name"]),
            raw_text=data["raw_text"],
            normalized_value=cls._decode_value(data["normalized_value"]),
            confidence=Decimal(data["confidence"]),
            captured_at=cls._datetime(data["captured_at"]),
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
