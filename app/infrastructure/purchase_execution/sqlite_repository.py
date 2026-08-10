"""Append-only SQLite persistence for external Purchase Execution Records."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.purchase_execution import (
    PURCHASE_EXECUTION_RECEIPT_SCHEMA_VERSION,
    PURCHASE_EXECUTION_RECEIPT_SCHEMA_VERSION_V2,
    PurchaseExecutionCardinalityConflictError,
    PurchaseExecutionPublication,
    PurchaseExecutionReceipt,
    PurchaseExecutionReplayConflictError,
    RecordPurchaseExecutionCommand,
    RecordPurchaseExecutionCommandV2,
)
from app.domain.capital import (
    PURCHASE_EXECUTION_EVIDENCE_SCHEMA_VERSION,
    PURCHASE_EXECUTION_RECORD_SCHEMA_VERSION,
    PURCHASE_EXECUTION_RECORD_SCHEMA_VERSION_V2,
    PURCHASE_EXECUTION_SOURCE_MANIFEST_SCHEMA_VERSION,
    PURCHASE_EXECUTION_SOURCE_MANIFEST_SCHEMA_VERSION_V2,
    PurchaseExecutionEvidenceReference,
    PurchaseExecutionRecord,
    PurchaseExecutionSourceManifest,
)
from app.domain.decision_engine import OpportunityIdentity
from app.infrastructure.real_money_execution_intent import (
    SQLiteRealMoneyExecutionIntentRepository,
)


HISTORY_TABLE = "purchase_execution_record_history"
RECEIPT_TABLE = "purchase_execution_record_receipts"
INTENT_INDEX = "ux_purchase_execution_record_per_intent"


class PurchaseExecutionPersistenceError(RuntimeError):
    pass


class PurchaseExecutionHistoryError(PurchaseExecutionPersistenceError):
    pass


class PurchaseExecutionReceiptError(PurchaseExecutionPersistenceError):
    pass


class PurchaseExecutionCommitError(PurchaseExecutionPersistenceError):
    pass


class MalformedPurchaseExecutionPersistenceError(PurchaseExecutionPersistenceError):
    pass


class UnsupportedPurchaseExecutionVersionError(
    MalformedPurchaseExecutionPersistenceError
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


_MANIFEST_KEYS = {
    "opportunity_identity",
    "real_money_execution_intent_id",
    "founder_capital_approval_id",
    "capital_gate_id",
    "capital_requirement_id",
    "intended_order_quantity_id",
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
    "current_deployable_capital_snapshot_id",
    "expected_quantity",
    "expected_quantity_unit",
    "expected_total_amount",
    "currency",
    "founder_id",
    "execution_intent_evaluated_at",
    "execution_safety_policy_name",
    "execution_safety_policy_version",
    "schema_version",
}
_MANIFEST_KEYS_V2 = (_MANIFEST_KEYS - {"expected_total_amount", "currency"}) | {
    "authorized_acquisition_capital_amount",
    "authorized_acquisition_capital_currency",
    "proposed_supplier_order_committed_amount",
    "supplier_order_currency",
}
_EVIDENCE_KEYS = {"reference", "observed_at", "schema_version"}
_PAYLOAD_KEYS = {
    "record_id",
    "source_manifest",
    "actual_quantity",
    "actual_quantity_unit",
    "actual_total_committed_amount",
    "currency",
    "external_order_reference",
    "founder_id",
    "executed_at",
    "evidence_references",
    "requested_at",
    "admitted_at",
    "policy_name",
    "policy_version",
    "schema_version",
}
_PAYLOAD_KEYS_V2 = (_PAYLOAD_KEYS - {"actual_total_committed_amount", "currency"}) | {
    "supplier_order_committed_amount",
    "supplier_order_currency",
}


def _manifest(value: PurchaseExecutionSourceManifest) -> dict[str, object]:
    is_v2 = value.schema_version == PURCHASE_EXECUTION_SOURCE_MANIFEST_SCHEMA_VERSION_V2
    return {
        "opportunity_identity": {
            "opportunity_id": value.opportunity_identity.opportunity_id,
            "discovery_reference": value.opportunity_identity.discovery_reference,
        },
        "real_money_execution_intent_id": value.real_money_execution_intent_id,
        "founder_capital_approval_id": value.founder_capital_approval_id,
        "capital_gate_id": value.capital_gate_id,
        "capital_requirement_id": value.capital_requirement_id,
        "intended_order_quantity_id": value.intended_order_quantity_id,
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
        "current_deployable_capital_snapshot_id": value.current_deployable_capital_snapshot_id,
        "expected_quantity": value.expected_quantity,
        "expected_quantity_unit": value.expected_quantity_unit,
        **({
            "authorized_acquisition_capital_amount": format(value.authorized_acquisition_capital_amount, "f"),
            "authorized_acquisition_capital_currency": value.authorized_acquisition_capital_currency,
            "proposed_supplier_order_committed_amount": format(value.proposed_supplier_order_committed_amount, "f"),
            "supplier_order_currency": value.supplier_order_currency,
        } if is_v2 else {
            "expected_total_amount": format(value.expected_total_amount, "f"),
            "currency": value.currency,
        }),
        "founder_id": value.founder_id,
        "execution_intent_evaluated_at": value.execution_intent_evaluated_at.isoformat(),
        "execution_safety_policy_name": value.execution_safety_policy_name,
        "execution_safety_policy_version": value.execution_safety_policy_version,
        "schema_version": value.schema_version,
    }


def _load_manifest(value: object) -> PurchaseExecutionSourceManifest:
    if not isinstance(value, dict):
        raise ValueError("Purchase Execution source manifest must be an object")
    is_v2 = value.get("schema_version") == PURCHASE_EXECUTION_SOURCE_MANIFEST_SCHEMA_VERSION_V2
    data = _exact(value, _MANIFEST_KEYS_V2 if is_v2 else _MANIFEST_KEYS, "Purchase Execution source manifest")
    if data["schema_version"] not in {PURCHASE_EXECUTION_SOURCE_MANIFEST_SCHEMA_VERSION, PURCHASE_EXECUTION_SOURCE_MANIFEST_SCHEMA_VERSION_V2}:
        raise UnsupportedPurchaseExecutionVersionError(
            "unsupported Purchase Execution source manifest version"
        )
    identity = _exact(
        data["opportunity_identity"],
        {"opportunity_id", "discovery_reference"},
        "Opportunity identity",
    )
    return PurchaseExecutionSourceManifest(
        opportunity_identity=OpportunityIdentity(
            identity["opportunity_id"], identity["discovery_reference"]
        ),
        real_money_execution_intent_id=data["real_money_execution_intent_id"],
        founder_capital_approval_id=data["founder_capital_approval_id"],
        capital_gate_id=data["capital_gate_id"],
        capital_requirement_id=data["capital_requirement_id"],
        intended_order_quantity_id=data["intended_order_quantity_id"],
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
        current_deployable_capital_snapshot_id=data[
            "current_deployable_capital_snapshot_id"
        ],
        expected_quantity=data["expected_quantity"],
        expected_quantity_unit=data["expected_quantity_unit"],
        expected_total_amount=None if is_v2 else _decimal(data["expected_total_amount"], "expected_total_amount"),
        currency=None if is_v2 else data["currency"],
        founder_id=data["founder_id"],
        execution_intent_evaluated_at=_datetime(
            data["execution_intent_evaluated_at"], "execution_intent_evaluated_at"
        ),
        execution_safety_policy_name=data["execution_safety_policy_name"],
        execution_safety_policy_version=data["execution_safety_policy_version"],
        schema_version=data["schema_version"],
        authorized_acquisition_capital_amount=_decimal(data["authorized_acquisition_capital_amount"], "authorized_acquisition_capital_amount") if is_v2 else None,
        authorized_acquisition_capital_currency=data["authorized_acquisition_capital_currency"] if is_v2 else None,
        proposed_supplier_order_committed_amount=_decimal(data["proposed_supplier_order_committed_amount"], "proposed_supplier_order_committed_amount") if is_v2 else None,
        supplier_order_currency=data["supplier_order_currency"] if is_v2 else None,
    )


def _evidence(value: PurchaseExecutionEvidenceReference) -> dict[str, object]:
    return {
        "reference": value.reference,
        "observed_at": value.observed_at.isoformat(),
        "schema_version": value.schema_version,
    }


def _load_evidence(value: object) -> PurchaseExecutionEvidenceReference:
    data = _exact(value, _EVIDENCE_KEYS, "Purchase Execution evidence")
    if data["schema_version"] != PURCHASE_EXECUTION_EVIDENCE_SCHEMA_VERSION:
        raise UnsupportedPurchaseExecutionVersionError(
            "unsupported Purchase Execution evidence version"
        )
    return PurchaseExecutionEvidenceReference(
        reference=data["reference"],
        observed_at=_datetime(data["observed_at"], "evidence observed_at"),
        schema_version=data["schema_version"],
    )


def _payload(value: PurchaseExecutionRecord) -> str:
    is_v2 = value.schema_version == PURCHASE_EXECUTION_RECORD_SCHEMA_VERSION_V2
    return _dump({
            "record_id": value.record_id,
            "source_manifest": _manifest(value.source_manifest),
            "actual_quantity": value.actual_quantity,
            "actual_quantity_unit": value.actual_quantity_unit,
            **({
                "supplier_order_committed_amount": format(value.supplier_order_committed_amount, "f"),
                "supplier_order_currency": value.supplier_order_currency,
            } if is_v2 else {
                "actual_total_committed_amount": format(value.actual_total_committed_amount, "f"),
                "currency": value.currency,
            }),
            "external_order_reference": value.external_order_reference,
            "founder_id": value.founder_id,
            "executed_at": value.executed_at.isoformat(),
            "evidence_references": [
                _evidence(item) for item in value.evidence_references
            ],
            "requested_at": value.requested_at.isoformat(),
            "admitted_at": value.admitted_at.isoformat(),
            "policy_name": value.policy_name,
            "policy_version": value.policy_version,
            "schema_version": value.schema_version,
        })


def _action_fingerprint(record: PurchaseExecutionRecord) -> str:
    source = record.source_manifest
    is_v2 = record.schema_version == PURCHASE_EXECUTION_RECORD_SCHEMA_VERSION_V2
    command_type = RecordPurchaseExecutionCommandV2 if is_v2 else RecordPurchaseExecutionCommand
    command = command_type(
        command_id="persistence-reconstruction-only",
        real_money_execution_intent_id=source.real_money_execution_intent_id,
        quote_id=source.quote_id,
        quote_revision=source.quote_revision,
        actual_quantity=record.actual_quantity,
        actual_quantity_unit=record.actual_quantity_unit,
        **({
            "supplier_order_committed_amount": record.supplier_order_committed_amount,
            "supplier_order_currency": record.supplier_order_currency,
        } if is_v2 else {
            "actual_total_committed_amount": record.actual_total_committed_amount,
            "currency": record.currency,
        }),
        external_order_reference=record.external_order_reference,
        founder_id=record.founder_id,
        executed_at=record.executed_at,
        evidence_references=record.evidence_references,
        requested_at=record.requested_at,
        policy_name=record.policy_name,
        policy_version=record.policy_version,
    )
    return command.action_fingerprint


class SQLitePurchaseExecutionRepository:
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
        self._execution = SQLiteRealMoneyExecutionIntentRepository(
            connection=self._connection
        )
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {HISTORY_TABLE}(
                    record_id TEXT PRIMARY KEY,
                    execution_intent_id TEXT NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    discovery_reference TEXT NOT NULL,
                    action_fingerprint TEXT NOT NULL,
                    policy_name TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(execution_intent_id)
                      REFERENCES real_money_execution_intent_history(intent_id)
                )"""
            )
            self._connection.execute(
                f"""CREATE UNIQUE INDEX IF NOT EXISTS {INTENT_INDEX}
                ON {HISTORY_TABLE}(execution_intent_id)"""
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

    def get_execution_intent(self, intent_id: str):
        return self._execution.get_intent(intent_id)

    def get_sourcing_admission(self, admission_id: str, revision: int):
        return self._execution.get_sourcing_admission(admission_id, revision)

    def _history_row(self, record_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE record_id=?", (record_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise PurchaseExecutionHistoryError(
                "Purchase Execution history query failed"
            ) from error

    def _intent_row(self, intent_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE execution_intent_id=?",
                (intent_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise PurchaseExecutionHistoryError(
                "Purchase Execution intent query failed"
            ) from error

    def _load_record(self, row) -> PurchaseExecutionRecord:
        try:
            if row["schema_version"] not in {PURCHASE_EXECUTION_RECORD_SCHEMA_VERSION, PURCHASE_EXECUTION_RECORD_SCHEMA_VERSION_V2}:
                raise UnsupportedPurchaseExecutionVersionError(
                    "unsupported Purchase Execution Record version"
                )
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _integrity(encoded) != row["integrity_fingerprint"]:
                raise ValueError("Purchase Execution integrity mismatch")
            raw = json.loads(encoded)
            is_v2 = isinstance(raw, dict) and raw.get("schema_version") == PURCHASE_EXECUTION_RECORD_SCHEMA_VERSION_V2
            data = _exact(raw, _PAYLOAD_KEYS_V2 if is_v2 else _PAYLOAD_KEYS, "Purchase Execution payload")
            if data["schema_version"] not in {PURCHASE_EXECUTION_RECORD_SCHEMA_VERSION, PURCHASE_EXECUTION_RECORD_SCHEMA_VERSION_V2}:
                raise UnsupportedPurchaseExecutionVersionError(
                    "unsupported Purchase Execution payload version"
                )
            manifest = _load_manifest(data["source_manifest"])
            evidence_data = data["evidence_references"]
            if not isinstance(evidence_data, list):
                raise ValueError("evidence_references must be a list")
            record = PurchaseExecutionRecord(
                record_id=data["record_id"],
                source_manifest=manifest,
                actual_quantity=data["actual_quantity"],
                actual_quantity_unit=data["actual_quantity_unit"],
                actual_total_committed_amount=None if is_v2 else _decimal(data["actual_total_committed_amount"], "actual_total_committed_amount"),
                currency=None if is_v2 else data["currency"],
                external_order_reference=data["external_order_reference"],
                founder_id=data["founder_id"],
                executed_at=_datetime(data["executed_at"], "executed_at"),
                evidence_references=tuple(_load_evidence(item) for item in evidence_data),
                requested_at=_datetime(data["requested_at"], "requested_at"),
                admitted_at=_datetime(data["admitted_at"], "admitted_at"),
                policy_name=data["policy_name"],
                policy_version=data["policy_version"],
                schema_version=data["schema_version"],
                supplier_order_committed_amount=_decimal(data["supplier_order_committed_amount"], "supplier_order_committed_amount") if is_v2 else None,
                supplier_order_currency=data["supplier_order_currency"] if is_v2 else None,
            )
            if (
                record.record_id != row["record_id"]
                or manifest.real_money_execution_intent_id
                != row["execution_intent_id"]
                or manifest.opportunity_identity.opportunity_id != row["opportunity_id"]
                or manifest.opportunity_identity.discovery_reference
                != row["discovery_reference"]
                or record.policy_name != row["policy_name"]
                or record.policy_version != row["policy_version"]
                or _action_fingerprint(record) != row["action_fingerprint"]
                or record.schema_version != row["schema_version"]
            ):
                raise ValueError("Purchase Execution columns differ from payload")
            self._validate_source(record)
            return record
        except UnsupportedPurchaseExecutionVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedPurchaseExecutionPersistenceError):
                raise
            raise MalformedPurchaseExecutionPersistenceError(
                "persisted Purchase Execution Record is malformed"
            ) from error

    def get_record(self, record_id: str):
        row = self._history_row(record_id)
        return None if row is None else self._load_record(row)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?", (command_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise PurchaseExecutionReceiptError(
                "Purchase Execution receipt query failed"
            ) from error

    def _load_receipt(self, row) -> PurchaseExecutionReceipt:
        try:
            if row["schema_version"] not in {PURCHASE_EXECUTION_RECEIPT_SCHEMA_VERSION, PURCHASE_EXECUTION_RECEIPT_SCHEMA_VERSION_V2}:
                raise UnsupportedPurchaseExecutionVersionError(
                    "unsupported Purchase Execution receipt version"
                )
            receipt = PurchaseExecutionReceipt(
                row["command_id"],
                row["record_id"],
                row["command_fingerprint"],
                _datetime(row["committed_at"], "committed_at"),
                row["schema_version"],
            )
            if self.get_record(receipt.record_id) is None:
                raise ValueError("Purchase Execution receipt is orphaned")
            return receipt
        except UnsupportedPurchaseExecutionVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedPurchaseExecutionPersistenceError):
                raise
            raise MalformedPurchaseExecutionPersistenceError(
                "persisted Purchase Execution receipt is malformed"
            ) from error

    def validate_replay(self, command_id: str, fingerprint: str):
        row = self._receipt_row(command_id)
        if row is None:
            return None
        receipt = self._load_receipt(row)
        if receipt.command_fingerprint != fingerprint:
            raise PurchaseExecutionReplayConflictError(
                "Purchase Execution command payload conflicts"
            )
        record = self.get_record(receipt.record_id)
        if record is None:
            raise MalformedPurchaseExecutionPersistenceError(
                "Purchase Execution receipt is orphaned"
            )
        return PurchaseExecutionPublication(record, receipt, True)

    def find_alias(self, intent_id: str, action_fingerprint: str):
        row = self._intent_row(intent_id)
        if row is None or row["action_fingerprint"] != action_fingerprint:
            return None
        return self._load_record(row)

    def _validate_source(self, record: PurchaseExecutionRecord) -> None:
        source = record.source_manifest
        intent = self.get_execution_intent(source.real_money_execution_intent_id)
        admission = self.get_sourcing_admission(
            source.sourcing_admission_id, source.sourcing_admission_revision
        )
        if intent is None or admission is None:
            raise ValueError("Purchase Execution references missing source")
        intent_source = intent.source_manifest
        supplier = admission.supplier_identity
        product = admission.sourcing_product_identity
        quote = admission.quote_revision
        if (
            intent_source.opportunity_identity != source.opportunity_identity
            or intent_source.founder_capital_approval_id
            != source.founder_capital_approval_id
            or intent_source.capital_gate_id != source.capital_gate_id
            or intent_source.capital_requirement_id != source.capital_requirement_id
            or intent_source.intended_order_quantity_id
            != source.intended_order_quantity_id
            or intent_source.sourcing_admission_id != source.sourcing_admission_id
            or intent_source.sourcing_admission_revision
            != source.sourcing_admission_revision
            or intent_source.quote_id != source.quote_id
            or intent_source.quote_revision != source.quote_revision
            or intent_source.current_deployable_capital_snapshot_id
            != source.current_deployable_capital_snapshot_id
            or intent_source.execution_quantity != source.expected_quantity
            or intent_source.execution_quantity_unit != source.expected_quantity_unit
            or (
                intent_source.authorized_acquisition_capital_amount != source.authorized_acquisition_capital_amount
                or intent_source.authorized_acquisition_capital_currency != source.authorized_acquisition_capital_currency
                or intent_source.proposed_supplier_order_committed_amount != source.proposed_supplier_order_committed_amount
                or intent_source.supplier_order_currency != source.supplier_order_currency
                if source.schema_version == PURCHASE_EXECUTION_SOURCE_MANIFEST_SCHEMA_VERSION_V2
                else intent_source.planned_execution_amount != source.expected_total_amount
                or intent_source.currency != source.currency
            )
            or intent_source.founder_id != source.founder_id
            or intent.evaluated_at != source.execution_intent_evaluated_at
            or intent_source.policy_name != source.execution_safety_policy_name
            or intent_source.policy_version != source.execution_safety_policy_version
            or supplier.supplier_id != source.supplier_id
            or supplier.source_platform != source.source_platform
            or supplier.external_supplier_reference
            != source.external_supplier_reference
            or product.sourcing_product_id != source.sourcing_product_id
            or product.external_product_reference != source.external_product_reference
            or product.option_reference != source.option_reference
            or product.sku_reference != source.sku_reference
            or quote.quote_id != source.quote_id
            or quote.revision != source.quote_revision
        ):
            raise ValueError("Purchase Execution source lineage differs")

    @staticmethod
    def _validate_write(command, record, receipt) -> None:
        if not isinstance(command, (RecordPurchaseExecutionCommand, RecordPurchaseExecutionCommandV2)):
            raise TypeError("command must be a supported RecordPurchaseExecutionCommand")
        if not isinstance(record, PurchaseExecutionRecord):
            raise TypeError("record must be PurchaseExecutionRecord")
        if not isinstance(receipt, PurchaseExecutionReceipt):
            raise TypeError("receipt must be PurchaseExecutionReceipt")
        source = record.source_manifest
        if (
            receipt.command_id != command.command_id
            or receipt.record_id != record.record_id
            or receipt.command_fingerprint != command.fingerprint
            or source.real_money_execution_intent_id
            != command.real_money_execution_intent_id
            or source.quote_id != command.quote_id
            or source.quote_revision != command.quote_revision
            or record.actual_quantity != command.actual_quantity
            or record.actual_quantity_unit != command.actual_quantity_unit
            or (
                record.supplier_order_committed_amount != command.supplier_order_committed_amount
                or record.supplier_order_currency != command.supplier_order_currency
                if isinstance(command, RecordPurchaseExecutionCommandV2)
                else record.actual_total_committed_amount != command.actual_total_committed_amount
                or record.currency != command.currency
            )
            or record.external_order_reference != command.external_order_reference
            or record.founder_id != command.founder_id
            or record.executed_at != command.executed_at
            or record.evidence_references != command.evidence_references
            or record.requested_at != command.requested_at
            or record.policy_name != command.policy_name
            or record.policy_version != command.policy_version
        ):
            raise PurchaseExecutionReplayConflictError(
                "command, Purchase Execution Record, and receipt differ"
            )

    def _insert_receipt(self, receipt: PurchaseExecutionReceipt) -> None:
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
            raise PurchaseExecutionReceiptError(
                "Purchase Execution receipt insert failed"
            ) from error

    def save_alias(self, command, record, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            row = self._intent_row(command.real_money_execution_intent_id)
            if (
                row is None
                or row["record_id"] != record.record_id
                or row["action_fingerprint"] != command.action_fingerprint
                or receipt.record_id != record.record_id
                or receipt.command_fingerprint != command.fingerprint
            ):
                raise PurchaseExecutionCardinalityConflictError(
                    "READY intent already has a different Purchase Execution Record"
                )
            authoritative = self._load_record(row)
            self._insert_receipt(receipt)
            try:
                self._commit()
            except sqlite3.Error as error:
                raise PurchaseExecutionCommitError(
                    "Purchase Execution alias commit failed"
                ) from error
            return PurchaseExecutionPublication(authoritative, receipt, True)
        except Exception:
            self._rollback()
            raise

    def save_record(self, command, record, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            self._validate_write(command, record, receipt)
            self._validate_source(record)
            existing_row = self._intent_row(command.real_money_execution_intent_id)
            if existing_row is not None:
                existing = self._load_record(existing_row)
                if existing_row["action_fingerprint"] != command.action_fingerprint:
                    raise PurchaseExecutionCardinalityConflictError(
                        "READY intent already has a different Purchase Execution Record"
                    )
                alias_receipt = PurchaseExecutionReceipt(
                    command.command_id,
                    existing.record_id,
                    command.fingerprint,
                    receipt.committed_at,
                    receipt.schema_version,
                )
                self._insert_receipt(alias_receipt)
                try:
                    self._commit()
                except sqlite3.Error as error:
                    raise PurchaseExecutionCommitError(
                        "Purchase Execution alias commit failed"
                    ) from error
                return PurchaseExecutionPublication(existing, alias_receipt, True)
            encoded = _payload(record)
            source = record.source_manifest
            try:
                self._connection.execute(
                    f"""INSERT INTO {HISTORY_TABLE}(
                        record_id,execution_intent_id,opportunity_id,
                        discovery_reference,action_fingerprint,policy_name,
                        policy_version,payload_json,integrity_fingerprint,
                        schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        record.record_id,
                        source.real_money_execution_intent_id,
                        source.opportunity_identity.opportunity_id,
                        source.opportunity_identity.discovery_reference,
                        command.action_fingerprint,
                        record.policy_name,
                        record.policy_version,
                        encoded,
                        _integrity(encoded),
                        record.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as error:
                if self._intent_row(source.real_money_execution_intent_id) is not None:
                    raise PurchaseExecutionCardinalityConflictError(
                        "READY intent already has a Purchase Execution Record"
                    ) from error
                raise PurchaseExecutionHistoryError(
                    "Purchase Execution insert failed"
                ) from error
            except sqlite3.Error as error:
                raise PurchaseExecutionHistoryError(
                    "Purchase Execution insert failed"
                ) from error
            self._insert_receipt(receipt)
            try:
                self._commit()
            except sqlite3.Error as error:
                raise PurchaseExecutionCommitError(
                    "Purchase Execution commit failed"
                ) from error
            return PurchaseExecutionPublication(record, receipt, False)
        except Exception:
            self._rollback()
            raise

    def _rollback(self) -> None:
        if self._connection.in_transaction:
            self._connection.rollback()

    def _commit(self) -> None:
        self._connection.commit()

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
    if name.startswith(("Malformed", "PurchaseExecution", "SQLite", "Unsupported"))
]
