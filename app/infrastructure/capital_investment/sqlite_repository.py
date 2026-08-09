"""Append-only SQLite persistence for Founder Capital investment facts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.capital_investment import (
    DEPLOYABLE_CAPITAL_RECEIPT_SCHEMA_VERSION,
    INTENDED_ORDER_QUANTITY_RECEIPT_SCHEMA_VERSION,
    AdmitDeployableCapitalSnapshotCommand,
    AdmitIntendedOrderQuantityCommand,
    CapitalInvestmentReplayConflictError,
    DeployableCapitalPublication,
    DeployableCapitalSnapshotReceipt,
    IntendedOrderQuantityPublication,
    IntendedOrderQuantityReceipt,
)
from app.domain.capital import (
    DEPLOYABLE_CAPITAL_SEMANTICS_VERSION,
    DEPLOYABLE_CAPITAL_SNAPSHOT_SCHEMA_VERSION,
    INTENDED_ORDER_QUANTITY_SCHEMA_VERSION,
    DeployableCapitalSnapshot,
    IntendedOrderQuantity,
)
from app.domain.decision_engine import OpportunityIdentity
from app.infrastructure.sourcing import SQLiteSourcingAuthorityRepository


INTENT_HISTORY_TABLE = "capital_investment_intent_history"
INTENT_RECEIPT_TABLE = "capital_investment_intent_receipts"
CAPITAL_HISTORY_TABLE = "deployable_capital_snapshot_history"
CAPITAL_RECEIPT_TABLE = "deployable_capital_snapshot_receipts"


class CapitalInvestmentPersistenceError(RuntimeError):
    pass


class CapitalInvestmentIntentHistoryError(CapitalInvestmentPersistenceError):
    pass


class CapitalInvestmentIntentReceiptError(CapitalInvestmentPersistenceError):
    pass


class DeployableCapitalSnapshotHistoryError(CapitalInvestmentPersistenceError):
    pass


class DeployableCapitalSnapshotReceiptError(CapitalInvestmentPersistenceError):
    pass


class CapitalInvestmentCommitError(CapitalInvestmentPersistenceError):
    pass


class MalformedCapitalInvestmentPersistenceError(CapitalInvestmentPersistenceError):
    pass


class UnsupportedCapitalInvestmentVersionError(MalformedCapitalInvestmentPersistenceError):
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


_OPPORTUNITY_KEYS = {"opportunity_id", "discovery_reference"}
_INTENT_KEYS = {
    "intent_id", "opportunity_identity", "sourcing_admission_id",
    "sourcing_admission_revision", "quote_id", "quote_revision", "quantity",
    "quantity_unit", "operator_id", "requested_at", "declared_at", "admitted_at",
    "schema_version",
}
_CAPITAL_KEYS = {
    "snapshot_id", "amount", "currency", "as_of", "operator_id", "requested_at",
    "admitted_at", "semantics_version", "schema_version",
}


def _opportunity(value: OpportunityIdentity) -> dict[str, str]:
    return {
        "opportunity_id": value.opportunity_id,
        "discovery_reference": value.discovery_reference,
    }


def _load_opportunity(value: object) -> OpportunityIdentity:
    data = _exact(value, _OPPORTUNITY_KEYS, "Opportunity identity")
    return OpportunityIdentity(data["opportunity_id"], data["discovery_reference"])


def _intent_payload(value: IntendedOrderQuantity) -> str:
    return _dump({
        "intent_id": value.intent_id,
        "opportunity_identity": _opportunity(value.opportunity_identity),
        "sourcing_admission_id": value.sourcing_admission_id,
        "sourcing_admission_revision": value.sourcing_admission_revision,
        "quote_id": value.quote_id,
        "quote_revision": value.quote_revision,
        "quantity": value.quantity,
        "quantity_unit": value.quantity_unit,
        "operator_id": value.operator_id,
        "requested_at": value.requested_at.isoformat(),
        "declared_at": value.declared_at.isoformat(),
        "admitted_at": value.admitted_at.isoformat(),
        "schema_version": value.schema_version,
    })


def _capital_payload(value: DeployableCapitalSnapshot) -> str:
    return _dump({
        "snapshot_id": value.snapshot_id,
        "amount": format(value.amount, "f"),
        "currency": value.currency,
        "as_of": value.as_of.isoformat(),
        "operator_id": value.operator_id,
        "requested_at": value.requested_at.isoformat(),
        "admitted_at": value.admitted_at.isoformat(),
        "semantics_version": value.semantics_version,
        "schema_version": value.schema_version,
    })


class SQLiteCapitalInvestmentFactsRepository:
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
        self._sourcing = SQLiteSourcingAuthorityRepository(connection=self._connection)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(f"""CREATE TABLE IF NOT EXISTS {INTENT_HISTORY_TABLE}(
                intent_id TEXT PRIMARY KEY,
                opportunity_id TEXT NOT NULL,
                discovery_reference TEXT NOT NULL,
                sourcing_admission_id TEXT NOT NULL,
                sourcing_admission_revision INTEGER NOT NULL,
                quote_id TEXT NOT NULL,
                quote_revision INTEGER NOT NULL,
                quantity INTEGER NOT NULL,
                quantity_unit TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                integrity_fingerprint TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL,
                FOREIGN KEY(sourcing_admission_id,sourcing_admission_revision)
                  REFERENCES founder_sourcing_admission_history(admission_id,revision)
            )""")
            self._connection.execute(f"""CREATE TABLE IF NOT EXISTS {INTENT_RECEIPT_TABLE}(
                command_id TEXT PRIMARY KEY,
                intent_id TEXT NOT NULL,
                command_fingerprint TEXT NOT NULL,
                committed_at TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL,
                FOREIGN KEY(intent_id) REFERENCES {INTENT_HISTORY_TABLE}(intent_id)
            )""")
            self._connection.execute(f"""CREATE TABLE IF NOT EXISTS {CAPITAL_HISTORY_TABLE}(
                snapshot_id TEXT PRIMARY KEY,
                amount TEXT NOT NULL,
                currency TEXT NOT NULL,
                as_of TEXT NOT NULL,
                semantics_version TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                integrity_fingerprint TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL
            )""")
            self._connection.execute(f"""CREATE TABLE IF NOT EXISTS {CAPITAL_RECEIPT_TABLE}(
                command_id TEXT PRIMARY KEY,
                snapshot_id TEXT NOT NULL,
                command_fingerprint TEXT NOT NULL,
                committed_at TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL,
                FOREIGN KEY(snapshot_id) REFERENCES {CAPITAL_HISTORY_TABLE}(snapshot_id)
            )""")
            for table in (
                INTENT_HISTORY_TABLE, INTENT_RECEIPT_TABLE,
                CAPITAL_HISTORY_TABLE, CAPITAL_RECEIPT_TABLE,
            ):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(f"""CREATE TRIGGER IF NOT EXISTS
                        trg_{table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END""")

    def get_sourcing_admission(self, admission_id: str, revision: int):
        return self._sourcing.get_admission_revision(admission_id, revision)

    def _row(self, table: str, column: str, identity: str, error_type):
        try:
            return self._connection.execute(
                f"SELECT * FROM {table} WHERE {column}=?", (identity,)
            ).fetchone()
        except sqlite3.Error as error:
            raise error_type(f"{table} query failed") from error

    def _load_intent(self, row) -> IntendedOrderQuantity:
        try:
            if row["schema_version"] != INTENDED_ORDER_QUANTITY_SCHEMA_VERSION:
                raise UnsupportedCapitalInvestmentVersionError("unsupported intent version")
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _integrity(encoded) != row["integrity_fingerprint"]:
                raise ValueError("intent integrity fingerprint mismatch")
            data = _exact(json.loads(encoded), _INTENT_KEYS, "Intended Order Quantity payload")
            intent = IntendedOrderQuantity(
                intent_id=data["intent_id"],
                opportunity_identity=_load_opportunity(data["opportunity_identity"]),
                sourcing_admission_id=data["sourcing_admission_id"],
                sourcing_admission_revision=data["sourcing_admission_revision"],
                quote_id=data["quote_id"],
                quote_revision=data["quote_revision"],
                quantity=data["quantity"],
                quantity_unit=data["quantity_unit"],
                operator_id=data["operator_id"],
                requested_at=_datetime(data["requested_at"], "requested_at"),
                declared_at=_datetime(data["declared_at"], "declared_at"),
                admitted_at=_datetime(data["admitted_at"], "admitted_at"),
                schema_version=data["schema_version"],
            )
            if (
                intent.intent_id != row["intent_id"]
                or intent.opportunity_identity.opportunity_id != row["opportunity_id"]
                or intent.opportunity_identity.discovery_reference != row["discovery_reference"]
                or intent.sourcing_admission_id != row["sourcing_admission_id"]
                or intent.sourcing_admission_revision != row["sourcing_admission_revision"]
                or intent.quote_id != row["quote_id"]
                or intent.quote_revision != row["quote_revision"]
                or intent.quantity != row["quantity"]
                or intent.quantity_unit != row["quantity_unit"]
                or intent.schema_version != row["schema_version"]
            ):
                raise ValueError("intent columns differ from payload")
            self._validate_intent_source(intent)
            return intent
        except UnsupportedCapitalInvestmentVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedCapitalInvestmentPersistenceError):
                raise
            raise MalformedCapitalInvestmentPersistenceError(
                "persisted Intended Order Quantity is malformed"
            ) from error

    def _load_capital(self, row) -> DeployableCapitalSnapshot:
        try:
            if row["schema_version"] != DEPLOYABLE_CAPITAL_SNAPSHOT_SCHEMA_VERSION:
                raise UnsupportedCapitalInvestmentVersionError("unsupported capital version")
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _integrity(encoded) != row["integrity_fingerprint"]:
                raise ValueError("capital integrity fingerprint mismatch")
            data = _exact(json.loads(encoded), _CAPITAL_KEYS, "Deployable Capital payload")
            snapshot = DeployableCapitalSnapshot(
                snapshot_id=data["snapshot_id"],
                amount=_decimal(data["amount"], "amount"),
                currency=data["currency"],
                as_of=_datetime(data["as_of"], "as_of"),
                operator_id=data["operator_id"],
                requested_at=_datetime(data["requested_at"], "requested_at"),
                admitted_at=_datetime(data["admitted_at"], "admitted_at"),
                semantics_version=data["semantics_version"],
                schema_version=data["schema_version"],
            )
            if (
                snapshot.snapshot_id != row["snapshot_id"]
                or format(snapshot.amount, "f") != row["amount"]
                or snapshot.currency != row["currency"]
                or snapshot.as_of.isoformat() != row["as_of"]
                or snapshot.semantics_version != row["semantics_version"]
                or snapshot.schema_version != row["schema_version"]
            ):
                raise ValueError("capital columns differ from payload")
            return snapshot
        except UnsupportedCapitalInvestmentVersionError:
            raise
        except Exception as error:
            raise MalformedCapitalInvestmentPersistenceError(
                "persisted Deployable Capital snapshot is malformed"
            ) from error

    def _validate_intent_source(self, intent: IntendedOrderQuantity) -> None:
        admission = self.get_sourcing_admission(
            intent.sourcing_admission_id, intent.sourcing_admission_revision
        )
        if admission is None:
            raise ValueError("intent references missing Sourcing Admission")
        quote = admission.quote_revision
        if (
            admission.selling_product_lineage.opportunity_identity != intent.opportunity_identity
            or admission.admission_id != intent.sourcing_admission_id
            or admission.revision != intent.sourcing_admission_revision
            or quote.quote_id != intent.quote_id
            or quote.revision != intent.quote_revision
        ):
            raise ValueError("intent Sourcing lineage differs")

    def get_intent(self, intent_id: str):
        row = self._row(INTENT_HISTORY_TABLE, "intent_id", intent_id, CapitalInvestmentIntentHistoryError)
        return None if row is None else self._load_intent(row)

    def get_deployable_capital_snapshot(self, snapshot_id: str):
        row = self._row(CAPITAL_HISTORY_TABLE, "snapshot_id", snapshot_id, DeployableCapitalSnapshotHistoryError)
        return None if row is None else self._load_capital(row)

    def _load_intent_receipt(self, row) -> IntendedOrderQuantityReceipt:
        try:
            if row["schema_version"] != INTENDED_ORDER_QUANTITY_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedCapitalInvestmentVersionError("unsupported intent receipt version")
            receipt = IntendedOrderQuantityReceipt(
                row["command_id"], row["intent_id"], row["command_fingerprint"],
                _datetime(row["committed_at"], "committed_at"), row["schema_version"],
            )
            if self.get_intent(receipt.intent_id) is None:
                raise ValueError("intent receipt references missing intent")
            return receipt
        except UnsupportedCapitalInvestmentVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedCapitalInvestmentPersistenceError):
                raise
            raise MalformedCapitalInvestmentPersistenceError(
                "persisted Intended Order Quantity receipt is malformed"
            ) from error

    def _load_capital_receipt(self, row) -> DeployableCapitalSnapshotReceipt:
        try:
            if row["schema_version"] != DEPLOYABLE_CAPITAL_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedCapitalInvestmentVersionError("unsupported capital receipt version")
            receipt = DeployableCapitalSnapshotReceipt(
                row["command_id"], row["snapshot_id"], row["command_fingerprint"],
                _datetime(row["committed_at"], "committed_at"), row["schema_version"],
            )
            if self.get_deployable_capital_snapshot(receipt.snapshot_id) is None:
                raise ValueError("capital receipt references missing snapshot")
            return receipt
        except UnsupportedCapitalInvestmentVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedCapitalInvestmentPersistenceError):
                raise
            raise MalformedCapitalInvestmentPersistenceError(
                "persisted Deployable Capital receipt is malformed"
            ) from error

    def get_intent_receipt(self, command_id: str):
        row = self._row(INTENT_RECEIPT_TABLE, "command_id", command_id, CapitalInvestmentIntentReceiptError)
        return None if row is None else self._load_intent_receipt(row)

    def get_deployable_capital_receipt(self, command_id: str):
        row = self._row(CAPITAL_RECEIPT_TABLE, "command_id", command_id, DeployableCapitalSnapshotReceiptError)
        return None if row is None else self._load_capital_receipt(row)

    def validate_intent_replay(self, command_id: str, fingerprint: str):
        receipt = self.get_intent_receipt(command_id)
        if receipt is None:
            return None
        if receipt.command_fingerprint != fingerprint:
            raise CapitalInvestmentReplayConflictError("Intended Order Quantity payload conflicts")
        intent = self.get_intent(receipt.intent_id)
        if intent is None:
            raise MalformedCapitalInvestmentPersistenceError("intent receipt is orphaned")
        return IntendedOrderQuantityPublication(intent, receipt, True)

    def validate_capital_replay(self, command_id: str, fingerprint: str):
        receipt = self.get_deployable_capital_receipt(command_id)
        if receipt is None:
            return None
        if receipt.command_fingerprint != fingerprint:
            raise CapitalInvestmentReplayConflictError("Deployable Capital payload conflicts")
        snapshot = self.get_deployable_capital_snapshot(receipt.snapshot_id)
        if snapshot is None:
            raise MalformedCapitalInvestmentPersistenceError("capital receipt is orphaned")
        return DeployableCapitalPublication(snapshot, receipt, True)

    @staticmethod
    def _validate_intent_write(command, intent, receipt) -> None:
        if not isinstance(command, AdmitIntendedOrderQuantityCommand):
            raise TypeError("command must be AdmitIntendedOrderQuantityCommand")
        if not isinstance(intent, IntendedOrderQuantity):
            raise TypeError("intent must be IntendedOrderQuantity")
        if not isinstance(receipt, IntendedOrderQuantityReceipt):
            raise TypeError("receipt must be IntendedOrderQuantityReceipt")
        if (
            receipt.command_id != command.command_id
            or receipt.intent_id != intent.intent_id
            or receipt.command_fingerprint != command.fingerprint
            or intent.opportunity_identity != command.opportunity_identity
            or intent.sourcing_admission_id != command.sourcing_admission_id
            or intent.sourcing_admission_revision != command.sourcing_admission_revision
            or intent.quote_id != command.quote_id
            or intent.quote_revision != command.quote_revision
            or intent.quantity != command.quantity
            or intent.quantity_unit != command.quantity_unit
            or intent.operator_id != command.operator_id
            or intent.requested_at != command.requested_at
            or intent.declared_at != command.declared_at
        ):
            raise CapitalInvestmentReplayConflictError("command, intent, and receipt differ")

    @staticmethod
    def _validate_capital_write(command, snapshot, receipt) -> None:
        if not isinstance(command, AdmitDeployableCapitalSnapshotCommand):
            raise TypeError("command must be AdmitDeployableCapitalSnapshotCommand")
        if not isinstance(snapshot, DeployableCapitalSnapshot):
            raise TypeError("snapshot must be DeployableCapitalSnapshot")
        if not isinstance(receipt, DeployableCapitalSnapshotReceipt):
            raise TypeError("receipt must be DeployableCapitalSnapshotReceipt")
        if (
            receipt.command_id != command.command_id
            or receipt.snapshot_id != snapshot.snapshot_id
            or receipt.command_fingerprint != command.fingerprint
            or snapshot.amount != command.amount
            or snapshot.currency != command.currency
            or snapshot.as_of != command.as_of
            or snapshot.operator_id != command.operator_id
            or snapshot.requested_at != command.requested_at
        ):
            raise CapitalInvestmentReplayConflictError("command, snapshot, and receipt differ")

    def _rollback(self) -> None:
        if self._connection.in_transaction:
            self._connection.rollback()

    def _commit(self) -> None:
        self._connection.commit()

    def save_intent(self, command, intent, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_intent_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            self._validate_intent_write(command, intent, receipt)
            self._validate_intent_source(intent)
            encoded = _intent_payload(intent)
            try:
                self._connection.execute(f"""INSERT INTO {INTENT_HISTORY_TABLE}(
                    intent_id,opportunity_id,discovery_reference,sourcing_admission_id,
                    sourcing_admission_revision,quote_id,quote_revision,quantity,
                    quantity_unit,payload_json,integrity_fingerprint,schema_version,inserted_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    intent.intent_id, intent.opportunity_identity.opportunity_id,
                    intent.opportunity_identity.discovery_reference,
                    intent.sourcing_admission_id, intent.sourcing_admission_revision,
                    intent.quote_id, intent.quote_revision, intent.quantity,
                    intent.quantity_unit, encoded, _integrity(encoded), intent.schema_version,
                    receipt.committed_at.isoformat(),
                ))
            except sqlite3.Error as error:
                raise CapitalInvestmentIntentHistoryError("intent insert failed") from error
            try:
                self._connection.execute(f"""INSERT INTO {INTENT_RECEIPT_TABLE}(
                    command_id,intent_id,command_fingerprint,committed_at,schema_version,inserted_at
                ) VALUES(?,?,?,?,?,?)""", (
                    receipt.command_id, receipt.intent_id, receipt.command_fingerprint,
                    receipt.committed_at.isoformat(), receipt.schema_version,
                    receipt.committed_at.isoformat(),
                ))
            except sqlite3.Error as error:
                raise CapitalInvestmentIntentReceiptError("intent receipt insert failed") from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise CapitalInvestmentCommitError("intent commit failed") from error
            return IntendedOrderQuantityPublication(intent, receipt, False)
        except (CapitalInvestmentReplayConflictError, CapitalInvestmentPersistenceError):
            self._rollback()
            raise
        except Exception:
            self._rollback()
            raise

    def save_deployable_capital(self, command, snapshot, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_capital_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            self._validate_capital_write(command, snapshot, receipt)
            encoded = _capital_payload(snapshot)
            try:
                self._connection.execute(f"""INSERT INTO {CAPITAL_HISTORY_TABLE}(
                    snapshot_id,amount,currency,as_of,semantics_version,payload_json,
                    integrity_fingerprint,schema_version,inserted_at
                ) VALUES(?,?,?,?,?,?,?,?,?)""", (
                    snapshot.snapshot_id, format(snapshot.amount, "f"), snapshot.currency,
                    snapshot.as_of.isoformat(), snapshot.semantics_version, encoded,
                    _integrity(encoded), snapshot.schema_version, receipt.committed_at.isoformat(),
                ))
            except sqlite3.Error as error:
                raise DeployableCapitalSnapshotHistoryError("capital snapshot insert failed") from error
            try:
                self._connection.execute(f"""INSERT INTO {CAPITAL_RECEIPT_TABLE}(
                    command_id,snapshot_id,command_fingerprint,committed_at,schema_version,inserted_at
                ) VALUES(?,?,?,?,?,?)""", (
                    receipt.command_id, receipt.snapshot_id, receipt.command_fingerprint,
                    receipt.committed_at.isoformat(), receipt.schema_version,
                    receipt.committed_at.isoformat(),
                ))
            except sqlite3.Error as error:
                raise DeployableCapitalSnapshotReceiptError("capital receipt insert failed") from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise CapitalInvestmentCommitError("capital snapshot commit failed") from error
            return DeployableCapitalPublication(snapshot, receipt, False)
        except (CapitalInvestmentReplayConflictError, CapitalInvestmentPersistenceError):
            self._rollback()
            raise
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
    "CAPITAL_HISTORY_TABLE", "CAPITAL_RECEIPT_TABLE",
    "CapitalInvestmentCommitError", "CapitalInvestmentIntentHistoryError",
    "CapitalInvestmentIntentReceiptError", "CapitalInvestmentPersistenceError",
    "DeployableCapitalSnapshotHistoryError", "DeployableCapitalSnapshotReceiptError",
    "INTENT_HISTORY_TABLE", "INTENT_RECEIPT_TABLE",
    "MalformedCapitalInvestmentPersistenceError",
    "SQLiteCapitalInvestmentFactsRepository",
    "UnsupportedCapitalInvestmentVersionError",
]
