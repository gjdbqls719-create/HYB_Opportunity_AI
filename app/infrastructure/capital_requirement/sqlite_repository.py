"""Append-only SQLite persistence for planned acquisition capital requirements."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.capital_requirement import (
    PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_RECEIPT_SCHEMA_VERSION,
    CalculatePlannedAcquisitionCapitalRequirementCommand,
    PlannedAcquisitionCapitalRequirementPublication,
    PlannedAcquisitionCapitalRequirementReceipt,
    PlannedAcquisitionCapitalRequirementReplayConflictError,
)
from app.domain.capital import (
    PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_SCHEMA_VERSION,
    PlannedAcquisitionCapitalRequirement,
    PlannedAcquisitionCapitalRequirementBlockingReason,
    PlannedAcquisitionCapitalRequirementState,
    UpfrontCostScopeStatus,
    UpfrontCostScopeVerification,
)
from app.domain.decision_engine import OpportunityIdentity
from app.infrastructure.capital_investment import SQLiteCapitalInvestmentFactsRepository
from app.infrastructure.sourcing import (
    SQLiteAcquisitionCostNormalizationRepository,
    SQLiteLandedCostCompositionRepository,
)


HISTORY_TABLE = "planned_acquisition_capital_requirement_history"
RECEIPT_TABLE = "planned_acquisition_capital_requirement_receipts"


class PlannedAcquisitionCapitalRequirementPersistenceError(RuntimeError):
    pass


class PlannedAcquisitionCapitalRequirementHistoryError(
    PlannedAcquisitionCapitalRequirementPersistenceError
):
    pass


class PlannedAcquisitionCapitalRequirementReceiptError(
    PlannedAcquisitionCapitalRequirementPersistenceError
):
    pass


class PlannedAcquisitionCapitalRequirementCommitError(
    PlannedAcquisitionCapitalRequirementPersistenceError
):
    pass


class MalformedPlannedAcquisitionCapitalRequirementPersistenceError(
    PlannedAcquisitionCapitalRequirementPersistenceError
):
    pass


class UnsupportedPlannedAcquisitionCapitalRequirementVersionError(
    MalformedPlannedAcquisitionCapitalRequirementPersistenceError
):
    pass


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _integrity(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


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
_SCOPE_KEYS = {
    "status",
    "intended_order_quantity_id",
    "acquisition_normalization_id",
    "operator_id",
    "verified_at",
    "semantics_version",
}
_REQUIREMENT_KEYS = {
    "requirement_id",
    "opportunity_identity",
    "state",
    "intended_order_quantity_id",
    "acquisition_normalization_id",
    "sourcing_binding_id",
    "sourcing_admission_id",
    "sourcing_admission_revision",
    "quote_id",
    "quote_revision",
    "quantity",
    "quantity_unit",
    "normalized_acquisition_cost_per_unit",
    "currency",
    "planned_acquisition_capital",
    "scope_verification",
    "blocking_reasons",
    "policy_name",
    "policy_version",
    "policy_precision",
    "policy_rounding",
    "requested_at",
    "calculated_at",
    "schema_version",
}


def _opportunity(value: OpportunityIdentity) -> dict[str, str]:
    return {
        "opportunity_id": value.opportunity_id,
        "discovery_reference": value.discovery_reference,
    }


def _load_opportunity(value: object) -> OpportunityIdentity:
    data = _exact(value, _OPPORTUNITY_KEYS, "Opportunity identity")
    return OpportunityIdentity(data["opportunity_id"], data["discovery_reference"])


def _scope(value: UpfrontCostScopeVerification) -> dict[str, object]:
    return {
        "status": value.status.value,
        "intended_order_quantity_id": value.intended_order_quantity_id,
        "acquisition_normalization_id": value.acquisition_normalization_id,
        "operator_id": value.operator_id,
        "verified_at": value.verified_at.isoformat(),
        "semantics_version": value.semantics_version,
    }


def _load_scope(value: object) -> UpfrontCostScopeVerification:
    data = _exact(value, _SCOPE_KEYS, "upfront-cost scope verification")
    return UpfrontCostScopeVerification(
        status=UpfrontCostScopeStatus(data["status"]),
        intended_order_quantity_id=data["intended_order_quantity_id"],
        acquisition_normalization_id=data["acquisition_normalization_id"],
        operator_id=data["operator_id"],
        verified_at=_datetime(data["verified_at"], "verified_at"),
        semantics_version=data["semantics_version"],
    )


def _payload(value: PlannedAcquisitionCapitalRequirement) -> str:
    return _dump(
        {
            "requirement_id": value.requirement_id,
            "opportunity_identity": _opportunity(value.opportunity_identity),
            "state": value.state.value,
            "intended_order_quantity_id": value.intended_order_quantity_id,
            "acquisition_normalization_id": value.acquisition_normalization_id,
            "sourcing_binding_id": value.sourcing_binding_id,
            "sourcing_admission_id": value.sourcing_admission_id,
            "sourcing_admission_revision": value.sourcing_admission_revision,
            "quote_id": value.quote_id,
            "quote_revision": value.quote_revision,
            "quantity": value.quantity,
            "quantity_unit": value.quantity_unit,
            "normalized_acquisition_cost_per_unit": format(
                value.normalized_acquisition_cost_per_unit, "f"
            ),
            "currency": value.currency,
            "planned_acquisition_capital": (
                None
                if value.planned_acquisition_capital is None
                else format(value.planned_acquisition_capital, "f")
            ),
            "scope_verification": _scope(value.scope_verification),
            "blocking_reasons": [item.value for item in value.blocking_reasons],
            "policy_name": value.policy_name,
            "policy_version": value.policy_version,
            "policy_precision": value.policy_precision,
            "policy_rounding": value.policy_rounding,
            "requested_at": value.requested_at.isoformat(),
            "calculated_at": value.calculated_at.isoformat(),
            "schema_version": value.schema_version,
        }
    )


class SQLitePlannedAcquisitionCapitalRequirementRepository:
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
        self._investment = SQLiteCapitalInvestmentFactsRepository(
            connection=self._connection
        )
        self._normalizations = SQLiteAcquisitionCostNormalizationRepository(
            connection=self._connection
        )
        self._landed_cost = SQLiteLandedCostCompositionRepository(
            connection=self._connection
        )
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {HISTORY_TABLE}(
                    requirement_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    discovery_reference TEXT NOT NULL,
                    intended_order_quantity_id TEXT NOT NULL,
                    acquisition_normalization_id TEXT NOT NULL,
                    sourcing_binding_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(intended_order_quantity_id) REFERENCES
                      capital_investment_intent_history(intent_id),
                    FOREIGN KEY(acquisition_normalization_id) REFERENCES
                      acquisition_cost_normalization_history(normalization_id),
                    FOREIGN KEY(sourcing_binding_id) REFERENCES
                      sourcing_economics_binding_history(binding_id)
                )"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE}(
                    command_id TEXT PRIMARY KEY,
                    requirement_id TEXT NOT NULL,
                    command_fingerprint TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(requirement_id) REFERENCES {HISTORY_TABLE}(requirement_id)
                )"""
            )
            for table in (HISTORY_TABLE, RECEIPT_TABLE):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END"""
                    )

    def get_intent(self, intent_id: str):
        return self._investment.get_intent(intent_id)

    def get_normalization(self, normalization_id: str):
        return self._normalizations.get_normalization(normalization_id)

    def get_composition(self, composition_id: str):
        return self._landed_cost.get_composition(composition_id)

    def get_binding(self, reference):
        return self._landed_cost.get_binding(reference)

    def _history_row(self, requirement_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE requirement_id=?",
                (requirement_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise PlannedAcquisitionCapitalRequirementHistoryError(
                "planned acquisition capital requirement query failed"
            ) from error

    def _load_requirement(self, row) -> PlannedAcquisitionCapitalRequirement:
        try:
            if row["schema_version"] != PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_SCHEMA_VERSION:
                raise UnsupportedPlannedAcquisitionCapitalRequirementVersionError(
                    "unsupported planned acquisition capital requirement version"
                )
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _integrity(encoded) != row["integrity_fingerprint"]:
                raise ValueError("requirement integrity fingerprint mismatch")
            data = _exact(json.loads(encoded), _REQUIREMENT_KEYS, "requirement payload")
            amount = data["planned_acquisition_capital"]
            reasons = data["blocking_reasons"]
            if not isinstance(reasons, list):
                raise ValueError("blocking reasons must be ordered list")
            value = PlannedAcquisitionCapitalRequirement(
                requirement_id=data["requirement_id"],
                opportunity_identity=_load_opportunity(data["opportunity_identity"]),
                state=PlannedAcquisitionCapitalRequirementState(data["state"]),
                intended_order_quantity_id=data["intended_order_quantity_id"],
                acquisition_normalization_id=data["acquisition_normalization_id"],
                sourcing_binding_id=data["sourcing_binding_id"],
                sourcing_admission_id=data["sourcing_admission_id"],
                sourcing_admission_revision=data["sourcing_admission_revision"],
                quote_id=data["quote_id"],
                quote_revision=data["quote_revision"],
                quantity=data["quantity"],
                quantity_unit=data["quantity_unit"],
                normalized_acquisition_cost_per_unit=_decimal(
                    data["normalized_acquisition_cost_per_unit"],
                    "normalized_acquisition_cost_per_unit",
                ),
                currency=data["currency"],
                planned_acquisition_capital=(
                    None if amount is None else _decimal(amount, "planned_acquisition_capital")
                ),
                scope_verification=_load_scope(data["scope_verification"]),
                blocking_reasons=tuple(
                    PlannedAcquisitionCapitalRequirementBlockingReason(item)
                    for item in reasons
                ),
                policy_name=data["policy_name"],
                policy_version=data["policy_version"],
                policy_precision=data["policy_precision"],
                policy_rounding=data["policy_rounding"],
                requested_at=_datetime(data["requested_at"], "requested_at"),
                calculated_at=_datetime(data["calculated_at"], "calculated_at"),
                schema_version=data["schema_version"],
            )
            if (
                value.requirement_id != row["requirement_id"]
                or value.opportunity_identity.opportunity_id != row["opportunity_id"]
                or value.opportunity_identity.discovery_reference != row["discovery_reference"]
                or value.intended_order_quantity_id != row["intended_order_quantity_id"]
                or value.acquisition_normalization_id != row["acquisition_normalization_id"]
                or value.sourcing_binding_id != row["sourcing_binding_id"]
                or value.state.value != row["state"]
                or value.currency != row["currency"]
                or value.schema_version != row["schema_version"]
            ):
                raise ValueError("requirement columns differ from payload")
            self._validate_sources(value)
            return value
        except UnsupportedPlannedAcquisitionCapitalRequirementVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedPlannedAcquisitionCapitalRequirementPersistenceError):
                raise
            raise MalformedPlannedAcquisitionCapitalRequirementPersistenceError(
                "persisted planned acquisition capital requirement is malformed"
            ) from error

    def get_requirement(self, requirement_id: str):
        row = self._history_row(requirement_id)
        return None if row is None else self._load_requirement(row)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?", (command_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise PlannedAcquisitionCapitalRequirementReceiptError(
                "planned acquisition capital receipt query failed"
            ) from error

    def _load_receipt(self, row) -> PlannedAcquisitionCapitalRequirementReceipt:
        try:
            if row["schema_version"] != PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedPlannedAcquisitionCapitalRequirementVersionError(
                    "unsupported planned acquisition capital receipt version"
                )
            value = PlannedAcquisitionCapitalRequirementReceipt(
                command_id=row["command_id"],
                requirement_id=row["requirement_id"],
                command_fingerprint=row["command_fingerprint"],
                committed_at=_datetime(row["committed_at"], "committed_at"),
                schema_version=row["schema_version"],
            )
            if self.get_requirement(value.requirement_id) is None:
                raise ValueError("requirement receipt is orphaned")
            return value
        except UnsupportedPlannedAcquisitionCapitalRequirementVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedPlannedAcquisitionCapitalRequirementPersistenceError):
                raise
            raise MalformedPlannedAcquisitionCapitalRequirementPersistenceError(
                "persisted planned acquisition capital receipt is malformed"
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
            raise PlannedAcquisitionCapitalRequirementReplayConflictError(
                "planned acquisition capital command payload conflicts"
            )
        requirement = self.get_requirement(receipt.requirement_id)
        if requirement is None:
            raise MalformedPlannedAcquisitionCapitalRequirementPersistenceError(
                "requirement receipt is orphaned"
            )
        return PlannedAcquisitionCapitalRequirementPublication(
            requirement, receipt, True
        )

    def _validate_sources(self, value: PlannedAcquisitionCapitalRequirement) -> None:
        intent = self.get_intent(value.intended_order_quantity_id)
        normalization = self.get_normalization(value.acquisition_normalization_id)
        if intent is None or normalization is None:
            raise ValueError("requirement references missing intent or normalization")
        composition = self.get_composition(normalization.composition_id)
        if composition is None:
            raise ValueError("requirement references missing composition")
        binding = self.get_binding(composition.binding_reference)
        if binding is None:
            raise ValueError("requirement references missing binding")
        source = binding.source_reference
        if (
            any(
                identity != value.opportunity_identity
                for identity in (
                    intent.opportunity_identity,
                    normalization.opportunity_identity,
                    composition.opportunity_identity,
                    binding.opportunity_identity,
                )
            )
            or normalization.composition_id != composition.composition_id
            or binding.reference != composition.binding_reference
            or binding.binding_id != value.sourcing_binding_id
            or source.admission_id != intent.sourcing_admission_id
            or source.admission_revision != intent.sourcing_admission_revision
            or source.quote_id != intent.quote_id
            or source.quote_revision != intent.quote_revision
            or source.admission_id != value.sourcing_admission_id
            or source.admission_revision != value.sourcing_admission_revision
            or source.quote_id != value.quote_id
            or source.quote_revision != value.quote_revision
            or intent.quantity != value.quantity
            or intent.quantity_unit != value.quantity_unit
            or normalization.total_per_unit_acquisition_cost
            != value.normalized_acquisition_cost_per_unit
            or normalization.target_currency != value.currency
        ):
            raise ValueError("requirement source lineage differs")

    @staticmethod
    def _validate_write(command, requirement, receipt) -> None:
        if not isinstance(command, CalculatePlannedAcquisitionCapitalRequirementCommand):
            raise TypeError("command must be CalculatePlannedAcquisitionCapitalRequirementCommand")
        if not isinstance(requirement, PlannedAcquisitionCapitalRequirement):
            raise TypeError("requirement must be PlannedAcquisitionCapitalRequirement")
        if not isinstance(receipt, PlannedAcquisitionCapitalRequirementReceipt):
            raise TypeError("receipt must be PlannedAcquisitionCapitalRequirementReceipt")
        verification = requirement.scope_verification
        if (
            receipt.command_id != command.command_id
            or receipt.requirement_id != requirement.requirement_id
            or receipt.command_fingerprint != command.fingerprint
            or requirement.opportunity_identity != command.opportunity_identity
            or requirement.intended_order_quantity_id != command.intended_order_quantity_id
            or requirement.acquisition_normalization_id != command.acquisition_normalization_id
            or verification.status is not command.scope_status
            or verification.operator_id != command.operator_id
            or verification.verified_at != command.verified_at
            or requirement.requested_at != command.requested_at
            or requirement.policy_name != command.policy_name
            or requirement.policy_version != command.policy_version
        ):
            raise PlannedAcquisitionCapitalRequirementReplayConflictError(
                "command, requirement, and receipt differ"
            )

    def save_requirement(self, command, requirement, receipt):
        self._validate_write(command, requirement, receipt)
        self._validate_sources(requirement)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            existing = self._receipt_row(command.command_id)
            if existing is not None:
                stored_receipt = self._load_receipt(existing)
                if stored_receipt.command_fingerprint != command.fingerprint:
                    raise PlannedAcquisitionCapitalRequirementReplayConflictError(
                        "planned acquisition capital command payload conflicts"
                    )
                stored = self.get_requirement(stored_receipt.requirement_id)
                if stored is None:
                    raise MalformedPlannedAcquisitionCapitalRequirementPersistenceError(
                        "requirement receipt is orphaned"
                    )
                self._rollback()
                return PlannedAcquisitionCapitalRequirementPublication(
                    stored, stored_receipt, True
                )
            encoded = _payload(requirement)
            try:
                self._connection.execute(
                    f"""INSERT INTO {HISTORY_TABLE}(
                        requirement_id,opportunity_id,discovery_reference,
                        intended_order_quantity_id,acquisition_normalization_id,
                        sourcing_binding_id,state,currency,payload_json,
                        integrity_fingerprint,schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        requirement.requirement_id,
                        requirement.opportunity_identity.opportunity_id,
                        requirement.opportunity_identity.discovery_reference,
                        requirement.intended_order_quantity_id,
                        requirement.acquisition_normalization_id,
                        requirement.sourcing_binding_id,
                        requirement.state.value,
                        requirement.currency,
                        encoded,
                        _integrity(encoded),
                        requirement.schema_version,
                        requirement.calculated_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise PlannedAcquisitionCapitalRequirementHistoryError(
                    "planned acquisition capital requirement insert failed"
                ) from error
            try:
                self._connection.execute(
                    f"""INSERT INTO {RECEIPT_TABLE}(
                        command_id,requirement_id,command_fingerprint,committed_at,
                        schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?)""",
                    (
                        receipt.command_id,
                        receipt.requirement_id,
                        receipt.command_fingerprint,
                        receipt.committed_at.isoformat(),
                        receipt.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise PlannedAcquisitionCapitalRequirementReceiptError(
                    "planned acquisition capital receipt insert failed"
                ) from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise PlannedAcquisitionCapitalRequirementCommitError(
                    "planned acquisition capital transaction commit failed"
                ) from error
            return PlannedAcquisitionCapitalRequirementPublication(
                requirement, receipt, False
            )
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
    if name.startswith(("SQLite", "Planned", "Malformed", "Unsupported"))
]
