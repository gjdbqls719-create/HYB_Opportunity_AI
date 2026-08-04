"""Atomic append-only SQLite persistence for Discovery commands and receipts."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
import json
from pathlib import Path
import sqlite3

from app.application.discovery_persistence import (
    DISCOVERY_COMMAND_RECEIPT_SCHEMA_VERSION,
    DiscoveryCommandCommitError,
    DiscoveryCommandHistoryError,
    DiscoveryCommandReceipt,
    DiscoveryCommandReceiptError,
    DiscoveryReplayConflict,
    DuplicateDiscoveryExecutionError,
    MalformedDiscoveryCommandPersistenceError,
    MalformedDiscoveryReceipt,
    UnsupportedDiscoveryReceiptVersion,
)
from app.domain.discovery_identity import (
    DISCOVERY_COMMAND_SCHEMA_VERSION,
    DiscoveryCommand,
    DiscoveryCommandParameters,
    MalformedDiscoveryCommandError,
    UnsupportedDiscoveryCommandVersionError,
)


class SQLiteDiscoveryCommandRepository:
    """Owns one atomic command/receipt pair per command and execution ID."""

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
                """CREATE TABLE IF NOT EXISTS discovery_command_history (
                    command_id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL UNIQUE,
                    canonical_payload_json TEXT NOT NULL,
                    canonical_payload_fingerprint TEXT NOT NULL,
                    requested_at TEXT NOT NULL,
                    command_schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    UNIQUE(command_id, execution_id)
                )"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS discovery_command_receipts (
                    command_id TEXT PRIMARY KEY,
                    execution_id TEXT NOT NULL UNIQUE,
                    canonical_payload_fingerprint TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    receipt_schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(command_id, execution_id)
                        REFERENCES discovery_command_history(command_id, execution_id)
                )"""
            )
            for table in ("discovery_command_history", "discovery_command_receipts"):
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

    @staticmethod
    def _payload(command: DiscoveryCommand) -> str:
        parameters = command.parameters
        value = {
            "command_id": command.command_id,
            "discovery_execution_id": command.discovery_execution_id,
            "parameters": {
                "query": parameters.query,
                "selling_price_multiplier": str(parameters.selling_price_multiplier),
                "shipping_cost": None if parameters.shipping_cost is None else str(parameters.shipping_cost),
                "marketplace_fee_rate": str(parameters.marketplace_fee_rate),
                "payment_fee_rate": str(parameters.payment_fee_rate),
                "fixed_fee": None if parameters.fixed_fee is None else str(parameters.fixed_fee),
                "marketplace_fee_known": parameters.marketplace_fee_known,
                "payment_fee_known": parameters.payment_fee_known,
                "fixed_fee_known": parameters.fixed_fee_known,
                "tax_rate": str(parameters.tax_rate),
                "other_cost": str(parameters.other_cost),
                "minimum_net_profit": str(parameters.minimum_net_profit),
                "minimum_roi": str(parameters.minimum_roi),
                "estimated_monthly_sales": parameters.estimated_monthly_sales,
                "competitor_count": parameters.competitor_count,
                "risk_level": parameters.risk_level,
                "limit": parameters.limit,
                "match_threshold": str(parameters.match_threshold),
                "target_currency": parameters.target_currency,
                "policy_references": [list(item) for item in parameters.policy_references],
                "source_references": [list(item) for item in parameters.source_references],
            },
            "requested_at": command.requested_at.isoformat(),
            "schema_version": command.schema_version,
        }
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _parse_datetime(value: object, name: str) -> datetime:
        if not isinstance(value, str):
            raise ValueError(f"{name} must be text")
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")
        return parsed

    @classmethod
    def _command_from_row(cls, row: sqlite3.Row) -> DiscoveryCommand:
        try:
            payload = json.loads(row["canonical_payload_json"])
            if not isinstance(payload, dict) or not isinstance(payload.get("parameters"), dict):
                raise ValueError("command payload must be an object")
            values = payload["parameters"]
            decimal_names = (
                "selling_price_multiplier", "marketplace_fee_rate",
                "payment_fee_rate", "tax_rate", "other_cost",
                "minimum_net_profit", "minimum_roi", "match_threshold",
            )
            decimals = {name: Decimal(values[name]) for name in decimal_names}
            shipping = values["shipping_cost"]
            fixed = values["fixed_fee"]
            parameters = DiscoveryCommandParameters(
                query=values["query"],
                shipping_cost=None if shipping is None else Decimal(shipping),
                fixed_fee=None if fixed is None else Decimal(fixed),
                marketplace_fee_known=values["marketplace_fee_known"],
                payment_fee_known=values["payment_fee_known"],
                fixed_fee_known=values["fixed_fee_known"],
                estimated_monthly_sales=values["estimated_monthly_sales"],
                competitor_count=values["competitor_count"],
                risk_level=values["risk_level"], limit=values["limit"],
                target_currency=values["target_currency"],
                policy_references=tuple(tuple(item) for item in values["policy_references"]),
                source_references=tuple(tuple(item) for item in values["source_references"]),
                **decimals,
            )
            command = DiscoveryCommand(
                command_id=payload["command_id"],
                discovery_execution_id=payload["discovery_execution_id"],
                parameters=parameters,
                requested_at=cls._parse_datetime(payload["requested_at"], "requested_at"),
                schema_version=payload["schema_version"],
            )
            if (
                command.command_id != row["command_id"]
                or command.discovery_execution_id != row["execution_id"]
                or command.requested_at.isoformat() != row["requested_at"]
                or command.schema_version != row["command_schema_version"]
                or command.fingerprint != row["canonical_payload_fingerprint"]
            ):
                raise ValueError("stored command columns do not match canonical payload")
            return command
        except UnsupportedDiscoveryCommandVersionError:
            raise
        except (KeyError, TypeError, ValueError, ArithmeticError, MalformedDiscoveryCommandError) as error:
            raise MalformedDiscoveryCommandPersistenceError(
                "malformed persisted discovery command"
            ) from error

    @classmethod
    def _receipt_from_row(cls, row: sqlite3.Row) -> DiscoveryCommandReceipt:
        try:
            return DiscoveryCommandReceipt(
                command_id=row["command_id"], execution_id=row["execution_id"],
                canonical_payload_fingerprint=row["canonical_payload_fingerprint"],
                committed_at=cls._parse_datetime(row["committed_at"], "committed_at"),
                schema_version=row["receipt_schema_version"],
            )
        except UnsupportedDiscoveryReceiptVersion:
            raise
        except (KeyError, TypeError, ValueError, MalformedDiscoveryReceipt) as error:
            raise MalformedDiscoveryCommandPersistenceError(
                "malformed persisted discovery receipt"
            ) from error

    def _rollback(self) -> None:
        if self._connection.in_transaction:
            self._connection.rollback()

    def save_command(
        self, command: DiscoveryCommand, receipt: DiscoveryCommandReceipt
    ) -> DiscoveryCommandReceipt:
        if not isinstance(command, DiscoveryCommand):
            raise TypeError("command must be DiscoveryCommand")
        if not isinstance(receipt, DiscoveryCommandReceipt):
            raise TypeError("receipt must be DiscoveryCommandReceipt")
        if (
            receipt.command_id != command.command_id
            or receipt.execution_id != command.discovery_execution_id
            or receipt.canonical_payload_fingerprint != command.fingerprint
        ):
            raise DiscoveryReplayConflict("command and receipt do not match")
        payload = self._payload(command)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:
            raise DiscoveryCommandCommitError("discovery command transaction could not start") from error
        try:
            existing = self._select_receipt(command.command_id)
            if existing is not None:
                if existing.canonical_payload_fingerprint != receipt.canonical_payload_fingerprint:
                    raise DiscoveryReplayConflict("discovery command payload conflicts with committed receipt")
                committed = self._select_command("command_id", command.command_id)
                if committed is None or committed != command:
                    raise MalformedDiscoveryCommandPersistenceError("committed receipt and command disagree")
                self._rollback()
                return existing
            execution = self._select_command("execution_id", command.discovery_execution_id)
            if execution is not None:
                raise DuplicateDiscoveryExecutionError("discovery execution ID is already committed")
            try:
                self._insert_command(command, payload, receipt.committed_at)
            except sqlite3.Error as error:
                raise DiscoveryCommandHistoryError("discovery command history insert failed") from error
            try:
                self._insert_receipt(receipt)
            except sqlite3.Error as error:
                raise DiscoveryCommandReceiptError("discovery command receipt insert failed") from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise DiscoveryCommandCommitError("discovery command transaction commit failed") from error
            return receipt
        except Exception:
            self._rollback()
            raise

    def _insert_command(self, command: DiscoveryCommand, payload: str, inserted_at: datetime) -> None:
        self._connection.execute(
            """INSERT INTO discovery_command_history (
                command_id, execution_id, canonical_payload_json,
                canonical_payload_fingerprint, requested_at,
                command_schema_version, inserted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (command.command_id, command.discovery_execution_id, payload,
             command.fingerprint, command.requested_at.isoformat(),
             command.schema_version, inserted_at.astimezone(timezone.utc).isoformat()),
        )

    def _insert_receipt(self, receipt: DiscoveryCommandReceipt) -> None:
        self._connection.execute(
            """INSERT INTO discovery_command_receipts (
                command_id, execution_id, canonical_payload_fingerprint,
                committed_at, receipt_schema_version, inserted_at
            ) VALUES (?, ?, ?, ?, ?, ?)""",
            (receipt.command_id, receipt.execution_id,
             receipt.canonical_payload_fingerprint, receipt.committed_at.isoformat(),
             receipt.schema_version,
             receipt.committed_at.astimezone(timezone.utc).isoformat()),
        )

    def _commit(self) -> None:
        self._connection.commit()

    def _select_command(self, column: str, value: str) -> DiscoveryCommand | None:
        if column not in {"command_id", "execution_id"}:
            raise ValueError("unsupported discovery command lookup")
        try:
            row = self._connection.execute(
                f"SELECT * FROM discovery_command_history WHERE {column} = ?", (value,)
            ).fetchone()
        except sqlite3.Error as error:
            raise DiscoveryCommandHistoryError("discovery command query failed") from error
        return None if row is None else self._command_from_row(row)

    def _select_receipt(self, command_id: str) -> DiscoveryCommandReceipt | None:
        try:
            row = self._connection.execute(
                "SELECT * FROM discovery_command_receipts WHERE command_id = ?", (command_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise DiscoveryCommandReceiptError("discovery command receipt query failed") from error
        return None if row is None else self._receipt_from_row(row)

    @staticmethod
    def _required(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{name} must be non-empty text")
        return value.strip()

    def get_command(self, command_id: str) -> DiscoveryCommand | None:
        return self._select_command("command_id", self._required(command_id, "command_id"))

    def get_by_execution(self, discovery_execution_id: str) -> DiscoveryCommand | None:
        return self._select_command(
            "execution_id", self._required(discovery_execution_id, "discovery_execution_id")
        )

    def exists(self, command_id: str) -> bool:
        return self.get_command(command_id) is not None

    def validate_replay(
        self, command_id: str, canonical_payload_fingerprint: str
    ) -> DiscoveryCommandReceipt | None:
        command_id = self._required(command_id, "command_id")
        fingerprint = self._required(canonical_payload_fingerprint, "canonical_payload_fingerprint")
        receipt = self._select_receipt(command_id)
        command = self._select_command("command_id", command_id)
        if receipt is None and command is None:
            return None
        if receipt is None or command is None:
            raise MalformedDiscoveryCommandPersistenceError("command and receipt must exist together")
        if (
            receipt.execution_id != command.discovery_execution_id
            or receipt.canonical_payload_fingerprint != command.fingerprint
        ):
            raise MalformedDiscoveryCommandPersistenceError("command and receipt persistence disagree")
        if receipt.canonical_payload_fingerprint != fingerprint:
            raise DiscoveryReplayConflict("discovery command payload conflicts with committed receipt")
        return receipt

    def close(self) -> None:
        if self._owns_connection:
            self._connection.close()

    def __enter__(self) -> "SQLiteDiscoveryCommandRepository":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.close()
