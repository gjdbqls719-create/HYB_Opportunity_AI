from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from app.application.opportunity_validation import (
    DuplicateValidationConflictError,
    ValidationAdmissionSnapshot,
    ValidationQueueItem,
    canonicalize_discovery_reference,
)
from app.application.opportunity_lifecycle import LifecycleVersionConflictError
from app.domain.opportunity import OpportunityLifecycle, OpportunityLifecycleStatus, OpportunityLifecycleTransition
from app.infrastructure.opportunity_lifecycle import SQLiteOpportunityLifecycleRepository


_SNAPSHOT_TABLE = """
CREATE TABLE IF NOT EXISTS validation_queue_admission_snapshots (
    opportunity_id TEXT PRIMARY KEY,
    discovery_reference TEXT NOT NULL,
    marketplace TEXT NOT NULL,
    title TEXT NOT NULL,
    admission_recommendation TEXT NOT NULL,
    admission_score REAL NOT NULL,
    admission_roi REAL NOT NULL,
    currency TEXT NOT NULL,
    admission_safety_status TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    FOREIGN KEY (opportunity_id) REFERENCES opportunity_lifecycles(opportunity_id)
)
"""

_NON_ARCHIVED_REFERENCE_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_validation_discovery_reference
ON opportunity_lifecycles (discovery_reference)
WHERE archived_at IS NULL
"""


class SQLiteValidationQueueRepository:
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
            connection = sqlite3.connect(resolved, check_same_thread=False)
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._lifecycles = SQLiteOpportunityLifecycleRepository(connection=connection)
        with self._connection:
            self._connection.execute(_SNAPSHOT_TABLE)
            self._migrate_canonical_references()
            self._connection.execute(_NON_ARCHIVED_REFERENCE_INDEX)
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_validation_snapshot_reference "
                "ON validation_queue_admission_snapshots(discovery_reference)"
            )

    def admit(
        self,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        snapshot: ValidationAdmissionSnapshot,
    ) -> None:
        if snapshot.opportunity_id != lifecycle.opportunity_id:
            raise ValueError("snapshot opportunity_id does not match lifecycle")
        if snapshot.discovery_reference != lifecycle.discovery_reference:
            raise ValueError("snapshot discovery_reference does not match lifecycle")
        self._lifecycles._validate_creation(lifecycle, transition)
        try:
            with self._connection:
                self._lifecycles._insert_current(lifecycle)
                self._lifecycles._insert_transition(transition)
                self._connection.execute(
                    """INSERT INTO validation_queue_admission_snapshots (
                        opportunity_id, discovery_reference, marketplace, title,
                        admission_recommendation, admission_score, admission_roi,
                        currency, admission_safety_status, captured_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        snapshot.opportunity_id,
                        snapshot.discovery_reference,
                        snapshot.marketplace,
                        snapshot.title,
                        snapshot.admission_recommendation,
                        snapshot.admission_score,
                        snapshot.admission_roi,
                        snapshot.currency,
                        snapshot.admission_safety_status,
                        snapshot.captured_at.isoformat(),
                    ),
                )
        except sqlite3.IntegrityError as error:
            if self._non_archived_reference_exists(snapshot.discovery_reference):
                raise DuplicateValidationConflictError(snapshot.discovery_reference) from error
            raise

    def list_queue(
        self,
        *,
        statuses: tuple[OpportunityLifecycleStatus, ...],
        limit: int,
    ) -> tuple[ValidationQueueItem, ...]:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if not statuses:
            return ()
        placeholders = ",".join("?" for _ in statuses)
        rows = self._connection.execute(
            f"""SELECT s.*, l.status, l.version, l.created_at, l.updated_at
            FROM validation_queue_admission_snapshots AS s
            JOIN opportunity_lifecycles AS l ON l.opportunity_id = s.opportunity_id
            WHERE l.archived_at IS NULL AND l.status IN ({placeholders})
            ORDER BY l.created_at ASC, l.opportunity_id ASC
            LIMIT ?""",
            tuple(status.value for status in statuses) + (limit,),
        ).fetchall()
        return tuple(self._to_item(row) for row in rows)

    def get_queue_item(self, opportunity_id: str) -> ValidationQueueItem | None:
        row = self._connection.execute(
            """SELECT s.*, l.status, l.version, l.created_at, l.updated_at
            FROM validation_queue_admission_snapshots AS s
            JOIN opportunity_lifecycles AS l ON l.opportunity_id = s.opportunity_id
            WHERE l.opportunity_id = ? AND l.archived_at IS NULL""",
            (opportunity_id,),
        ).fetchone()
        return self._to_item(row) if row is not None else None

    def create(self, lifecycle, transition) -> None:
        self._lifecycles.create(lifecycle, transition)

    def get(self, opportunity_id: str):
        return self._lifecycles.get(opportunity_id)

    def save_transition(self, lifecycle, transition, *, expected_version: int) -> None:
        if (
            not lifecycle.is_archived
            and self._non_archived_reference_exists(
                lifecycle.discovery_reference,
                excluding_opportunity_id=lifecycle.opportunity_id,
            )
        ):
            raise DuplicateValidationConflictError(lifecycle.discovery_reference)
        try:
            self._lifecycles.save_transition(
                lifecycle,
                transition,
                expected_version=expected_version,
            )
        except LifecycleVersionConflictError as error:
            if (
                not lifecycle.is_archived
                and self._non_archived_reference_exists(
                    lifecycle.discovery_reference,
                    excluding_opportunity_id=lifecycle.opportunity_id,
                )
            ):
                raise DuplicateValidationConflictError(lifecycle.discovery_reference) from error
            raise

    def list_transitions(self, opportunity_id: str):
        return self._lifecycles.list_transitions(opportunity_id)

    def close(self) -> None:
        if self._owns_connection:
            self._connection.close()

    def _non_archived_reference_exists(
        self,
        discovery_reference: str,
        *,
        excluding_opportunity_id: str | None = None,
    ) -> bool:
        parameters: list[str] = [canonicalize_discovery_reference(discovery_reference)]
        exclusion = ""
        if excluding_opportunity_id is not None:
            exclusion = " AND opportunity_id <> ?"
            parameters.append(excluding_opportunity_id)
        row = self._connection.execute(
            """SELECT 1 FROM opportunity_lifecycles
            WHERE discovery_reference = ? AND archived_at IS NULL"""
            + exclusion
            + " LIMIT 1",
            tuple(parameters),
        ).fetchone()
        return row is not None

    def _migrate_canonical_references(self) -> None:
        self._connection.execute("DROP INDEX IF EXISTS uq_active_validation_discovery_reference")
        rows = self._connection.execute(
            "SELECT opportunity_id, discovery_reference FROM opportunity_lifecycles"
        ).fetchall()
        for row in rows:
            canonical = canonicalize_discovery_reference(row["discovery_reference"])
            self._connection.execute(
                "UPDATE opportunity_lifecycles SET discovery_reference = ? WHERE opportunity_id = ?",
                (canonical, row["opportunity_id"]),
            )
            self._connection.execute(
                "UPDATE validation_queue_admission_snapshots SET discovery_reference = ? "
                "WHERE opportunity_id = ?",
                (canonical, row["opportunity_id"]),
            )

    @staticmethod
    def _to_item(row: sqlite3.Row) -> ValidationQueueItem:
        return ValidationQueueItem(
            opportunity_id=row["opportunity_id"],
            discovery_reference=row["discovery_reference"],
            marketplace=row["marketplace"],
            title=row["title"],
            recommendation=row["admission_recommendation"],
            score=float(row["admission_score"]),
            roi=float(row["admission_roi"]),
            currency=row["currency"],
            safety_status=row["admission_safety_status"],
            lifecycle_status=OpportunityLifecycleStatus(row["status"]),
            lifecycle_version=int(row["version"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
        )
