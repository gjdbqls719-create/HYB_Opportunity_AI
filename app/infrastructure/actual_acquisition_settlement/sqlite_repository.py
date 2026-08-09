"""Append-only SQLite persistence for Actual Acquisition Settlement revisions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.actual_acquisition_settlement import (
    ACTUAL_ACQUISITION_RECEIPT_SCHEMA_VERSION,
    ActualAcquisitionSettlementPublication,
    ActualAcquisitionSettlementReceipt,
    ActualAcquisitionSettlementReplayConflictError,
    ActualAcquisitionSettlementRevisionConflictError,
    ActualAcquisitionSettlementTerminalConflictError,
    AdmitActualAcquisitionSettlementCommand,
    actual_acquisition_manifest_from_purchase,
)
from app.domain.capital import (
    ACTUAL_ACQUISITION_EVIDENCE_SCHEMA_VERSION,
    ACTUAL_ACQUISITION_FX_SCHEMA_VERSION,
    ACTUAL_ACQUISITION_SETTLEMENT_SCHEMA_VERSION,
    ACTUAL_ACQUISITION_SOURCE_MANIFEST_SCHEMA_VERSION,
    ActualAcquisitionBlockingReason,
    ActualAcquisitionCostCategory,
    ActualAcquisitionCostFact,
    ActualAcquisitionEvidenceReference,
    ActualAcquisitionFXSettlement,
    ActualAcquisitionFactAvailability,
    ActualAcquisitionSettlement,
    ActualAcquisitionSettlementSourceManifest,
    ActualAcquisitionSettlementState,
    NormalizedActualAcquisitionCategory,
    OtherMandatoryAcquisitionCosts,
    OtherMandatoryAcquisitionCostItem,
)
from app.domain.decision_engine import OpportunityIdentity
from app.infrastructure.purchase_execution import SQLitePurchaseExecutionRepository


HISTORY_TABLE = "actual_acquisition_settlement_history"
RECEIPT_TABLE = "actual_acquisition_settlement_receipts"
REVISION_INDEX = "ux_actual_acquisition_settlement_revision"
PREDECESSOR_INDEX = "ux_actual_acquisition_settlement_predecessor"
COMPLETE_INDEX = "ux_actual_acquisition_settlement_complete"


class ActualAcquisitionSettlementPersistenceError(RuntimeError):
    pass


class ActualAcquisitionSettlementHistoryError(ActualAcquisitionSettlementPersistenceError):
    pass


class ActualAcquisitionSettlementReceiptError(ActualAcquisitionSettlementPersistenceError):
    pass


class ActualAcquisitionSettlementCommitError(ActualAcquisitionSettlementPersistenceError):
    pass


class MalformedActualAcquisitionSettlementPersistenceError(
    ActualAcquisitionSettlementPersistenceError
):
    pass


class UnsupportedActualAcquisitionSettlementVersionError(
    MalformedActualAcquisitionSettlementPersistenceError
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


def _optional_decimal(value: object, name: str) -> Decimal | None:
    return None if value is None else _decimal(value, name)


def _exact(value: object, keys: set[str], name: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{name} has unsupported fields")
    return value


def _evidence(value: ActualAcquisitionEvidenceReference) -> dict[str, object]:
    return {
        "reference": value.reference,
        "observed_at": value.observed_at.isoformat(),
        "operator_id": value.operator_id,
        "collection_method": value.collection_method,
        "schema_version": value.schema_version,
    }


def _load_evidence(value: object) -> ActualAcquisitionEvidenceReference:
    data = _exact(
        value,
        {"reference", "observed_at", "operator_id", "collection_method", "schema_version"},
        "actual acquisition evidence",
    )
    if data["schema_version"] != ACTUAL_ACQUISITION_EVIDENCE_SCHEMA_VERSION:
        raise UnsupportedActualAcquisitionSettlementVersionError(
            "unsupported actual acquisition evidence version"
        )
    return ActualAcquisitionEvidenceReference(
        data["reference"],
        _datetime(data["observed_at"], "evidence observed_at"),
        data["operator_id"],
        data["collection_method"],
        data["schema_version"],
    )


def _optional_evidence(value: object) -> ActualAcquisitionEvidenceReference | None:
    return None if value is None else _load_evidence(value)


def _fx(value: ActualAcquisitionFXSettlement) -> dict[str, object]:
    return {
        "source_currency": value.source_currency,
        "target_currency": value.target_currency,
        "original_amount": format(value.original_amount, "f"),
        "target_amount": None if value.target_amount is None else format(value.target_amount, "f"),
        "applied_rate": None if value.applied_rate is None else format(value.applied_rate, "f"),
        "provider": value.provider,
        "payment_channel": value.payment_channel,
        "external_reference": value.external_reference,
        "settled_at": value.settled_at.isoformat(),
        "evidence": _evidence(value.evidence),
        "schema_version": value.schema_version,
    }


def _load_fx(value: object) -> ActualAcquisitionFXSettlement:
    data = _exact(
        value,
        {
            "source_currency", "target_currency", "original_amount", "target_amount",
            "applied_rate", "provider", "payment_channel", "external_reference",
            "settled_at", "evidence", "schema_version",
        },
        "actual acquisition FX",
    )
    if data["schema_version"] != ACTUAL_ACQUISITION_FX_SCHEMA_VERSION:
        raise UnsupportedActualAcquisitionSettlementVersionError(
            "unsupported actual acquisition FX version"
        )
    return ActualAcquisitionFXSettlement(
        source_currency=data["source_currency"],
        target_currency=data["target_currency"],
        original_amount=_decimal(data["original_amount"], "FX original_amount"),
        target_amount=_optional_decimal(data["target_amount"], "FX target_amount"),
        applied_rate=_optional_decimal(data["applied_rate"], "FX applied_rate"),
        provider=data["provider"],
        payment_channel=data["payment_channel"],
        external_reference=data["external_reference"],
        settled_at=_datetime(data["settled_at"], "FX settled_at"),
        evidence=_load_evidence(data["evidence"]),
        schema_version=data["schema_version"],
    )


def _optional_fx(value: object) -> ActualAcquisitionFXSettlement | None:
    return None if value is None else _load_fx(value)


def _fact(value: ActualAcquisitionCostFact) -> dict[str, object]:
    return {
        "category": value.category.value,
        "availability": value.availability.value,
        "amount": None if value.amount is None else format(value.amount, "f"),
        "currency": value.currency,
        "settled_at": None if value.settled_at is None else value.settled_at.isoformat(),
        "evidence": None if value.evidence is None else _evidence(value.evidence),
        "unresolved_reason": value.unresolved_reason,
        "actual_fx": None if value.actual_fx is None else _fx(value.actual_fx),
    }


def _load_fact(value: object) -> ActualAcquisitionCostFact:
    data = _exact(
        value,
        {"category", "availability", "amount", "currency", "settled_at", "evidence", "unresolved_reason", "actual_fx"},
        "actual acquisition cost fact",
    )
    return ActualAcquisitionCostFact(
        category=data["category"],
        availability=data["availability"],
        amount=_optional_decimal(data["amount"], "cost amount"),
        currency=data["currency"],
        settled_at=None if data["settled_at"] is None else _datetime(data["settled_at"], "cost settled_at"),
        evidence=_optional_evidence(data["evidence"]),
        unresolved_reason=data["unresolved_reason"],
        actual_fx=_optional_fx(data["actual_fx"]),
    )


def _other_item(value: OtherMandatoryAcquisitionCostItem) -> dict[str, object]:
    return {
        "scope": value.scope,
        "amount": format(value.amount, "f"),
        "currency": value.currency,
        "settled_at": value.settled_at.isoformat(),
        "evidence": _evidence(value.evidence),
        "actual_fx": None if value.actual_fx is None else _fx(value.actual_fx),
    }


def _load_other_item(value: object) -> OtherMandatoryAcquisitionCostItem:
    data = _exact(
        value,
        {"scope", "amount", "currency", "settled_at", "evidence", "actual_fx"},
        "other mandatory cost item",
    )
    return OtherMandatoryAcquisitionCostItem(
        scope=data["scope"],
        amount=_decimal(data["amount"], "other amount"),
        currency=data["currency"],
        settled_at=_datetime(data["settled_at"], "other settled_at"),
        evidence=_load_evidence(data["evidence"]),
        actual_fx=_optional_fx(data["actual_fx"]),
    )


def _other(value: OtherMandatoryAcquisitionCosts) -> dict[str, object]:
    return {
        "availability": value.availability.value,
        "items": [_other_item(item) for item in value.items],
        "scope_evidence": None if value.scope_evidence is None else _evidence(value.scope_evidence),
        "unresolved_reason": value.unresolved_reason,
    }


def _load_other(value: object) -> OtherMandatoryAcquisitionCosts:
    data = _exact(
        value,
        {"availability", "items", "scope_evidence", "unresolved_reason"},
        "other mandatory costs",
    )
    if not isinstance(data["items"], list):
        raise ValueError("other mandatory items must be a list")
    return OtherMandatoryAcquisitionCosts(
        availability=data["availability"],
        items=tuple(_load_other_item(item) for item in data["items"]),
        scope_evidence=_optional_evidence(data["scope_evidence"]),
        unresolved_reason=data["unresolved_reason"],
    )


def _manifest(value: ActualAcquisitionSettlementSourceManifest) -> dict[str, object]:
    return {
        "opportunity_identity": {
            "opportunity_id": value.opportunity_identity.opportunity_id,
            "discovery_reference": value.opportunity_identity.discovery_reference,
        },
        "purchase_execution_record_id": value.purchase_execution_record_id,
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
        "executed_quantity": value.executed_quantity,
        "executed_quantity_unit": value.executed_quantity_unit,
        "external_order_reference": value.external_order_reference,
        "purchase_executed_at": value.purchase_executed_at.isoformat(),
        "purchase_policy_name": value.purchase_policy_name,
        "purchase_policy_version": value.purchase_policy_version,
        "purchase_record_schema_version": value.purchase_record_schema_version,
        "schema_version": value.schema_version,
    }


_MANIFEST_KEYS = {
    "opportunity_identity", "purchase_execution_record_id", "real_money_execution_intent_id",
    "founder_capital_approval_id", "capital_gate_id", "capital_requirement_id",
    "intended_order_quantity_id", "sourcing_admission_id", "sourcing_admission_revision",
    "supplier_id", "source_platform", "external_supplier_reference", "sourcing_product_id",
    "external_product_reference", "option_reference", "sku_reference", "quote_id",
    "quote_revision", "executed_quantity", "executed_quantity_unit", "external_order_reference",
    "purchase_executed_at", "purchase_policy_name", "purchase_policy_version",
    "purchase_record_schema_version", "schema_version",
}


def _load_manifest(value: object) -> ActualAcquisitionSettlementSourceManifest:
    data = _exact(value, _MANIFEST_KEYS, "actual acquisition source manifest")
    if data["schema_version"] != ACTUAL_ACQUISITION_SOURCE_MANIFEST_SCHEMA_VERSION:
        raise UnsupportedActualAcquisitionSettlementVersionError(
            "unsupported actual acquisition source manifest version"
        )
    identity = _exact(
        data["opportunity_identity"],
        {"opportunity_id", "discovery_reference"},
        "Opportunity identity",
    )
    return ActualAcquisitionSettlementSourceManifest(
        opportunity_identity=OpportunityIdentity(identity["opportunity_id"], identity["discovery_reference"]),
        purchase_execution_record_id=data["purchase_execution_record_id"],
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
        executed_quantity=data["executed_quantity"],
        executed_quantity_unit=data["executed_quantity_unit"],
        external_order_reference=data["external_order_reference"],
        purchase_executed_at=_datetime(data["purchase_executed_at"], "purchase_executed_at"),
        purchase_policy_name=data["purchase_policy_name"],
        purchase_policy_version=data["purchase_policy_version"],
        purchase_record_schema_version=data["purchase_record_schema_version"],
        schema_version=data["schema_version"],
    )


def _normalized(value: NormalizedActualAcquisitionCategory) -> dict[str, object]:
    return {
        "category": value.category.value,
        "target_currency": value.target_currency,
        "target_batch_amount": None if value.target_batch_amount is None else format(value.target_batch_amount, "f"),
    }


def _load_normalized(value: object) -> NormalizedActualAcquisitionCategory:
    data = _exact(value, {"category", "target_currency", "target_batch_amount"}, "normalized category")
    return NormalizedActualAcquisitionCategory(
        data["category"],
        data["target_currency"],
        _optional_decimal(data["target_batch_amount"], "target_batch_amount"),
    )


_PAYLOAD_KEYS = {
    "settlement_id", "source_manifest", "revision", "predecessor_settlement_id",
    "target_currency", "fixed_cost_facts", "other_mandatory_costs",
    "normalized_categories", "state", "blocking_reasons", "acquisition_batch_total",
    "acquisition_per_unit", "operator_id", "requested_at", "admitted_at", "policy_name",
    "policy_version", "policy_precision", "policy_rounding", "schema_version",
}


def _payload(value: ActualAcquisitionSettlement) -> str:
    return _dump({
        "settlement_id": value.settlement_id,
        "source_manifest": _manifest(value.source_manifest),
        "revision": value.revision,
        "predecessor_settlement_id": value.predecessor_settlement_id,
        "target_currency": value.target_currency,
        "fixed_cost_facts": [_fact(fact) for fact in value.fixed_cost_facts],
        "other_mandatory_costs": _other(value.other_mandatory_costs),
        "normalized_categories": [_normalized(item) for item in value.normalized_categories],
        "state": value.state.value,
        "blocking_reasons": [reason.value for reason in value.blocking_reasons],
        "acquisition_batch_total": None if value.acquisition_batch_total is None else format(value.acquisition_batch_total, "f"),
        "acquisition_per_unit": None if value.acquisition_per_unit is None else format(value.acquisition_per_unit, "f"),
        "operator_id": value.operator_id,
        "requested_at": value.requested_at.isoformat(),
        "admitted_at": value.admitted_at.isoformat(),
        "policy_name": value.policy_name,
        "policy_version": value.policy_version,
        "policy_precision": value.policy_precision,
        "policy_rounding": value.policy_rounding,
        "schema_version": value.schema_version,
    })


class SQLiteActualAcquisitionSettlementRepository:
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
                    settlement_id TEXT PRIMARY KEY,
                    purchase_execution_record_id TEXT NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    predecessor_settlement_id TEXT,
                    state TEXT NOT NULL,
                    target_currency TEXT NOT NULL,
                    policy_name TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(purchase_execution_record_id)
                      REFERENCES purchase_execution_record_history(record_id),
                    FOREIGN KEY(predecessor_settlement_id)
                      REFERENCES {HISTORY_TABLE}(settlement_id),
                    CHECK(revision >= 1),
                    CHECK(state IN ('blocked','complete'))
                )"""
            )
            self._connection.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {REVISION_INDEX} ON {HISTORY_TABLE}(purchase_execution_record_id,revision)"
            )
            self._connection.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {PREDECESSOR_INDEX} ON {HISTORY_TABLE}(predecessor_settlement_id) WHERE predecessor_settlement_id IS NOT NULL"
            )
            self._connection.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS {COMPLETE_INDEX} ON {HISTORY_TABLE}(purchase_execution_record_id) WHERE state='complete'"
            )
            self._connection.execute(
                f"""CREATE TRIGGER IF NOT EXISTS trg_{HISTORY_TABLE}_complete_terminal
                BEFORE INSERT ON {HISTORY_TABLE}
                WHEN EXISTS(
                    SELECT 1 FROM {HISTORY_TABLE}
                    WHERE purchase_execution_record_id=NEW.purchase_execution_record_id
                      AND state='complete'
                )
                BEGIN SELECT RAISE(ABORT,'COMPLETE actual acquisition settlement is terminal'); END"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE}(
                    command_id TEXT PRIMARY KEY,
                    settlement_id TEXT NOT NULL,
                    command_fingerprint TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(settlement_id) REFERENCES {HISTORY_TABLE}(settlement_id)
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

    def _history_row(self, settlement_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE settlement_id=?", (settlement_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise ActualAcquisitionSettlementHistoryError("settlement history query failed") from error

    def _tip_row(self, purchase_execution_record_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE purchase_execution_record_id=? ORDER BY revision DESC LIMIT 1",
                (purchase_execution_record_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise ActualAcquisitionSettlementHistoryError("settlement tip query failed") from error

    def _load_row(self, row, *, validate_chain: bool) -> ActualAcquisitionSettlement:
        try:
            if row["schema_version"] != ACTUAL_ACQUISITION_SETTLEMENT_SCHEMA_VERSION:
                raise UnsupportedActualAcquisitionSettlementVersionError("unsupported settlement version")
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _integrity(encoded) != row["integrity_fingerprint"]:
                raise ValueError("actual acquisition settlement integrity mismatch")
            data = _exact(json.loads(encoded), _PAYLOAD_KEYS, "actual acquisition settlement payload")
            if data["schema_version"] != ACTUAL_ACQUISITION_SETTLEMENT_SCHEMA_VERSION:
                raise UnsupportedActualAcquisitionSettlementVersionError("unsupported settlement payload version")
            if not isinstance(data["fixed_cost_facts"], list) or not isinstance(data["normalized_categories"], list) or not isinstance(data["blocking_reasons"], list):
                raise ValueError("settlement collection fields must be lists")
            settlement = ActualAcquisitionSettlement(
                settlement_id=data["settlement_id"],
                source_manifest=_load_manifest(data["source_manifest"]),
                revision=data["revision"],
                predecessor_settlement_id=data["predecessor_settlement_id"],
                target_currency=data["target_currency"],
                fixed_cost_facts=tuple(_load_fact(value) for value in data["fixed_cost_facts"]),
                other_mandatory_costs=_load_other(data["other_mandatory_costs"]),
                normalized_categories=tuple(_load_normalized(value) for value in data["normalized_categories"]),
                state=data["state"],
                blocking_reasons=tuple(ActualAcquisitionBlockingReason(value) for value in data["blocking_reasons"]),
                acquisition_batch_total=_optional_decimal(data["acquisition_batch_total"], "acquisition_batch_total"),
                acquisition_per_unit=_optional_decimal(data["acquisition_per_unit"], "acquisition_per_unit"),
                operator_id=data["operator_id"],
                requested_at=_datetime(data["requested_at"], "requested_at"),
                admitted_at=_datetime(data["admitted_at"], "admitted_at"),
                policy_name=data["policy_name"],
                policy_version=data["policy_version"],
                policy_precision=data["policy_precision"],
                policy_rounding=data["policy_rounding"],
                schema_version=data["schema_version"],
            )
            source = settlement.source_manifest
            if (
                settlement.settlement_id != row["settlement_id"]
                or source.purchase_execution_record_id != row["purchase_execution_record_id"]
                or source.opportunity_identity.opportunity_id != row["opportunity_id"]
                or settlement.revision != row["revision"]
                or settlement.predecessor_settlement_id != row["predecessor_settlement_id"]
                or settlement.state.value != row["state"]
                or settlement.target_currency != row["target_currency"]
                or settlement.policy_name != row["policy_name"]
                or settlement.policy_version != row["policy_version"]
                or settlement.schema_version != row["schema_version"]
            ):
                raise ValueError("settlement columns differ from payload")
            purchase = self.get_purchase_execution_record(source.purchase_execution_record_id)
            if purchase is None or actual_acquisition_manifest_from_purchase(purchase) != source:
                raise ValueError("settlement Purchase Execution lineage differs")
            if validate_chain:
                self._validate_chain(source.purchase_execution_record_id)
            return settlement
        except UnsupportedActualAcquisitionSettlementVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedActualAcquisitionSettlementPersistenceError):
                raise
            raise MalformedActualAcquisitionSettlementPersistenceError(
                "persisted Actual Acquisition Settlement is malformed"
            ) from error

    def _validate_chain(self, purchase_execution_record_id: str) -> None:
        rows = self._connection.execute(
            f"SELECT * FROM {HISTORY_TABLE} WHERE purchase_execution_record_id=? ORDER BY revision",
            (purchase_execution_record_id,),
        ).fetchall()
        previous = None
        complete_seen = False
        for expected_revision, row in enumerate(rows, 1):
            settlement = self._load_row(row, validate_chain=False)
            if settlement.revision != expected_revision:
                raise MalformedActualAcquisitionSettlementPersistenceError("settlement revisions are not contiguous")
            if settlement.predecessor_settlement_id != (None if previous is None else previous.settlement_id):
                raise MalformedActualAcquisitionSettlementPersistenceError("settlement predecessor lineage is malformed")
            if previous is not None and settlement.target_currency != previous.target_currency:
                raise MalformedActualAcquisitionSettlementPersistenceError("settlement target currency changed")
            if previous is not None:
                for old, new in zip(
                    previous.fixed_cost_facts,
                    settlement.fixed_cost_facts,
                    strict=True,
                ):
                    if (
                        old.availability
                        is not ActualAcquisitionFactAvailability.UNKNOWN
                        and new.availability
                        is ActualAcquisitionFactAvailability.UNKNOWN
                    ):
                        raise MalformedActualAcquisitionSettlementPersistenceError(
                            "settlement fact regressed to UNKNOWN"
                        )
                if (
                    previous.other_mandatory_costs.availability
                    is not ActualAcquisitionFactAvailability.UNKNOWN
                    and settlement.other_mandatory_costs.availability
                    is ActualAcquisitionFactAvailability.UNKNOWN
                ):
                    raise MalformedActualAcquisitionSettlementPersistenceError(
                        "other mandatory scope regressed to UNKNOWN"
                    )
            if complete_seen:
                raise MalformedActualAcquisitionSettlementPersistenceError("settlement exists after COMPLETE")
            complete_seen = settlement.state is ActualAcquisitionSettlementState.COMPLETE
            previous = settlement

    def get_settlement(self, settlement_id: str):
        row = self._history_row(settlement_id)
        return None if row is None else self._load_row(row, validate_chain=True)

    def get_chain_tip_for_cardinality(self, purchase_execution_record_id: str):
        row = self._tip_row(purchase_execution_record_id)
        return None if row is None else self._load_row(row, validate_chain=True)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?", (command_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise ActualAcquisitionSettlementReceiptError("settlement receipt query failed") from error

    def _load_receipt(self, row) -> ActualAcquisitionSettlementReceipt:
        try:
            if row["schema_version"] != ACTUAL_ACQUISITION_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedActualAcquisitionSettlementVersionError("unsupported settlement receipt version")
            receipt = ActualAcquisitionSettlementReceipt(
                row["command_id"], row["settlement_id"], row["command_fingerprint"],
                _datetime(row["committed_at"], "committed_at"), row["schema_version"],
            )
            if self.get_settlement(receipt.settlement_id) is None:
                raise ValueError("settlement receipt is orphaned")
            return receipt
        except UnsupportedActualAcquisitionSettlementVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedActualAcquisitionSettlementPersistenceError):
                raise
            raise MalformedActualAcquisitionSettlementPersistenceError("persisted settlement receipt is malformed") from error

    def validate_replay(self, command_id: str, fingerprint: str):
        row = self._receipt_row(command_id)
        if row is None:
            return None
        receipt = self._load_receipt(row)
        if receipt.command_fingerprint != fingerprint:
            raise ActualAcquisitionSettlementReplayConflictError("actual acquisition settlement command payload conflicts")
        settlement = self.get_settlement(receipt.settlement_id)
        if settlement is None:
            raise MalformedActualAcquisitionSettlementPersistenceError("settlement receipt is orphaned")
        return ActualAcquisitionSettlementPublication(settlement, receipt, True)

    @staticmethod
    def _validate_write(command, settlement, receipt) -> None:
        if not isinstance(command, AdmitActualAcquisitionSettlementCommand):
            raise TypeError("command must be AdmitActualAcquisitionSettlementCommand")
        if not isinstance(settlement, ActualAcquisitionSettlement):
            raise TypeError("settlement must be ActualAcquisitionSettlement")
        if not isinstance(receipt, ActualAcquisitionSettlementReceipt):
            raise TypeError("receipt must be ActualAcquisitionSettlementReceipt")
        if (
            receipt.command_id != command.command_id
            or receipt.settlement_id != settlement.settlement_id
            or receipt.command_fingerprint != command.fingerprint
            or settlement.source_manifest.purchase_execution_record_id != command.purchase_execution_record_id
            or settlement.source_manifest.opportunity_identity.opportunity_id != command.opportunity_id
            or settlement.predecessor_settlement_id != command.predecessor_settlement_id
            or settlement.target_currency != command.target_currency
            or settlement.fixed_cost_facts != command.fixed_cost_facts
            or settlement.other_mandatory_costs != command.other_mandatory_costs
            or settlement.operator_id != command.operator_id
            or settlement.requested_at != command.requested_at
            or settlement.policy_name != command.policy_name
            or settlement.policy_version != command.policy_version
        ):
            raise ActualAcquisitionSettlementReplayConflictError("command, settlement, and receipt differ")

    def _insert_receipt(self, receipt: ActualAcquisitionSettlementReceipt) -> None:
        try:
            self._connection.execute(
                f"INSERT INTO {RECEIPT_TABLE} VALUES(?,?,?,?,?,?)",
                (
                    receipt.command_id, receipt.settlement_id, receipt.command_fingerprint,
                    receipt.committed_at.isoformat(), receipt.schema_version,
                    receipt.committed_at.isoformat(),
                ),
            )
        except sqlite3.Error as error:
            raise ActualAcquisitionSettlementReceiptError("settlement receipt insert failed") from error

    def save(self, command, settlement, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            self._validate_write(command, settlement, receipt)
            source = settlement.source_manifest
            purchase = self.get_purchase_execution_record(source.purchase_execution_record_id)
            if purchase is None or actual_acquisition_manifest_from_purchase(purchase) != source:
                raise ActualAcquisitionSettlementRevisionConflictError("Purchase Execution lineage differs")
            tip_row = self._tip_row(source.purchase_execution_record_id)
            if tip_row is None:
                if settlement.revision != 1 or settlement.predecessor_settlement_id is not None:
                    raise ActualAcquisitionSettlementRevisionConflictError("first settlement revision must be revision 1")
            else:
                tip = self._load_row(tip_row, validate_chain=True)
                if tip.state is ActualAcquisitionSettlementState.COMPLETE:
                    raise ActualAcquisitionSettlementTerminalConflictError("COMPLETE settlement is terminal")
                if (
                    settlement.predecessor_settlement_id != tip.settlement_id
                    or settlement.revision != tip.revision + 1
                    or settlement.target_currency != tip.target_currency
                ):
                    raise ActualAcquisitionSettlementRevisionConflictError("settlement revision would fork or change chain")
            encoded = _payload(settlement)
            try:
                self._connection.execute(
                    f"""INSERT INTO {HISTORY_TABLE}(
                        settlement_id,purchase_execution_record_id,opportunity_id,revision,
                        predecessor_settlement_id,state,target_currency,policy_name,policy_version,
                        payload_json,integrity_fingerprint,schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        settlement.settlement_id, source.purchase_execution_record_id,
                        source.opportunity_identity.opportunity_id, settlement.revision,
                        settlement.predecessor_settlement_id, settlement.state.value,
                        settlement.target_currency, settlement.policy_name, settlement.policy_version,
                        encoded, _integrity(encoded), settlement.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as error:
                current = self._tip_row(source.purchase_execution_record_id)
                if current is not None and current["state"] == ActualAcquisitionSettlementState.COMPLETE.value:
                    raise ActualAcquisitionSettlementTerminalConflictError("COMPLETE settlement is terminal") from error
                if current is not None:
                    raise ActualAcquisitionSettlementRevisionConflictError("settlement revision cardinality conflict") from error
                raise ActualAcquisitionSettlementHistoryError("settlement history insert failed") from error
            except sqlite3.Error as error:
                raise ActualAcquisitionSettlementHistoryError("settlement history insert failed") from error
            self._insert_receipt(receipt)
            try:
                self._commit()
            except sqlite3.Error as error:
                raise ActualAcquisitionSettlementCommitError("settlement commit failed") from error
            return ActualAcquisitionSettlementPublication(settlement, receipt, False)
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
    name for name in globals()
    if name.startswith(("ActualAcquisition", "MalformedActual", "SQLiteActual", "UnsupportedActual"))
]
