"""Append-only SQLite persistence for exact-source Capital Gate assessments."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.capital_gate import (
    CAPITAL_GATE_RECEIPT_SCHEMA_VERSION,
    CapitalGatePublication,
    CapitalGateReceipt,
    CapitalGateReplayConflictError,
    EvaluateCapitalGateCommand,
)
from app.domain.capital import (
    CAPITAL_GATE_EVALUATED_FACTS_SCHEMA_VERSION,
    CAPITAL_GATE_SCHEMA_VERSION,
    CAPITAL_GATE_SOURCE_MANIFEST_SCHEMA_VERSION,
    CapitalGateAssessment,
    CapitalGateBlockingReasonCode,
    CapitalGateEvaluatedFacts,
    CapitalGateRejectionReasonCode,
    CapitalGateSourceManifest,
    CapitalGateState,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.opportunity import ConservativeEconomicsStatus
from app.domain.sourcing import CommercialFactAvailability, SourcingQuantityFact
from app.infrastructure.capital_investment import SQLiteCapitalInvestmentFactsRepository
from app.infrastructure.capital_readiness import SQLiteCapitalReadinessRepository
from app.infrastructure.capital_requirement import (
    SQLitePlannedAcquisitionCapitalRequirementRepository,
)


HISTORY_TABLE = "capital_gate_history"
RECEIPT_TABLE = "capital_gate_receipts"


class CapitalGatePersistenceError(RuntimeError):
    pass


class CapitalGateHistoryError(CapitalGatePersistenceError):
    pass


class CapitalGateReceiptError(CapitalGatePersistenceError):
    pass


class CapitalGateCommitError(CapitalGatePersistenceError):
    pass


class MalformedCapitalGatePersistenceError(CapitalGatePersistenceError):
    pass


class UnsupportedCapitalGateVersionError(MalformedCapitalGatePersistenceError):
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


def _opportunity(value: OpportunityIdentity) -> dict[str, str]:
    return {
        "opportunity_id": value.opportunity_id,
        "discovery_reference": value.discovery_reference,
    }


def _load_opportunity(value: object) -> OpportunityIdentity:
    data = _exact(value, {"opportunity_id", "discovery_reference"}, "Opportunity identity")
    return OpportunityIdentity(data["opportunity_id"], data["discovery_reference"])


_MANIFEST_KEYS = {
    "opportunity_identity",
    "capital_readiness_assessment_id",
    "capital_requirement_id",
    "deployable_capital_snapshot_id",
    "conservative_economics_result_id",
    "intended_order_quantity_id",
    "acquisition_normalization_id",
    "sourcing_binding_id",
    "sourcing_admission_id",
    "sourcing_admission_revision",
    "quote_id",
    "quote_revision",
    "schema_version",
}


def _manifest(value: CapitalGateSourceManifest) -> dict[str, object]:
    return {
        "opportunity_identity": _opportunity(value.opportunity_identity),
        "capital_readiness_assessment_id": value.capital_readiness_assessment_id,
        "capital_requirement_id": value.capital_requirement_id,
        "deployable_capital_snapshot_id": value.deployable_capital_snapshot_id,
        "conservative_economics_result_id": value.conservative_economics_result_id,
        "intended_order_quantity_id": value.intended_order_quantity_id,
        "acquisition_normalization_id": value.acquisition_normalization_id,
        "sourcing_binding_id": value.sourcing_binding_id,
        "sourcing_admission_id": value.sourcing_admission_id,
        "sourcing_admission_revision": value.sourcing_admission_revision,
        "quote_id": value.quote_id,
        "quote_revision": value.quote_revision,
        "schema_version": value.schema_version,
    }


def _load_manifest(value: object) -> CapitalGateSourceManifest:
    data = _exact(value, _MANIFEST_KEYS, "Capital Gate source manifest")
    if data["schema_version"] != CAPITAL_GATE_SOURCE_MANIFEST_SCHEMA_VERSION:
        raise UnsupportedCapitalGateVersionError("unsupported source manifest version")
    return CapitalGateSourceManifest(
        opportunity_identity=_load_opportunity(data["opportunity_identity"]),
        capital_readiness_assessment_id=data["capital_readiness_assessment_id"],
        capital_requirement_id=data["capital_requirement_id"],
        deployable_capital_snapshot_id=data["deployable_capital_snapshot_id"],
        conservative_economics_result_id=data["conservative_economics_result_id"],
        intended_order_quantity_id=data["intended_order_quantity_id"],
        acquisition_normalization_id=data["acquisition_normalization_id"],
        sourcing_binding_id=data["sourcing_binding_id"],
        sourcing_admission_id=data["sourcing_admission_id"],
        sourcing_admission_revision=data["sourcing_admission_revision"],
        quote_id=data["quote_id"],
        quote_revision=data["quote_revision"],
        schema_version=data["schema_version"],
    )


_FACT_KEYS = {
    "capital_readiness_state",
    "capital_requirement_state",
    "conservative_economics_status",
    "requirement_currency",
    "deployable_currency",
    "planned_acquisition_capital",
    "deployable_capital",
    "conservative_profit_per_unit",
    "conservative_margin",
    "conservative_acquisition_roi",
    "intended_order_quantity",
    "intended_order_quantity_unit",
    "minimum_order_quantity",
    "deployable_capital_semantics_version",
    "schema_version",
}


def _optional_decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _facts(value: CapitalGateEvaluatedFacts) -> dict[str, object]:
    return {
        "capital_readiness_state": value.capital_readiness_state.value,
        "capital_requirement_state": value.capital_requirement_state.value,
        "conservative_economics_status": value.conservative_economics_status.value,
        "requirement_currency": value.requirement_currency,
        "deployable_currency": value.deployable_currency,
        "planned_acquisition_capital": _optional_decimal(value.planned_acquisition_capital),
        "deployable_capital": format(value.deployable_capital, "f"),
        "conservative_profit_per_unit": _optional_decimal(value.conservative_profit_per_unit),
        "conservative_margin": _optional_decimal(value.conservative_margin),
        "conservative_acquisition_roi": _optional_decimal(value.conservative_acquisition_roi),
        "intended_order_quantity": value.intended_order_quantity,
        "intended_order_quantity_unit": value.intended_order_quantity_unit,
        "minimum_order_quantity": {
            "availability": value.minimum_order_quantity.availability.value,
            "quantity": value.minimum_order_quantity.quantity,
        },
        "deployable_capital_semantics_version": value.deployable_capital_semantics_version,
        "schema_version": value.schema_version,
    }


def _load_optional_decimal(value: object, name: str) -> Decimal | None:
    return None if value is None else _decimal(value, name)


def _load_facts(value: object) -> CapitalGateEvaluatedFacts:
    data = _exact(value, _FACT_KEYS, "Capital Gate evaluated facts")
    if data["schema_version"] != CAPITAL_GATE_EVALUATED_FACTS_SCHEMA_VERSION:
        raise UnsupportedCapitalGateVersionError("unsupported evaluated facts version")
    quantity = _exact(
        data["minimum_order_quantity"],
        {"availability", "quantity"},
        "minimum order quantity",
    )
    return CapitalGateEvaluatedFacts(
        capital_readiness_state=data["capital_readiness_state"],
        capital_requirement_state=data["capital_requirement_state"],
        conservative_economics_status=ConservativeEconomicsStatus(
            data["conservative_economics_status"]
        ),
        requirement_currency=data["requirement_currency"],
        deployable_currency=data["deployable_currency"],
        planned_acquisition_capital=_load_optional_decimal(
            data["planned_acquisition_capital"], "planned_acquisition_capital"
        ),
        deployable_capital=_decimal(data["deployable_capital"], "deployable_capital"),
        conservative_profit_per_unit=_load_optional_decimal(
            data["conservative_profit_per_unit"], "conservative_profit_per_unit"
        ),
        conservative_margin=_load_optional_decimal(
            data["conservative_margin"], "conservative_margin"
        ),
        conservative_acquisition_roi=_load_optional_decimal(
            data["conservative_acquisition_roi"], "conservative_acquisition_roi"
        ),
        intended_order_quantity=data["intended_order_quantity"],
        intended_order_quantity_unit=data["intended_order_quantity_unit"],
        minimum_order_quantity=SourcingQuantityFact(
            CommercialFactAvailability(quantity["availability"]), quantity["quantity"]
        ),
        deployable_capital_semantics_version=data["deployable_capital_semantics_version"],
        schema_version=data["schema_version"],
    )


_PAYLOAD_KEYS = {
    "gate_id",
    "source_manifest",
    "evaluated_facts",
    "state",
    "blocking_reasons",
    "rejection_reasons",
    "policy_name",
    "policy_version",
    "requested_at",
    "evaluated_at",
    "schema_version",
}


def _payload(value: CapitalGateAssessment) -> str:
    return _dump(
        {
            "gate_id": value.gate_id,
            "source_manifest": _manifest(value.source_manifest),
            "evaluated_facts": _facts(value.evaluated_facts),
            "state": value.state.value,
            "blocking_reasons": [reason.value for reason in value.blocking_reasons],
            "rejection_reasons": [reason.value for reason in value.rejection_reasons],
            "policy_name": value.policy_name,
            "policy_version": value.policy_version,
            "requested_at": value.requested_at.isoformat(),
            "evaluated_at": value.evaluated_at.isoformat(),
            "schema_version": value.schema_version,
        }
    )


class SQLiteCapitalGateRepository:
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
        self._readiness = SQLiteCapitalReadinessRepository(connection=self._connection)
        self._requirements = SQLitePlannedAcquisitionCapitalRequirementRepository(
            connection=self._connection
        )
        self._investment = SQLiteCapitalInvestmentFactsRepository(connection=self._connection)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {HISTORY_TABLE}(
                    gate_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    discovery_reference TEXT NOT NULL,
                    capital_readiness_assessment_id TEXT NOT NULL,
                    capital_requirement_id TEXT NOT NULL,
                    deployable_capital_snapshot_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    policy_name TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL
                )"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE}(
                    command_id TEXT PRIMARY KEY,
                    gate_id TEXT NOT NULL,
                    command_fingerprint TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(gate_id) REFERENCES {HISTORY_TABLE}(gate_id)
                )"""
            )
            for table in (HISTORY_TABLE, RECEIPT_TABLE):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END"""
                    )

    def get_capital_readiness(self, assessment_id: str):
        return self._readiness.get_assessment(assessment_id)

    def get_capital_requirement(self, requirement_id: str):
        return self._requirements.get_requirement(requirement_id)

    def get_deployable_capital(self, snapshot_id: str):
        return self._investment.get_deployable_capital_snapshot(snapshot_id)

    def get_conservative_economics(self, result_id: str):
        return self._readiness.get_conservative_economics_result(result_id)

    def get_intended_order_quantity(self, intent_id: str):
        return self._investment.get_intent(intent_id)

    def get_sourcing_admission(self, admission_id: str, revision: int):
        return self._investment.get_sourcing_admission(admission_id, revision)

    def _history_row(self, gate_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE gate_id=?", (gate_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise CapitalGateHistoryError("Capital Gate history query failed") from error

    def _load_gate(self, row) -> CapitalGateAssessment:
        try:
            if row["schema_version"] != CAPITAL_GATE_SCHEMA_VERSION:
                raise UnsupportedCapitalGateVersionError("unsupported Capital Gate version")
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _integrity(encoded) != row["integrity_fingerprint"]:
                raise ValueError("Capital Gate integrity fingerprint mismatch")
            data = _exact(json.loads(encoded), _PAYLOAD_KEYS, "Capital Gate payload")
            if data["schema_version"] != CAPITAL_GATE_SCHEMA_VERSION:
                raise UnsupportedCapitalGateVersionError("unsupported payload version")
            blockers = data["blocking_reasons"]
            rejections = data["rejection_reasons"]
            if not isinstance(blockers, list) or not isinstance(rejections, list):
                raise ValueError("Gate reasons must be ordered lists")
            value = CapitalGateAssessment(
                gate_id=data["gate_id"],
                source_manifest=_load_manifest(data["source_manifest"]),
                evaluated_facts=_load_facts(data["evaluated_facts"]),
                state=CapitalGateState(data["state"]),
                blocking_reasons=tuple(CapitalGateBlockingReasonCode(item) for item in blockers),
                rejection_reasons=tuple(CapitalGateRejectionReasonCode(item) for item in rejections),
                policy_name=data["policy_name"],
                policy_version=data["policy_version"],
                requested_at=_datetime(data["requested_at"], "requested_at"),
                evaluated_at=_datetime(data["evaluated_at"], "evaluated_at"),
                schema_version=data["schema_version"],
            )
            manifest = value.source_manifest
            if (
                value.gate_id != row["gate_id"]
                or manifest.opportunity_identity.opportunity_id != row["opportunity_id"]
                or manifest.opportunity_identity.discovery_reference != row["discovery_reference"]
                or manifest.capital_readiness_assessment_id
                != row["capital_readiness_assessment_id"]
                or manifest.capital_requirement_id != row["capital_requirement_id"]
                or manifest.deployable_capital_snapshot_id
                != row["deployable_capital_snapshot_id"]
                or value.state.value != row["state"]
                or value.policy_name != row["policy_name"]
                or value.policy_version != row["policy_version"]
                or value.schema_version != row["schema_version"]
            ):
                raise ValueError("Capital Gate columns differ from payload")
            self._validate_sources(value)
            return value
        except UnsupportedCapitalGateVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedCapitalGatePersistenceError):
                raise
            raise MalformedCapitalGatePersistenceError(
                "persisted Capital Gate assessment is malformed"
            ) from error

    def get_gate(self, gate_id: str):
        row = self._history_row(gate_id)
        return None if row is None else self._load_gate(row)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?", (command_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise CapitalGateReceiptError("Capital Gate receipt query failed") from error

    def _load_receipt(self, row) -> CapitalGateReceipt:
        try:
            if row["schema_version"] != CAPITAL_GATE_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedCapitalGateVersionError("unsupported Capital Gate receipt version")
            value = CapitalGateReceipt(
                row["command_id"],
                row["gate_id"],
                row["command_fingerprint"],
                _datetime(row["committed_at"], "committed_at"),
                row["schema_version"],
            )
            if self.get_gate(value.gate_id) is None:
                raise ValueError("Capital Gate receipt is orphaned")
            return value
        except UnsupportedCapitalGateVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedCapitalGatePersistenceError):
                raise
            raise MalformedCapitalGatePersistenceError(
                "persisted Capital Gate receipt is malformed"
            ) from error

    def get_receipt(self, command_id: str):
        row = self._receipt_row(command_id)
        return None if row is None else self._load_receipt(row)

    def validate_replay(self, command_id: str, fingerprint: str):
        receipt = self.get_receipt(command_id)
        if receipt is None:
            return None
        if receipt.command_fingerprint != fingerprint:
            raise CapitalGateReplayConflictError("Capital Gate command payload conflicts")
        assessment = self.get_gate(receipt.gate_id)
        if assessment is None:
            raise MalformedCapitalGatePersistenceError("Capital Gate receipt is orphaned")
        return CapitalGatePublication(assessment, receipt, True)

    def _validate_sources(self, value: CapitalGateAssessment) -> None:
        manifest = value.source_manifest
        facts = value.evaluated_facts
        readiness = self.get_capital_readiness(manifest.capital_readiness_assessment_id)
        requirement = self.get_capital_requirement(manifest.capital_requirement_id)
        deployable = self.get_deployable_capital(manifest.deployable_capital_snapshot_id)
        conservative = self.get_conservative_economics(
            manifest.conservative_economics_result_id
        )
        intent = self.get_intended_order_quantity(manifest.intended_order_quantity_id)
        admission = self.get_sourcing_admission(
            manifest.sourcing_admission_id, manifest.sourcing_admission_revision
        )
        if any(
            item is None
            for item in (readiness, requirement, deployable, conservative, intent, admission)
        ):
            raise ValueError("Capital Gate exact source is missing")
        if (
            readiness.source_manifest.conservative_economics_result_id
            != manifest.conservative_economics_result_id
            or requirement.intended_order_quantity_id != manifest.intended_order_quantity_id
            or requirement.acquisition_normalization_id != manifest.acquisition_normalization_id
            or requirement.sourcing_binding_id != manifest.sourcing_binding_id
            or requirement.sourcing_admission_id != manifest.sourcing_admission_id
            or requirement.sourcing_admission_revision != manifest.sourcing_admission_revision
            or requirement.quote_id != manifest.quote_id
            or requirement.quote_revision != manifest.quote_revision
            or facts.capital_readiness_state != readiness.state
            or facts.capital_requirement_state != requirement.state
            or facts.conservative_economics_status != conservative.status
            or facts.requirement_currency != requirement.currency
            or facts.deployable_currency != deployable.currency
            or facts.planned_acquisition_capital != requirement.planned_acquisition_capital
            or facts.deployable_capital != deployable.amount
            or facts.conservative_profit_per_unit
            != conservative.conservative_profit_per_unit
            or facts.conservative_margin != conservative.conservative_margin
            or facts.conservative_acquisition_roi
            != conservative.conservative_acquisition_roi
            or facts.intended_order_quantity != intent.quantity
            or facts.intended_order_quantity_unit != intent.quantity_unit
            or facts.minimum_order_quantity
            != admission.quote_revision.minimum_order_quantity
            or facts.deployable_capital_semantics_version != deployable.semantics_version
        ):
            raise ValueError("Capital Gate exact source snapshot differs")

    @staticmethod
    def _validate_write(command, assessment, receipt) -> None:
        if not isinstance(command, EvaluateCapitalGateCommand):
            raise TypeError("command must be EvaluateCapitalGateCommand")
        if not isinstance(assessment, CapitalGateAssessment):
            raise TypeError("assessment must be CapitalGateAssessment")
        if not isinstance(receipt, CapitalGateReceipt):
            raise TypeError("receipt must be CapitalGateReceipt")
        manifest = assessment.source_manifest
        if (
            receipt.command_id != command.command_id
            or receipt.gate_id != assessment.gate_id
            or receipt.command_fingerprint != command.fingerprint
            or manifest.opportunity_identity != command.opportunity_identity
            or manifest.capital_readiness_assessment_id
            != command.capital_readiness_assessment_id
            or manifest.capital_requirement_id != command.capital_requirement_id
            or manifest.deployable_capital_snapshot_id
            != command.deployable_capital_snapshot_id
            or assessment.policy_name != command.policy_name
            or assessment.policy_version != command.policy_version
            or assessment.requested_at != command.requested_at
        ):
            raise CapitalGateReplayConflictError(
                "command, Capital Gate assessment, and receipt differ"
            )

    def _rollback(self) -> None:
        if self._connection.in_transaction:
            self._connection.rollback()

    def _commit(self) -> None:
        self._connection.commit()

    def save_gate(self, command, assessment, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            self._validate_write(command, assessment, receipt)
            self._validate_sources(assessment)
            encoded = _payload(assessment)
            manifest = assessment.source_manifest
            try:
                self._connection.execute(
                    f"""INSERT INTO {HISTORY_TABLE}(
                        gate_id,opportunity_id,discovery_reference,
                        capital_readiness_assessment_id,capital_requirement_id,
                        deployable_capital_snapshot_id,state,policy_name,policy_version,
                        payload_json,integrity_fingerprint,schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        assessment.gate_id,
                        manifest.opportunity_identity.opportunity_id,
                        manifest.opportunity_identity.discovery_reference,
                        manifest.capital_readiness_assessment_id,
                        manifest.capital_requirement_id,
                        manifest.deployable_capital_snapshot_id,
                        assessment.state.value,
                        assessment.policy_name,
                        assessment.policy_version,
                        encoded,
                        _integrity(encoded),
                        assessment.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise CapitalGateHistoryError("Capital Gate insert failed") from error
            try:
                self._connection.execute(
                    f"""INSERT INTO {RECEIPT_TABLE}(
                        command_id,gate_id,command_fingerprint,committed_at,
                        schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?)""",
                    (
                        receipt.command_id,
                        receipt.gate_id,
                        receipt.command_fingerprint,
                        receipt.committed_at.isoformat(),
                        receipt.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise CapitalGateReceiptError("Capital Gate receipt insert failed") from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise CapitalGateCommitError("Capital Gate commit failed") from error
            return CapitalGatePublication(assessment, receipt, False)
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
    if name.startswith(("Capital", "Malformed", "SQLite", "Unsupported"))
]
