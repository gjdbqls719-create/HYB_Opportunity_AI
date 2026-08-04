"""Immutable SQLite persistence for completed Discovery execution results."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from app.application.discovery_persistence import (
    DiscoveryExecutionIdentityConflictError,
    DiscoveryExecutionNotFoundError,
    DiscoveryExecutionReplayConflict,
    DiscoveryExecutionResultCommitError,
    DiscoveryExecutionResultHistoryError,
    DiscoveryGroupMembershipError,
    MalformedDiscoveryExecutionResult,
    UnsupportedDiscoveryExecutionResultVersion,
)
from app.domain.discovery_identity import (
    DISCOVERY_EXECUTION_RESULT_SCHEMA_VERSION,
    DiscoveryCommandPayloadConflictError,
    DiscoveryExecutionResult,
)


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed


class SQLiteDiscoveryResultRepository:
    """Stores one append-only completion fact per command/execution pair."""

    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if database_path is None and connection is None:
            raise ValueError("database_path or connection is required")
        if database_path is not None and connection is not None:
            raise ValueError("database_path and connection are mutually exclusive")
        self._owns_connection = connection is None
        if connection is None:
            path = Path(database_path)  # type: ignore[arg-type]
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS discovery_execution_result_history (
                    command_id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL UNIQUE,
                    ordered_finalized_group_ids_json TEXT NOT NULL,
                    zero_result INTEGER NOT NULL CHECK(zero_result IN (0, 1)),
                    completed_at TEXT NOT NULL,
                    result_schema_version TEXT NOT NULL,
                    result_fingerprint TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(command_id, execution_id)
                        REFERENCES discovery_command_history(command_id, execution_id)
                )"""
            )
            for operation in ("UPDATE", "DELETE"):
                self._connection.execute(
                    f"""CREATE TRIGGER IF NOT EXISTS
                    trg_discovery_execution_result_history_no_{operation.lower()}
                    BEFORE {operation} ON discovery_execution_result_history
                    BEGIN SELECT RAISE(ABORT,
                        'discovery_execution_result_history is append-only'); END"""
                )

    def _command_pair_exists(self, command_id: str, execution_id: str) -> bool:
        try:
            return self._connection.execute(
                """SELECT 1 FROM discovery_command_history
                WHERE command_id = ? AND execution_id = ?""",
                (command_id, execution_id),
            ).fetchone() is not None
        except sqlite3.Error as error:
            raise DiscoveryExecutionResultHistoryError(
                "discovery command identity query failed"
            ) from error

    def _validate_groups(self, result: DiscoveryExecutionResult) -> None:
        for group_id in result.finalized_group_ids:
            try:
                row = self._connection.execute(
                    """SELECT discovery_execution_id
                    FROM discovery_finalized_group_history
                    WHERE finalized_group_id = ?""",
                    (group_id,),
                ).fetchone()
            except sqlite3.Error as error:
                raise DiscoveryExecutionResultHistoryError(
                    "finalized group lineage query failed"
                ) from error
            if row is None:
                raise DiscoveryGroupMembershipError(
                    "execution result references a missing finalized group"
                )
            if row["discovery_execution_id"] != result.discovery_execution_id:
                raise DiscoveryExecutionIdentityConflictError(
                    "execution result and finalized group execution must match"
                )

    def save_result(self, result: DiscoveryExecutionResult) -> DiscoveryExecutionResult:
        if not isinstance(result, DiscoveryExecutionResult):
            raise TypeError("result must be DiscoveryExecutionResult")
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:
            raise DiscoveryExecutionResultCommitError(
                "execution result transaction could not start"
            ) from error
        try:
            existing = self._get_by("command_id", result.command_id)
            if existing is not None:
                if existing.fingerprint != result.fingerprint or existing != result:
                    raise DiscoveryExecutionReplayConflict(
                        "execution result conflicts with committed result"
                    )
                self._rollback()
                return existing
            execution_result = self._get_by(
                "execution_id", result.discovery_execution_id
            )
            if execution_result is not None:
                raise DiscoveryExecutionReplayConflict(
                    "execution already has a committed result"
                )
            if not self._command_pair_exists(
                result.command_id, result.discovery_execution_id
            ):
                command_exists = self._command_exists(result.command_id)
                execution_exists = self._execution_exists(
                    result.discovery_execution_id
                )
                if command_exists or execution_exists:
                    raise DiscoveryExecutionIdentityConflictError(
                        "result command and execution identity do not match"
                    )
                raise DiscoveryExecutionNotFoundError(
                    "result has no committed discovery command"
                )
            self._validate_groups(result)
            try:
                self._insert_result(result)
            except sqlite3.Error as error:
                raise DiscoveryExecutionResultHistoryError(
                    "execution result history insert failed"
                ) from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise DiscoveryExecutionResultCommitError(
                    "execution result transaction commit failed"
                ) from error
            return result
        except Exception:
            self._rollback()
            raise

    def _command_exists(self, command_id: str) -> bool:
        try:
            return self._connection.execute(
                "SELECT 1 FROM discovery_command_history WHERE command_id = ?",
                (command_id,),
            ).fetchone() is not None
        except sqlite3.Error as error:
            raise DiscoveryExecutionResultHistoryError(
                "discovery command query failed"
            ) from error

    def _execution_exists(self, execution_id: str) -> bool:
        try:
            return self._connection.execute(
                "SELECT 1 FROM discovery_command_history WHERE execution_id = ?",
                (execution_id,),
            ).fetchone() is not None
        except sqlite3.Error as error:
            raise DiscoveryExecutionResultHistoryError(
                "discovery execution query failed"
            ) from error

    def _insert_result(self, result: DiscoveryExecutionResult) -> None:
        self._connection.execute(
            """INSERT INTO discovery_execution_result_history (
                command_id, execution_id, ordered_finalized_group_ids_json,
                zero_result, completed_at, result_schema_version,
                result_fingerprint, inserted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.command_id,
                result.discovery_execution_id,
                json.dumps(list(result.finalized_group_ids), separators=(",", ":")),
                int(result.is_zero_result),
                result.completed_at.isoformat(),
                result.schema_version,
                result.fingerprint,
                result.completed_at.astimezone(timezone.utc).isoformat(),
            ),
        )

    def _commit(self) -> None:
        self._connection.commit()

    def _rollback(self) -> None:
        if self._connection.in_transaction:
            self._connection.rollback()

    @staticmethod
    def _from_row(row: sqlite3.Row) -> DiscoveryExecutionResult:
        if row["result_schema_version"] != DISCOVERY_EXECUTION_RESULT_SCHEMA_VERSION:
            raise UnsupportedDiscoveryExecutionResultVersion(
                f"unsupported result version: {row['result_schema_version']}"
            )
        try:
            group_ids = json.loads(row["ordered_finalized_group_ids_json"])
            if not isinstance(group_ids, list) or any(
                not isinstance(value, str) for value in group_ids
            ):
                raise ValueError("ordered finalized group IDs must be text array")
            result = DiscoveryExecutionResult(
                command_id=row["command_id"],
                discovery_execution_id=row["execution_id"],
                finalized_group_ids=tuple(group_ids),
                completed_at=_aware(row["completed_at"], "completed_at"),
                schema_version=row["result_schema_version"],
            )
            if bool(row["zero_result"]) != result.is_zero_result:
                raise ValueError("zero-result flag conflicts with group membership")
            if result.fingerprint != row["result_fingerprint"]:
                raise ValueError("execution result fingerprint mismatch")
            return result
        except UnsupportedDiscoveryExecutionResultVersion:
            raise
        except (DiscoveryCommandPayloadConflictError, KeyError, TypeError, ValueError) as error:
            raise MalformedDiscoveryExecutionResult(
                "malformed persisted execution result"
            ) from error

    def _get_by(self, column: str, value: str) -> DiscoveryExecutionResult | None:
        if column not in {"command_id", "execution_id"}:
            raise ValueError("unsupported result lookup")
        try:
            row = self._connection.execute(
                f"SELECT * FROM discovery_execution_result_history WHERE {column} = ?",
                (value,),
            ).fetchone()
        except sqlite3.Error as error:
            raise DiscoveryExecutionResultHistoryError(
                "execution result query failed"
            ) from error
        if row is None:
            return None
        result = self._from_row(row)
        if not self._command_pair_exists(result.command_id, result.discovery_execution_id):
            raise MalformedDiscoveryExecutionResult(
                "persisted result has no matching command identity"
            )
        try:
            self._validate_groups(result)
        except (
            DiscoveryGroupMembershipError,
            DiscoveryExecutionIdentityConflictError,
        ) as error:
            raise MalformedDiscoveryExecutionResult(
                "persisted result has invalid finalized group lineage"
            ) from error
        return result

    def get_result(
        self, discovery_execution_id: str
    ) -> DiscoveryExecutionResult | None:
        return self.get_by_execution(discovery_execution_id)

    def get_by_command(self, command_id: str) -> DiscoveryExecutionResult | None:
        return self._get_by("command_id", _required(command_id, "command_id"))

    def get_by_execution(
        self, discovery_execution_id: str
    ) -> DiscoveryExecutionResult | None:
        return self._get_by(
            "execution_id",
            _required(discovery_execution_id, "discovery_execution_id"),
        )

    def close(self) -> None:
        if self._owns_connection:
            self._connection.close()

    def __enter__(self) -> "SQLiteDiscoveryResultRepository":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
