"""Append-only SQLite persistence for Real-Money Execution Intents."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.real_money_execution_intent import (
    REAL_MONEY_EXECUTION_INTENT_COMMAND_SCHEMA_VERSION,
    REAL_MONEY_EXECUTION_INTENT_RECEIPT_SCHEMA_VERSION,
    EvaluateRealMoneyExecutionIntentCommand,
    RealMoneyExecutionIntentPublication,
    RealMoneyExecutionIntentReadyConflictError,
    RealMoneyExecutionIntentReceipt,
    RealMoneyExecutionIntentReplayConflictError,
    EvaluateRealMoneyExecutionIntent,
)
from app.domain.capital import (
    REAL_MONEY_EXECUTION_INTENT_SCHEMA_VERSION,
    REAL_MONEY_EXECUTION_SOURCE_MANIFEST_SCHEMA_VERSION,
    RealMoneyExecutionIntent,
    RealMoneyExecutionIntentBlockingReasonCode,
    RealMoneyExecutionIntentState,
    RealMoneyExecutionSourceManifest,
)
from app.domain.decision_engine import OpportunityIdentity
from app.infrastructure.capital_gate import SQLiteCapitalGateRepository
from app.infrastructure.capital_investment import SQLiteCapitalInvestmentFactsRepository
from app.infrastructure.capital_requirement import (
    SQLitePlannedAcquisitionCapitalRequirementRepository,
)
from app.infrastructure.founder_capital_approval import (
    SQLiteFounderCapitalApprovalRepository,
)
from app.infrastructure.sourcing import SQLiteSourcingAuthorityRepository


HISTORY_TABLE = "real_money_execution_intent_history"
RECEIPT_TABLE = "real_money_execution_intent_receipts"
READY_INDEX = "ux_real_money_execution_ready_per_approval"


class RealMoneyExecutionIntentPersistenceError(RuntimeError):
    pass


class RealMoneyExecutionIntentHistoryError(RealMoneyExecutionIntentPersistenceError):
    pass


class RealMoneyExecutionIntentReceiptError(RealMoneyExecutionIntentPersistenceError):
    pass


class RealMoneyExecutionIntentCommitError(RealMoneyExecutionIntentPersistenceError):
    pass


class MalformedRealMoneyExecutionIntentPersistenceError(
    RealMoneyExecutionIntentPersistenceError
):
    pass


class UnsupportedRealMoneyExecutionIntentVersionError(
    MalformedRealMoneyExecutionIntentPersistenceError
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


def _fingerprint_action(source: RealMoneyExecutionSourceManifest) -> str:
    value = {
        "founder_capital_approval_id": source.founder_capital_approval_id,
        "quote_id": source.quote_id,
        "quote_revision": source.quote_revision,
        "current_deployable_capital_snapshot_id": source.current_deployable_capital_snapshot_id,
        "execution_quantity": source.execution_quantity,
        "execution_quantity_unit": source.execution_quantity_unit,
        "planned_execution_amount": format(source.planned_execution_amount, "f"),
        "currency": source.currency,
        "founder_id": source.founder_id,
        "confirmed_at": source.confirmed_at.astimezone(timezone.utc).isoformat(),
        "current_execution_confirmed": source.current_execution_confirmed,
        "policy_name": source.policy_name,
        "policy_version": source.policy_version,
        "schema_version": REAL_MONEY_EXECUTION_INTENT_COMMAND_SCHEMA_VERSION,
    }
    return _integrity(_dump(value))


_MANIFEST_KEYS = {
    "opportunity_identity",
    "founder_capital_approval_id",
    "capital_gate_id",
    "capital_requirement_id",
    "intended_order_quantity_id",
    "sourcing_admission_id",
    "sourcing_admission_revision",
    "quote_id",
    "quote_revision",
    "current_deployable_capital_snapshot_id",
    "execution_quantity",
    "execution_quantity_unit",
    "planned_execution_amount",
    "currency",
    "founder_id",
    "confirmed_at",
    "current_execution_confirmed",
    "policy_name",
    "policy_version",
    "schema_version",
}
_PAYLOAD_KEYS = {
    "intent_id",
    "source_manifest",
    "state",
    "blocking_reasons",
    "requested_at",
    "evaluated_at",
    "schema_version",
}


def _manifest(value: RealMoneyExecutionSourceManifest) -> dict[str, object]:
    return {
        "opportunity_identity": {
            "opportunity_id": value.opportunity_identity.opportunity_id,
            "discovery_reference": value.opportunity_identity.discovery_reference,
        },
        "founder_capital_approval_id": value.founder_capital_approval_id,
        "capital_gate_id": value.capital_gate_id,
        "capital_requirement_id": value.capital_requirement_id,
        "intended_order_quantity_id": value.intended_order_quantity_id,
        "sourcing_admission_id": value.sourcing_admission_id,
        "sourcing_admission_revision": value.sourcing_admission_revision,
        "quote_id": value.quote_id,
        "quote_revision": value.quote_revision,
        "current_deployable_capital_snapshot_id": value.current_deployable_capital_snapshot_id,
        "execution_quantity": value.execution_quantity,
        "execution_quantity_unit": value.execution_quantity_unit,
        "planned_execution_amount": format(value.planned_execution_amount, "f"),
        "currency": value.currency,
        "founder_id": value.founder_id,
        "confirmed_at": value.confirmed_at.isoformat(),
        "current_execution_confirmed": value.current_execution_confirmed,
        "policy_name": value.policy_name,
        "policy_version": value.policy_version,
        "schema_version": value.schema_version,
    }


def _load_manifest(value: object) -> RealMoneyExecutionSourceManifest:
    data = _exact(value, _MANIFEST_KEYS, "execution source manifest")
    if data["schema_version"] != REAL_MONEY_EXECUTION_SOURCE_MANIFEST_SCHEMA_VERSION:
        raise UnsupportedRealMoneyExecutionIntentVersionError(
            "unsupported Real-Money Execution source manifest version"
        )
    opportunity = _exact(
        data["opportunity_identity"],
        {"opportunity_id", "discovery_reference"},
        "Opportunity identity",
    )
    return RealMoneyExecutionSourceManifest(
        opportunity_identity=OpportunityIdentity(
            opportunity["opportunity_id"], opportunity["discovery_reference"]
        ),
        founder_capital_approval_id=data["founder_capital_approval_id"],
        capital_gate_id=data["capital_gate_id"],
        capital_requirement_id=data["capital_requirement_id"],
        intended_order_quantity_id=data["intended_order_quantity_id"],
        sourcing_admission_id=data["sourcing_admission_id"],
        sourcing_admission_revision=data["sourcing_admission_revision"],
        quote_id=data["quote_id"],
        quote_revision=data["quote_revision"],
        current_deployable_capital_snapshot_id=data[
            "current_deployable_capital_snapshot_id"
        ],
        execution_quantity=data["execution_quantity"],
        execution_quantity_unit=data["execution_quantity_unit"],
        planned_execution_amount=_decimal(
            data["planned_execution_amount"], "planned_execution_amount"
        ),
        currency=data["currency"],
        founder_id=data["founder_id"],
        confirmed_at=_datetime(data["confirmed_at"], "confirmed_at"),
        current_execution_confirmed=data["current_execution_confirmed"],
        policy_name=data["policy_name"],
        policy_version=data["policy_version"],
        schema_version=data["schema_version"],
    )


def _payload(value: RealMoneyExecutionIntent) -> str:
    return _dump(
        {
            "intent_id": value.intent_id,
            "source_manifest": _manifest(value.source_manifest),
            "state": value.state.value,
            "blocking_reasons": [reason.value for reason in value.blocking_reasons],
            "requested_at": value.requested_at.isoformat(),
            "evaluated_at": value.evaluated_at.isoformat(),
            "schema_version": value.schema_version,
        }
    )


class SQLiteRealMoneyExecutionIntentRepository:
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
        self._approvals = SQLiteFounderCapitalApprovalRepository(connection=self._connection)
        self._gates = SQLiteCapitalGateRepository(connection=self._connection)
        self._requirements = SQLitePlannedAcquisitionCapitalRequirementRepository(
            connection=self._connection
        )
        self._investment = SQLiteCapitalInvestmentFactsRepository(
            connection=self._connection
        )
        self._sourcing = SQLiteSourcingAuthorityRepository(connection=self._connection)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {HISTORY_TABLE}(
                    intent_id TEXT PRIMARY KEY,
                    founder_capital_approval_id TEXT NOT NULL,
                    opportunity_id TEXT NOT NULL,
                    discovery_reference TEXT NOT NULL,
                    state TEXT NOT NULL,
                    action_fingerprint TEXT NOT NULL,
                    policy_name TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(founder_capital_approval_id)
                      REFERENCES founder_capital_approval_history(approval_id)
                )"""
            )
            self._connection.execute(
                f"""CREATE UNIQUE INDEX IF NOT EXISTS {READY_INDEX}
                ON {HISTORY_TABLE}(founder_capital_approval_id)
                WHERE state='{RealMoneyExecutionIntentState.READY_FOR_MANUAL_EXECUTION.value}'"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE}(
                    command_id TEXT PRIMARY KEY,
                    intent_id TEXT NOT NULL,
                    command_fingerprint TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(intent_id) REFERENCES {HISTORY_TABLE}(intent_id)
                )"""
            )
            for table in (HISTORY_TABLE, RECEIPT_TABLE):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END"""
                    )

    def get_founder_capital_approval(self, approval_id: str):
        return self._approvals.get_approval(approval_id)

    def get_capital_gate(self, gate_id: str):
        return self._gates.get_gate(gate_id)

    def get_capital_requirement(self, requirement_id: str):
        return self._requirements.get_requirement(requirement_id)

    def get_intended_order_quantity(self, intent_id: str):
        return self._investment.get_intent(intent_id)

    def get_sourcing_admission(self, admission_id: str, revision: int):
        return self._sourcing.get_admission_revision(admission_id, revision)

    def get_deployable_capital_snapshot(self, snapshot_id: str):
        return self._investment.get_deployable_capital_snapshot(snapshot_id)

    def _history_row(self, intent_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE intent_id=?", (intent_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise RealMoneyExecutionIntentHistoryError(
                "Real-Money Execution Intent history query failed"
            ) from error

    def _load_intent(self, row) -> RealMoneyExecutionIntent:
        try:
            if row["schema_version"] != REAL_MONEY_EXECUTION_INTENT_SCHEMA_VERSION:
                raise UnsupportedRealMoneyExecutionIntentVersionError(
                    "unsupported Real-Money Execution Intent version"
                )
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _integrity(encoded) != row["integrity_fingerprint"]:
                raise ValueError("Real-Money Execution Intent integrity mismatch")
            data = _exact(json.loads(encoded), _PAYLOAD_KEYS, "execution intent payload")
            if data["schema_version"] != REAL_MONEY_EXECUTION_INTENT_SCHEMA_VERSION:
                raise UnsupportedRealMoneyExecutionIntentVersionError(
                    "unsupported execution intent payload version"
                )
            source = _load_manifest(data["source_manifest"])
            intent = RealMoneyExecutionIntent(
                intent_id=data["intent_id"],
                source_manifest=source,
                state=data["state"],
                blocking_reasons=tuple(
                    RealMoneyExecutionIntentBlockingReasonCode(value)
                    for value in data["blocking_reasons"]
                ),
                requested_at=_datetime(data["requested_at"], "requested_at"),
                evaluated_at=_datetime(data["evaluated_at"], "evaluated_at"),
                schema_version=data["schema_version"],
            )
            if (
                intent.intent_id != row["intent_id"]
                or source.founder_capital_approval_id
                != row["founder_capital_approval_id"]
                or source.opportunity_identity.opportunity_id != row["opportunity_id"]
                or source.opportunity_identity.discovery_reference
                != row["discovery_reference"]
                or intent.state.value != row["state"]
                or source.policy_name != row["policy_name"]
                or source.policy_version != row["policy_version"]
                or _fingerprint_action(source) != row["action_fingerprint"]
                or intent.schema_version != row["schema_version"]
            ):
                raise ValueError("Real-Money Execution Intent columns differ from payload")
            self._validate_source(intent)
            return intent
        except UnsupportedRealMoneyExecutionIntentVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedRealMoneyExecutionIntentPersistenceError):
                raise
            raise MalformedRealMoneyExecutionIntentPersistenceError(
                "persisted Real-Money Execution Intent is malformed"
            ) from error

    def get_intent(self, intent_id: str):
        row = self._history_row(intent_id)
        return None if row is None else self._load_intent(row)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?", (command_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise RealMoneyExecutionIntentReceiptError(
                "Real-Money Execution Intent receipt query failed"
            ) from error

    def _load_receipt(self, row) -> RealMoneyExecutionIntentReceipt:
        try:
            if row["schema_version"] != REAL_MONEY_EXECUTION_INTENT_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedRealMoneyExecutionIntentVersionError(
                    "unsupported Real-Money Execution Intent receipt version"
                )
            receipt = RealMoneyExecutionIntentReceipt(
                command_id=row["command_id"],
                intent_id=row["intent_id"],
                command_fingerprint=row["command_fingerprint"],
                committed_at=_datetime(row["committed_at"], "committed_at"),
                schema_version=row["schema_version"],
            )
            if self.get_intent(receipt.intent_id) is None:
                raise ValueError("Real-Money Execution Intent receipt is orphaned")
            return receipt
        except UnsupportedRealMoneyExecutionIntentVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedRealMoneyExecutionIntentPersistenceError):
                raise
            raise MalformedRealMoneyExecutionIntentPersistenceError(
                "persisted Real-Money Execution Intent receipt is malformed"
            ) from error

    def get_receipt(self, command_id: str):
        row = self._receipt_row(command_id)
        return None if row is None else self._load_receipt(row)

    def validate_replay(self, command_id: str, fingerprint: str):
        receipt = self.get_receipt(command_id)
        if receipt is None:
            return None
        if receipt.command_fingerprint != fingerprint:
            raise RealMoneyExecutionIntentReplayConflictError(
                "Real-Money Execution Intent command payload conflicts"
            )
        intent = self.get_intent(receipt.intent_id)
        if intent is None:
            raise MalformedRealMoneyExecutionIntentPersistenceError(
                "Real-Money Execution Intent receipt is orphaned"
            )
        return RealMoneyExecutionIntentPublication(intent, receipt, True)

    def _ready_row(self, approval_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE founder_capital_approval_id=? AND state=?",
                (
                    approval_id,
                    RealMoneyExecutionIntentState.READY_FOR_MANUAL_EXECUTION.value,
                ),
            ).fetchone()
        except sqlite3.Error as error:
            raise RealMoneyExecutionIntentHistoryError(
                "READY Real-Money Execution Intent query failed"
            ) from error

    def find_ready_alias(self, approval_id: str, action_fingerprint: str):
        row = self._ready_row(approval_id)
        if row is None or row["action_fingerprint"] != action_fingerprint:
            return None
        return self._load_intent(row)

    def _validate_source(self, intent: RealMoneyExecutionIntent) -> None:
        source = intent.source_manifest
        approval = self.get_founder_capital_approval(source.founder_capital_approval_id)
        gate = self.get_capital_gate(source.capital_gate_id)
        requirement = self.get_capital_requirement(source.capital_requirement_id)
        intended = self.get_intended_order_quantity(source.intended_order_quantity_id)
        admission = self.get_sourcing_admission(
            source.sourcing_admission_id, source.sourcing_admission_revision
        )
        capital = self.get_deployable_capital_snapshot(
            source.current_deployable_capital_snapshot_id
        )
        if any(value is None for value in (approval, gate, requirement, intended, admission, capital)):
            raise ValueError("Real-Money Execution Intent references missing source")
        gate_source = gate.source_manifest
        if (
            approval.opportunity_identity != source.opportunity_identity
            or approval.capital_gate_id != source.capital_gate_id
            or approval.capital_requirement_id != source.capital_requirement_id
            or approval.intended_order_quantity_id != source.intended_order_quantity_id
            or gate_source.opportunity_identity != source.opportunity_identity
            or gate_source.capital_requirement_id != source.capital_requirement_id
            or gate_source.intended_order_quantity_id != source.intended_order_quantity_id
            or gate_source.sourcing_admission_id != source.sourcing_admission_id
            or gate_source.sourcing_admission_revision != source.sourcing_admission_revision
            or requirement.opportunity_identity != source.opportunity_identity
            or requirement.intended_order_quantity_id != source.intended_order_quantity_id
            or intended.opportunity_identity != source.opportunity_identity
            or admission.selling_product_lineage.opportunity_identity
            != source.opportunity_identity
            or capital.snapshot_id != source.current_deployable_capital_snapshot_id
        ):
            raise ValueError("Real-Money Execution Intent source lineage differs")
        reconstructed = EvaluateRealMoneyExecutionIntentCommand(
            command_id="persistence-reconstruction-only",
            founder_capital_approval_id=source.founder_capital_approval_id,
            quote_id=source.quote_id,
            quote_revision=source.quote_revision,
            current_deployable_capital_snapshot_id=source.current_deployable_capital_snapshot_id,
            execution_quantity=source.execution_quantity,
            execution_quantity_unit=source.execution_quantity_unit,
            planned_execution_amount=source.planned_execution_amount,
            currency=source.currency,
            founder_id=source.founder_id,
            requested_at=intent.requested_at,
            confirmed_at=source.confirmed_at,
            current_execution_confirmed=source.current_execution_confirmed,
            policy_name=source.policy_name,
            policy_version=source.policy_version,
        )
        expected_reasons = EvaluateRealMoneyExecutionIntent.blocking_reasons(
            reconstructed,
            approval,
            gate,
            requirement,
            intended,
            admission,
            capital,
            intent.evaluated_at,
        )
        expected_state = (
            RealMoneyExecutionIntentState.BLOCKED
            if expected_reasons
            else RealMoneyExecutionIntentState.READY_FOR_MANUAL_EXECUTION
        )
        if intent.blocking_reasons != expected_reasons or intent.state is not expected_state:
            raise ValueError("Real-Money Execution Intent safety result differs from exact sources")

    @staticmethod
    def _validate_write(command, intent, receipt) -> None:
        if not isinstance(command, EvaluateRealMoneyExecutionIntentCommand):
            raise TypeError("command must be EvaluateRealMoneyExecutionIntentCommand")
        if not isinstance(intent, RealMoneyExecutionIntent):
            raise TypeError("intent must be RealMoneyExecutionIntent")
        if not isinstance(receipt, RealMoneyExecutionIntentReceipt):
            raise TypeError("receipt must be RealMoneyExecutionIntentReceipt")
        source = intent.source_manifest
        if (
            receipt.command_id != command.command_id
            or receipt.intent_id != intent.intent_id
            or receipt.command_fingerprint != command.fingerprint
            or source.founder_capital_approval_id
            != command.founder_capital_approval_id
            or source.quote_id != command.quote_id
            or source.quote_revision != command.quote_revision
            or source.current_deployable_capital_snapshot_id
            != command.current_deployable_capital_snapshot_id
            or source.execution_quantity != command.execution_quantity
            or source.execution_quantity_unit != command.execution_quantity_unit
            or source.planned_execution_amount != command.planned_execution_amount
            or source.currency != command.currency
            or source.founder_id != command.founder_id
            or source.confirmed_at != command.confirmed_at
            or source.current_execution_confirmed
            != command.current_execution_confirmed
            or source.policy_name != command.policy_name
            or source.policy_version != command.policy_version
            or intent.requested_at != command.requested_at
        ):
            raise RealMoneyExecutionIntentReplayConflictError(
                "command, Real-Money Execution Intent, and receipt differ"
            )

    def _insert_receipt(self, receipt: RealMoneyExecutionIntentReceipt) -> None:
        try:
            self._connection.execute(
                f"""INSERT INTO {RECEIPT_TABLE}(
                    command_id,intent_id,command_fingerprint,committed_at,
                    schema_version,inserted_at
                ) VALUES(?,?,?,?,?,?)""",
                (
                    receipt.command_id,
                    receipt.intent_id,
                    receipt.command_fingerprint,
                    receipt.committed_at.isoformat(),
                    receipt.schema_version,
                    receipt.committed_at.isoformat(),
                ),
            )
        except sqlite3.Error as error:
            raise RealMoneyExecutionIntentReceiptError(
                "Real-Money Execution Intent receipt insert failed"
            ) from error

    def save_alias(self, command, intent, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            if not isinstance(command, EvaluateRealMoneyExecutionIntentCommand):
                raise TypeError("command must be EvaluateRealMoneyExecutionIntentCommand")
            if not isinstance(intent, RealMoneyExecutionIntent):
                raise TypeError("intent must be RealMoneyExecutionIntent")
            if not isinstance(receipt, RealMoneyExecutionIntentReceipt):
                raise TypeError("receipt must be RealMoneyExecutionIntentReceipt")
            row = self._ready_row(command.founder_capital_approval_id)
            if (
                row is None
                or row["intent_id"] != intent.intent_id
                or row["action_fingerprint"] != command.action_fingerprint
                or receipt.command_id != command.command_id
                or receipt.intent_id != intent.intent_id
                or receipt.command_fingerprint != command.fingerprint
            ):
                raise RealMoneyExecutionIntentReadyConflictError(
                    "READY alias no longer matches the exact approved action"
                )
            authoritative = self._load_intent(row)
            self._insert_receipt(receipt)
            try:
                self._commit()
            except sqlite3.Error as error:
                raise RealMoneyExecutionIntentCommitError(
                    "Real-Money Execution Intent alias commit failed"
                ) from error
            return RealMoneyExecutionIntentPublication(
                authoritative, receipt, True
            )
        except Exception:
            self._rollback()
            raise

    def _rollback(self) -> None:
        if self._connection.in_transaction:
            self._connection.rollback()

    def _commit(self) -> None:
        self._connection.commit()

    def save_intent(self, command, intent, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            self._validate_write(command, intent, receipt)
            self._validate_source(intent)
            if intent.state is RealMoneyExecutionIntentState.READY_FOR_MANUAL_EXECUTION:
                ready_row = self._ready_row(
                    intent.source_manifest.founder_capital_approval_id
                )
                if ready_row is not None:
                    existing = self._load_intent(ready_row)
                    if ready_row["action_fingerprint"] != command.action_fingerprint:
                        raise RealMoneyExecutionIntentReadyConflictError(
                            "Founder Capital Approval already has a different READY action"
                        )
                    alias_receipt = RealMoneyExecutionIntentReceipt(
                        command_id=command.command_id,
                        intent_id=existing.intent_id,
                        command_fingerprint=command.fingerprint,
                        committed_at=receipt.committed_at,
                    )
                    self._insert_receipt(alias_receipt)
                    try:
                        self._commit()
                    except sqlite3.Error as error:
                        raise RealMoneyExecutionIntentCommitError(
                            "Real-Money Execution Intent alias commit failed"
                        ) from error
                    return RealMoneyExecutionIntentPublication(
                        existing, alias_receipt, True
                    )

            encoded = _payload(intent)
            source = intent.source_manifest
            try:
                self._connection.execute(
                    f"""INSERT INTO {HISTORY_TABLE}(
                        intent_id,founder_capital_approval_id,opportunity_id,
                        discovery_reference,state,action_fingerprint,policy_name,
                        policy_version,payload_json,integrity_fingerprint,
                        schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        intent.intent_id,
                        source.founder_capital_approval_id,
                        source.opportunity_identity.opportunity_id,
                        source.opportunity_identity.discovery_reference,
                        intent.state.value,
                        command.action_fingerprint,
                        source.policy_name,
                        source.policy_version,
                        encoded,
                        _integrity(encoded),
                        intent.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as error:
                if (
                    intent.state
                    is RealMoneyExecutionIntentState.READY_FOR_MANUAL_EXECUTION
                    and self._ready_row(source.founder_capital_approval_id)
                    is not None
                ):
                    raise RealMoneyExecutionIntentReadyConflictError(
                        "Founder Capital Approval already has a READY action"
                    ) from error
                raise RealMoneyExecutionIntentHistoryError(
                    "Real-Money Execution Intent insert failed"
                ) from error
            except sqlite3.Error as error:
                raise RealMoneyExecutionIntentHistoryError(
                    "Real-Money Execution Intent insert failed"
                ) from error
            self._insert_receipt(receipt)
            try:
                self._commit()
            except sqlite3.Error as error:
                raise RealMoneyExecutionIntentCommitError(
                    "Real-Money Execution Intent commit failed"
                ) from error
            return RealMoneyExecutionIntentPublication(intent, receipt, False)
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
    if name.startswith(
        (
            "Malformed",
            "RealMoney",
            "SQLite",
            "Unsupported",
        )
    )
]
