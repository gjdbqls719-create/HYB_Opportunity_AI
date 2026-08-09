"""Append-only SQLite persistence for Actual Sale Settlement revisions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.actual_sale_settlement import (
    ACTUAL_SALE_RECEIPT_SCHEMA_VERSION,
    AdmitActualSaleSettlementCommand,
    ActualSaleSettlementOversellConflictError,
    ActualSaleSettlementPublication,
    ActualSaleSettlementReceipt,
    ActualSaleSettlementReplayConflictError,
    ActualSaleSettlementReportConflictError,
    ActualSaleSettlementRevisionConflictError,
    ActualSaleSettlementSourceLineageError,
    ActualSaleSettlementTerminalConflictError,
    ActualSaleSettlementWindowConflictError,
    _inventory_safe,
    _same_subject,
    owned_inventory_product_key_from_receipt,
)
from app.domain.capital import (
    ACTUAL_SALE_EVIDENCE_SCHEMA_VERSION,
    ACTUAL_SALE_FINALITY_SCHEMA_VERSION,
    ACTUAL_SALE_MONETARY_FACT_SCHEMA_VERSION,
    ACTUAL_SALE_OTHER_COSTS_SCHEMA_VERSION,
    ACTUAL_SALE_PAYOUT_SCHEMA_VERSION,
    ACTUAL_SALE_SETTLEMENT_SCHEMA_VERSION,
    ACTUAL_SALE_SOURCE_MANIFEST_SCHEMA_VERSION,
    ActualSaleBlockingReason,
    ActualSaleEvidenceReference,
    ActualSaleFactAvailability,
    ActualSaleFinalityFact,
    ActualSaleMonetaryCategory,
    ActualSaleMonetaryFact,
    ActualSalePayoutFact,
    ActualSalePayoutReconciliationState,
    ActualSaleSettlement,
    ActualSaleSettlementSourceManifest,
    ActualSaleSettlementState,
    OtherActualSaleCostItem,
    OtherActualSaleCosts,
    OwnedInventoryProductKey,
)
from app.domain.decision_engine import OpportunityIdentity
from app.infrastructure.goods_receipt import SQLiteGoodsReceiptRepository


HISTORY_TABLE = "actual_sale_settlement_history"
RECEIPT_TABLE = "actual_sale_settlement_receipts"


class ActualSaleSettlementPersistenceError(RuntimeError): pass
class ActualSaleSettlementHistoryError(ActualSaleSettlementPersistenceError): pass
class ActualSaleSettlementReceiptError(ActualSaleSettlementPersistenceError): pass
class ActualSaleSettlementCommitError(ActualSaleSettlementPersistenceError): pass
class MalformedActualSaleSettlementPersistenceError(ActualSaleSettlementPersistenceError): pass
class UnsupportedActualSaleSettlementVersionError(MalformedActualSaleSettlementPersistenceError): pass


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


def _evidence(value: ActualSaleEvidenceReference | None):
    if value is None:
        return None
    return {"reference": value.reference, "observed_at": value.observed_at.isoformat(), "operator_id": value.operator_id, "collection_method": value.collection_method, "schema_version": value.schema_version}


def _load_evidence(value: object) -> ActualSaleEvidenceReference | None:
    if value is None:
        return None
    data = _exact(value, {"reference", "observed_at", "operator_id", "collection_method", "schema_version"}, "actual sale evidence")
    if data["schema_version"] != ACTUAL_SALE_EVIDENCE_SCHEMA_VERSION:
        raise UnsupportedActualSaleSettlementVersionError("unsupported actual sale evidence version")
    return ActualSaleEvidenceReference(data["reference"], _datetime(data["observed_at"], "observed_at"), data["operator_id"], data["collection_method"], data["schema_version"])


def _fact(value: ActualSaleMonetaryFact) -> dict[str, object]:
    return {"category": value.category.value, "availability": value.availability.value, "amount": None if value.amount is None else str(value.amount), "currency": value.currency, "occurred_at": None if value.occurred_at is None else value.occurred_at.isoformat(), "evidence": _evidence(value.evidence), "unresolved_reason": value.unresolved_reason, "schema_version": value.schema_version}


def _load_fact(value: object) -> ActualSaleMonetaryFact:
    data = _exact(value, {"category", "availability", "amount", "currency", "occurred_at", "evidence", "unresolved_reason", "schema_version"}, "actual sale monetary fact")
    if data["schema_version"] != ACTUAL_SALE_MONETARY_FACT_SCHEMA_VERSION:
        raise UnsupportedActualSaleSettlementVersionError("unsupported actual sale monetary fact version")
    return ActualSaleMonetaryFact(ActualSaleMonetaryCategory(data["category"]), ActualSaleFactAvailability(data["availability"]), None if data["amount"] is None else Decimal(data["amount"]), data["currency"], None if data["occurred_at"] is None else _datetime(data["occurred_at"], "occurred_at"), _load_evidence(data["evidence"]), data["unresolved_reason"], data["schema_version"])


def _other(value: OtherActualSaleCosts) -> dict[str, object]:
    return {"availability": value.availability.value, "items": [{"scope": v.scope, "amount": str(v.amount), "currency": v.currency, "occurred_at": v.occurred_at.isoformat(), "evidence": _evidence(v.evidence)} for v in value.items], "scope_evidence": _evidence(value.scope_evidence), "unresolved_reason": value.unresolved_reason, "schema_version": value.schema_version}


def _load_other(value: object) -> OtherActualSaleCosts:
    data = _exact(value, {"availability", "items", "scope_evidence", "unresolved_reason", "schema_version"}, "other sale costs")
    if data["schema_version"] != ACTUAL_SALE_OTHER_COSTS_SCHEMA_VERSION or not isinstance(data["items"], list):
        raise UnsupportedActualSaleSettlementVersionError("unsupported other sale costs version")
    items = []
    for raw in data["items"]:
        item = _exact(raw, {"scope", "amount", "currency", "occurred_at", "evidence"}, "other sale cost item")
        items.append(OtherActualSaleCostItem(item["scope"], Decimal(item["amount"]), item["currency"], _datetime(item["occurred_at"], "occurred_at"), _load_evidence(item["evidence"])))
    return OtherActualSaleCosts(ActualSaleFactAvailability(data["availability"]), tuple(items), _load_evidence(data["scope_evidence"]), data["unresolved_reason"], data["schema_version"])


def _payout(value: ActualSalePayoutFact) -> dict[str, object]:
    return {"availability": value.availability.value, "amount": None if value.amount is None else str(value.amount), "currency": value.currency, "external_reference": value.external_reference, "paid_at": None if value.paid_at is None else value.paid_at.isoformat(), "evidence": _evidence(value.evidence), "unresolved_reason": value.unresolved_reason, "reconciliation_state": value.reconciliation_state.value, "reconciliation_explanation": value.reconciliation_explanation, "reconciliation_evidence": _evidence(value.reconciliation_evidence), "schema_version": value.schema_version}


def _load_payout(value: object) -> ActualSalePayoutFact:
    keys = {"availability", "amount", "currency", "external_reference", "paid_at", "evidence", "unresolved_reason", "reconciliation_state", "reconciliation_explanation", "reconciliation_evidence", "schema_version"}
    data = _exact(value, keys, "actual sale payout")
    if data["schema_version"] != ACTUAL_SALE_PAYOUT_SCHEMA_VERSION:
        raise UnsupportedActualSaleSettlementVersionError("unsupported actual sale payout version")
    return ActualSalePayoutFact(ActualSaleFactAvailability(data["availability"]), None if data["amount"] is None else Decimal(data["amount"]), data["currency"], data["external_reference"], None if data["paid_at"] is None else _datetime(data["paid_at"], "paid_at"), _load_evidence(data["evidence"]), data["unresolved_reason"], ActualSalePayoutReconciliationState(data["reconciliation_state"]), data["reconciliation_explanation"], _load_evidence(data["reconciliation_evidence"]), data["schema_version"])


def _finality(value: ActualSaleFinalityFact) -> dict[str, object]:
    return {"confirmed": value.confirmed, "observed_at": None if value.observed_at is None else value.observed_at.isoformat(), "evidence": _evidence(value.evidence), "unresolved_reason": value.unresolved_reason, "schema_version": value.schema_version}


def _load_finality(value: object) -> ActualSaleFinalityFact:
    data = _exact(value, {"confirmed", "observed_at", "evidence", "unresolved_reason", "schema_version"}, "actual sale finality")
    if data["schema_version"] != ACTUAL_SALE_FINALITY_SCHEMA_VERSION:
        raise UnsupportedActualSaleSettlementVersionError("unsupported actual sale finality version")
    return ActualSaleFinalityFact(data["confirmed"], None if data["observed_at"] is None else _datetime(data["observed_at"], "finality observed_at"), _load_evidence(data["evidence"]), data["unresolved_reason"], data["schema_version"])


def _key(value: OwnedInventoryProductKey) -> dict[str, object]:
    identity = value.opportunity_identity
    return {"opportunity_id": identity.opportunity_id, "discovery_reference": identity.discovery_reference, "source_platform": value.source_platform, "supplier_id": value.supplier_id, "sourcing_product_id": value.sourcing_product_id, "external_product_reference": value.external_product_reference, "option_reference": value.option_reference, "sku_reference": value.sku_reference, "quantity_unit": value.quantity_unit}


def _load_key(value: object) -> OwnedInventoryProductKey:
    data = _exact(value, {"opportunity_id", "discovery_reference", "source_platform", "supplier_id", "sourcing_product_id", "external_product_reference", "option_reference", "sku_reference", "quantity_unit"}, "owned inventory product key")
    return OwnedInventoryProductKey(OpportunityIdentity(data["opportunity_id"], data["discovery_reference"]), data["source_platform"], data["supplier_id"], data["sourcing_product_id"], data["external_product_reference"], data["option_reference"], data["sku_reference"], data["quantity_unit"])


def _manifest(value: ActualSaleSettlementSourceManifest) -> dict[str, object]:
    return {"product_key": _key(value.product_key), "anchor_goods_receipt_id": value.anchor_goods_receipt_id, "eligible_goods_receipt_ids": list(value.eligible_goods_receipt_ids), "contributing_purchase_execution_ids": list(value.contributing_purchase_execution_ids), "marketplace": value.marketplace, "seller_account_reference": value.seller_account_reference, "marketplace_product_reference": value.marketplace_product_reference, "marketplace_option_reference": value.marketplace_option_reference, "marketplace_sku_reference": value.marketplace_sku_reference, "external_report_reference": value.external_report_reference, "transaction_references": list(value.transaction_references), "schema_version": value.schema_version}


def _load_manifest(value: object) -> ActualSaleSettlementSourceManifest:
    keys = {"product_key", "anchor_goods_receipt_id", "eligible_goods_receipt_ids", "contributing_purchase_execution_ids", "marketplace", "seller_account_reference", "marketplace_product_reference", "marketplace_option_reference", "marketplace_sku_reference", "external_report_reference", "transaction_references", "schema_version"}
    data = _exact(value, keys, "actual sale source manifest")
    if data["schema_version"] != ACTUAL_SALE_SOURCE_MANIFEST_SCHEMA_VERSION:
        raise UnsupportedActualSaleSettlementVersionError("unsupported actual sale source manifest version")
    for name in ("eligible_goods_receipt_ids", "contributing_purchase_execution_ids", "transaction_references"):
        if not isinstance(data[name], list):
            raise ValueError(f"{name} must be list")
    return ActualSaleSettlementSourceManifest(_load_key(data["product_key"]), data["anchor_goods_receipt_id"], tuple(data["eligible_goods_receipt_ids"]), tuple(data["contributing_purchase_execution_ids"]), data["marketplace"], data["seller_account_reference"], data["marketplace_product_reference"], data["marketplace_option_reference"], data["marketplace_sku_reference"], data["external_report_reference"], tuple(data["transaction_references"]), data["schema_version"])


def _payload(value: ActualSaleSettlement) -> str:
    return _dump({"settlement_id": value.settlement_id, "source_manifest": _manifest(value.source_manifest), "revision": value.revision, "predecessor_settlement_id": value.predecessor_settlement_id, "period_start": value.period_start.isoformat(), "period_end": value.period_end.isoformat(), "fulfilled_outbound_quantity": value.fulfilled_outbound_quantity, "cancelled_quantity": value.cancelled_quantity, "refunded_quantity": value.refunded_quantity, "returned_quantity": value.returned_quantity, "quantity_unit": value.quantity_unit, "settlement_currency": value.settlement_currency, "fixed_monetary_facts": [_fact(v) for v in value.fixed_monetary_facts], "other_sale_side_costs": _other(value.other_sale_side_costs), "payout": _payout(value.payout), "finality": _finality(value.finality), "state": value.state.value, "blocking_reasons": [v.value for v in value.blocking_reasons], "operator_id": value.operator_id, "requested_at": value.requested_at.isoformat(), "admitted_at": value.admitted_at.isoformat(), "policy_name": value.policy_name, "policy_version": value.policy_version, "policy_precision": value.policy_precision, "policy_rounding": value.policy_rounding, "schema_version": value.schema_version})


_PAYLOAD_KEYS = {"settlement_id", "source_manifest", "revision", "predecessor_settlement_id", "period_start", "period_end", "fulfilled_outbound_quantity", "cancelled_quantity", "refunded_quantity", "returned_quantity", "quantity_unit", "settlement_currency", "fixed_monetary_facts", "other_sale_side_costs", "payout", "finality", "state", "blocking_reasons", "operator_id", "requested_at", "admitted_at", "policy_name", "policy_version", "policy_precision", "policy_rounding", "schema_version"}


def _key_fingerprint(value: OwnedInventoryProductKey) -> str:
    return _integrity(_dump(_key(value)))


def _subject_fingerprint(value: ActualSaleSettlementSourceManifest) -> str:
    return _integrity(_dump({"product_key": _key(value.product_key), "marketplace": value.marketplace, "seller_account_reference": value.seller_account_reference, "external_report_reference": value.external_report_reference}))


class SQLiteActualSaleSettlementRepository:
    def __init__(self, database_path: str | Path | None = None, *, connection: sqlite3.Connection | None = None) -> None:
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
        self._goods = SQLiteGoodsReceiptRepository(connection=self._connection)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(f"""CREATE TABLE IF NOT EXISTS {HISTORY_TABLE}(
                settlement_id TEXT PRIMARY KEY, subject_fingerprint TEXT NOT NULL,
                product_fingerprint TEXT NOT NULL, opportunity_id TEXT NOT NULL,
                marketplace TEXT NOT NULL, seller_account_reference TEXT NOT NULL,
                external_report_reference TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision>0),
                predecessor_settlement_id TEXT, state TEXT NOT NULL, period_start TEXT NOT NULL,
                period_end TEXT NOT NULL, fulfilled_outbound_quantity INTEGER NOT NULL CHECK(fulfilled_outbound_quantity>=0),
                payload_json TEXT NOT NULL, integrity_fingerprint TEXT NOT NULL,
                policy_name TEXT NOT NULL, policy_version TEXT NOT NULL, schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL, FOREIGN KEY(predecessor_settlement_id) REFERENCES {HISTORY_TABLE}(settlement_id),
                UNIQUE(subject_fingerprint,revision), UNIQUE(predecessor_settlement_id))""")
            self._connection.execute(f"CREATE INDEX IF NOT EXISTS ix_actual_sale_product ON {HISTORY_TABLE}(product_fingerprint,state,period_end)")
            self._connection.execute(f"CREATE UNIQUE INDEX IF NOT EXISTS ux_actual_sale_complete_subject ON {HISTORY_TABLE}(subject_fingerprint) WHERE state='complete'")
            self._connection.execute(f"""CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE}(
                command_id TEXT PRIMARY KEY, settlement_id TEXT NOT NULL UNIQUE,
                command_fingerprint TEXT NOT NULL, committed_at TEXT NOT NULL,
                schema_version TEXT NOT NULL, inserted_at TEXT NOT NULL,
                FOREIGN KEY(settlement_id) REFERENCES {HISTORY_TABLE}(settlement_id))""")
            for table in (HISTORY_TABLE, RECEIPT_TABLE):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(f"CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END")
            self._connection.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_actual_sale_no_child_after_complete
                BEFORE INSERT ON {HISTORY_TABLE} WHEN NEW.predecessor_settlement_id IS NOT NULL
                AND (SELECT state FROM {HISTORY_TABLE} WHERE settlement_id=NEW.predecessor_settlement_id)='complete'
                BEGIN SELECT RAISE(ABORT,'COMPLETE actual sale settlement is terminal'); END""")

    def get_goods_receipt(self, record_id: str): return self._goods.get_record(record_id)
    def list_goods_receipts_for_opportunity(self, opportunity_id: str): return self._goods.list_goods_receipts_for_opportunity(opportunity_id)

    def _row(self, settlement_id: str):
        try: return self._connection.execute(f"SELECT * FROM {HISTORY_TABLE} WHERE settlement_id=?", (settlement_id,)).fetchone()
        except sqlite3.Error as error: raise ActualSaleSettlementHistoryError("actual sale settlement query failed") from error

    def _load_row(self, row) -> ActualSaleSettlement:
        try:
            if row["schema_version"] != ACTUAL_SALE_SETTLEMENT_SCHEMA_VERSION:
                raise UnsupportedActualSaleSettlementVersionError("unsupported actual sale settlement version")
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _integrity(encoded) != row["integrity_fingerprint"]:
                raise ValueError("actual sale settlement integrity mismatch")
            data = _exact(json.loads(encoded), _PAYLOAD_KEYS, "actual sale settlement payload")
            if data["schema_version"] != ACTUAL_SALE_SETTLEMENT_SCHEMA_VERSION or not isinstance(data["fixed_monetary_facts"], list) or not isinstance(data["blocking_reasons"], list):
                raise UnsupportedActualSaleSettlementVersionError("unsupported actual sale settlement payload")
            value = ActualSaleSettlement(
                data["settlement_id"], _load_manifest(data["source_manifest"]), data["revision"], data["predecessor_settlement_id"],
                _datetime(data["period_start"], "period_start"), _datetime(data["period_end"], "period_end"),
                data["fulfilled_outbound_quantity"], data["cancelled_quantity"], data["refunded_quantity"], data["returned_quantity"],
                data["quantity_unit"], data["settlement_currency"], tuple(_load_fact(v) for v in data["fixed_monetary_facts"]),
                _load_other(data["other_sale_side_costs"]), _load_payout(data["payout"]), _load_finality(data["finality"]),
                ActualSaleSettlementState(data["state"]), tuple(ActualSaleBlockingReason(v) for v in data["blocking_reasons"]),
                data["operator_id"], _datetime(data["requested_at"], "requested_at"), _datetime(data["admitted_at"], "admitted_at"),
                data["policy_name"], data["policy_version"], data["policy_precision"], data["policy_rounding"], data["schema_version"])
            manifest = value.source_manifest
            if any((value.settlement_id != row["settlement_id"], _subject_fingerprint(manifest) != row["subject_fingerprint"], _key_fingerprint(manifest.product_key) != row["product_fingerprint"], manifest.product_key.opportunity_identity.opportunity_id != row["opportunity_id"], manifest.marketplace != row["marketplace"], manifest.seller_account_reference != row["seller_account_reference"], manifest.external_report_reference != row["external_report_reference"], value.revision != row["revision"], value.predecessor_settlement_id != row["predecessor_settlement_id"], value.state.value != row["state"], value.period_start.isoformat() != row["period_start"], value.period_end.isoformat() != row["period_end"], value.fulfilled_outbound_quantity != row["fulfilled_outbound_quantity"], value.policy_name != row["policy_name"], value.policy_version != row["policy_version"])):
                raise ValueError("actual sale columns differ from payload")
            self._validate_source(value)
            return value
        except UnsupportedActualSaleSettlementVersionError: raise
        except Exception as error:
            if isinstance(error, MalformedActualSaleSettlementPersistenceError): raise
            raise MalformedActualSaleSettlementPersistenceError("persisted actual sale settlement is malformed") from error

    def _subject_rows(self, fingerprint: str):
        return self._connection.execute(f"SELECT * FROM {HISTORY_TABLE} WHERE subject_fingerprint=? ORDER BY revision", (fingerprint,)).fetchall()

    def _validate_chain(self, fingerprint: str) -> tuple[ActualSaleSettlement, ...]:
        values = tuple(self._load_row(row) for row in self._subject_rows(fingerprint))
        previous = None
        complete_seen = False
        for index, value in enumerate(values, start=1):
            if value.revision != index:
                raise MalformedActualSaleSettlementPersistenceError(
                    "actual sale revision sequence is malformed"
                )
            expected_predecessor = None if previous is None else previous.settlement_id
            if value.predecessor_settlement_id != expected_predecessor:
                raise MalformedActualSaleSettlementPersistenceError(
                    "actual sale predecessor sequence is malformed"
                )
            if previous is not None:
                if (
                    value.period_start != previous.period_start
                    or value.period_end != previous.period_end
                    or value.settlement_currency != previous.settlement_currency
                    or value.source_manifest.marketplace_product_reference
                    != previous.source_manifest.marketplace_product_reference
                    or value.source_manifest.marketplace_option_reference
                    != previous.source_manifest.marketplace_option_reference
                    or value.source_manifest.marketplace_sku_reference
                    != previous.source_manifest.marketplace_sku_reference
                ):
                    raise MalformedActualSaleSettlementPersistenceError(
                        "actual sale immutable scope changed across revisions"
                    )
                for old, new in zip(
                    previous.fixed_monetary_facts,
                    value.fixed_monetary_facts,
                    strict=True,
                ):
                    if (
                        old.availability is not ActualSaleFactAvailability.UNKNOWN
                        and new.availability is ActualSaleFactAvailability.UNKNOWN
                    ):
                        raise MalformedActualSaleSettlementPersistenceError(
                            "resolved actual sale fact regressed to UNKNOWN"
                        )
            if complete_seen:
                raise MalformedActualSaleSettlementPersistenceError(
                    "actual sale settlement exists after COMPLETE"
                )
            complete_seen = value.state is ActualSaleSettlementState.COMPLETE
            previous = value
        return values

    def get_settlement(self, settlement_id: str):
        row = self._row(settlement_id)
        if row is None:
            return None
        value = self._load_row(row)
        self._validate_chain(row["subject_fingerprint"])
        return value

    def get_chain_tip_for_subject(self, manifest):
        values = self._validate_chain(_subject_fingerprint(manifest))
        return None if not values else values[-1]

    def list_complete_settlements_for_product(self, product_key):
        rows = self._connection.execute(f"SELECT * FROM {HISTORY_TABLE} WHERE product_fingerprint=? AND state='complete' ORDER BY period_end,settlement_id", (_key_fingerprint(product_key),)).fetchall()
        return tuple(self.get_settlement(row["settlement_id"]) for row in rows)

    def _receipt_row(self, command_id: str):
        try: return self._connection.execute(f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?", (command_id,)).fetchone()
        except sqlite3.Error as error: raise ActualSaleSettlementReceiptError("actual sale receipt query failed") from error

    def _load_receipt(self, row):
        try:
            if row["schema_version"] != ACTUAL_SALE_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedActualSaleSettlementVersionError("unsupported actual sale receipt version")
            value = ActualSaleSettlementReceipt(row["command_id"], row["settlement_id"], row["command_fingerprint"], _datetime(row["committed_at"], "committed_at"), row["schema_version"])
            if self.get_settlement(value.settlement_id) is None: raise ValueError("actual sale receipt is orphaned")
            return value
        except UnsupportedActualSaleSettlementVersionError: raise
        except Exception as error: raise MalformedActualSaleSettlementPersistenceError("persisted actual sale receipt is malformed") from error

    def validate_replay(self, command_id: str, fingerprint: str):
        row = self._receipt_row(command_id)
        if row is None: return None
        receipt = self._load_receipt(row)
        if receipt.command_fingerprint != fingerprint:
            raise ActualSaleSettlementReplayConflictError("actual sale settlement command payload conflicts")
        return ActualSaleSettlementPublication(self.get_settlement(receipt.settlement_id), receipt, True)

    def _validate_source(self, settlement: ActualSaleSettlement) -> None:
        manifest = settlement.source_manifest
        records = []
        for record_id in manifest.eligible_goods_receipt_ids:
            record = self.get_goods_receipt(record_id)
            if record is None or owned_inventory_product_key_from_receipt(record) != manifest.product_key or record.inspected_at >= settlement.period_end:
                raise ActualSaleSettlementSourceLineageError("actual sale Goods Receipt lineage differs")
            records.append(record)
        if manifest.anchor_goods_receipt_id not in {v.record_id for v in records}:
            raise ActualSaleSettlementSourceLineageError("actual sale anchor is missing from eligible receipts")
        purchase_ids = []
        for value in records:
            source_id = value.source_manifest.purchase_execution_record_id
            if source_id not in purchase_ids: purchase_ids.append(source_id)
        if tuple(purchase_ids) != manifest.contributing_purchase_execution_ids:
            raise ActualSaleSettlementSourceLineageError("actual sale Purchase Execution lineage differs")

    @staticmethod
    def _validate_write(command, settlement, receipt):
        if not isinstance(command, AdmitActualSaleSettlementCommand) or not isinstance(settlement, ActualSaleSettlement) or not isinstance(receipt, ActualSaleSettlementReceipt):
            raise TypeError("actual sale write values have unsupported type")
        manifest = settlement.source_manifest
        if any((receipt.command_id != command.command_id, receipt.settlement_id != settlement.settlement_id, receipt.command_fingerprint != command.fingerprint, manifest.anchor_goods_receipt_id != command.anchor_goods_receipt_id, manifest.product_key.opportunity_identity.opportunity_id != command.opportunity_id, settlement.predecessor_settlement_id != command.predecessor_settlement_id, manifest.marketplace != command.marketplace, manifest.seller_account_reference != command.seller_account_reference, manifest.marketplace_product_reference != command.marketplace_product_reference, manifest.marketplace_option_reference != command.marketplace_option_reference, manifest.marketplace_sku_reference != command.marketplace_sku_reference, manifest.external_report_reference != command.external_report_reference, manifest.transaction_references != command.transaction_references, settlement.period_start != command.period_start, settlement.period_end != command.period_end, settlement.fulfilled_outbound_quantity != command.fulfilled_outbound_quantity, settlement.cancelled_quantity != command.cancelled_quantity, settlement.refunded_quantity != command.refunded_quantity, settlement.returned_quantity != command.returned_quantity, settlement.quantity_unit != command.quantity_unit, settlement.settlement_currency != command.settlement_currency, settlement.fixed_monetary_facts != command.fixed_monetary_facts, settlement.other_sale_side_costs != command.other_sale_side_costs, settlement.payout != command.payout, settlement.finality != command.finality, settlement.operator_id != command.operator_id, settlement.requested_at != command.requested_at)):
            raise ActualSaleSettlementReplayConflictError("command, actual sale settlement, and receipt differ")

    def _validate_complete_safety(self, settlement: ActualSaleSettlement) -> None:
        manifest = settlement.source_manifest
        existing = self.list_complete_settlements_for_product(manifest.product_key)
        for value in existing:
            other = value.source_manifest
            if other.marketplace == manifest.marketplace and other.seller_account_reference == manifest.seller_account_reference:
                if other.external_report_reference == manifest.external_report_reference and not _same_subject(other, manifest):
                    raise ActualSaleSettlementReportConflictError("external report reference is already used")
                if settlement.period_start < value.period_end and value.period_start < settlement.period_end:
                    raise ActualSaleSettlementWindowConflictError("COMPLETE actual sale windows overlap")
                if set(other.transaction_references) & set(manifest.transaction_references):
                    raise ActualSaleSettlementReportConflictError("transaction reference is already used")
        receipts = tuple(v for v in self.list_goods_receipts_for_opportunity(manifest.product_key.opportunity_identity.opportunity_id) if owned_inventory_product_key_from_receipt(v) == manifest.product_key)
        if not _inventory_safe(receipts, (*existing, settlement)):
            raise ActualSaleSettlementOversellConflictError("COMPLETE outbound exceeds chronological sellable inventory")

    def _insert_history(self, settlement: ActualSaleSettlement, receipt: ActualSaleSettlementReceipt) -> None:
        encoded = _payload(settlement)
        manifest = settlement.source_manifest
        try:
            self._connection.execute(
                f"INSERT INTO {HISTORY_TABLE} VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    settlement.settlement_id,
                    _subject_fingerprint(manifest),
                    _key_fingerprint(manifest.product_key),
                    manifest.product_key.opportunity_identity.opportunity_id,
                    manifest.marketplace,
                    manifest.seller_account_reference,
                    manifest.external_report_reference,
                    settlement.revision,
                    settlement.predecessor_settlement_id,
                    settlement.state.value,
                    settlement.period_start.isoformat(),
                    settlement.period_end.isoformat(),
                    settlement.fulfilled_outbound_quantity,
                    encoded,
                    _integrity(encoded),
                    settlement.policy_name,
                    settlement.policy_version,
                    settlement.schema_version,
                    receipt.committed_at.isoformat(),
                ),
            )
        except sqlite3.IntegrityError as error:
            tip = self.get_chain_tip_for_subject(manifest)
            if tip is not None and tip.state is ActualSaleSettlementState.COMPLETE:
                raise ActualSaleSettlementTerminalConflictError(
                    "COMPLETE actual sale settlement is terminal"
                ) from error
            raise ActualSaleSettlementRevisionConflictError(
                "actual sale settlement cardinality conflict"
            ) from error
        except sqlite3.Error as error:
            raise ActualSaleSettlementHistoryError(
                "actual sale history insert failed"
            ) from error

    def _insert_receipt(self, receipt: ActualSaleSettlementReceipt) -> None:
        try:
            self._connection.execute(
                f"INSERT INTO {RECEIPT_TABLE} VALUES(?,?,?,?,?,?)",
                (
                    receipt.command_id,
                    receipt.settlement_id,
                    receipt.command_fingerprint,
                    receipt.committed_at.isoformat(),
                    receipt.schema_version,
                    receipt.committed_at.isoformat(),
                ),
            )
        except sqlite3.Error as error:
            raise ActualSaleSettlementReceiptError(
                "actual sale receipt insert failed"
            ) from error

    def _commit(self) -> None:
        self._connection.commit()

    def save(self, command, settlement, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._connection.commit(); return replay
            self._validate_write(command, settlement, receipt)
            self._validate_source(settlement)
            tip = self.get_chain_tip_for_subject(settlement.source_manifest)
            if tip is None:
                if settlement.revision != 1 or settlement.predecessor_settlement_id is not None:
                    raise ActualSaleSettlementRevisionConflictError("first actual sale revision must be revision 1")
            else:
                if tip.state is ActualSaleSettlementState.COMPLETE:
                    raise ActualSaleSettlementTerminalConflictError("COMPLETE actual sale settlement is terminal")
                if settlement.predecessor_settlement_id != tip.settlement_id or settlement.revision != tip.revision + 1:
                    raise ActualSaleSettlementRevisionConflictError("actual sale settlement revision would fork")
            if settlement.state is ActualSaleSettlementState.COMPLETE:
                self._validate_complete_safety(settlement)
            self._insert_history(settlement, receipt)
            self._insert_receipt(receipt)
            try: self._commit()
            except sqlite3.Error as error: raise ActualSaleSettlementCommitError("actual sale settlement commit failed") from error
            return ActualSaleSettlementPublication(settlement, receipt, False)
        except Exception:
            if self._connection.in_transaction: self._connection.rollback()
            raise

    def close(self):
        if self._connection.in_transaction: self._connection.rollback()
        if self._owns_connection: self._connection.close()
    def __enter__(self): return self
    def __exit__(self, exc_type, exc, traceback): self.close(); return False


__all__ = [name for name in globals() if name.startswith(("SQLiteActualSale", "ActualSaleSettlement", "MalformedActualSale", "UnsupportedActualSale"))]
