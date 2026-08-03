from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from app.application.review.models import (
    DuplicateReviewSessionError,
    MalformedReviewSessionError,
    ReviewCommandConflictError,
    ReviewCommandContext,
    ReviewCommandReceipt,
    ReviewCancelMetadata,
    ReviewSessionCommitError,
    ReviewSessionHistoryError,
    ReviewSessionHistoryEntry,
    ReviewSessionProjectionError,
    ReviewSessionVersionConflictError,
    ReviewTransitionMetadata,
    UnsupportedReviewSessionVersionError,
)
from app.application.review.ports import ReviewSessionRepository
from app.domain.market_intelligence import (
    CandidateReviewStatus,
    CandidateSkipRecord,
    ExternalSignalDirection,
    MarketObservationIdentity,
    MarketObservationScope,
    ReviewSession,
    ReviewSessionStatus,
)


_HISTORY = """
CREATE TABLE IF NOT EXISTS review_session_history (
    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    command_id TEXT NOT NULL UNIQUE,
    command_fingerprint TEXT NOT NULL,
    session_id TEXT NOT NULL,
    revision INTEGER NOT NULL,
    transition_type TEXT NOT NULL,
    prior_status TEXT,
    resulting_status TEXT NOT NULL,
    transition_at TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    inserted_at TEXT NOT NULL,
    UNIQUE(session_id, revision)
)
"""

_CURRENT = """
CREATE TABLE IF NOT EXISTS review_session_current (
    session_id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    event_id TEXT NOT NULL,
    projected_at TEXT NOT NULL,
    FOREIGN KEY(event_id) REFERENCES review_session_history(event_id)
)
"""

_CONTEXT_HISTORY = """
CREATE TABLE IF NOT EXISTS review_command_context_history (
    sequence_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(session_id, candidate_id)
)
"""

_CONTEXT_CURRENT = """
CREATE TABLE IF NOT EXISTS review_command_context_current (
    session_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    projected_at TEXT NOT NULL,
    PRIMARY KEY(session_id, candidate_id),
    FOREIGN KEY(fingerprint) REFERENCES review_command_context_history(fingerprint)
)
"""

_RECEIPTS = """
CREATE TABLE IF NOT EXISTS review_command_receipts (
    command_id TEXT PRIMARY KEY,
    command_fingerprint TEXT NOT NULL,
    session_id TEXT NOT NULL,
    resulting_revision INTEGER NOT NULL,
    payload_json TEXT NOT NULL,
    inserted_at TEXT NOT NULL
)
"""

_CANCEL_METADATA = """
CREATE TABLE IF NOT EXISTS review_cancel_metadata (
    session_id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    inserted_at TEXT NOT NULL
)
"""


