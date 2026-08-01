from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from app.application.opportunity_lifecycle import (
    DuplicateLifecycleError,
    LifecycleSemanticError,
    LifecycleVersionConflictError,
    OpportunityLifecycleRepository,
)
from app.domain.opportunity import (
    OpportunityLifecycle,
    OpportunityLifecycleAction,
    OpportunityLifecycleStatus,
    OpportunityLifecycleTransition,
)


_CURRENT_TABLE = """
CREATE TABLE IF NOT EXISTS opportunity_lifecycles (
    opportunity_id TEXT PRIMARY KEY,
    discovery_reference TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    archived_at TEXT,
    archived_by TEXT,
    archive_reason TEXT,
    CHECK (status IN ('discovered','under_review','approved','rejected','purchased','listed','sold')),
    CHECK ((archived_at IS NULL AND archived_by IS NULL AND archive_reason IS NULL)
        OR (archived_at IS NOT NULL AND archived_by IS NOT NULL AND archive_reason IS NOT NULL))
)
"""

_HISTORY_TABLE = """
CREATE TABLE IF NOT EXISTS opportunity_lifecycle_transitions (
    transition_id TEXT PRIMARY KEY,
    opportunity_id TEXT NOT NULL,
    action TEXT NOT NULL,
    previous_status TEXT NOT NULL,
    new_status TEXT NOT NULL,
    version INTEGER NOT NULL CHECK (version >= 1),
    occurred_at TEXT NOT NULL,
    operator_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    note TEXT,
    founder_decision_id TEXT,
    UNIQUE (opportunity_id, version),
    FOREIGN KEY (opportunity_id) REFERENCES opportunity_lifecycles(opportunity_id)
)
"""

_ACTION_TARGET_STATUS = {
    OpportunityLifecycleAction.START_REVIEW: OpportunityLifecycleStatus.UNDER_REVIEW,
    OpportunityLifecycleAction.RETURN_TO_REVIEW: OpportunityLifecycleStatus.UNDER_REVIEW,
    OpportunityLifecycleAction.APPROVE: OpportunityLifecycleStatus.APPROVED,
    OpportunityLifecycleAction.REJECT: OpportunityLifecycleStatus.REJECTED,
    OpportunityLifecycleAction.PURCHASE: OpportunityLifecycleStatus.PURCHASED,
    OpportunityLifecycleAction.WITHDRAW_LISTING: OpportunityLifecycleStatus.PURCHASED,
    OpportunityLifecycleAction.LIST: OpportunityLifecycleStatus.LISTED,
    OpportunityLifecycleAction.SELL: OpportunityLifecycleStatus.SOLD,
}


