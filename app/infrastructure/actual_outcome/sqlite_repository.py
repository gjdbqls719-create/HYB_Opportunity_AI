"""Append-only SQLite persistence for immutable Actual Outcomes."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.actual_outcome import (
    CalculateActualOutcomeCommand,
    ActualOutcomePublication,
    ActualOutcomeReceipt,
    ActualOutcomeReplayConflictError,
    ActualOutcomeSourceConflictError,
    actual_outcome_scope_fingerprint,
    product_key_from_acquisition,
    _snapshot,
)
from app.domain.capital import (
    ACTUAL_OUTCOME_RECEIPT_SCHEMA_VERSION,
    ACTUAL_OUTCOME_SCHEMA_VERSION,
    ACTUAL_OUTCOME_SOURCE_MANIFEST_SCHEMA_VERSION,
    ActualAcquisitionCostCategory,
    ActualOutcome,
    ActualOutcomeAcquisitionAllocation,
    ActualOutcomeBlockingReason,
    ActualOutcomeInventoryResolution,
    ActualOutcomeMetric,
    ActualOutcomeSaleComponent,
    ActualOutcomeSaleWindow,
    ActualOutcomeSourceManifest,
    ActualOutcomeState,
    ActualSaleMonetaryCategory,
    OwnedInventoryProductKey,
)
from app.domain.decision_engine import OpportunityIdentity
from app.infrastructure.actual_acquisition_settlement import SQLiteActualAcquisitionSettlementRepository
from app.infrastructure.actual_sale_settlement import SQLiteActualSaleSettlementRepository
from app.infrastructure.goods_receipt import SQLiteGoodsReceiptRepository


HISTORY_TABLE = "actual_outcome_history"
RECEIPT_TABLE = "actual_outcome_receipts"


class ActualOutcomePersistenceError(RuntimeError): pass
class ActualOutcomeHistoryError(ActualOutcomePersistenceError): pass
class ActualOutcomeReceiptError(ActualOutcomePersistenceError): pass
class ActualOutcomeCommitError(ActualOutcomePersistenceError): pass
class MalformedActualOutcomePersistenceError(ActualOutcomePersistenceError): pass
class UnsupportedActualOutcomeVersionError(MalformedActualOutcomePersistenceError): pass


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


def _key(value: OwnedInventoryProductKey) -> dict[str, object]:
    identity = value.opportunity_identity
    return {
        "opportunity_id": identity.opportunity_id,
        "discovery_reference": identity.discovery_reference,
        "source_platform": value.source_platform,
        "supplier_id": value.supplier_id,
        "sourcing_product_id": value.sourcing_product_id,
        "external_product_reference": value.external_product_reference,
        "option_reference": value.option_reference,
        "sku_reference": value.sku_reference,
        "quantity_unit": value.quantity_unit,
    }


def _load_key(value: object) -> OwnedInventoryProductKey:
    keys = {"opportunity_id", "discovery_reference", "source_platform", "supplier_id", "sourcing_product_id", "external_product_reference", "option_reference", "sku_reference", "quantity_unit"}
    data = _exact(value, keys, "Actual Outcome product key")
    return OwnedInventoryProductKey(
        OpportunityIdentity(data["opportunity_id"], data["discovery_reference"]),
        data["source_platform"], data["supplier_id"], data["sourcing_product_id"],
        data["external_product_reference"], data["option_reference"],
        data["sku_reference"], data["quantity_unit"],
    )


def _manifest(value: ActualOutcomeSourceManifest) -> dict[str, object]:
    return {
        "product_key": _key(value.product_key),
        "purchase_execution_record_id": value.purchase_execution_record_id,
        "actual_acquisition_settlement_id": value.actual_acquisition_settlement_id,
        "goods_receipt_ids": list(value.goods_receipt_ids),
        "actual_sale_settlement_ids": list(value.actual_sale_settlement_ids),
        "sale_windows": [{"settlement_id": v.settlement_id, "period_start": v.period_start.isoformat(), "period_end": v.period_end.isoformat()} for v in value.sale_windows],
        "executed_quantity": value.executed_quantity,
        "received_quantity": value.received_quantity,
        "sellable_received_quantity": value.sellable_received_quantity,
        "damaged_quantity": value.damaged_quantity,
        "sold_quantity": value.sold_quantity,
        "remaining_sellable_quantity": value.remaining_sellable_quantity,
        "returned_quantity": value.returned_quantity,
        "unreceived_quantity": value.unreceived_quantity,
        "quantity_unit": value.quantity_unit,
        "currency": value.currency,
        "evaluation_start": value.evaluation_start.isoformat(),
        "evaluation_through": value.evaluation_through.isoformat(),
        "acquisition_policy_version": value.acquisition_policy_version,
        "acquisition_schema_version": value.acquisition_schema_version,
        "goods_receipt_policy_versions": list(value.goods_receipt_policy_versions),
        "goods_receipt_schema_versions": list(value.goods_receipt_schema_versions),
        "sale_policy_versions": list(value.sale_policy_versions),
        "sale_schema_versions": list(value.sale_schema_versions),
        "acquisition_source_snapshot": value.acquisition_source_snapshot,
        "goods_receipt_source_snapshots": list(value.goods_receipt_source_snapshots),
        "sale_source_snapshots": list(value.sale_source_snapshots),
        "schema_version": value.schema_version,
    }


_MANIFEST_KEYS = {
    "product_key", "purchase_execution_record_id", "actual_acquisition_settlement_id",
    "goods_receipt_ids", "actual_sale_settlement_ids", "sale_windows",
    "executed_quantity", "received_quantity", "sellable_received_quantity",
    "damaged_quantity", "sold_quantity", "remaining_sellable_quantity",
    "returned_quantity", "unreceived_quantity", "quantity_unit", "currency",
    "evaluation_start", "evaluation_through", "acquisition_policy_version",
    "acquisition_schema_version", "goods_receipt_policy_versions",
    "goods_receipt_schema_versions", "sale_policy_versions", "sale_schema_versions",
    "acquisition_source_snapshot", "goods_receipt_source_snapshots", "sale_source_snapshots",
    "schema_version",
}


def _load_manifest(value: object) -> ActualOutcomeSourceManifest:
    data = _exact(value, _MANIFEST_KEYS, "Actual Outcome source manifest")
    if data["schema_version"] != ACTUAL_OUTCOME_SOURCE_MANIFEST_SCHEMA_VERSION:
        raise UnsupportedActualOutcomeVersionError("unsupported Actual Outcome source manifest version")
    list_names = ("goods_receipt_ids", "actual_sale_settlement_ids", "sale_windows", "goods_receipt_policy_versions", "goods_receipt_schema_versions", "sale_policy_versions", "sale_schema_versions", "goods_receipt_source_snapshots", "sale_source_snapshots")
    if any(not isinstance(data[name], list) for name in list_names):
        raise ValueError("Actual Outcome manifest collection must be list")
    windows = []
    for raw in data["sale_windows"]:
        window = _exact(raw, {"settlement_id", "period_start", "period_end"}, "Actual Outcome sale window")
        windows.append(ActualOutcomeSaleWindow(window["settlement_id"], _datetime(window["period_start"], "period_start"), _datetime(window["period_end"], "period_end")))
    return ActualOutcomeSourceManifest(
        _load_key(data["product_key"]), data["purchase_execution_record_id"],
        data["actual_acquisition_settlement_id"], tuple(data["goods_receipt_ids"]),
        tuple(data["actual_sale_settlement_ids"]), tuple(windows),
        data["executed_quantity"], data["received_quantity"], data["sellable_received_quantity"],
        data["damaged_quantity"], data["sold_quantity"], data["remaining_sellable_quantity"],
        data["returned_quantity"], data["unreceived_quantity"], data["quantity_unit"],
        data["currency"], _datetime(data["evaluation_start"], "evaluation_start"),
        _datetime(data["evaluation_through"], "evaluation_through"),
        data["acquisition_policy_version"], data["acquisition_schema_version"],
        tuple(data["goods_receipt_policy_versions"]), tuple(data["goods_receipt_schema_versions"]),
        tuple(data["sale_policy_versions"]), tuple(data["sale_schema_versions"]),
        data["acquisition_source_snapshot"], tuple(data["goods_receipt_source_snapshots"]),
        tuple(data["sale_source_snapshots"]), data["schema_version"],
    )


def _payload(value: ActualOutcome) -> str:
    return _dump({
        "outcome_id": value.outcome_id,
        "source_manifest": _manifest(value.source_manifest),
        "state": value.state.value,
        "inventory_resolution": value.inventory_resolution.value,
        "blocking_reasons": [v.value for v in value.blocking_reasons],
        "acquisition_allocations": [{
            "category": v.category.value, "batch_amount": str(v.batch_amount),
            "per_executed_unit": str(v.per_executed_unit), "sold_cogs": str(v.sold_cogs),
            "remaining_sellable_basis": str(v.remaining_sellable_basis),
            "damaged_loss": str(v.damaged_loss), "unreceived_exposure": str(v.unreceived_exposure),
        } for v in value.acquisition_allocations],
        "sale_components": [{"category": v.category.value, "amount": str(v.amount)} for v in value.sale_components],
        "other_sale_side_costs": None if value.other_sale_side_costs is None else str(value.other_sale_side_costs),
        "acquisition_batch_total": None if value.acquisition_batch_total is None else str(value.acquisition_batch_total),
        "actual_cogs": None if value.actual_cogs is None else str(value.actual_cogs),
        "remaining_sellable_inventory_cost_basis": None if value.remaining_sellable_inventory_cost_basis is None else str(value.remaining_sellable_inventory_cost_basis),
        "damaged_acquisition_loss": None if value.damaged_acquisition_loss is None else str(value.damaged_acquisition_loss),
        "unreceived_acquisition_cost_basis": None if value.unreceived_acquisition_cost_basis is None else str(value.unreceived_acquisition_cost_basis),
        "gross_realized_merchandise_revenue": None if value.gross_realized_merchandise_revenue is None else str(value.gross_realized_merchandise_revenue),
        "recognized_sale_credits": None if value.recognized_sale_credits is None else str(value.recognized_sale_credits),
        "recognized_sale_side_costs": None if value.recognized_sale_side_costs is None else str(value.recognized_sale_side_costs),
        "net_realized_sale_contribution": None if value.net_realized_sale_contribution is None else str(value.net_realized_sale_contribution),
        "actual_realized_profit": None if value.actual_realized_profit is None else str(value.actual_realized_profit),
        "actual_margin": {"available": value.actual_margin.available, "value": None if value.actual_margin.value is None else str(value.actual_margin.value)},
        "actual_acquisition_roi": {"available": value.actual_acquisition_roi.available, "value": None if value.actual_acquisition_roi.value is None else str(value.actual_acquisition_roi.value)},
        "known_payout_total": None if value.known_payout_total is None else str(value.known_payout_total),
        "payout_reconciliation_states": list(value.payout_reconciliation_states),
        "requested_at": value.requested_at.isoformat(), "calculated_at": value.calculated_at.isoformat(),
        "committed_at": value.committed_at.isoformat(), "policy_name": value.policy_name,
        "policy_version": value.policy_version, "policy_precision": value.policy_precision,
        "policy_rounding": value.policy_rounding, "schema_version": value.schema_version,
    })


_PAYLOAD_KEYS = {
    "outcome_id", "source_manifest", "state", "inventory_resolution", "blocking_reasons",
    "acquisition_allocations", "sale_components", "other_sale_side_costs",
    "acquisition_batch_total", "actual_cogs", "remaining_sellable_inventory_cost_basis",
    "damaged_acquisition_loss", "unreceived_acquisition_cost_basis",
    "gross_realized_merchandise_revenue", "recognized_sale_credits",
    "recognized_sale_side_costs", "net_realized_sale_contribution", "actual_realized_profit",
    "actual_margin", "actual_acquisition_roi", "known_payout_total",
    "payout_reconciliation_states", "requested_at", "calculated_at", "committed_at",
    "policy_name", "policy_version", "policy_precision", "policy_rounding", "schema_version",
}


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(value)


class SQLiteActualOutcomeRepository:
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
        self._acquisition = SQLiteActualAcquisitionSettlementRepository(connection=self._connection)
        self._sale = SQLiteActualSaleSettlementRepository(connection=self._connection)
        self._goods = SQLiteGoodsReceiptRepository(connection=self._connection)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(f"""CREATE TABLE IF NOT EXISTS {HISTORY_TABLE}(
                outcome_id TEXT PRIMARY KEY, scope_fingerprint TEXT NOT NULL UNIQUE,
                opportunity_id TEXT NOT NULL, state TEXT NOT NULL,
                payload_json TEXT NOT NULL, integrity_fingerprint TEXT NOT NULL,
                policy_name TEXT NOT NULL, policy_version TEXT NOT NULL,
                schema_version TEXT NOT NULL, inserted_at TEXT NOT NULL)""")
            self._connection.execute(f"""CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE}(
                command_id TEXT PRIMARY KEY, outcome_id TEXT NOT NULL,
                command_fingerprint TEXT NOT NULL, committed_at TEXT NOT NULL,
                schema_version TEXT NOT NULL, inserted_at TEXT NOT NULL,
                FOREIGN KEY(outcome_id) REFERENCES {HISTORY_TABLE}(outcome_id))""")
            for table in (HISTORY_TABLE, RECEIPT_TABLE):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(f"CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END")

    def get_actual_acquisition_settlement(self, settlement_id: str):
        return self._acquisition.get_settlement(settlement_id)

    def get_actual_sale_settlement(self, settlement_id: str):
        return self._sale.get_settlement(settlement_id)

    def list_complete_settlements_for_product(self, product_key):
        return self._sale.list_complete_settlements_for_product(product_key)

    def list_goods_receipts_for_opportunity(self, opportunity_id: str):
        return self._goods.list_goods_receipts_for_opportunity(opportunity_id)

    def _row(self, outcome_id: str):
        try:
            return self._connection.execute(f"SELECT * FROM {HISTORY_TABLE} WHERE outcome_id=?", (outcome_id,)).fetchone()
        except sqlite3.Error as error:
            raise ActualOutcomeHistoryError("Actual Outcome query failed") from error

    def _load_row(self, row) -> ActualOutcome:
        try:
            if row["schema_version"] != ACTUAL_OUTCOME_SCHEMA_VERSION:
                raise UnsupportedActualOutcomeVersionError("unsupported Actual Outcome version")
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _integrity(encoded) != row["integrity_fingerprint"]:
                raise ValueError("Actual Outcome integrity mismatch")
            data = _exact(json.loads(encoded), _PAYLOAD_KEYS, "Actual Outcome payload")
            if data["schema_version"] != ACTUAL_OUTCOME_SCHEMA_VERSION:
                raise UnsupportedActualOutcomeVersionError("unsupported Actual Outcome payload version")
            if not all(isinstance(data[name], list) for name in ("blocking_reasons", "acquisition_allocations", "sale_components", "payout_reconciliation_states")):
                raise ValueError("Actual Outcome payload collection is malformed")
            allocations = []
            for raw in data["acquisition_allocations"]:
                value = _exact(raw, {"category", "batch_amount", "per_executed_unit", "sold_cogs", "remaining_sellable_basis", "damaged_loss", "unreceived_exposure"}, "Actual Outcome acquisition allocation")
                allocations.append(ActualOutcomeAcquisitionAllocation(ActualAcquisitionCostCategory(value["category"]), Decimal(value["batch_amount"]), Decimal(value["per_executed_unit"]), Decimal(value["sold_cogs"]), Decimal(value["remaining_sellable_basis"]), Decimal(value["damaged_loss"]), Decimal(value["unreceived_exposure"])))
            components = []
            for raw in data["sale_components"]:
                value = _exact(raw, {"category", "amount"}, "Actual Outcome sale component")
                components.append(ActualOutcomeSaleComponent(ActualSaleMonetaryCategory(value["category"]), Decimal(value["amount"])))
            margin = _exact(data["actual_margin"], {"available", "value"}, "Actual Outcome margin")
            roi = _exact(data["actual_acquisition_roi"], {"available", "value"}, "Actual Outcome ROI")
            outcome = ActualOutcome(
                data["outcome_id"], _load_manifest(data["source_manifest"]), ActualOutcomeState(data["state"]),
                ActualOutcomeInventoryResolution(data["inventory_resolution"]),
                tuple(ActualOutcomeBlockingReason(v) for v in data["blocking_reasons"]),
                tuple(allocations), tuple(components), _optional_decimal(data["other_sale_side_costs"]),
                _optional_decimal(data["acquisition_batch_total"]), _optional_decimal(data["actual_cogs"]),
                _optional_decimal(data["remaining_sellable_inventory_cost_basis"]),
                _optional_decimal(data["damaged_acquisition_loss"]), _optional_decimal(data["unreceived_acquisition_cost_basis"]),
                _optional_decimal(data["gross_realized_merchandise_revenue"]), _optional_decimal(data["recognized_sale_credits"]),
                _optional_decimal(data["recognized_sale_side_costs"]), _optional_decimal(data["net_realized_sale_contribution"]),
                _optional_decimal(data["actual_realized_profit"]),
                ActualOutcomeMetric(margin["available"], _optional_decimal(margin["value"])),
                ActualOutcomeMetric(roi["available"], _optional_decimal(roi["value"])),
                _optional_decimal(data["known_payout_total"]), tuple(data["payout_reconciliation_states"]),
                _datetime(data["requested_at"], "requested_at"), _datetime(data["calculated_at"], "calculated_at"),
                _datetime(data["committed_at"], "committed_at"), data["policy_name"], data["policy_version"],
                data["policy_precision"], data["policy_rounding"], data["schema_version"],
            )
            manifest = outcome.source_manifest
            if any((outcome.outcome_id != row["outcome_id"], actual_outcome_scope_fingerprint(manifest) != row["scope_fingerprint"], manifest.product_key.opportunity_identity.opportunity_id != row["opportunity_id"], outcome.state.value != row["state"], outcome.policy_name != row["policy_name"], outcome.policy_version != row["policy_version"])):
                raise ValueError("Actual Outcome columns differ from payload")
            return outcome
        except UnsupportedActualOutcomeVersionError:
            raise
        except Exception as error:
            raise MalformedActualOutcomePersistenceError("persisted Actual Outcome is malformed") from error

    def get_outcome(self, outcome_id: str):
        row = self._row(outcome_id)
        return None if row is None else self._load_row(row)

    def find_by_scope(self, scope_fingerprint: str):
        try:
            row = self._connection.execute(f"SELECT * FROM {HISTORY_TABLE} WHERE scope_fingerprint=?", (scope_fingerprint,)).fetchone()
        except sqlite3.Error as error:
            raise ActualOutcomeHistoryError("Actual Outcome scope query failed") from error
        return None if row is None else self._load_row(row)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?", (command_id,)).fetchone()
        except sqlite3.Error as error:
            raise ActualOutcomeReceiptError("Actual Outcome receipt query failed") from error

    def _load_receipt(self, row) -> ActualOutcomeReceipt:
        try:
            if row["schema_version"] != ACTUAL_OUTCOME_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedActualOutcomeVersionError("unsupported Actual Outcome receipt version")
            receipt = ActualOutcomeReceipt(row["command_id"], row["outcome_id"], row["command_fingerprint"], _datetime(row["committed_at"], "committed_at"), row["schema_version"])
            if self.get_outcome(receipt.outcome_id) is None:
                raise ValueError("Actual Outcome receipt is orphaned")
            return receipt
        except UnsupportedActualOutcomeVersionError:
            raise
        except Exception as error:
            raise MalformedActualOutcomePersistenceError("persisted Actual Outcome receipt is malformed") from error

    def validate_replay(self, command_id: str, fingerprint: str):
        row = self._receipt_row(command_id)
        if row is None:
            return None
        receipt = self._load_receipt(row)
        if receipt.command_fingerprint != fingerprint:
            raise ActualOutcomeReplayConflictError("Actual Outcome command payload conflicts")
        return ActualOutcomePublication(self.get_outcome(receipt.outcome_id), receipt, True)

    def _validate_source(self, outcome: ActualOutcome) -> None:
        manifest = outcome.source_manifest
        acquisition = self.get_actual_acquisition_settlement(manifest.actual_acquisition_settlement_id)
        if acquisition is None or acquisition.source_manifest.purchase_execution_record_id != manifest.purchase_execution_record_id or product_key_from_acquisition(acquisition) != manifest.product_key or _snapshot(acquisition) != manifest.acquisition_source_snapshot:
            raise ActualOutcomeSourceConflictError("Actual Outcome acquisition source lineage differs")
        for window, snapshot in zip(manifest.sale_windows, manifest.sale_source_snapshots, strict=True):
            sale = self.get_actual_sale_settlement(window.settlement_id)
            if sale is None or sale.source_manifest.product_key != manifest.product_key or sale.period_start != window.period_start or sale.period_end != window.period_end or _snapshot(sale) != snapshot:
                raise ActualOutcomeSourceConflictError("Actual Outcome sale source lineage differs")
        for record_id, snapshot in zip(manifest.goods_receipt_ids, manifest.goods_receipt_source_snapshots, strict=True):
            receipt = self._goods.get_record(record_id)
            if receipt is None or receipt.source_manifest.purchase_execution_record_id != manifest.purchase_execution_record_id or receipt.inspected_at >= manifest.evaluation_through or _snapshot(receipt) != snapshot:
                raise ActualOutcomeSourceConflictError("Actual Outcome Goods Receipt lineage differs")

    @staticmethod
    def _validate_write(command, outcome, receipt, scope_fingerprint: str) -> None:
        if not isinstance(command, CalculateActualOutcomeCommand) or not isinstance(outcome, ActualOutcome) or not isinstance(receipt, ActualOutcomeReceipt):
            raise TypeError("Actual Outcome write values have unsupported type")
        manifest = outcome.source_manifest
        if any((receipt.command_id != command.command_id, receipt.command_fingerprint != command.fingerprint, receipt.outcome_id != outcome.outcome_id, manifest.product_key.opportunity_identity.opportunity_id != command.opportunity_id, manifest.actual_acquisition_settlement_id != command.actual_acquisition_settlement_id, manifest.actual_sale_settlement_ids != command.actual_sale_settlement_ids, outcome.requested_at != command.requested_at, scope_fingerprint != actual_outcome_scope_fingerprint(manifest))):
            raise ActualOutcomeReplayConflictError("command, Actual Outcome, and receipt differ")

    def _insert_history(self, outcome: ActualOutcome, scope_fingerprint: str) -> None:
        encoded = _payload(outcome)
        try:
            self._connection.execute(f"INSERT INTO {HISTORY_TABLE} VALUES(?,?,?,?,?,?,?,?,?,?)", (
                outcome.outcome_id, scope_fingerprint,
                outcome.source_manifest.product_key.opportunity_identity.opportunity_id,
                outcome.state.value, encoded, _integrity(encoded), outcome.policy_name,
                outcome.policy_version, outcome.schema_version, outcome.committed_at.isoformat(),
            ))
        except sqlite3.IntegrityError as error:
            raise ActualOutcomeSourceConflictError("Actual Outcome scope or identity already exists") from error
        except sqlite3.Error as error:
            raise ActualOutcomeHistoryError("Actual Outcome history insert failed") from error

    def _insert_receipt(self, receipt: ActualOutcomeReceipt) -> None:
        try:
            self._connection.execute(f"INSERT INTO {RECEIPT_TABLE} VALUES(?,?,?,?,?,?)", (
                receipt.command_id, receipt.outcome_id, receipt.command_fingerprint,
                receipt.committed_at.isoformat(), receipt.schema_version, receipt.committed_at.isoformat(),
            ))
        except sqlite3.Error as error:
            raise ActualOutcomeReceiptError("Actual Outcome receipt insert failed") from error

    def _commit(self) -> None:
        self._connection.commit()

    def save(self, command, outcome, receipt, scope_fingerprint: str):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._connection.commit()
                return replay
            self._validate_write(command, outcome, receipt, scope_fingerprint)
            self._validate_source(outcome)
            existing = self.find_by_scope(scope_fingerprint)
            aliased = existing is not None
            if existing is None:
                self._insert_history(outcome, scope_fingerprint)
                persisted = outcome
                persisted_receipt = receipt
            else:
                persisted = existing
                persisted_receipt = ActualOutcomeReceipt(receipt.command_id, existing.outcome_id, receipt.command_fingerprint, receipt.committed_at)
            self._insert_receipt(persisted_receipt)
            try:
                self._commit()
            except sqlite3.Error as error:
                raise ActualOutcomeCommitError("Actual Outcome commit failed") from error
            return ActualOutcomePublication(persisted, persisted_receipt, False, aliased)
        except Exception:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise

    def close(self) -> None:
        if self._connection.in_transaction:
            self._connection.rollback()
        if self._owns_connection:
            self._connection.close()

    def __enter__(self): return self
    def __exit__(self, exc_type, exc, traceback): self.close(); return False


__all__ = [name for name in globals() if name.startswith(("SQLiteActualOutcome", "ActualOutcome", "MalformedActualOutcome", "UnsupportedActualOutcome"))]