class SQLiteReviewSessionRepository(ReviewSessionRepository):
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
                _HISTORY,
                _CURRENT,
                _CONTEXT_HISTORY,
                _CONTEXT_CURRENT,
                _RECEIPTS,
                _CANCEL_METADATA,
            ):
                self._connection.execute(statement)
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_review_session_history_session "
                "ON review_session_history(session_id, revision)"
            )
            for operation in ("UPDATE", "DELETE"):
                self._connection.execute(
                    f"""CREATE TRIGGER IF NOT EXISTS trg_review_session_history_no_{operation.lower()}
                    BEFORE {operation} ON review_session_history
                    BEGIN SELECT RAISE(ABORT, 'review_session_history is append-only'); END"""
                )
            for table in (
                "review_command_context_history",
                "review_command_context_current",
                "review_command_receipts",
                "review_cancel_metadata",
            ):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT, '{table} is immutable'); END"""
                    )

    def create(
        self,
        session: ReviewSession,
        metadata: ReviewTransitionMetadata,
        *,
        _manage_transaction: bool = True,
    ) -> ReviewSession:
        if session.revision != 1 or session.status is not ReviewSessionStatus.OPEN:
            raise ValueError("new review session must be OPEN at revision 1")
        existing = self._existing_command(metadata)
        if existing is not None:
            return self._resolve_retry(existing, metadata)
        if _manage_transaction:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
            except Exception as error:
                raise ReviewSessionCommitError("review session transaction could not start") from error
        try:
            if self.get(session.session_id) is not None:
                raise DuplicateReviewSessionError(session.session_id)
            try:
                self._insert_history(None, session, metadata)
            except Exception as error:
                raise ReviewSessionHistoryError("review session creation history failed") from error
            try:
                self._connection.execute(
                    """INSERT INTO review_session_current
                    (session_id, revision, payload_json, event_id, projected_at)
                    VALUES (?, ?, ?, ?, ?)""",
                    (
                        session.session_id,
                        session.revision,
                        self._payload(session),
                        metadata.event_id,
                        self._iso(metadata.occurred_at),
                    ),
                )
            except Exception as error:
                raise ReviewSessionProjectionError("review session creation projection failed") from error
            if _manage_transaction:
                try:
                    self._connection.commit()
                except Exception as error:
                    raise ReviewSessionCommitError("review session creation commit failed") from error
            return session
        except (
            DuplicateReviewSessionError,
            ReviewCommandConflictError,
            ReviewSessionHistoryError,
            ReviewSessionProjectionError,
            ReviewSessionCommitError,
        ):
            if _manage_transaction:
                self._connection.rollback()
            raise
        except Exception as error:
            if _manage_transaction:
                self._connection.rollback()
            raise ReviewSessionCommitError("review session creation failed") from error

    def get(self, session_id: str) -> ReviewSession | None:
        row = self._connection.execute(
            "SELECT payload_json FROM review_session_current WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return self._from_payload(row["payload_json"]) if row else None

    def list(self) -> tuple[ReviewSession, ...]:
        rows = self._connection.execute(
            "SELECT payload_json FROM review_session_current ORDER BY session_id"
        ).fetchall()
        return tuple(self._from_payload(row["payload_json"]) for row in rows)

    def get_history(self, session_id: str) -> tuple[ReviewSessionHistoryEntry, ...]:
        rows = self._connection.execute(
            """SELECT payload_json, event_id, command_id, command_fingerprint,
            transition_type, transition_at, prior_status, resulting_status
            FROM review_session_history WHERE session_id = ? ORDER BY revision""",
            (session_id,),
        ).fetchall()
        return tuple(
            ReviewSessionHistoryEntry(
                session=self._from_payload(row["payload_json"]),
                metadata=ReviewTransitionMetadata(
                    event_id=row["event_id"],
                    command_id=row["command_id"],
                    transition_type=row["transition_type"],
                    occurred_at=datetime.fromisoformat(row["transition_at"]),
                    command_fingerprint=row["command_fingerprint"],
                ),
                prior_status=row["prior_status"],
                resulting_status=row["resulting_status"],
            )
            for row in rows
        )

    def get_command_session(
        self, command_id: str, command_fingerprint: str
    ) -> ReviewSession | None:
        row = self._connection.execute(
            "SELECT command_fingerprint, payload_json FROM review_session_history WHERE command_id = ?",
            (command_id,),
        ).fetchone()
        if row is None:
            return None
        if row["command_fingerprint"] != command_fingerprint:
            raise ReviewCommandConflictError(command_id)
        return self._from_payload(row["payload_json"])

    def save_context(
        self, context: ReviewCommandContext, *, _manage_transaction: bool = True
    ) -> ReviewCommandContext:
        payload = self._context_payload(context)
        fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        try:
            if _manage_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            session = self.get(context.session_id)
            if session is None:
                raise ReviewSessionVersionConflictError(context.session_id)
            if context.candidate_id not in session.candidate_ids:
                raise ReviewCommandConflictError("context candidate is not a session member")
            candidate = self._connection.execute(
                "SELECT artifact_id FROM ocr_candidate_history WHERE candidate_id = ?",
                (context.candidate_id,),
            ).fetchone()
            if candidate is None or candidate["artifact_id"] != context.artifact_identity:
                raise ReviewCommandConflictError("context artifact identity mismatch")
            self._connection.execute(
                """INSERT INTO review_command_context_history
                (session_id, candidate_id, fingerprint, payload_json, created_at)
                VALUES (?, ?, ?, ?, ?)""",
                (
                    context.session_id,
                    context.candidate_id,
                    fingerprint,
                    payload,
                    self._iso(context.created_at),
                ),
            )
            self._connection.execute(
                """INSERT INTO review_command_context_current
                (session_id, candidate_id, fingerprint, payload_json, projected_at)
                VALUES (?, ?, ?, ?, ?)""",
                (
                    context.session_id,
                    context.candidate_id,
                    fingerprint,
                    payload,
                    self._iso(context.created_at),
                ),
            )
            if _manage_transaction:
                self._connection.commit()
            return context
        except (ReviewCommandConflictError, ReviewSessionVersionConflictError):
            if _manage_transaction:
                self._connection.rollback()
            raise
        except sqlite3.IntegrityError as error:
            if _manage_transaction:
                self._connection.rollback()
            existing = self.get_context(context.session_id, context.candidate_id)
            if existing == context:
                return existing
            raise ReviewCommandConflictError("review command context already exists") from error
        except Exception as error:
            if _manage_transaction:
                self._connection.rollback()
            raise ReviewSessionHistoryError("review command context persistence failed") from error

    def get_context(self, session_id: str, candidate_id: str) -> ReviewCommandContext | None:
        row = self._connection.execute(
            """SELECT payload_json FROM review_command_context_current
            WHERE session_id = ? AND candidate_id = ?""",
            (session_id, candidate_id),
        ).fetchone()
        return self._context_from_payload(row["payload_json"]) if row else None

    def save_receipt(
        self,
        receipt: ReviewCommandReceipt,
        command_fingerprint: str,
        *,
        _manage_transaction: bool = True,
    ) -> ReviewCommandReceipt:
        existing = self.get_receipt(receipt.command_id, command_fingerprint)
        if existing is not None:
            return existing
        try:
            if _manage_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute(
                """INSERT INTO review_command_receipts
                (command_id, command_fingerprint, session_id, resulting_revision,
                payload_json, inserted_at) VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    receipt.command_id,
                    command_fingerprint,
                    receipt.session_id,
                    receipt.resulting_revision,
                    self._receipt_payload(receipt),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            if _manage_transaction:
                self._connection.commit()
            return receipt
        except sqlite3.IntegrityError as error:
            if _manage_transaction:
                self._connection.rollback()
            existing = self.get_receipt(receipt.command_id, command_fingerprint)
            if existing is not None:
                return existing
            raise ReviewSessionHistoryError("review command receipt insert failed") from error
        except Exception as error:
            if _manage_transaction:
                self._connection.rollback()
            raise ReviewSessionHistoryError("review command receipt persistence failed") from error

    def get_receipt(
        self, command_id: str, command_fingerprint: str | None = None
    ) -> ReviewCommandReceipt | None:
        row = self._connection.execute(
            """SELECT command_fingerprint, payload_json FROM review_command_receipts
            WHERE command_id = ?""",
            (command_id,),
        ).fetchone()
        if row is None:
            return None
        if command_fingerprint is not None and row["command_fingerprint"] != command_fingerprint:
            raise ReviewCommandConflictError(command_id)
        return self._receipt_from_payload(row["payload_json"])

    def save_cancel_metadata(
        self, value: ReviewCancelMetadata, *, _manage_transaction: bool = True
    ) -> ReviewCancelMetadata:
        existing = self.get_cancel_metadata(value.session_id)
        if existing is not None:
            if existing == value:
                return existing
            raise ReviewCommandConflictError("cancel metadata already exists")
        try:
            if _manage_transaction:
                self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute(
                """INSERT INTO review_cancel_metadata
                (session_id, revision, payload_json, inserted_at) VALUES (?, ?, ?, ?)""",
                (
                    value.session_id,
                    value.revision,
                    self._cancel_payload(value),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            if _manage_transaction:
                self._connection.commit()
            return value
        except ReviewCommandConflictError:
            if _manage_transaction:
                self._connection.rollback()
            raise
        except Exception as error:
            if _manage_transaction:
                self._connection.rollback()
            raise ReviewSessionHistoryError("review cancel metadata persistence failed") from error

    def get_cancel_metadata(self, session_id: str) -> ReviewCancelMetadata | None:
        row = self._connection.execute(
            "SELECT payload_json FROM review_cancel_metadata WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return self._cancel_from_payload(row["payload_json"]) if row else None

    def get_revision(self, session_id: str, revision: int) -> ReviewSession | None:
        row = self._connection.execute(
            """SELECT payload_json FROM review_session_history
            WHERE session_id = ? AND revision = ?""",
            (session_id, revision),
        ).fetchone()
        return self._from_payload(row["payload_json"]) if row else None

    def validate_current(self, expected: ReviewSession) -> None:
        current = self.get(expected.session_id)
        if current is None or current.revision != expected.revision or current != expected:
            raise ReviewSessionVersionConflictError(expected.session_id)

    def rebuild_current(self, session_id: str | None = None) -> tuple[ReviewSession, ...]:
        parameters: tuple[object, ...] = ()
        where = ""
        if session_id is not None:
            where = "WHERE history.session_id = ?"
            parameters = (session_id,)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            rows = self._connection.execute(
                f"""SELECT history.session_id, history.revision, history.payload_json,
                history.event_id, history.transition_at
                FROM review_session_history AS history
                JOIN (
                    SELECT session_id, MAX(revision) AS revision
                    FROM review_session_history GROUP BY session_id
                ) AS latest ON latest.session_id = history.session_id
                    AND latest.revision = history.revision
                {where} ORDER BY history.session_id""",
                parameters,
            ).fetchall()
            sessions = tuple(self._from_payload(row["payload_json"]) for row in rows)
            if session_id is None:
                self._connection.execute("DELETE FROM review_session_current")
            else:
                self._connection.execute(
                    "DELETE FROM review_session_current WHERE session_id = ?", (session_id,)
                )
            for row in rows:
                self._connection.execute(
                    """INSERT INTO review_session_current
                    (session_id, revision, payload_json, event_id, projected_at)
                    VALUES (?, ?, ?, ?, ?)""",
                    (
                        row["session_id"],
                        row["revision"],
                        row["payload_json"],
                        row["event_id"],
                        row["transition_at"],
                    ),
                )
            self._connection.commit()
            return sessions
        except (MalformedReviewSessionError, UnsupportedReviewSessionVersionError):
            self._connection.rollback()
            raise
        except Exception as error:
            self._connection.rollback()
            raise ReviewSessionProjectionError("review current rebuild failed") from error

    def save_transition(
        self,
        previous_session: ReviewSession,
        next_session: ReviewSession,
        metadata: ReviewTransitionMetadata,
        *,
        _manage_transaction: bool = True,
    ) -> ReviewSession:
        existing = self._existing_command(metadata)
        if existing is not None:
            return self._resolve_retry(existing, metadata)
        if previous_session.session_id != next_session.session_id:
            raise ValueError("review transition cannot change session_id")
        if next_session.revision != previous_session.revision + 1:
            raise ReviewSessionVersionConflictError("revision must increase by exactly one")
        if _manage_transaction:
            try:
                self._connection.execute("BEGIN IMMEDIATE")
            except Exception as error:
                raise ReviewSessionCommitError("review session transaction could not start") from error
        try:
            row = self._connection.execute(
                "SELECT revision, payload_json FROM review_session_current WHERE session_id = ?",
                (previous_session.session_id,),
            ).fetchone()
            if row is None or row["revision"] != previous_session.revision:
                raise ReviewSessionVersionConflictError(previous_session.session_id)
            if self._from_payload(row["payload_json"]) != previous_session:
                raise ReviewSessionVersionConflictError("stale review session state")
            try:
                self._insert_history(previous_session, next_session, metadata)
            except Exception as error:
                raise ReviewSessionHistoryError("review session transition history failed") from error
            try:
                cursor = self._connection.execute(
                    """UPDATE review_session_current SET revision = ?, payload_json = ?,
                    event_id = ?, projected_at = ? WHERE session_id = ? AND revision = ?""",
                    (
                        next_session.revision,
                        self._payload(next_session),
                        metadata.event_id,
                        self._iso(metadata.occurred_at),
                        previous_session.session_id,
                        previous_session.revision,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ReviewSessionProjectionError("review current projection was not advanced")
            except ReviewSessionProjectionError:
                raise
            except Exception as error:
                raise ReviewSessionProjectionError("review current projection update failed") from error
            if _manage_transaction:
                try:
                    self._connection.commit()
                except Exception as error:
                    raise ReviewSessionCommitError("review session transition commit failed") from error
            return next_session
        except (
            ReviewSessionVersionConflictError,
            ReviewSessionHistoryError,
            ReviewSessionProjectionError,
            ReviewSessionCommitError,
        ):
            if _manage_transaction:
                self._connection.rollback()
            raise
        except sqlite3.IntegrityError as error:
            if _manage_transaction:
                self._connection.rollback()
            existing = self._existing_command(metadata)
            if existing is not None:
                return self._resolve_retry(existing, metadata)
            raise ReviewSessionHistoryError("review session transition constraint failed") from error
        except Exception as error:
            if _manage_transaction:
                self._connection.rollback()
            raise ReviewSessionCommitError("review session transition failed") from error

    def close(self) -> None:
        if self._owns_connection:
            self._connection.close()

    def _insert_history(self, previous, next_session, metadata) -> None:
        self._connection.execute(
            """INSERT INTO review_session_history (
            event_id, command_id, command_fingerprint, session_id, revision,
            transition_type, prior_status, resulting_status, transition_at,
            payload_json, inserted_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                metadata.event_id,
                metadata.command_id,
                metadata.command_fingerprint,
                next_session.session_id,
                next_session.revision,
                metadata.transition_type,
                previous.status.value if previous else None,
                next_session.status.value,
                self._iso(metadata.occurred_at),
                self._payload(next_session),
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    def _existing_command(self, metadata):
        return self._connection.execute(
            "SELECT command_fingerprint, payload_json FROM review_session_history WHERE command_id = ?",
            (metadata.command_id,),
        ).fetchone()

    def _resolve_retry(self, row, metadata):
        if row["command_fingerprint"] != metadata.command_fingerprint:
            raise ReviewCommandConflictError(metadata.command_id)
        return self._from_payload(row["payload_json"])

    @classmethod
    def _context_payload(cls, context: ReviewCommandContext) -> str:
        identity = context.market_observation_identity
        return json.dumps(
            {
                "session_id": context.session_id,
                "candidate_id": context.candidate_id,
                "market_observation_identity": {
                    "scope": identity.scope.value,
                    "market": identity.market,
                    "marketplace": identity.marketplace,
                    "canonical_product_id": identity.canonical_product_id,
                    "marketplace_item_id": identity.marketplace_item_id,
                    "normalized_query": identity.normalized_query,
                    "category": identity.category,
                    "variant_identity": identity.variant_identity,
                    "condition": identity.condition,
                    "window_started_at": identity.window_started_at.isoformat(),
                    "window_ended_at": identity.window_ended_at.isoformat(),
                },
                "signal_name": context.signal_name,
                "signal_direction": context.signal_direction.value,
                "artifact_identity": context.artifact_identity,
                "created_at": context.created_at.isoformat(),
                "schema_version": context.schema_version,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @classmethod
    def _context_from_payload(cls, payload: str) -> ReviewCommandContext:
        try:
            value = json.loads(payload)
            if value["schema_version"] != "review-command-context-v1":
                raise UnsupportedReviewSessionVersionError(value["schema_version"])
            identity = value["market_observation_identity"]
            return ReviewCommandContext(
                session_id=value["session_id"],
                candidate_id=value["candidate_id"],
                market_observation_identity=MarketObservationIdentity(
                    scope=MarketObservationScope(identity["scope"]),
                    market=identity["market"],
                    marketplace=identity["marketplace"],
                    canonical_product_id=identity["canonical_product_id"],
                    marketplace_item_id=identity["marketplace_item_id"],
                    normalized_query=identity["normalized_query"],
                    category=identity["category"],
                    variant_identity=identity["variant_identity"],
                    condition=identity["condition"],
                    window_started_at=datetime.fromisoformat(identity["window_started_at"]),
                    window_ended_at=datetime.fromisoformat(identity["window_ended_at"]),
                ),
                signal_name=value["signal_name"],
                signal_direction=ExternalSignalDirection(value["signal_direction"]),
                artifact_identity=value["artifact_identity"],
                created_at=datetime.fromisoformat(value["created_at"]),
                schema_version=value["schema_version"],
            )
        except UnsupportedReviewSessionVersionError:
            raise
        except Exception as error:
            raise MalformedReviewSessionError("malformed review command context") from error

    @staticmethod
    def _receipt_payload(receipt: ReviewCommandReceipt) -> str:
        return json.dumps(
            {
                "command_id": receipt.command_id,
                "session_id": receipt.session_id,
                "candidate_id": receipt.candidate_id,
                "transition_type": receipt.transition_type,
                "resulting_revision": receipt.resulting_revision,
                "verification_id": receipt.verification_id,
                "external_signal_id": receipt.external_signal_id,
                "transition_timestamp": receipt.transition_timestamp.isoformat(),
                "completed_at": receipt.completed_at.isoformat() if receipt.completed_at else None,
                "schema_version": receipt.schema_version,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _receipt_from_payload(payload: str) -> ReviewCommandReceipt:
        try:
            value = json.loads(payload)
            if value["schema_version"] != "review-command-receipt-v1":
                raise UnsupportedReviewSessionVersionError(value["schema_version"])
            return ReviewCommandReceipt(
                command_id=value["command_id"],
                session_id=value["session_id"],
                candidate_id=value["candidate_id"],
                transition_type=value["transition_type"],
                resulting_revision=value["resulting_revision"],
                verification_id=value["verification_id"],
                external_signal_id=value["external_signal_id"],
                transition_timestamp=datetime.fromisoformat(value["transition_timestamp"]),
                completed_at=datetime.fromisoformat(value["completed_at"]) if value["completed_at"] else None,
                schema_version=value["schema_version"],
            )
        except UnsupportedReviewSessionVersionError:
            raise
        except Exception as error:
            raise MalformedReviewSessionError("malformed review command receipt") from error

    @staticmethod
    def _cancel_payload(value: ReviewCancelMetadata) -> str:
        return json.dumps(
            {
                "session_id": value.session_id,
                "reason": value.reason,
                "operator_id": value.operator_id,
                "cancelled_at": value.cancelled_at.isoformat(),
                "revision": value.revision,
                "schema_version": value.schema_version,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _cancel_from_payload(payload: str) -> ReviewCancelMetadata:
        try:
            value = json.loads(payload)
            if value["schema_version"] != "review-cancel-metadata-v1":
                raise UnsupportedReviewSessionVersionError(value["schema_version"])
            return ReviewCancelMetadata(
                session_id=value["session_id"],
                reason=value["reason"],
                operator_id=value["operator_id"],
                cancelled_at=datetime.fromisoformat(value["cancelled_at"]),
                revision=value["revision"],
                schema_version=value["schema_version"],
            )
        except UnsupportedReviewSessionVersionError:
            raise
        except Exception as error:
            raise MalformedReviewSessionError("malformed review cancel metadata") from error

    @classmethod
    def _payload(cls, session: ReviewSession) -> str:
        value = {
            "session_id": session.session_id,
            "artifact_id": session.artifact_id,
            "candidate_ids": list(session.candidate_ids),
            "status": session.status.value,
            "created_at": session.created_at.isoformat(),
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "completed_at": session.completed_at.isoformat() if session.completed_at else None,
            "operator_id": session.operator_id,
            "schema_version": session.schema_version,
            "revision": session.revision,
            "candidate_statuses": [[key, status.value] for key, status in session.candidate_statuses],
            "skip_records": [
                {
                    "candidate_id": record.candidate_id,
                    "operator_id": record.operator_id,
                    "reason": record.reason,
                    "skipped_at": record.skipped_at.isoformat(),
                }
                for record in session.skip_records
            ],
        }
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @classmethod
    def _from_payload(cls, payload: str) -> ReviewSession:
        try:
            value = json.loads(payload)
            if value["schema_version"] != "review-session-v1":
                raise UnsupportedReviewSessionVersionError(value["schema_version"])
            return ReviewSession(
                session_id=value["session_id"],
                artifact_id=value["artifact_id"],
                candidate_ids=tuple(value["candidate_ids"]),
                status=ReviewSessionStatus(value["status"]),
                created_at=datetime.fromisoformat(value["created_at"]),
                started_at=datetime.fromisoformat(value["started_at"]) if value["started_at"] else None,
                completed_at=datetime.fromisoformat(value["completed_at"]) if value["completed_at"] else None,
                operator_id=value["operator_id"],
                schema_version=value["schema_version"],
                revision=value["revision"],
                candidate_statuses=tuple(
                    (candidate_id, CandidateReviewStatus(status))
                    for candidate_id, status in value["candidate_statuses"]
                ),
                skip_records=tuple(
                    CandidateSkipRecord(
                        candidate_id=record["candidate_id"],
                        operator_id=record["operator_id"],
                        reason=record["reason"],
                        skipped_at=datetime.fromisoformat(record["skipped_at"]),
                    )
                    for record in value["skip_records"]
                ),
            )
        except UnsupportedReviewSessionVersionError:
            raise
        except Exception as error:
            raise MalformedReviewSessionError("malformed persisted review session") from error

    @staticmethod
    def _iso(value: datetime) -> str:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("transition timestamp must be timezone-aware")
        return value.astimezone(timezone.utc).isoformat()
