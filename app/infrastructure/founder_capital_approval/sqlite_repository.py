"""Append-only SQLite persistence for Founder Capital Approval."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.founder_capital_approval import (
    FOUNDER_CAPITAL_APPROVAL_RECEIPT_SCHEMA_VERSION,
    ApproveFounderCapitalCommand,
    FounderCapitalApprovalPublication,
    FounderCapitalApprovalReceipt,
    FounderCapitalApprovalReplayConflictError,
)
from app.domain.capital import (
    CAPITAL_GATE_POLICY_NAME,
    CAPITAL_GATE_POLICY_VERSION,
    FOUNDER_CAPITAL_APPROVAL_SCHEMA_VERSION,
    CapitalGateState,
    FounderCapitalApproval,
)
from app.domain.decision_engine import OpportunityIdentity
from app.infrastructure.capital_gate import SQLiteCapitalGateRepository


HISTORY_TABLE = "founder_capital_approval_history"
RECEIPT_TABLE = "founder_capital_approval_receipts"


class FounderCapitalApprovalPersistenceError(RuntimeError):
    pass


class FounderCapitalApprovalHistoryError(FounderCapitalApprovalPersistenceError):
    pass


class FounderCapitalApprovalReceiptError(FounderCapitalApprovalPersistenceError):
    pass


class FounderCapitalApprovalCommitError(FounderCapitalApprovalPersistenceError):
    pass


class MalformedFounderCapitalApprovalPersistenceError(
    FounderCapitalApprovalPersistenceError
):
    pass


class UnsupportedFounderCapitalApprovalVersionError(
    MalformedFounderCapitalApprovalPersistenceError
):
    pass


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _integrity(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return result


def _decimal(value: object, name: str) -> Decimal:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be canonical Decimal text")
    try:
        result = Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{name} must be Decimal text") from error
    if format(result, "f") != value:
        raise ValueError(f"{name} must use canonical Decimal text")
    return result


def _exact(value: object, keys: set[str], name: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{name} has unsupported fields")
    return value


_PAYLOAD_KEYS = {
    "approval_id",
    "opportunity_identity",
    "capital_gate_id",
    "capital_gate_policy_name",
    "capital_gate_policy_version",
    "capital_requirement_id",
    "deployable_capital_snapshot_id",
    "intended_order_quantity_id",
    "capital_gate_evaluated_at",
    "approved_capital",
    "currency",
    "founder_id",
    "requested_at",
    "approved_at",
    "admitted_at",
    "schema_version",
}


def _payload(value: FounderCapitalApproval) -> str:
    return _dump(
        {
            "approval_id": value.approval_id,
            "opportunity_identity": {
                "opportunity_id": value.opportunity_identity.opportunity_id,
                "discovery_reference": value.opportunity_identity.discovery_reference,
            },
            "capital_gate_id": value.capital_gate_id,
            "capital_gate_policy_name": value.capital_gate_policy_name,
            "capital_gate_policy_version": value.capital_gate_policy_version,
            "capital_requirement_id": value.capital_requirement_id,
            "deployable_capital_snapshot_id": value.deployable_capital_snapshot_id,
            "intended_order_quantity_id": value.intended_order_quantity_id,
            "capital_gate_evaluated_at": value.capital_gate_evaluated_at.isoformat(),
            "approved_capital": format(value.approved_capital, "f"),
            "currency": value.currency,
            "founder_id": value.founder_id,
            "requested_at": value.requested_at.isoformat(),
            "approved_at": value.approved_at.isoformat(),
            "admitted_at": value.admitted_at.isoformat(),
            "schema_version": value.schema_version,
        }
    )


class SQLiteFounderCapitalApprovalRepository:
    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        if (database_path is None) == (connection is None):
            raise ValueError("provide exactly one database_path or connection")
        self._owns_connection = connection is None
        if connection is None:
            path = Path(database_path)  # type: ignore[arg-type]
            path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self._connection = connection
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._gates = SQLiteCapitalGateRepository(connection=self._connection)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {HISTORY_TABLE}(
                    approval_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    discovery_reference TEXT NOT NULL,
                    capital_gate_id TEXT NOT NULL,
                    capital_requirement_id TEXT NOT NULL,
                    deployable_capital_snapshot_id TEXT NOT NULL,
                    founder_id TEXT NOT NULL,
                    approved_capital TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(capital_gate_id) REFERENCES capital_gate_history(gate_id)
                )"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE}(
                    command_id TEXT PRIMARY KEY,
                    approval_id TEXT NOT NULL,
                    command_fingerprint TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(approval_id) REFERENCES {HISTORY_TABLE}(approval_id)
                )"""
            )
            for table in (HISTORY_TABLE, RECEIPT_TABLE):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END"""
                    )

    def get_capital_gate(self, gate_id: str):
        return self._gates.get_gate(gate_id)

    def _history_row(self, approval_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE approval_id=?", (approval_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise FounderCapitalApprovalHistoryError(
                "Founder Capital Approval history query failed"
            ) from error

    def _load_approval(self, row) -> FounderCapitalApproval:
        try:
            if row["schema_version"] != FOUNDER_CAPITAL_APPROVAL_SCHEMA_VERSION:
                raise UnsupportedFounderCapitalApprovalVersionError(
                    "unsupported Founder Capital Approval version"
                )
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _integrity(encoded) != row["integrity_fingerprint"]:
                raise ValueError("Founder Capital Approval integrity fingerprint mismatch")
            data = _exact(json.loads(encoded), _PAYLOAD_KEYS, "approval payload")
            if data["schema_version"] != FOUNDER_CAPITAL_APPROVAL_SCHEMA_VERSION:
                raise UnsupportedFounderCapitalApprovalVersionError(
                    "unsupported approval payload version"
                )
            opportunity = _exact(
                data["opportunity_identity"],
                {"opportunity_id", "discovery_reference"},
                "Opportunity identity",
            )
            value = FounderCapitalApproval(
                approval_id=data["approval_id"],
                opportunity_identity=OpportunityIdentity(
                    opportunity["opportunity_id"], opportunity["discovery_reference"]
                ),
                capital_gate_id=data["capital_gate_id"],
                capital_gate_policy_name=data["capital_gate_policy_name"],
                capital_gate_policy_version=data["capital_gate_policy_version"],
                capital_requirement_id=data["capital_requirement_id"],
                deployable_capital_snapshot_id=data["deployable_capital_snapshot_id"],
                intended_order_quantity_id=data["intended_order_quantity_id"],
                capital_gate_evaluated_at=_datetime(
                    data["capital_gate_evaluated_at"], "capital_gate_evaluated_at"
                ),
                approved_capital=_decimal(data["approved_capital"], "approved_capital"),
                currency=data["currency"],
                founder_id=data["founder_id"],
                requested_at=_datetime(data["requested_at"], "requested_at"),
                approved_at=_datetime(data["approved_at"], "approved_at"),
                admitted_at=_datetime(data["admitted_at"], "admitted_at"),
                schema_version=data["schema_version"],
            )
            if (
                value.approval_id != row["approval_id"]
                or value.opportunity_identity.opportunity_id != row["opportunity_id"]
                or value.opportunity_identity.discovery_reference
                != row["discovery_reference"]
                or value.capital_gate_id != row["capital_gate_id"]
                or value.capital_requirement_id != row["capital_requirement_id"]
                or value.deployable_capital_snapshot_id
                != row["deployable_capital_snapshot_id"]
                or value.founder_id != row["founder_id"]
                or format(value.approved_capital, "f") != row["approved_capital"]
                or value.currency != row["currency"]
                or value.schema_version != row["schema_version"]
            ):
                raise ValueError("Founder Capital Approval columns differ from payload")
            self._validate_source(value)
            return value
        except UnsupportedFounderCapitalApprovalVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedFounderCapitalApprovalPersistenceError):
                raise
            raise MalformedFounderCapitalApprovalPersistenceError(
                "persisted Founder Capital Approval is malformed"
            ) from error

    def get_approval(self, approval_id: str):
        row = self._history_row(approval_id)
        return None if row is None else self._load_approval(row)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?", (command_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise FounderCapitalApprovalReceiptError(
                "Founder Capital Approval receipt query failed"
            ) from error

    def _load_receipt(self, row) -> FounderCapitalApprovalReceipt:
        try:
            if row["schema_version"] != FOUNDER_CAPITAL_APPROVAL_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedFounderCapitalApprovalVersionError(
                    "unsupported Founder Capital Approval receipt version"
                )
            value = FounderCapitalApprovalReceipt(
                command_id=row["command_id"],
                approval_id=row["approval_id"],
                command_fingerprint=row["command_fingerprint"],
                committed_at=_datetime(row["committed_at"], "committed_at"),
                schema_version=row["schema_version"],
            )
            if self.get_approval(value.approval_id) is None:
                raise ValueError("Founder Capital Approval receipt is orphaned")
            return value
        except UnsupportedFounderCapitalApprovalVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedFounderCapitalApprovalPersistenceError):
                raise
            raise MalformedFounderCapitalApprovalPersistenceError(
                "persisted Founder Capital Approval receipt is malformed"
            ) from error

    def get_receipt(self, command_id: str):
        row = self._receipt_row(command_id)
        return None if row is None else self._load_receipt(row)

    def validate_replay(self, command_id: str, fingerprint: str):
        receipt = self.get_receipt(command_id)
        if receipt is None:
            return None
        if receipt.command_fingerprint != fingerprint:
            raise FounderCapitalApprovalReplayConflictError(
                "Founder Capital Approval command payload conflicts"
            )
        approval = self.get_approval(receipt.approval_id)
        if approval is None:
            raise MalformedFounderCapitalApprovalPersistenceError(
                "Founder Capital Approval receipt is orphaned"
            )
        return FounderCapitalApprovalPublication(approval, receipt, True)

    def _validate_source(self, value: FounderCapitalApproval) -> None:
        gate = self.get_capital_gate(value.capital_gate_id)
        if gate is None:
            raise ValueError("Founder Capital Approval references missing Capital Gate")
        manifest = gate.source_manifest
        facts = gate.evaluated_facts
        if (
            gate.state is not CapitalGateState.PASS
            or gate.policy_name != CAPITAL_GATE_POLICY_NAME
            or gate.policy_version != CAPITAL_GATE_POLICY_VERSION
            or value.opportunity_identity != manifest.opportunity_identity
            or value.capital_gate_policy_name != gate.policy_name
            or value.capital_gate_policy_version != gate.policy_version
            or value.capital_requirement_id != manifest.capital_requirement_id
            or value.deployable_capital_snapshot_id
            != manifest.deployable_capital_snapshot_id
            or value.intended_order_quantity_id != manifest.intended_order_quantity_id
            or value.capital_gate_evaluated_at != gate.evaluated_at
            or value.approved_capital != facts.planned_acquisition_capital
            or value.approved_capital > facts.deployable_capital
            or value.currency != facts.requirement_currency
            or value.currency != facts.deployable_currency
        ):
            raise ValueError("Founder Capital Approval differs from exact Gate PASS")

    @staticmethod
    def _validate_write(command, approval, receipt) -> None:
        if not isinstance(command, ApproveFounderCapitalCommand):
            raise TypeError("command must be ApproveFounderCapitalCommand")
        if not isinstance(approval, FounderCapitalApproval):
            raise TypeError("approval must be FounderCapitalApproval")
        if not isinstance(receipt, FounderCapitalApprovalReceipt):
            raise TypeError("receipt must be FounderCapitalApprovalReceipt")
        if (
            receipt.command_id != command.command_id
            or receipt.approval_id != approval.approval_id
            or receipt.command_fingerprint != command.fingerprint
            or approval.capital_gate_id != command.capital_gate_id
            or approval.founder_id != command.founder_id
            or approval.approved_capital != command.approved_capital
            or approval.currency != command.currency
            or approval.requested_at != command.requested_at
            or approval.approved_at != command.approved_at
        ):
            raise FounderCapitalApprovalReplayConflictError(
                "command, Founder Capital Approval, and receipt differ"
            )

    def _rollback(self) -> None:
        if self._connection.in_transaction:
            self._connection.rollback()

    def _commit(self) -> None:
        self._connection.commit()

    def save_approval(self, command, approval, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            self._validate_write(command, approval, receipt)
            self._validate_source(approval)
            encoded = _payload(approval)
            try:
                self._connection.execute(
                    f"""INSERT INTO {HISTORY_TABLE}(
                        approval_id,opportunity_id,discovery_reference,capital_gate_id,
                        capital_requirement_id,deployable_capital_snapshot_id,founder_id,
                        approved_capital,currency,payload_json,integrity_fingerprint,
                        schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        approval.approval_id,
                        approval.opportunity_identity.opportunity_id,
                        approval.opportunity_identity.discovery_reference,
                        approval.capital_gate_id,
                        approval.capital_requirement_id,
                        approval.deployable_capital_snapshot_id,
                        approval.founder_id,
                        format(approval.approved_capital, "f"),
                        approval.currency,
                        encoded,
                        _integrity(encoded),
                        approval.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise FounderCapitalApprovalHistoryError(
                    "Founder Capital Approval insert failed"
                ) from error
            try:
                self._connection.execute(
                    f"""INSERT INTO {RECEIPT_TABLE}(
                        command_id,approval_id,command_fingerprint,committed_at,
                        schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?)""",
                    (
                        receipt.command_id,
                        receipt.approval_id,
                        receipt.command_fingerprint,
                        receipt.committed_at.isoformat(),
                        receipt.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise FounderCapitalApprovalReceiptError(
                    "Founder Capital Approval receipt insert failed"
                ) from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise FounderCapitalApprovalCommitError(
                    "Founder Capital Approval commit failed"
                ) from error
            return FounderCapitalApprovalPublication(approval, receipt, False)
        except Exception:
            self._rollback()
            raise

    def close(self) -> None:
        self._rollback()
        if self._owns_connection:
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


__all__ = [
    name
    for name in globals()
    if name.startswith(("Founder", "Malformed", "SQLite", "Unsupported"))
]