class SQLiteOpportunityLifecycleRepository(OpportunityLifecycleRepository):
    def __init__(self, database_path: str | Path = "data/hyb_opportunity.db", *, connection: sqlite3.Connection | None = None) -> None:
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
            self._connection.execute(_CURRENT_TABLE)
            self._connection.execute(_HISTORY_TABLE)
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_lifecycle_status_updated ON opportunity_lifecycles(status, updated_at)"
            )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_lifecycle_history ON opportunity_lifecycle_transitions(opportunity_id, version)"
            )

    def create(self, lifecycle: OpportunityLifecycle, transition: OpportunityLifecycleTransition) -> None:
        self._validate_creation(lifecycle, transition)
        try:
            with self._connection:
                self._insert_current(lifecycle)
                self._insert_transition(transition)
        except sqlite3.IntegrityError as error:
            raise DuplicateLifecycleError(lifecycle.opportunity_id) from error

    def get(self, opportunity_id: str) -> OpportunityLifecycle | None:
        row = self._connection.execute(
            "SELECT * FROM opportunity_lifecycles WHERE opportunity_id = ?", (opportunity_id,)
        ).fetchone()
        if row is None:
            return None
        return OpportunityLifecycle._reconstitute(
            opportunity_id=row["opportunity_id"],
            discovery_reference=row["discovery_reference"],
            status=OpportunityLifecycleStatus(row["status"]),
            version=row["version"],
            created_at=self._datetime(row["created_at"]),
            updated_at=self._datetime(row["updated_at"]),
            archived_at=self._datetime(row["archived_at"]) if row["archived_at"] else None,
            archived_by=row["archived_by"],
            archive_reason=row["archive_reason"],
        )

    def save_transition(self, lifecycle: OpportunityLifecycle, transition: OpportunityLifecycleTransition, *, expected_version: int) -> None:
        current_row = self._connection.execute(
            "SELECT * FROM opportunity_lifecycles WHERE opportunity_id = ?",
            (lifecycle.opportunity_id,),
        ).fetchone()
        if current_row is None:
            raise LifecycleVersionConflictError(
                f"lifecycle {lifecycle.opportunity_id} does not exist"
            )
        self._validate_transition(
            lifecycle,
            transition,
            expected_version=expected_version,
            current_row=current_row,
        )
        try:
            with self._connection:
                cursor = self._connection.execute(
                    """
                    UPDATE opportunity_lifecycles SET
                        discovery_reference = ?, status = ?, version = ?, updated_at = ?,
                        archived_at = ?, archived_by = ?, archive_reason = ?
                    WHERE opportunity_id = ? AND version = ?
                    """,
                    (
                        lifecycle.discovery_reference, lifecycle.status.value, lifecycle.version,
                        lifecycle.updated_at.isoformat(), self._iso(lifecycle.archived_at),
                        lifecycle.archived_by, lifecycle.archive_reason,
                        lifecycle.opportunity_id, expected_version,
                    ),
                )
                if cursor.rowcount != 1:
                    raise LifecycleVersionConflictError(
                        f"lifecycle {lifecycle.opportunity_id} was updated concurrently"
                    )
                self._insert_transition(transition)
        except sqlite3.IntegrityError as error:
            raise LifecycleVersionConflictError("transition history conflict") from error

    def list_transitions(self, opportunity_id: str) -> tuple[OpportunityLifecycleTransition, ...]:
        rows = self._connection.execute(
            "SELECT * FROM opportunity_lifecycle_transitions WHERE opportunity_id = ? ORDER BY version",
            (opportunity_id,),
        ).fetchall()
        return tuple(
            OpportunityLifecycleTransition(
                transition_id=row["transition_id"], opportunity_id=row["opportunity_id"],
                action=OpportunityLifecycleAction(row["action"]),
                previous_status=OpportunityLifecycleStatus(row["previous_status"]),
                new_status=OpportunityLifecycleStatus(row["new_status"]), version=row["version"],
                occurred_at=self._datetime(row["occurred_at"]), operator_id=row["operator_id"],
                reason=row["reason"], note=row["note"], founder_decision_id=row["founder_decision_id"],
            )
            for row in rows
        )

    def close(self) -> None:
        if self._owns_connection:
            self._connection.close()

    def _insert_current(self, item: OpportunityLifecycle) -> None:
        self._connection.execute(
            """INSERT INTO opportunity_lifecycles
            (opportunity_id, discovery_reference, status, version, created_at, updated_at,
             archived_at, archived_by, archive_reason) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (item.opportunity_id, item.discovery_reference, item.status.value, item.version,
             item.created_at.isoformat(), item.updated_at.isoformat(), self._iso(item.archived_at),
             item.archived_by, item.archive_reason),
        )

    def _insert_transition(self, event: OpportunityLifecycleTransition) -> None:
        self._connection.execute(
            """INSERT INTO opportunity_lifecycle_transitions
            (transition_id, opportunity_id, action, previous_status, new_status, version,
             occurred_at, operator_id, reason, note, founder_decision_id)
             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event.transition_id, event.opportunity_id, event.action.value,
             event.previous_status.value, event.new_status.value, event.version,
             event.occurred_at.isoformat(), event.operator_id, event.reason, event.note,
             event.founder_decision_id),
        )

    @staticmethod
    def _iso(value):
        return value.isoformat() if value is not None else None

    @staticmethod
    def _datetime(value: str):
        return datetime.fromisoformat(value)

    @classmethod
    def _validate_creation(
        cls,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
    ) -> None:
        cls._validate_event_completeness(transition)
        if (
            lifecycle.status is not OpportunityLifecycleStatus.DISCOVERED
            or lifecycle.version != 1
            or lifecycle.created_at != lifecycle.updated_at
            or lifecycle.is_archived
            or transition.action is not OpportunityLifecycleAction.CREATE
            or transition.previous_status is not OpportunityLifecycleStatus.DISCOVERED
            or transition.new_status is not lifecycle.status
            or transition.version != lifecycle.version
            or transition.occurred_at != lifecycle.created_at
            or transition.opportunity_id != lifecycle.opportunity_id
        ):
            raise LifecycleSemanticError("invalid lifecycle creation event")

    @classmethod
    def _validate_transition(
        cls,
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        *,
        expected_version: int,
        current_row: sqlite3.Row,
    ) -> None:
        cls._validate_event_completeness(transition)
        persisted_version = current_row["version"]
        persisted_status = OpportunityLifecycleStatus(current_row["status"])
        persisted_updated_at = cls._datetime(current_row["updated_at"])

        if persisted_version != expected_version:
            raise LifecycleVersionConflictError(
                f"expected version {expected_version}, found {persisted_version}"
            )
        if lifecycle.version != expected_version + 1 or transition.version != lifecycle.version:
            raise LifecycleVersionConflictError(
                "transition version must advance expected_version exactly once"
            )
        if transition.opportunity_id != lifecycle.opportunity_id:
            raise LifecycleSemanticError("transition opportunity_id does not match aggregate")
        if transition.previous_status is not persisted_status:
            raise LifecycleSemanticError("transition previous_status does not match current state")
        if transition.new_status is not lifecycle.status:
            raise LifecycleSemanticError("transition new_status does not match aggregate state")
        if transition.occurred_at != lifecycle.updated_at:
            raise LifecycleSemanticError("transition timestamp does not match aggregate updated_at")
        if transition.occurred_at < persisted_updated_at:
            raise LifecycleSemanticError("transition timestamp precedes current state")
        if lifecycle.created_at != cls._datetime(current_row["created_at"]):
            raise LifecycleSemanticError("aggregate created_at cannot change")
        if lifecycle.discovery_reference != current_row["discovery_reference"]:
            raise LifecycleSemanticError("aggregate discovery_reference cannot change")
        cls._validate_action_semantics(lifecycle, transition, current_row=current_row)

    @staticmethod
    def _validate_action_semantics(
        lifecycle: OpportunityLifecycle,
        transition: OpportunityLifecycleTransition,
        *,
        current_row: sqlite3.Row,
    ) -> None:
        if transition.action is OpportunityLifecycleAction.CREATE:
            raise LifecycleSemanticError("CREATE is only valid for lifecycle creation")
        expected_target = _ACTION_TARGET_STATUS.get(transition.action)
        if expected_target is not None:
            if transition.new_status is not expected_target:
                raise LifecycleSemanticError("transition action does not match new_status")
            if lifecycle.is_archived or current_row["archived_at"] is not None:
                raise LifecycleSemanticError("business transition cannot use archived state")
            return
        if transition.action is OpportunityLifecycleAction.ARCHIVE:
            if (
                current_row["archived_at"] is not None
                or not lifecycle.is_archived
                or lifecycle.archived_at != transition.occurred_at
                or lifecycle.archived_by != transition.operator_id
                or lifecycle.archive_reason != transition.reason
                or transition.previous_status is not transition.new_status
            ):
                raise LifecycleSemanticError("archive event does not match aggregate metadata")
            return
        if transition.action is OpportunityLifecycleAction.RESTORE:
            if (
                current_row["archived_at"] is None
                or lifecycle.is_archived
                or transition.previous_status is not transition.new_status
            ):
                raise LifecycleSemanticError("restore event does not match aggregate metadata")
            return
        raise LifecycleSemanticError("transition action is unsupported")

    @staticmethod
    def _validate_event_completeness(transition: OpportunityLifecycleTransition) -> None:
        if not isinstance(transition, OpportunityLifecycleTransition):
            raise LifecycleSemanticError("transition must be an OpportunityLifecycleTransition")
        if not isinstance(transition.action, OpportunityLifecycleAction):
            raise LifecycleSemanticError("transition action is invalid")
        if not isinstance(transition.previous_status, OpportunityLifecycleStatus):
            raise LifecycleSemanticError("transition previous_status is invalid")
        if not isinstance(transition.new_status, OpportunityLifecycleStatus):
            raise LifecycleSemanticError("transition new_status is invalid")
        if not isinstance(transition.version, int) or isinstance(transition.version, bool) or transition.version < 1:
            raise LifecycleSemanticError("transition version is invalid")
        if not isinstance(transition.occurred_at, datetime):
            raise LifecycleSemanticError("transition timestamp is invalid")
        if transition.occurred_at.tzinfo is None or transition.occurred_at.utcoffset() is None:
            raise LifecycleSemanticError("transition timestamp must be timezone-aware")
        for field_name in ("transition_id", "opportunity_id", "operator_id", "reason"):
            value = getattr(transition, field_name, None)
            if not isinstance(value, str) or not value.strip():
                raise LifecycleSemanticError(f"transition {field_name} is incomplete")
