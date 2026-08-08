"""Append-only SQLite persistence for Conservative Economics results."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.conservative_economics import (
    CONSERVATIVE_ECONOMICS_RECEIPT_SCHEMA_VERSION,
    ConservativeEconomicsPublication,
    ConservativeEconomicsReceipt,
    ConservativeEconomicsReplayConflictError,
    EvaluateConservativeEconomicsCommand,
    conservative_economics_blocking_reasons,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.opportunity import (
    CONSERVATIVE_ECONOMICS_POLICY_NAME,
    CONSERVATIVE_ECONOMICS_POLICY_VERSION,
    CONSERVATIVE_ECONOMICS_SCHEMA_VERSION,
    ConservativeEconomicsAssumption,
    ConservativeEconomicsAssumptionKind,
    ConservativeEconomicsBlockingCode,
    ConservativeEconomicsBlockingReason,
    ConservativeEconomicsResult,
    ConservativeEconomicsStatus,
    EvidenceStatus,
    calculate_conservative_unit_values,
)
from app.infrastructure.economics_source_composition import (
    SQLiteEconomicsSourceCompositionRepository,
)


HISTORY_TABLE = "conservative_economics_history"
RECEIPT_TABLE = "conservative_economics_receipts"


class ConservativeEconomicsPersistenceError(RuntimeError):
    pass


class ConservativeEconomicsHistoryError(ConservativeEconomicsPersistenceError):
    pass


class ConservativeEconomicsReceiptError(ConservativeEconomicsPersistenceError):
    pass


class ConservativeEconomicsCommitError(ConservativeEconomicsPersistenceError):
    pass


class MalformedConservativeEconomicsPersistenceError(
    ConservativeEconomicsPersistenceError
):
    pass


class UnsupportedConservativeEconomicsVersionError(
    MalformedConservativeEconomicsPersistenceError
):
    pass


def _dump(value: dict[str, object]) -> str:
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


def _optional_decimal(value: object) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def _assumption(value: ConservativeEconomicsAssumption) -> dict[str, object]:
    return {"kind": value.kind.value, "value": str(value.value), "owner": value.owner}


def _load_assumption(value: object) -> ConservativeEconomicsAssumption:
    if not isinstance(value, dict) or set(value) != {"kind", "value", "owner"}:
        raise ValueError("assumption is malformed")
    return ConservativeEconomicsAssumption(
        ConservativeEconomicsAssumptionKind(value["kind"]),
        Decimal(str(value["value"])),
        value["owner"],
    )


def _reason(value: ConservativeEconomicsBlockingReason) -> dict[str, object]:
    return {
        "code": value.code.value,
        "category": value.category,
        "source_reference": value.source_reference,
    }


def _load_reason(value: object) -> ConservativeEconomicsBlockingReason:
    if not isinstance(value, dict) or set(value) != {
        "code",
        "category",
        "source_reference",
    }:
        raise ValueError("blocking reason is malformed")
    return ConservativeEconomicsBlockingReason(
        ConservativeEconomicsBlockingCode(value["code"]),
        value["category"],
        value["source_reference"],
    )


_PAYLOAD_KEYS = {
    "result_id",
    "opportunity_identity",
    "source_composition_id",
    "source_composition_schema_version",
    "economics_currency",
    "authoritative_expected_sale_price",
    "expected_sale_price_evidence_status",
    "expected_sale_price_evidence_reference",
    "conservative_sale_price",
    "acquisition_cost_per_unit",
    "marketplace_fee",
    "payment_fee",
    "fixed_fee",
    "accepted_tax_cost",
    "accepted_duty_cost",
    "accepted_other_cost",
    "total_unit_cost",
    "conservative_profit_per_unit",
    "conservative_margin",
    "conservative_acquisition_roi",
    "assumptions",
    "scenario_name",
    "scenario_version",
    "status",
    "blocking_reasons",
    "policy_name",
    "policy_version",
    "policy_precision",
    "policy_rounding",
    "requested_at",
    "calculated_at",
    "schema_version",
}


def _payload(value: ConservativeEconomicsResult) -> str:
    def decimal(name: str):
        item = getattr(value, name)
        return None if item is None else str(item)

    return _dump(
        {
            "result_id": value.result_id,
            "opportunity_identity": {
                "opportunity_id": value.opportunity_identity.opportunity_id,
                "discovery_reference": value.opportunity_identity.discovery_reference,
            },
            "source_composition_id": value.source_composition_id,
            "source_composition_schema_version": value.source_composition_schema_version,
            "economics_currency": value.economics_currency,
            "authoritative_expected_sale_price": decimal("authoritative_expected_sale_price"),
            "expected_sale_price_evidence_status": value.expected_sale_price_evidence_status.value,
            "expected_sale_price_evidence_reference": value.expected_sale_price_evidence_reference,
            "conservative_sale_price": decimal("conservative_sale_price"),
            "acquisition_cost_per_unit": str(value.acquisition_cost_per_unit),
            "marketplace_fee": decimal("marketplace_fee"),
            "payment_fee": decimal("payment_fee"),
            "fixed_fee": decimal("fixed_fee"),
            "accepted_tax_cost": decimal("accepted_tax_cost"),
            "accepted_duty_cost": decimal("accepted_duty_cost"),
            "accepted_other_cost": decimal("accepted_other_cost"),
            "total_unit_cost": decimal("total_unit_cost"),
            "conservative_profit_per_unit": decimal("conservative_profit_per_unit"),
            "conservative_margin": decimal("conservative_margin"),
            "conservative_acquisition_roi": decimal("conservative_acquisition_roi"),
            "assumptions": [_assumption(item) for item in value.assumptions],
            "scenario_name": value.scenario_name,
            "scenario_version": value.scenario_version,
            "status": value.status.value,
            "blocking_reasons": [_reason(item) for item in value.blocking_reasons],
            "policy_name": value.policy_name,
            "policy_version": value.policy_version,
            "policy_precision": value.policy_precision,
            "policy_rounding": value.policy_rounding,
            "requested_at": value.requested_at.isoformat(),
            "calculated_at": value.calculated_at.isoformat(),
            "schema_version": value.schema_version,
        }
    )


class SQLiteConservativeEconomicsRepository:
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
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._sources = SQLiteEconomicsSourceCompositionRepository(
            connection=self._connection
        )
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {HISTORY_TABLE}(
                    result_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    discovery_reference TEXT NOT NULL,
                    source_composition_id TEXT NOT NULL,
                    economics_currency TEXT NOT NULL,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(source_composition_id) REFERENCES
                      economics_source_composition_history(composition_id)
                )"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE}(
                    command_id TEXT PRIMARY KEY,
                    result_id TEXT NOT NULL,
                    command_fingerprint TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(result_id) REFERENCES {HISTORY_TABLE}(result_id)
                )"""
            )
            for table in (HISTORY_TABLE, RECEIPT_TABLE):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END"""
                    )

    def _rollback(self) -> None:
        if self._connection.in_transaction:
            self._connection.rollback()

    def _commit(self) -> None:
        self._connection.commit()

    def get_source_composition(self, composition_id: str):
        return self._sources.get_composition(composition_id)

    def _history_row(self, result_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE result_id=?", (result_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise ConservativeEconomicsHistoryError("Conservative result query failed") from error

    def _load_result(self, row) -> ConservativeEconomicsResult:
        try:
            if row["schema_version"] != CONSERVATIVE_ECONOMICS_SCHEMA_VERSION:
                raise UnsupportedConservativeEconomicsVersionError(
                    "unsupported Conservative Economics result version"
                )
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _integrity(encoded) != row["integrity_fingerprint"]:
                raise ValueError("result integrity fingerprint mismatch")
            payload = json.loads(encoded)
            if not isinstance(payload, dict) or set(payload) != _PAYLOAD_KEYS:
                raise ValueError("result payload has unsupported fields")
            opportunity = payload["opportunity_identity"]
            if not isinstance(opportunity, dict) or set(opportunity) != {
                "opportunity_id",
                "discovery_reference",
            }:
                raise ValueError("Opportunity identity is malformed")
            value = ConservativeEconomicsResult(
                result_id=payload["result_id"],
                opportunity_identity=OpportunityIdentity(
                    opportunity["opportunity_id"], opportunity["discovery_reference"]
                ),
                source_composition_id=payload["source_composition_id"],
                source_composition_schema_version=payload["source_composition_schema_version"],
                economics_currency=payload["economics_currency"],
                authoritative_expected_sale_price=_optional_decimal(payload["authoritative_expected_sale_price"]),
                expected_sale_price_evidence_status=EvidenceStatus(payload["expected_sale_price_evidence_status"]),
                expected_sale_price_evidence_reference=payload["expected_sale_price_evidence_reference"],
                conservative_sale_price=_optional_decimal(payload["conservative_sale_price"]),
                acquisition_cost_per_unit=Decimal(str(payload["acquisition_cost_per_unit"])),
                marketplace_fee=_optional_decimal(payload["marketplace_fee"]),
                payment_fee=_optional_decimal(payload["payment_fee"]),
                fixed_fee=_optional_decimal(payload["fixed_fee"]),
                accepted_tax_cost=_optional_decimal(payload["accepted_tax_cost"]),
                accepted_duty_cost=_optional_decimal(payload["accepted_duty_cost"]),
                accepted_other_cost=_optional_decimal(payload["accepted_other_cost"]),
                total_unit_cost=_optional_decimal(payload["total_unit_cost"]),
                conservative_profit_per_unit=_optional_decimal(payload["conservative_profit_per_unit"]),
                conservative_margin=_optional_decimal(payload["conservative_margin"]),
                conservative_acquisition_roi=_optional_decimal(payload["conservative_acquisition_roi"]),
                assumptions=tuple(_load_assumption(item) for item in payload["assumptions"]),
                scenario_name=payload["scenario_name"],
                scenario_version=payload["scenario_version"],
                status=ConservativeEconomicsStatus(payload["status"]),
                blocking_reasons=tuple(_load_reason(item) for item in payload["blocking_reasons"]),
                policy_name=payload["policy_name"],
                policy_version=payload["policy_version"],
                policy_precision=payload["policy_precision"],
                policy_rounding=payload["policy_rounding"],
                requested_at=_datetime(payload["requested_at"], "requested_at"),
                calculated_at=_datetime(payload["calculated_at"], "calculated_at"),
                schema_version=payload["schema_version"],
            )
            if (
                value.result_id != row["result_id"]
                or value.opportunity_identity.opportunity_id != row["opportunity_id"]
                or value.opportunity_identity.discovery_reference != row["discovery_reference"]
                or value.source_composition_id != row["source_composition_id"]
                or value.economics_currency != row["economics_currency"]
                or value.status.value != row["status"]
                or value.schema_version != row["schema_version"]
            ):
                raise ValueError("result columns differ from payload")
            self._validate_source(value)
            return value
        except UnsupportedConservativeEconomicsVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedConservativeEconomicsPersistenceError):
                raise
            raise MalformedConservativeEconomicsPersistenceError(
                "persisted Conservative Economics result is malformed"
            ) from error

    def get_result(self, result_id: str):
        row = self._history_row(result_id)
        return None if row is None else self._load_result(row)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?", (command_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise ConservativeEconomicsReceiptError("Conservative receipt query failed") from error

    def _load_receipt(self, row):
        try:
            if row["schema_version"] != CONSERVATIVE_ECONOMICS_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedConservativeEconomicsVersionError(
                    "unsupported Conservative Economics receipt version"
                )
            value = ConservativeEconomicsReceipt(
                row["command_id"],
                row["result_id"],
                row["command_fingerprint"],
                _datetime(row["committed_at"], "committed_at"),
                row["schema_version"],
            )
            if self.get_result(value.result_id) is None:
                raise ValueError("receipt references missing result")
            return value
        except Exception as error:
            if isinstance(error, MalformedConservativeEconomicsPersistenceError):
                raise
            raise MalformedConservativeEconomicsPersistenceError(
                "persisted Conservative Economics receipt is malformed"
            ) from error

    def get_receipt(self, command_id: str):
        row = self._receipt_row(command_id)
        return None if row is None else self._load_receipt(row)

    def validate_replay(self, command_id: str, fingerprint: str):
        row = self._receipt_row(command_id)
        if row is None:
            return None
        receipt = self._load_receipt(row)
        if receipt.command_fingerprint != fingerprint:
            raise ConservativeEconomicsReplayConflictError(
                "Conservative Economics command payload conflicts"
            )
        result = self.get_result(receipt.result_id)
        if result is None:
            raise MalformedConservativeEconomicsPersistenceError(
                "receipt references missing result"
            )
        return ConservativeEconomicsPublication(result, receipt, True)

    def _validate_source(self, value: ConservativeEconomicsResult) -> None:
        source = self.get_source_composition(value.source_composition_id)
        if (
            source is None
            or source.opportunity_identity != value.opportunity_identity
            or source.schema_version != value.source_composition_schema_version
            or source.economics_currency != value.economics_currency
            or source.acquisition_cost_per_unit != value.acquisition_cost_per_unit
            or source.expected_sale_price.amount != value.authoritative_expected_sale_price
            or source.expected_sale_price.evidence.status != value.expected_sale_price_evidence_status
            or source.expected_sale_price.evidence.reference != value.expected_sale_price_evidence_reference
        ):
            raise ValueError("exact Economics Source Composition differs")
        if value.status is ConservativeEconomicsStatus.CALCULABLE:
            if conservative_economics_blocking_reasons(source):
                raise ValueError("CALCULABLE result has blocked exact source")
            expected = calculate_conservative_unit_values(
                expected_sale_price=source.expected_sale_price.amount,
                sale_price_factor=value.assumptions[0].value,
                acquisition_cost_per_unit=source.acquisition_cost_per_unit,
                marketplace_fee_rate=source.marketplace_fee_rate.rate,
                payment_fee_rate=source.payment_fee_rate.rate,
                fixed_fee=source.fixed_fee.amount,
                tax_cost=source.tax_rate.rate,
                duty_cost=source.duty_cost.amount,
                other_cost=source.other_cost.amount,
            )
            for name, expected_value in expected.items():
                if getattr(value, name) != expected_value:
                    raise ValueError(f"{name} differs from exact source calculation")
            if (
                value.fixed_fee != source.fixed_fee.amount
                or value.accepted_tax_cost != source.tax_rate.rate
                or value.accepted_duty_cost != source.duty_cost.amount
                or value.accepted_other_cost != source.other_cost.amount
            ):
                raise ValueError("accepted source cost differs")
        elif value.blocking_reasons != conservative_economics_blocking_reasons(source):
            raise ValueError("blocking reasons differ from exact source policy")

    def _validate_write(self, command, result, receipt) -> None:
        if not isinstance(command, EvaluateConservativeEconomicsCommand):
            raise TypeError("command must be EvaluateConservativeEconomicsCommand")
        if not isinstance(result, ConservativeEconomicsResult):
            raise TypeError("result must be ConservativeEconomicsResult")
        if not isinstance(receipt, ConservativeEconomicsReceipt):
            raise TypeError("receipt must be ConservativeEconomicsReceipt")
        if (
            command.command_id != receipt.command_id
            or command.fingerprint != receipt.command_fingerprint
            or result.result_id != receipt.result_id
            or command.opportunity_identity != result.opportunity_identity
            or command.source_composition_id != result.source_composition_id
            or command.scenario.manifest != result.assumptions
            or command.scenario.scenario_name != result.scenario_name
            or command.scenario.scenario_version != result.scenario_version
            or command.requested_at != result.requested_at
            or command.policy_name != result.policy_name
            or command.policy_version != result.policy_version
            or result.policy_name != CONSERVATIVE_ECONOMICS_POLICY_NAME
            or result.policy_version != CONSERVATIVE_ECONOMICS_POLICY_VERSION
        ):
            raise ConservativeEconomicsReplayConflictError(
                "command, result, and receipt do not match"
            )
        self._validate_source(result)

    def save_result(self, command, result, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            self._validate_write(command, result, receipt)
            encoded = _payload(result)
            try:
                self._connection.execute(
                    f"""INSERT INTO {HISTORY_TABLE}(
                        result_id,opportunity_id,discovery_reference,
                        source_composition_id,economics_currency,status,
                        payload_json,integrity_fingerprint,schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        result.result_id,
                        result.opportunity_identity.opportunity_id,
                        result.opportunity_identity.discovery_reference,
                        result.source_composition_id,
                        result.economics_currency,
                        result.status.value,
                        encoded,
                        _integrity(encoded),
                        result.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise ConservativeEconomicsHistoryError(
                    "Conservative Economics result insert failed"
                ) from error
            try:
                self._connection.execute(
                    f"""INSERT INTO {RECEIPT_TABLE}(
                        command_id,result_id,command_fingerprint,
                        committed_at,schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?)""",
                    (
                        receipt.command_id,
                        receipt.result_id,
                        receipt.command_fingerprint,
                        receipt.committed_at.isoformat(),
                        receipt.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise ConservativeEconomicsReceiptError(
                    "Conservative Economics receipt insert failed"
                ) from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise ConservativeEconomicsCommitError(
                    "Conservative Economics commit failed"
                ) from error
            return ConservativeEconomicsPublication(result, receipt, False)
        except ConservativeEconomicsReplayConflictError:
            self._rollback()
            raise
        except ConservativeEconomicsPersistenceError:
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
    "ConservativeEconomicsCommitError",
    "ConservativeEconomicsHistoryError",
    "ConservativeEconomicsPersistenceError",
    "ConservativeEconomicsReceiptError",
    "HISTORY_TABLE",
    "MalformedConservativeEconomicsPersistenceError",
    "RECEIPT_TABLE",
    "SQLiteConservativeEconomicsRepository",
    "UnsupportedConservativeEconomicsVersionError",
]
