"""Append-only SQLite persistence for Critical Cost Completeness assessments."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.sourcing.critical_cost import (
    CRITICAL_COST_COMPLETENESS_RECEIPT_SCHEMA_VERSION,
    CriticalCostCompletenessPersistenceResult,
    CriticalCostCompletenessReceipt,
    CriticalCostCompletenessReplayConflictError,
    CriticalCostSourceMismatchError,
    DOMESTIC_COMMERCE_CRITICAL_COST_POLICY,
    PersistCriticalCostCompletenessCommand,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing import (
    CRITICAL_COST_COMPLETENESS_SCHEMA_VERSION,
    CriticalCostCompleteness,
    CriticalCostCompletenessReason,
    CriticalCostCompletenessState,
    CriticalCostReasonCode,
    CriticalCostReasonSeverity,
    SourcingEconomicsBindingReference,
    SourcingEconomicsSourceReference,
)
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository
from app.infrastructure.sourcing.sqlite_landed_cost_repository import (
    SQLiteLandedCostCompositionRepository,
)


class CriticalCostCompletenessPersistenceError(RuntimeError):
    pass


class CriticalCostCompletenessHistoryError(CriticalCostCompletenessPersistenceError):
    pass


class CriticalCostCompletenessReceiptError(CriticalCostCompletenessPersistenceError):
    pass


class CriticalCostCompletenessCommitError(CriticalCostCompletenessPersistenceError):
    pass


class MalformedCriticalCostCompletenessPersistenceError(
    CriticalCostCompletenessPersistenceError
):
    pass


class UnsupportedCriticalCostCompletenessVersionError(
    MalformedCriticalCostCompletenessPersistenceError
):
    pass


def _dump(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return result


def _reason(value: CriticalCostCompletenessReason, ordinal: int) -> dict[str, object]:
    return {
        "ordinal": ordinal,
        "code": value.code.value,
        "severity": value.severity.value,
        "category": value.category,
        "source_reference": value.source_reference,
    }


def _load_reason(value: object, ordinal: int) -> CriticalCostCompletenessReason:
    if not isinstance(value, dict) or value.get("ordinal") != ordinal:
        raise ValueError("reason ordinal is malformed")
    return CriticalCostCompletenessReason(
        CriticalCostReasonCode(value["code"]),
        CriticalCostReasonSeverity(value["severity"]),
        value["category"],
        value["source_reference"],
    )


def _payload(value: CriticalCostCompleteness) -> str:
    source = value.source_reference
    return _dump({
        "opportunity_identity": {
            "opportunity_id": value.opportunity_identity.opportunity_id,
            "discovery_reference": value.opportunity_identity.discovery_reference,
        },
        "composition_id": value.composition_id,
        "binding_reference": {
            "binding_id": value.binding_reference.binding_id,
            "schema_version": value.binding_reference.schema_version,
        },
        "source_reference": {
            "admission_id": source.admission_id,
            "admission_revision": source.admission_revision,
            "quote_id": source.quote_id,
            "quote_revision": source.quote_revision,
            "schema_version": source.schema_version,
        },
        "verified_economics_source": {
            "opportunity_id": value.verified_economics_opportunity_id,
            "snapshot_at": value.verified_economics_snapshot_at.isoformat(),
            "schema_version": value.verified_economics_schema_version,
        },
        "policy_name": value.policy_name,
        "policy_version": value.policy_version,
        "evaluated_at": value.evaluated_at.isoformat(),
        "state": value.state.value,
        "blocking_reasons": [
            _reason(reason, ordinal)
            for ordinal, reason in enumerate(value.blocking_reasons)
        ],
        "warning_reasons": [
            _reason(reason, ordinal)
            for ordinal, reason in enumerate(value.warning_reasons)
        ],
        "schema_version": value.schema_version,
    })


class SQLiteCriticalCostCompletenessRepository:
    """Persists assessed facts; it never re-evaluates completeness or policy."""

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
        self._landed_cost = SQLiteLandedCostCompositionRepository(
            connection=self._connection
        )
        self._verified_economics = SQLiteValidationQueueRepository(
            connection=self._connection
        )
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS critical_cost_completeness_history(
                    assessment_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    discovery_reference TEXT NOT NULL,
                    composition_id TEXT NOT NULL,
                    verified_economics_opportunity_id TEXT NOT NULL,
                    policy_name TEXT NOT NULL,
                    policy_version TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(composition_id) REFERENCES
                      landed_cost_composition_history(composition_id),
                    FOREIGN KEY(verified_economics_opportunity_id) REFERENCES
                      verified_economics_snapshots(opportunity_id)
                )"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS critical_cost_completeness_receipts(
                    command_id TEXT PRIMARY KEY,
                    assessment_id TEXT NOT NULL,
                    command_fingerprint TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(assessment_id) REFERENCES
                      critical_cost_completeness_history(assessment_id)
                )"""
            )
            for table in (
                "critical_cost_completeness_history",
                "critical_cost_completeness_receipts",
            ):
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

    def get_composition(self, composition_id: str):
        return self._landed_cost.get_composition(composition_id)

    def get_binding(self, reference: SourcingEconomicsBindingReference):
        return self._landed_cost.get_binding(reference)

    def get_source_admission(self, reference: SourcingEconomicsSourceReference):
        return self._landed_cost.get_source_admission(reference)

    def get_verified_economics_snapshot(self, opportunity_id: str):
        return self._verified_economics.get_verified_economics_snapshot(opportunity_id)

    def _assessment_row(self, assessment_id: str):
        try:
            return self._connection.execute(
                "SELECT * FROM critical_cost_completeness_history WHERE assessment_id=?",
                (assessment_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise CriticalCostCompletenessHistoryError("assessment query failed") from error

    def _assessment(self, row) -> CriticalCostCompleteness:
        try:
            if row["schema_version"] != CRITICAL_COST_COMPLETENESS_SCHEMA_VERSION:
                raise UnsupportedCriticalCostCompletenessVersionError(
                    "unsupported Critical Cost Completeness version"
                )
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _fingerprint(encoded) != row["integrity_fingerprint"]:
                raise ValueError("assessment integrity fingerprint mismatch")
            payload = json.loads(encoded)
            if not isinstance(payload, dict) or payload.get("schema_version") != row["schema_version"]:
                raise ValueError("assessment payload is malformed")
            opportunity = payload["opportunity_identity"]
            binding = payload["binding_reference"]
            source = payload["source_reference"]
            verified = payload["verified_economics_source"]
            blocking = payload["blocking_reasons"]
            warnings = payload["warning_reasons"]
            if not all(isinstance(value, dict) for value in (opportunity, binding, source, verified)):
                raise ValueError("assessment source lineage is malformed")
            if not isinstance(blocking, list) or not isinstance(warnings, list):
                raise ValueError("assessment reasons must be ordered lists")
            value = CriticalCostCompleteness(
                opportunity_identity=OpportunityIdentity(
                    opportunity["opportunity_id"], opportunity["discovery_reference"]
                ),
                composition_id=payload["composition_id"],
                binding_reference=SourcingEconomicsBindingReference(
                    binding["binding_id"], binding["schema_version"]
                ),
                source_reference=SourcingEconomicsSourceReference(
                    source["admission_id"], source["admission_revision"],
                    source["quote_id"], source["quote_revision"],
                    source["schema_version"],
                ),
                verified_economics_opportunity_id=verified["opportunity_id"],
                verified_economics_snapshot_at=_datetime(
                    verified["snapshot_at"], "verified snapshot_at"
                ),
                verified_economics_schema_version=verified["schema_version"],
                policy_name=payload["policy_name"],
                policy_version=payload["policy_version"],
                evaluated_at=_datetime(payload["evaluated_at"], "evaluated_at"),
                state=CriticalCostCompletenessState(payload["state"]),
                blocking_reasons=tuple(
                    _load_reason(reason, ordinal)
                    for ordinal, reason in enumerate(blocking)
                ),
                warning_reasons=tuple(
                    _load_reason(reason, ordinal)
                    for ordinal, reason in enumerate(warnings)
                ),
                schema_version=payload["schema_version"],
            )
            if (
                value.opportunity_identity.opportunity_id != row["opportunity_id"]
                or value.opportunity_identity.discovery_reference != row["discovery_reference"]
                or value.composition_id != row["composition_id"]
                or value.verified_economics_opportunity_id
                != row["verified_economics_opportunity_id"]
                or value.policy_name != row["policy_name"]
                or value.policy_version != row["policy_version"]
            ):
                raise ValueError("assessment columns differ from payload")
            self._validate_source_integrity(value)
            return value
        except UnsupportedCriticalCostCompletenessVersionError:
            raise
        except Exception as error:
            raise MalformedCriticalCostCompletenessPersistenceError(
                "persisted Critical Cost Completeness assessment is malformed"
            ) from error

    def _validate_source_integrity(self, assessment: CriticalCostCompleteness) -> None:
        composition = self.get_composition(assessment.composition_id)
        if (
            composition is None
            or composition.opportunity_identity != assessment.opportunity_identity
            or composition.binding_reference != assessment.binding_reference
        ):
            raise ValueError("assessment references malformed composition lineage")
        binding = self.get_binding(assessment.binding_reference)
        if binding is None or binding.source_reference != assessment.source_reference:
            raise ValueError("assessment references malformed Sourcing lineage")
        verified = self.get_verified_economics_snapshot(
            assessment.verified_economics_opportunity_id
        )
        if (
            verified is None
            or verified.opportunity_id != assessment.opportunity_identity.opportunity_id
            or verified.snapshot_at != assessment.verified_economics_snapshot_at
            or verified.schema_version != assessment.verified_economics_schema_version
        ):
            raise ValueError("assessment references malformed Verified Economics source")
        if (
            assessment.policy_name != DOMESTIC_COMMERCE_CRITICAL_COST_POLICY.name
            or assessment.policy_version != DOMESTIC_COMMERCE_CRITICAL_COST_POLICY.version
        ):
            raise ValueError("assessment policy identity/version is unsupported")

    def get_assessment(self, assessment_id: str) -> CriticalCostCompleteness | None:
        row = self._assessment_row(assessment_id)
        return None if row is None else self._assessment(row)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                "SELECT * FROM critical_cost_completeness_receipts WHERE command_id=?",
                (command_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise CriticalCostCompletenessReceiptError("receipt query failed") from error

    def _receipt(self, row) -> CriticalCostCompletenessReceipt:
        try:
            if row["schema_version"] != CRITICAL_COST_COMPLETENESS_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedCriticalCostCompletenessVersionError(
                    "unsupported Critical Cost Completeness receipt version"
                )
            return CriticalCostCompletenessReceipt(
                row["command_id"], row["assessment_id"],
                row["command_fingerprint"],
                _datetime(row["committed_at"], "committed_at"),
                row["schema_version"],
            )
        except UnsupportedCriticalCostCompletenessVersionError:
            raise
        except Exception as error:
            raise MalformedCriticalCostCompletenessPersistenceError(
                "persisted Critical Cost Completeness receipt is malformed"
            ) from error

    def get_receipt(self, command_id: str) -> CriticalCostCompletenessReceipt | None:
        row = self._receipt_row(command_id)
        return None if row is None else self._receipt(row)

    def validate_replay(
        self, command_id: str, fingerprint: str
    ) -> CriticalCostCompletenessPersistenceResult | None:
        row = self._receipt_row(command_id)
        if row is None:
            return None
        receipt = self._receipt(row)
        if receipt.command_fingerprint != fingerprint:
            raise CriticalCostCompletenessReplayConflictError(
                "Critical Cost Completeness command payload conflicts"
            )
        assessment = self.get_assessment(receipt.assessment_id)
        if assessment is None:
            raise MalformedCriticalCostCompletenessPersistenceError(
                "receipt references missing Critical Cost assessment"
            )
        return CriticalCostCompletenessPersistenceResult(assessment, receipt, True)

    @staticmethod
    def _validate_write(command, assessment, receipt) -> None:
        if not isinstance(command, PersistCriticalCostCompletenessCommand):
            raise TypeError("command must be PersistCriticalCostCompletenessCommand")
        if not isinstance(assessment, CriticalCostCompleteness):
            raise TypeError("assessment must be CriticalCostCompleteness")
        if not isinstance(receipt, CriticalCostCompletenessReceipt):
            raise TypeError("receipt must be CriticalCostCompletenessReceipt")
        if (
            assessment.composition_id != command.composition_id
            or assessment.verified_economics_opportunity_id
            != command.verified_economics_opportunity_id
            or assessment.verified_economics_snapshot_at
            != command.verified_economics_snapshot_at
            or assessment.verified_economics_schema_version
            != command.verified_economics_schema_version
            or assessment.policy_name != command.policy_name
            or assessment.policy_version != command.policy_version
            or receipt.command_id != command.command_id
            or receipt.command_fingerprint != command.fingerprint
        ):
            raise CriticalCostCompletenessReplayConflictError(
                "command, assessment, and receipt do not match"
            )

    def save_assessment(self, command, assessment, receipt):
        self._validate_write(command, assessment, receipt)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            try:
                self._validate_source_integrity(assessment)
            except Exception as error:
                raise CriticalCostSourceMismatchError(
                    "assessment exact persisted sources differ"
                ) from error
            encoded = _payload(assessment)
            try:
                self._connection.execute(
                    """INSERT INTO critical_cost_completeness_history
                    VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        receipt.assessment_id,
                        assessment.opportunity_identity.opportunity_id,
                        assessment.opportunity_identity.discovery_reference,
                        assessment.composition_id,
                        assessment.verified_economics_opportunity_id,
                        assessment.policy_name,
                        assessment.policy_version,
                        encoded,
                        _fingerprint(encoded),
                        assessment.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise CriticalCostCompletenessHistoryError(
                    "assessment insert failed"
                ) from error
            try:
                self._connection.execute(
                    """INSERT INTO critical_cost_completeness_receipts
                    VALUES(?,?,?,?,?,?)""",
                    (
                        receipt.command_id,
                        receipt.assessment_id,
                        receipt.command_fingerprint,
                        receipt.committed_at.isoformat(),
                        receipt.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise CriticalCostCompletenessReceiptError(
                    "assessment receipt insert failed"
                ) from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise CriticalCostCompletenessCommitError(
                    "assessment commit failed"
                ) from error
            return CriticalCostCompletenessPersistenceResult(
                assessment, receipt, False
            )
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
    name for name in globals()
    if name.startswith("SQLite")
    or name.startswith("CriticalCost")
    or name.startswith("Malformed")
    or name.startswith("Unsupported")
]
