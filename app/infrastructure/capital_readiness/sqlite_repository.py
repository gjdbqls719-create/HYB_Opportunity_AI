"""Append-only SQLite persistence for Capital Readiness assessments."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.capital_readiness import (
    CAPITAL_READINESS_RECEIPT_SCHEMA_VERSION,
    CapitalReadinessPublication,
    CapitalReadinessReceipt,
    CapitalReadinessReplayConflictError,
    EvaluateCapitalReadinessCommand,
)
from app.domain.capital import (
    CAPITAL_READINESS_SCHEMA_VERSION,
    CAPITAL_READINESS_SOURCE_MANIFEST_SCHEMA_VERSION,
    CapitalReadinessAssessment,
    CapitalReadinessReason,
    CapitalReadinessReasonCode,
    CapitalReadinessSourceManifest,
    CapitalReadinessState,
)
from app.domain.decision_engine import OpportunityIdentity
from app.infrastructure.conservative_economics import SQLiteConservativeEconomicsRepository
from app.infrastructure.domestic_market_validation import SQLiteDomesticMarketValidationRepository
from app.infrastructure.economics_source_composition import SQLiteEconomicsSourceCompositionRepository
from app.infrastructure.sourcing import SQLiteCriticalCostCompletenessRepository


HISTORY_TABLE = "capital_readiness_history"
RECEIPT_TABLE = "capital_readiness_receipts"


class CapitalReadinessPersistenceError(RuntimeError):
    pass


class CapitalReadinessHistoryError(CapitalReadinessPersistenceError):
    pass


class CapitalReadinessReceiptError(CapitalReadinessPersistenceError):
    pass


class CapitalReadinessCommitError(CapitalReadinessPersistenceError):
    pass


class MalformedCapitalReadinessPersistenceError(CapitalReadinessPersistenceError):
    pass


class UnsupportedCapitalReadinessVersionError(MalformedCapitalReadinessPersistenceError):
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
    "opportunity_identity", "conservative_economics_result_id",
    "economics_source_composition_id", "acquisition_normalization_id",
    "landed_cost_composition_id", "domestic_market_validation_assessment_id",
    "critical_cost_assessment_id", "sourcing_binding_id",
    "sourcing_admission_id", "sourcing_admission_revision", "quote_id",
    "quote_revision", "product_match_verification_id", "quote_valid_until",
    "schema_version",
}


def _manifest(value: CapitalReadinessSourceManifest) -> dict[str, object]:
    return {
        "opportunity_identity": {
            "opportunity_id": value.opportunity_identity.opportunity_id,
            "discovery_reference": value.opportunity_identity.discovery_reference,
        },
        "conservative_economics_result_id": value.conservative_economics_result_id,
        "economics_source_composition_id": value.economics_source_composition_id,
        "acquisition_normalization_id": value.acquisition_normalization_id,
        "landed_cost_composition_id": value.landed_cost_composition_id,
        "domestic_market_validation_assessment_id": value.domestic_market_validation_assessment_id,
        "critical_cost_assessment_id": value.critical_cost_assessment_id,
        "sourcing_binding_id": value.sourcing_binding_id,
        "sourcing_admission_id": value.sourcing_admission_id,
        "sourcing_admission_revision": value.sourcing_admission_revision,
        "quote_id": value.quote_id,
        "quote_revision": value.quote_revision,
        "product_match_verification_id": value.product_match_verification_id,
        "quote_valid_until": (
            None if value.quote_valid_until is None else value.quote_valid_until.isoformat()
        ),
        "schema_version": value.schema_version,
    }


def _load_manifest(value: object) -> CapitalReadinessSourceManifest:
    data = _exact(value, _MANIFEST_KEYS, "Capital Readiness source manifest")
    if data["schema_version"] != CAPITAL_READINESS_SOURCE_MANIFEST_SCHEMA_VERSION:
        raise UnsupportedCapitalReadinessVersionError("unsupported source manifest version")
    opportunity = _exact(
        data["opportunity_identity"],
        {"opportunity_id", "discovery_reference"},
        "Opportunity identity",
    )
    return CapitalReadinessSourceManifest(
        opportunity_identity=OpportunityIdentity(
            opportunity["opportunity_id"], opportunity["discovery_reference"]
        ),
        conservative_economics_result_id=data["conservative_economics_result_id"],
        economics_source_composition_id=data["economics_source_composition_id"],
        acquisition_normalization_id=data["acquisition_normalization_id"],
        landed_cost_composition_id=data["landed_cost_composition_id"],
        domestic_market_validation_assessment_id=data[
            "domestic_market_validation_assessment_id"
        ],
        critical_cost_assessment_id=data["critical_cost_assessment_id"],
        sourcing_binding_id=data["sourcing_binding_id"],
        sourcing_admission_id=data["sourcing_admission_id"],
        sourcing_admission_revision=data["sourcing_admission_revision"],
        quote_id=data["quote_id"],
        quote_revision=data["quote_revision"],
        product_match_verification_id=data["product_match_verification_id"],
        quote_valid_until=(
            None
            if data["quote_valid_until"] is None
            else _datetime(data["quote_valid_until"], "quote_valid_until")
        ),
        schema_version=data["schema_version"],
    )


_PAYLOAD_KEYS = {
    "assessment_id", "source_manifest", "state", "blocking_reasons",
    "policy_name", "policy_version", "requested_at", "evaluated_at",
    "schema_version",
}


def _payload(value: CapitalReadinessAssessment) -> str:
    return _dump({
        "assessment_id": value.assessment_id,
        "source_manifest": _manifest(value.source_manifest),
        "state": value.state.value,
        "blocking_reasons": [reason.code.value for reason in value.blocking_reasons],
        "policy_name": value.policy_name,
        "policy_version": value.policy_version,
        "requested_at": value.requested_at.isoformat(),
        "evaluated_at": value.evaluated_at.isoformat(),
        "schema_version": value.schema_version,
    })


class SQLiteCapitalReadinessRepository:
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
        self._conservative = SQLiteConservativeEconomicsRepository(connection=self._connection)
        self._economics_sources = SQLiteEconomicsSourceCompositionRepository(
            connection=self._connection
        )
        self._critical = SQLiteCriticalCostCompletenessRepository(connection=self._connection)
        self._market = SQLiteDomesticMarketValidationRepository(connection=self._connection)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(f"""CREATE TABLE IF NOT EXISTS {HISTORY_TABLE}(
                assessment_id TEXT PRIMARY KEY,
                opportunity_id TEXT NOT NULL,
                discovery_reference TEXT NOT NULL,
                conservative_result_id TEXT NOT NULL,
                market_validation_assessment_id TEXT NOT NULL,
                critical_cost_assessment_id TEXT NOT NULL,
                state TEXT NOT NULL,
                policy_name TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                integrity_fingerprint TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL
            )""")
            self._connection.execute(f"""CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE}(
                command_id TEXT PRIMARY KEY,
                assessment_id TEXT NOT NULL,
                command_fingerprint TEXT NOT NULL,
                committed_at TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL,
                FOREIGN KEY(assessment_id) REFERENCES {HISTORY_TABLE}(assessment_id)
            )""")
            for table in (HISTORY_TABLE, RECEIPT_TABLE):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(f"""CREATE TRIGGER IF NOT EXISTS
                        trg_{table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END""")

    def get_conservative_economics_result(self, result_id):
        return self._conservative.get_result(result_id)

    def get_economics_source_composition(self, composition_id):
        return self._economics_sources.get_composition(composition_id)

    def get_acquisition_normalization(self, normalization_id):
        return self._economics_sources.get_normalization(normalization_id)

    def get_critical_cost_assessment(self, assessment_id):
        return self._critical.get_assessment(assessment_id)

    def get_domestic_market_validation(self, assessment_id):
        return self._market.get_assessment(assessment_id)

    def get_sourcing_binding(self, reference):
        return self._critical.get_binding(reference)

    def get_sourcing_admission(self, reference):
        return self._critical.get_source_admission(reference)

    def _history_row(self, assessment_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE assessment_id=?", (assessment_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise CapitalReadinessHistoryError("Capital Readiness history query failed") from error

    def _load_assessment(self, row) -> CapitalReadinessAssessment:
        try:
            if row["schema_version"] != CAPITAL_READINESS_SCHEMA_VERSION:
                raise UnsupportedCapitalReadinessVersionError("unsupported assessment version")
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _integrity(encoded) != row["integrity_fingerprint"]:
                raise ValueError("assessment integrity fingerprint mismatch")
            data = _exact(json.loads(encoded), _PAYLOAD_KEYS, "Capital Readiness payload")
            if data["schema_version"] != CAPITAL_READINESS_SCHEMA_VERSION:
                raise UnsupportedCapitalReadinessVersionError("unsupported payload version")
            reasons = data["blocking_reasons"]
            if not isinstance(reasons, list):
                raise ValueError("blocking reasons must be a list")
            assessment = CapitalReadinessAssessment(
                assessment_id=data["assessment_id"],
                source_manifest=_load_manifest(data["source_manifest"]),
                state=CapitalReadinessState(data["state"]),
                blocking_reasons=tuple(
                    CapitalReadinessReason(CapitalReadinessReasonCode(code))
                    for code in reasons
                ),
                policy_name=data["policy_name"],
                policy_version=data["policy_version"],
                requested_at=_datetime(data["requested_at"], "requested_at"),
                evaluated_at=_datetime(data["evaluated_at"], "evaluated_at"),
                schema_version=data["schema_version"],
            )
            manifest = assessment.source_manifest
            if (
                assessment.assessment_id != row["assessment_id"]
                or manifest.opportunity_identity.opportunity_id != row["opportunity_id"]
                or manifest.opportunity_identity.discovery_reference != row["discovery_reference"]
                or manifest.conservative_economics_result_id != row["conservative_result_id"]
                or manifest.domestic_market_validation_assessment_id
                != row["market_validation_assessment_id"]
                or manifest.critical_cost_assessment_id != row["critical_cost_assessment_id"]
                or assessment.state.value != row["state"]
                or assessment.policy_name != row["policy_name"]
                or assessment.policy_version != row["policy_version"]
                or assessment.schema_version != row["schema_version"]
            ):
                raise ValueError("assessment columns differ from payload")
            self._validate_exact_sources(assessment)
            return assessment
        except UnsupportedCapitalReadinessVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedCapitalReadinessPersistenceError):
                raise
            raise MalformedCapitalReadinessPersistenceError(
                "persisted Capital Readiness assessment is malformed"
            ) from error

    def _validate_exact_sources(self, assessment: CapitalReadinessAssessment) -> None:
        manifest = assessment.source_manifest
        conservative = self.get_conservative_economics_result(
            manifest.conservative_economics_result_id
        )
        source = self.get_economics_source_composition(
            manifest.economics_source_composition_id
        )
        normalization = self.get_acquisition_normalization(
            manifest.acquisition_normalization_id
        )
        critical = self.get_critical_cost_assessment(
            manifest.critical_cost_assessment_id
        )
        market = self.get_domestic_market_validation(
            manifest.domestic_market_validation_assessment_id
        )
        if any(
            value is None
            for value in (conservative, source, normalization, critical, market)
        ):
            raise ValueError("Capital Readiness exact source is missing")
        binding = self.get_sourcing_binding(critical.binding_reference)
        admission = self.get_sourcing_admission(critical.source_reference)
        if binding is None or admission is None:
            raise ValueError("Capital Readiness exact Sourcing source is missing")
        if (
            conservative.opportunity_identity != manifest.opportunity_identity
            or conservative.source_composition_id != source.composition_id
            or source.acquisition_normalization_id != normalization.normalization_id
            or normalization.composition_id != manifest.landed_cost_composition_id
            or critical.composition_id != manifest.landed_cost_composition_id
            or critical.opportunity_identity != manifest.opportunity_identity
            or market.source_manifest.opportunity_id
            != manifest.opportunity_identity.opportunity_id
            or market.source_manifest.discovery_reference
            != manifest.opportunity_identity.discovery_reference
            or binding.binding_id != manifest.sourcing_binding_id
            or admission.admission_id != manifest.sourcing_admission_id
            or admission.revision != manifest.sourcing_admission_revision
            or admission.quote_revision.quote_id != manifest.quote_id
            or admission.quote_revision.revision != manifest.quote_revision
            or admission.match_verification.verification_id
            != manifest.product_match_verification_id
            or admission.quote_revision.valid_until != manifest.quote_valid_until
        ):
            raise ValueError("Capital Readiness exact source lineage differs")

    def get_assessment(self, assessment_id: str):
        row = self._history_row(assessment_id)
        return None if row is None else self._load_assessment(row)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?", (command_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise CapitalReadinessReceiptError("Capital Readiness receipt query failed") from error

    def _load_receipt(self, row) -> CapitalReadinessReceipt:
        try:
            if row["schema_version"] != CAPITAL_READINESS_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedCapitalReadinessVersionError("unsupported receipt version")
            receipt = CapitalReadinessReceipt(
                row["command_id"], row["assessment_id"], row["command_fingerprint"],
                _datetime(row["committed_at"], "committed_at"), row["schema_version"],
            )
            if self.get_assessment(receipt.assessment_id) is None:
                raise ValueError("receipt references missing assessment")
            return receipt
        except UnsupportedCapitalReadinessVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedCapitalReadinessPersistenceError):
                raise
            raise MalformedCapitalReadinessPersistenceError(
                "persisted Capital Readiness receipt is malformed"
            ) from error

    def get_receipt(self, command_id: str):
        row = self._receipt_row(command_id)
        return None if row is None else self._load_receipt(row)

    def validate_replay(self, command_id: str, fingerprint: str):
        receipt = self.get_receipt(command_id)
        if receipt is None:
            return None
        if receipt.command_fingerprint != fingerprint:
            raise CapitalReadinessReplayConflictError(
                "Capital Readiness command payload conflicts"
            )
        assessment = self.get_assessment(receipt.assessment_id)
        if assessment is None:
            raise MalformedCapitalReadinessPersistenceError(
                "receipt references missing assessment"
            )
        return CapitalReadinessPublication(assessment, receipt, True)

    @staticmethod
    def _validate_write(command, assessment, receipt) -> None:
        if not isinstance(command, EvaluateCapitalReadinessCommand):
            raise TypeError("command must be EvaluateCapitalReadinessCommand")
        if not isinstance(assessment, CapitalReadinessAssessment):
            raise TypeError("assessment must be CapitalReadinessAssessment")
        if not isinstance(receipt, CapitalReadinessReceipt):
            raise TypeError("receipt must be CapitalReadinessReceipt")
        manifest = assessment.source_manifest
        if (
            receipt.command_id != command.command_id
            or receipt.assessment_id != assessment.assessment_id
            or receipt.command_fingerprint != command.fingerprint
            or manifest.opportunity_identity != command.opportunity_identity
            or manifest.conservative_economics_result_id
            != command.conservative_economics_result_id
            or manifest.domestic_market_validation_assessment_id
            != command.domestic_market_validation_assessment_id
            or manifest.critical_cost_assessment_id != command.critical_cost_assessment_id
            or assessment.policy_name != command.policy_name
            or assessment.policy_version != command.policy_version
            or assessment.requested_at != command.requested_at
        ):
            raise CapitalReadinessReplayConflictError(
                "command, assessment, and receipt do not match"
            )

    def _rollback(self) -> None:
        if self._connection.in_transaction:
            self._connection.rollback()

    def _commit(self) -> None:
        self._connection.commit()

    def save_assessment(self, command, assessment, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            self._validate_write(command, assessment, receipt)
            encoded = _payload(assessment)
            manifest = assessment.source_manifest
            try:
                self._connection.execute(f"""INSERT INTO {HISTORY_TABLE}(
                    assessment_id,opportunity_id,discovery_reference,
                    conservative_result_id,market_validation_assessment_id,
                    critical_cost_assessment_id,state,policy_name,policy_version,
                    payload_json,integrity_fingerprint,schema_version,inserted_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                    assessment.assessment_id,
                    manifest.opportunity_identity.opportunity_id,
                    manifest.opportunity_identity.discovery_reference,
                    manifest.conservative_economics_result_id,
                    manifest.domestic_market_validation_assessment_id,
                    manifest.critical_cost_assessment_id,
                    assessment.state.value,
                    assessment.policy_name,
                    assessment.policy_version,
                    encoded,
                    _integrity(encoded),
                    assessment.schema_version,
                    receipt.committed_at.isoformat(),
                ))
            except sqlite3.Error as error:
                raise CapitalReadinessHistoryError("Capital Readiness insert failed") from error
            try:
                self._connection.execute(f"""INSERT INTO {RECEIPT_TABLE}(
                    command_id,assessment_id,command_fingerprint,committed_at,
                    schema_version,inserted_at
                ) VALUES(?,?,?,?,?,?)""", (
                    receipt.command_id, receipt.assessment_id,
                    receipt.command_fingerprint, receipt.committed_at.isoformat(),
                    receipt.schema_version, receipt.committed_at.isoformat(),
                ))
            except sqlite3.Error as error:
                raise CapitalReadinessReceiptError("Capital Readiness receipt insert failed") from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise CapitalReadinessCommitError("Capital Readiness commit failed") from error
            return CapitalReadinessPublication(assessment, receipt, False)
        except CapitalReadinessReplayConflictError:
            self._rollback()
            raise
        except CapitalReadinessPersistenceError:
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
    "CapitalReadinessCommitError", "CapitalReadinessHistoryError",
    "CapitalReadinessPersistenceError", "CapitalReadinessReceiptError",
    "HISTORY_TABLE", "MalformedCapitalReadinessPersistenceError",
    "RECEIPT_TABLE", "SQLiteCapitalReadinessRepository",
    "UnsupportedCapitalReadinessVersionError",
]
