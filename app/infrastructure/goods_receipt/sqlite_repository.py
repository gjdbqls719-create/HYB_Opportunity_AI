"""Append-only SQLite persistence for physical Goods Receipt events."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.goods_receipt import (
    GOODS_RECEIPT_RECEIPT_SCHEMA_VERSION,
    AdmitGoodsReceiptCommand,
    GoodsReceiptCommandReceipt,
    GoodsReceiptCumulativeQuantityConflictError,
    GoodsReceiptPublication,
    GoodsReceiptReplayConflictError,
    GoodsReceiptSourceLineageError,
    goods_receipt_manifest_from_purchase,
)
from app.domain.capital import (
    GOODS_RECEIPT_EVIDENCE_SCHEMA_VERSION,
    GOODS_RECEIPT_RECORD_SCHEMA_VERSION,
    GOODS_RECEIPT_SOURCE_MANIFEST_SCHEMA_VERSION,
    GoodsReceiptEvidenceReference,
    GoodsReceiptRecord,
    GoodsReceiptSourceManifest,
)
from app.domain.decision_engine import OpportunityIdentity
from app.infrastructure.purchase_execution import SQLitePurchaseExecutionRepository


HISTORY_TABLE = "goods_receipt_record_history"
RECEIPT_TABLE = "goods_receipt_record_receipts"
PURCHASE_INDEX = "ix_goods_receipt_record_purchase_execution"
OPPORTUNITY_INDEX = "ix_goods_receipt_record_opportunity"


class GoodsReceiptPersistenceError(RuntimeError):
    pass


class GoodsReceiptHistoryError(GoodsReceiptPersistenceError):
    pass


class GoodsReceiptReceiptError(GoodsReceiptPersistenceError):
    pass


class GoodsReceiptCommitError(GoodsReceiptPersistenceError):
    pass


class MalformedGoodsReceiptPersistenceError(GoodsReceiptPersistenceError):
    pass


class UnsupportedGoodsReceiptVersionError(MalformedGoodsReceiptPersistenceError):
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


def _exact(value: object, keys: set[str], name: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{name} has unsupported fields")
    return value


_MANIFEST_KEYS = {
    "opportunity_identity",
    "purchase_execution_record_id",
    "real_money_execution_intent_id",
    "sourcing_admission_id",
    "sourcing_admission_revision",
    "supplier_id",
    "source_platform",
    "external_supplier_reference",
    "sourcing_product_id",
    "external_product_reference",
    "option_reference",
    "sku_reference",
    "quote_id",
    "quote_revision",
    "executed_quantity",
    "executed_quantity_unit",
    "external_order_reference",
    "founder_id",
    "purchase_executed_at",
    "purchase_policy_name",
    "purchase_policy_version",
    "purchase_record_schema_version",
    "schema_version",
}
_EVIDENCE_KEYS = {
    "reference",
    "observed_at",
    "operator_id",
    "collection_method",
    "schema_version",
}
_PAYLOAD_KEYS = {
    "record_id",
    "source_manifest",
    "received_quantity",
    "quantity_unit",
    "sellable_quantity",
    "damaged_quantity",
    "evidence_references",
    "delivery_reference",
    "operator_id",
    "received_at",
    "inspected_at",
    "requested_at",
    "admitted_at",
    "policy_name",
    "policy_version",
    "schema_version",
}


def _manifest(value: GoodsReceiptSourceManifest) -> dict[str, object]:
    return {
        "opportunity_identity": {
            "opportunity_id": value.opportunity_identity.opportunity_id,
            "discovery_reference": value.opportunity_identity.discovery_reference,
        },
        "purchase_execution_record_id": value.purchase_execution_record_id,
        "real_money_execution_intent_id": value.real_money_execution_intent_id,
        "sourcing_admission_id": value.sourcing_admission_id,
        "sourcing_admission_revision": value.sourcing_admission_revision,
        "supplier_id": value.supplier_id,
        "source_platform": value.source_platform,
        "external_supplier_reference": value.external_supplier_reference,
        "sourcing_product_id": value.sourcing_product_id,
        "external_product_reference": value.external_product_reference,
        "option_reference": value.option_reference,
        "sku_reference": value.sku_reference,
        "quote_id": value.quote_id,
        "quote_revision": value.quote_revision,
        "executed_quantity": value.executed_quantity,
        "executed_quantity_unit": value.executed_quantity_unit,
        "external_order_reference": value.external_order_reference,
        "founder_id": value.founder_id,
        "purchase_executed_at": value.purchase_executed_at.isoformat(),
        "purchase_policy_name": value.purchase_policy_name,
        "purchase_policy_version": value.purchase_policy_version,
        "purchase_record_schema_version": value.purchase_record_schema_version,
        "schema_version": value.schema_version,
    }


def _load_manifest(value: object) -> GoodsReceiptSourceManifest:
    data = _exact(value, _MANIFEST_KEYS, "Goods Receipt source manifest")
    if data["schema_version"] != GOODS_RECEIPT_SOURCE_MANIFEST_SCHEMA_VERSION:
        raise UnsupportedGoodsReceiptVersionError(
            "unsupported Goods Receipt source manifest version"
        )
    identity = _exact(
        data["opportunity_identity"],
        {"opportunity_id", "discovery_reference"},
        "Opportunity identity",
    )
    return GoodsReceiptSourceManifest(
        opportunity_identity=OpportunityIdentity(
            identity["opportunity_id"], identity["discovery_reference"]
        ),
        purchase_execution_record_id=data["purchase_execution_record_id"],
        real_money_execution_intent_id=data["real_money_execution_intent_id"],
        sourcing_admission_id=data["sourcing_admission_id"],
        sourcing_admission_revision=data["sourcing_admission_revision"],
        supplier_id=data["supplier_id"],
        source_platform=data["source_platform"],
        external_supplier_reference=data["external_supplier_reference"],
        sourcing_product_id=data["sourcing_product_id"],
        external_product_reference=data["external_product_reference"],
        option_reference=data["option_reference"],
        sku_reference=data["sku_reference"],
        quote_id=data["quote_id"],
        quote_revision=data["quote_revision"],
        executed_quantity=data["executed_quantity"],
        executed_quantity_unit=data["executed_quantity_unit"],
        external_order_reference=data["external_order_reference"],
        founder_id=data["founder_id"],
        purchase_executed_at=_datetime(data["purchase_executed_at"], "purchase_executed_at"),
        purchase_policy_name=data["purchase_policy_name"],
        purchase_policy_version=data["purchase_policy_version"],
        purchase_record_schema_version=data["purchase_record_schema_version"],
        schema_version=data["schema_version"],
    )


def _evidence(value: GoodsReceiptEvidenceReference) -> dict[str, object]:
    return {
        "reference": value.reference,
        "observed_at": value.observed_at.isoformat(),
        "operator_id": value.operator_id,
        "collection_method": value.collection_method,
        "schema_version": value.schema_version,
    }


def _load_evidence(value: object) -> GoodsReceiptEvidenceReference:
    data = _exact(value, _EVIDENCE_KEYS, "Goods Receipt evidence")
    if data["schema_version"] != GOODS_RECEIPT_EVIDENCE_SCHEMA_VERSION:
        raise UnsupportedGoodsReceiptVersionError(
            "unsupported Goods Receipt evidence version"
        )
    return GoodsReceiptEvidenceReference(
        reference=data["reference"],
        observed_at=_datetime(data["observed_at"], "evidence observed_at"),
        operator_id=data["operator_id"],
        collection_method=data["collection_method"],
        schema_version=data["schema_version"],
    )


def _payload(value: GoodsReceiptRecord) -> str:
    return _dump(
        {
            "record_id": value.record_id,
            "source_manifest": _manifest(value.source_manifest),
            "received_quantity": value.received_quantity,
            "quantity_unit": value.quantity_unit,
            "sellable_quantity": value.sellable_quantity,
            "damaged_quantity": value.damaged_quantity,
            "evidence_references": [_evidence(item) for item in value.evidence_references],
            "delivery_reference": value.delivery_reference,
            "operator_id": value.operator_id,
            "received_at": value.received_at.isoformat(),
            "inspected_at": value.inspected_at.isoformat(),
            "requested_at": value.requested_at.isoformat(),
            "admitted_at": value.admitted_at.isoformat(),
            "policy_name": value.policy_name,
            "policy_version": value.policy_version,
            "schema_version": value.schema_version,
        }
    )


class SQLiteGoodsReceiptRepository:
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
        self._purchase = SQLitePurchaseExecutionRepository(connection=self._connection)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {HISTORY_TABLE}(
                    record_id TEXT PRIMARY KEY,
                    purchase_execution_record_id TEXT NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    discovery_reference TEXT NOT NULL,
                    received_quantity INTEGER NOT NULL CHECK(received_quantity > 0),
                    policy_name TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(purchase_execution_record_id)
                      REFERENCES purchase_execution_record_history(record_id)
                )"""
            )
            self._connection.execute(
                f"""CREATE INDEX IF NOT EXISTS {PURCHASE_INDEX}
                ON {HISTORY_TABLE}(purchase_execution_record_id)"""
            )
            self._connection.execute(
                f"""CREATE INDEX IF NOT EXISTS {OPPORTUNITY_INDEX}
                ON {HISTORY_TABLE}(opportunity_id)"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE}(
                    command_id TEXT PRIMARY KEY,
                    record_id TEXT NOT NULL,
                    command_fingerprint TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(record_id) REFERENCES {HISTORY_TABLE}(record_id)
                )"""
            )
            for table in (HISTORY_TABLE, RECEIPT_TABLE):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END"""
                    )

    def get_purchase_execution_record(self, record_id: str):
        return self._purchase.get_record(record_id)

    def get_opportunity_identity(self, opportunity_id: str):
        try:
            row = self._connection.execute(
                """SELECT opportunity_id,discovery_reference
                FROM opportunity_lifecycles WHERE opportunity_id=?""",
                (opportunity_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise GoodsReceiptHistoryError(
                "Goods Receipt Opportunity query failed"
            ) from error
        if row is None:
            return None
        return OpportunityIdentity(row["opportunity_id"], row["discovery_reference"])

    def _history_row(self, record_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE record_id=?", (record_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise GoodsReceiptHistoryError("Goods Receipt history query failed") from error

    def _purchase_rows(self, purchase_execution_record_id: str):
        try:
            return self._connection.execute(
                f"""SELECT * FROM {HISTORY_TABLE}
                WHERE purchase_execution_record_id=? ORDER BY inserted_at,record_id""",
                (purchase_execution_record_id,),
            ).fetchall()
        except sqlite3.Error as error:
            raise GoodsReceiptHistoryError("Goods Receipt cumulative query failed") from error

    def _opportunity_rows(self, opportunity_id: str):
        try:
            return self._connection.execute(
                f"""SELECT * FROM {HISTORY_TABLE}
                WHERE opportunity_id=? ORDER BY inserted_at,record_id""",
                (opportunity_id,),
            ).fetchall()
        except sqlite3.Error as error:
            raise GoodsReceiptHistoryError(
                "Goods Receipt Opportunity history query failed"
            ) from error

    def _load_record(self, row) -> GoodsReceiptRecord:
        try:
            if row["schema_version"] != GOODS_RECEIPT_RECORD_SCHEMA_VERSION:
                raise UnsupportedGoodsReceiptVersionError(
                    "unsupported Goods Receipt Record version"
                )
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _integrity(encoded) != row["integrity_fingerprint"]:
                raise ValueError("Goods Receipt integrity mismatch")
            data = _exact(json.loads(encoded), _PAYLOAD_KEYS, "Goods Receipt payload")
            if data["schema_version"] != GOODS_RECEIPT_RECORD_SCHEMA_VERSION:
                raise UnsupportedGoodsReceiptVersionError(
                    "unsupported Goods Receipt payload version"
                )
            manifest = _load_manifest(data["source_manifest"])
            evidence_data = data["evidence_references"]
            if not isinstance(evidence_data, list):
                raise ValueError("evidence_references must be a list")
            record = GoodsReceiptRecord(
                record_id=data["record_id"],
                source_manifest=manifest,
                received_quantity=data["received_quantity"],
                quantity_unit=data["quantity_unit"],
                sellable_quantity=data["sellable_quantity"],
                damaged_quantity=data["damaged_quantity"],
                evidence_references=tuple(_load_evidence(item) for item in evidence_data),
                delivery_reference=data["delivery_reference"],
                operator_id=data["operator_id"],
                received_at=_datetime(data["received_at"], "received_at"),
                inspected_at=_datetime(data["inspected_at"], "inspected_at"),
                requested_at=_datetime(data["requested_at"], "requested_at"),
                admitted_at=_datetime(data["admitted_at"], "admitted_at"),
                policy_name=data["policy_name"],
                policy_version=data["policy_version"],
                schema_version=data["schema_version"],
            )
            if (
                record.record_id != row["record_id"]
                or manifest.purchase_execution_record_id
                != row["purchase_execution_record_id"]
                or manifest.opportunity_identity.opportunity_id != row["opportunity_id"]
                or manifest.opportunity_identity.discovery_reference
                != row["discovery_reference"]
                or record.received_quantity != row["received_quantity"]
                or record.policy_name != row["policy_name"]
                or record.policy_version != row["policy_version"]
                or record.schema_version != row["schema_version"]
            ):
                raise ValueError("Goods Receipt columns differ from payload")
            self._validate_source(record)
            return record
        except UnsupportedGoodsReceiptVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedGoodsReceiptPersistenceError):
                raise
            raise MalformedGoodsReceiptPersistenceError(
                "persisted Goods Receipt Record is malformed"
            ) from error

    def get_record(self, record_id: str):
        row = self._history_row(record_id)
        return None if row is None else self._load_record(row)

    def get_records_for_purchase(self, purchase_execution_record_id: str):
        return tuple(self._load_record(row) for row in self._purchase_rows(purchase_execution_record_id))

    def list_goods_receipts_for_opportunity(self, opportunity_id: str):
        return tuple(self._load_record(row) for row in self._opportunity_rows(opportunity_id))

    def get_cumulative_received_quantity(self, purchase_execution_record_id: str) -> int:
        return sum(
            record.received_quantity
            for record in self.get_records_for_purchase(purchase_execution_record_id)
        )

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?", (command_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise GoodsReceiptReceiptError("Goods Receipt command receipt query failed") from error

    def _load_receipt(self, row) -> GoodsReceiptCommandReceipt:
        try:
            if row["schema_version"] != GOODS_RECEIPT_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedGoodsReceiptVersionError(
                    "unsupported Goods Receipt command receipt version"
                )
            receipt = GoodsReceiptCommandReceipt(
                command_id=row["command_id"],
                record_id=row["record_id"],
                command_fingerprint=row["command_fingerprint"],
                committed_at=_datetime(row["committed_at"], "committed_at"),
                schema_version=row["schema_version"],
            )
            if self.get_record(receipt.record_id) is None:
                raise ValueError("Goods Receipt command receipt is orphaned")
            return receipt
        except UnsupportedGoodsReceiptVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedGoodsReceiptPersistenceError):
                raise
            raise MalformedGoodsReceiptPersistenceError(
                "persisted Goods Receipt command receipt is malformed"
            ) from error

    def validate_replay(self, command_id: str, fingerprint: str):
        row = self._receipt_row(command_id)
        if row is None:
            return None
        receipt = self._load_receipt(row)
        if receipt.command_fingerprint != fingerprint:
            raise GoodsReceiptReplayConflictError("Goods Receipt command payload conflicts")
        record = self.get_record(receipt.record_id)
        if record is None:
            raise MalformedGoodsReceiptPersistenceError(
                "Goods Receipt command receipt is orphaned"
            )
        return GoodsReceiptPublication(record, receipt, True)

    def _validate_source(self, record: GoodsReceiptRecord) -> None:
        purchase = self.get_purchase_execution_record(
            record.source_manifest.purchase_execution_record_id
        )
        if purchase is None:
            raise GoodsReceiptSourceLineageError(
                "Goods Receipt references missing Purchase Execution Record"
            )
        if goods_receipt_manifest_from_purchase(purchase) != record.source_manifest:
            raise GoodsReceiptSourceLineageError(
                "Goods Receipt source differs from Purchase Execution Record"
            )

    @staticmethod
    def _validate_write(command, record, receipt) -> None:
        if not isinstance(command, AdmitGoodsReceiptCommand):
            raise TypeError("command must be AdmitGoodsReceiptCommand")
        if not isinstance(record, GoodsReceiptRecord):
            raise TypeError("record must be GoodsReceiptRecord")
        if not isinstance(receipt, GoodsReceiptCommandReceipt):
            raise TypeError("receipt must be GoodsReceiptCommandReceipt")
        source = record.source_manifest
        if (
            receipt.command_id != command.command_id
            or receipt.record_id != record.record_id
            or receipt.command_fingerprint != command.fingerprint
            or source.opportunity_identity.opportunity_id != command.opportunity_id
            or source.purchase_execution_record_id != command.purchase_execution_record_id
            or record.received_quantity != command.received_quantity
            or record.quantity_unit != command.quantity_unit
            or record.sellable_quantity != command.sellable_quantity
            or record.damaged_quantity != command.damaged_quantity
            or record.evidence_references != command.evidence_references
            or record.delivery_reference != command.delivery_reference
            or record.operator_id != command.operator_id
            or record.received_at != command.received_at
            or record.inspected_at != command.inspected_at
            or record.requested_at != command.requested_at
            or record.policy_name != command.policy_name
            or record.policy_version != command.policy_version
        ):
            raise GoodsReceiptReplayConflictError(
                "command, Goods Receipt Record, and command receipt differ"
            )

    def _insert_receipt(self, receipt: GoodsReceiptCommandReceipt) -> None:
        try:
            self._connection.execute(
                f"""INSERT INTO {RECEIPT_TABLE}(
                    command_id,record_id,command_fingerprint,committed_at,
                    schema_version,inserted_at
                ) VALUES(?,?,?,?,?,?)""",
                (
                    receipt.command_id,
                    receipt.record_id,
                    receipt.command_fingerprint,
                    receipt.committed_at.isoformat(),
                    receipt.schema_version,
                    receipt.committed_at.isoformat(),
                ),
            )
        except sqlite3.Error as error:
            raise GoodsReceiptReceiptError("Goods Receipt command receipt insert failed") from error

    def save(self, command, record, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            self._validate_write(command, record, receipt)
            self._validate_source(record)
            purchase = self.get_purchase_execution_record(
                record.source_manifest.purchase_execution_record_id
            )
            if purchase is None:
                raise GoodsReceiptSourceLineageError(
                    "exact Purchase Execution Record is missing"
                )
            cumulative = self.get_cumulative_received_quantity(purchase.record_id)
            if cumulative + record.received_quantity > purchase.actual_quantity:
                raise GoodsReceiptCumulativeQuantityConflictError(
                    "Goods Receipt cumulative quantity exceeds Purchase Execution quantity"
                )
            encoded = _payload(record)
            source = record.source_manifest
            try:
                self._connection.execute(
                    f"""INSERT INTO {HISTORY_TABLE}(
                        record_id,purchase_execution_record_id,opportunity_id,
                        discovery_reference,received_quantity,policy_name,
                        policy_version,payload_json,integrity_fingerprint,
                        schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        record.record_id,
                        source.purchase_execution_record_id,
                        source.opportunity_identity.opportunity_id,
                        source.opportunity_identity.discovery_reference,
                        record.received_quantity,
                        record.policy_name,
                        record.policy_version,
                        encoded,
                        _integrity(encoded),
                        record.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise GoodsReceiptHistoryError("Goods Receipt history insert failed") from error
            self._insert_receipt(receipt)
            try:
                self._commit()
            except sqlite3.Error as error:
                raise GoodsReceiptCommitError("Goods Receipt commit failed") from error
            return GoodsReceiptPublication(record, receipt, False)
        except Exception:
            self._rollback()
            raise

    def _commit(self) -> None:
        self._connection.commit()

    def _rollback(self) -> None:
        if self._connection.in_transaction:
            self._connection.rollback()

    def close(self) -> None:
        if self._owns_connection:
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        return False


__all__ = [
    name
    for name in globals()
    if name.startswith(("SQLiteGoods", "GoodsReceipt", "MalformedGoods", "UnsupportedGoods"))
]
