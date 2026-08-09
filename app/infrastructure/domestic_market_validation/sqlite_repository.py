"""Append-only SQLite persistence for Domestic Market Validation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.domestic_market_validation import (
    DOMESTIC_MARKET_VALIDATION_RECEIPT_SCHEMA_VERSION,
    DomesticMarketValidationPublication,
    DomesticMarketValidationReceipt,
    DomesticMarketValidationReplayConflictError,
    ValidateDomesticMarketCommand,
)
from app.domain.market_intelligence import (
    DOMESTIC_MARKET_SOURCE_MANIFEST_SCHEMA_VERSION,
    DOMESTIC_MARKET_VALIDATION_SCHEMA_VERSION,
    DOMESTIC_MARKET_VERIFICATION_SCHEMA_VERSION,
    DomesticMarketAnalysisSourceManifest,
    DomesticMarketMetricEvidence,
    DomesticMarketValidationAssessment,
    DomesticMarketValidationReason,
    DomesticMarketValidationReasonCode,
    DomesticMarketValidationSourceManifest,
    DomesticMarketValidationState,
    DomesticMarketVerification,
    MarketEvidenceStatus,
    MarketObservationIdentity,
    MarketObservationScope,
)
from app.infrastructure.market_observation import SQLiteMarketObservationRepository
from app.infrastructure.opportunity_validation import SQLiteValidationQueueRepository


HISTORY_TABLE = "domestic_market_validation_history"
RECEIPT_TABLE = "domestic_market_validation_receipts"


class DomesticMarketValidationPersistenceError(RuntimeError):
    pass


class DomesticMarketValidationHistoryError(DomesticMarketValidationPersistenceError):
    pass


class DomesticMarketValidationReceiptError(DomesticMarketValidationPersistenceError):
    pass


class DomesticMarketValidationCommitError(DomesticMarketValidationPersistenceError):
    pass


class MalformedDomesticMarketValidationPersistenceError(DomesticMarketValidationPersistenceError):
    pass


class UnsupportedDomesticMarketValidationVersionError(MalformedDomesticMarketValidationPersistenceError):
    pass


def _dump(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _integrity(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _aware(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return result


def _optional_aware(value: object, name: str) -> datetime | None:
    return None if value is None else _aware(value, name)


def _exact(value: object, keys: set[str], name: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{name} is malformed")
    return value


def _identity(value: MarketObservationIdentity) -> dict[str, object]:
    return {
        "scope": value.scope.value,
        "market": value.market,
        "marketplace": value.marketplace,
        "canonical_product_id": value.canonical_product_id,
        "marketplace_item_id": value.marketplace_item_id,
        "normalized_query": value.normalized_query,
        "category": value.category,
        "variant_identity": value.variant_identity,
        "condition": value.condition,
        "window_started_at": value.window_started_at.isoformat(),
        "window_ended_at": value.window_ended_at.isoformat(),
    }


_IDENTITY_KEYS = {
    "scope", "market", "marketplace", "canonical_product_id",
    "marketplace_item_id", "normalized_query", "category", "variant_identity",
    "condition", "window_started_at", "window_ended_at",
}


def _load_identity(value: object) -> MarketObservationIdentity:
    data = _exact(value, _IDENTITY_KEYS, "market identity")
    return MarketObservationIdentity(
        scope=MarketObservationScope(data["scope"]),
        market=data["market"],
        marketplace=data["marketplace"],
        canonical_product_id=data["canonical_product_id"],
        marketplace_item_id=data["marketplace_item_id"],
        normalized_query=data["normalized_query"],
        category=data["category"],
        variant_identity=data["variant_identity"],
        condition=data["condition"],
        window_started_at=_aware(data["window_started_at"], "window_started_at"),
        window_ended_at=_aware(data["window_ended_at"], "window_ended_at"),
    )


def _metric(value: DomesticMarketMetricEvidence) -> dict[str, object]:
    value_type = "decimal" if isinstance(value.value, Decimal) else "int"
    encoded_value: object = str(value.value) if value_type == "decimal" else value.value
    return {
        "metric": value.metric,
        "value": encoded_value,
        "value_type": value_type,
        "source": value.source,
        "reference": value.reference,
        "observed_at": None if value.observed_at is None else value.observed_at.isoformat(),
        "collection_method": value.collection_method,
        "status": value.status.value,
        "confidence": str(value.confidence),
        "unit": value.unit,
    }


_METRIC_KEYS = {
    "metric", "value", "value_type", "source", "reference", "observed_at",
    "collection_method", "status", "confidence", "unit",
}


def _load_metric(value: object) -> DomesticMarketMetricEvidence:
    data = _exact(value, _METRIC_KEYS, "metric evidence")
    if data["value_type"] == "decimal":
        metric_value = Decimal(str(data["value"]))
    elif data["value_type"] == "int" and isinstance(data["value"], int) and not isinstance(data["value"], bool):
        metric_value = data["value"]
    else:
        raise ValueError("metric value type is malformed")
    return DomesticMarketMetricEvidence(
        metric=data["metric"],
        value=metric_value,
        source=data["source"],
        reference=data["reference"],
        observed_at=_optional_aware(data["observed_at"], "observed_at"),
        collection_method=data["collection_method"],
        status=MarketEvidenceStatus(data["status"]),
        confidence=Decimal(str(data["confidence"])),
        unit=data["unit"],
    )


def _source(value: DomesticMarketAnalysisSourceManifest) -> dict[str, object]:
    return {
        "observation_id": value.observation_id,
        "assessment_id": value.assessment_id,
        "observation_schema_version": value.observation_schema_version,
        "assessment_schema_version": value.assessment_schema_version,
        "assessment_policy_version": value.assessment_policy_version,
        "availability": value.availability,
        "evidence": [_metric(item) for item in value.evidence],
    }


_SOURCE_KEYS = {
    "observation_id", "assessment_id", "observation_schema_version",
    "assessment_schema_version", "assessment_policy_version", "availability", "evidence",
}


def _load_source(value: object) -> DomesticMarketAnalysisSourceManifest:
    data = _exact(value, _SOURCE_KEYS, "analysis source")
    if not isinstance(data["evidence"], list):
        raise ValueError("source evidence must be a list")
    return DomesticMarketAnalysisSourceManifest(
        observation_id=data["observation_id"],
        assessment_id=data["assessment_id"],
        observation_schema_version=data["observation_schema_version"],
        assessment_schema_version=data["assessment_schema_version"],
        assessment_policy_version=data["assessment_policy_version"],
        availability=data["availability"],
        evidence=tuple(_load_metric(item) for item in data["evidence"]),
    )


def _manifest(value: DomesticMarketValidationSourceManifest) -> dict[str, object]:
    return {
        "opportunity_id": value.opportunity_id,
        "discovery_reference": value.discovery_reference,
        "market_identity": _identity(value.market_identity),
        "competition": _source(value.competition),
        "demand": _source(value.demand),
        "accepted_external_signal_ids": list(value.accepted_external_signal_ids),
        "schema_version": value.schema_version,
    }


_MANIFEST_KEYS = {
    "opportunity_id", "discovery_reference", "market_identity", "competition",
    "demand", "accepted_external_signal_ids", "schema_version",
}


def _load_manifest(value: object) -> DomesticMarketValidationSourceManifest:
    data = _exact(value, _MANIFEST_KEYS, "source manifest")
    if data["schema_version"] != DOMESTIC_MARKET_SOURCE_MANIFEST_SCHEMA_VERSION:
        raise UnsupportedDomesticMarketValidationVersionError("unsupported source manifest version")
    if not isinstance(data["accepted_external_signal_ids"], list):
        raise ValueError("external signal ids must be a list")
    return DomesticMarketValidationSourceManifest(
        opportunity_id=data["opportunity_id"],
        discovery_reference=data["discovery_reference"],
        market_identity=_load_identity(data["market_identity"]),
        competition=_load_source(data["competition"]),
        demand=_load_source(data["demand"]),
        accepted_external_signal_ids=tuple(data["accepted_external_signal_ids"]),
        schema_version=data["schema_version"],
    )


def _verification(value: DomesticMarketVerification) -> dict[str, object]:
    return {
        "operator_id": value.operator_id,
        "verified_at": value.verified_at.isoformat(),
        "current_use_confirmed": value.current_use_confirmed,
        "reviewed_source_ids": list(value.reviewed_source_ids),
        "schema_version": value.schema_version,
    }


_VERIFICATION_KEYS = {
    "operator_id", "verified_at", "current_use_confirmed", "reviewed_source_ids", "schema_version",
}


def _load_verification(value: object) -> DomesticMarketVerification:
    data = _exact(value, _VERIFICATION_KEYS, "verification")
    if data["schema_version"] != DOMESTIC_MARKET_VERIFICATION_SCHEMA_VERSION:
        raise UnsupportedDomesticMarketValidationVersionError("unsupported verification version")
    if not isinstance(data["reviewed_source_ids"], list):
        raise ValueError("reviewed source ids must be a list")
    return DomesticMarketVerification(
        operator_id=data["operator_id"],
        verified_at=_aware(data["verified_at"], "verified_at"),
        current_use_confirmed=data["current_use_confirmed"],
        reviewed_source_ids=tuple(data["reviewed_source_ids"]),
        schema_version=data["schema_version"],
    )


def _payload(value: DomesticMarketValidationAssessment) -> str:
    return _dump({
        "assessment_id": value.assessment_id,
        "source_manifest": _manifest(value.source_manifest),
        "verification": _verification(value.verification),
        "state": value.state.value,
        "blocking_reasons": [item.code.value for item in value.blocking_reasons],
        "policy_name": value.policy_name,
        "policy_version": value.policy_version,
        "requested_at": value.requested_at.isoformat(),
        "evaluated_at": value.evaluated_at.isoformat(),
        "schema_version": value.schema_version,
    })


_PAYLOAD_KEYS = {
    "assessment_id", "source_manifest", "verification", "state", "blocking_reasons",
    "policy_name", "policy_version", "requested_at", "evaluated_at", "schema_version",
}


class SQLiteDomesticMarketValidationRepository:
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
        self._opportunities = SQLiteValidationQueueRepository(connection=self._connection)
        self._market = SQLiteMarketObservationRepository(connection=self._connection)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(f"""CREATE TABLE IF NOT EXISTS {HISTORY_TABLE}(
                assessment_id TEXT PRIMARY KEY,
                opportunity_id TEXT NOT NULL,
                discovery_reference TEXT NOT NULL,
                market TEXT NOT NULL,
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
                    self._connection.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()}
                    BEFORE {operation} ON {table}
                    BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END""")

    def get_market_identity_binding(self, opportunity_id):
        return self._opportunities.get_market_identity_binding(opportunity_id)

    def get_opportunity_lifecycle(self, opportunity_id):
        return self._opportunities.get(opportunity_id)

    def get_observation_by_id(self, observation_id):
        return self._market.get_observation_by_id(observation_id)

    def get_competition_assessment_snapshot(self, snapshot_id):
        return self._market.get_competition_assessment_snapshot(snapshot_id)

    def get_demand_assessment_snapshot(self, snapshot_id):
        return self._market.get_demand_assessment_snapshot(snapshot_id)

    def get_human_verified_external_signals_by_ids(self, identity, signal_ids):
        return self._market.get_human_verified_external_signals_by_ids(identity, signal_ids)

    def _history_row(self, assessment_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE assessment_id=?", (assessment_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise DomesticMarketValidationHistoryError("validation history query failed") from error

    def _load_assessment(self, row) -> DomesticMarketValidationAssessment:
        try:
            if row["schema_version"] != DOMESTIC_MARKET_VALIDATION_SCHEMA_VERSION:
                raise UnsupportedDomesticMarketValidationVersionError("unsupported assessment version")
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _integrity(encoded) != row["integrity_fingerprint"]:
                raise ValueError("assessment integrity fingerprint mismatch")
            data = _exact(json.loads(encoded), _PAYLOAD_KEYS, "assessment payload")
            if data["schema_version"] != DOMESTIC_MARKET_VALIDATION_SCHEMA_VERSION:
                raise UnsupportedDomesticMarketValidationVersionError("unsupported assessment payload version")
            reasons = data["blocking_reasons"]
            if not isinstance(reasons, list):
                raise ValueError("blocking reasons must be a list")
            result = DomesticMarketValidationAssessment(
                assessment_id=data["assessment_id"],
                source_manifest=_load_manifest(data["source_manifest"]),
                verification=_load_verification(data["verification"]),
                state=DomesticMarketValidationState(data["state"]),
                blocking_reasons=tuple(
                    DomesticMarketValidationReason(DomesticMarketValidationReasonCode(value))
                    for value in reasons
                ),
                policy_name=data["policy_name"],
                policy_version=data["policy_version"],
                requested_at=_aware(data["requested_at"], "requested_at"),
                evaluated_at=_aware(data["evaluated_at"], "evaluated_at"),
                schema_version=data["schema_version"],
            )
            manifest = result.source_manifest
            if (
                result.assessment_id != row["assessment_id"]
                or manifest.opportunity_id != row["opportunity_id"]
                or manifest.discovery_reference != row["discovery_reference"]
                or manifest.market_identity.market != row["market"]
                or result.state.value != row["state"]
                or result.policy_name != row["policy_name"]
                or result.policy_version != row["policy_version"]
                or result.schema_version != row["schema_version"]
            ):
                raise ValueError("assessment columns differ from payload")
            self._validate_exact_sources(result)
            return result
        except UnsupportedDomesticMarketValidationVersionError:
            raise
        except Exception as error:
            raise MalformedDomesticMarketValidationPersistenceError(
                "persisted domestic market validation is malformed"
            ) from error

    def _validate_exact_sources(
        self, assessment: DomesticMarketValidationAssessment
    ) -> None:
        """Validate pinned source existence and lineage without re-evaluating policy."""
        manifest = assessment.source_manifest
        binding = self.get_market_identity_binding(manifest.opportunity_id)
        if (
            binding is None
            or binding.discovery_reference != manifest.discovery_reference
            or binding.market_observation_identity != manifest.market_identity
        ):
            raise ValueError("assessment Opportunity/Market lineage is unavailable")

        for source, observation_getter, snapshot_getter in (
            (
                manifest.competition,
                self.get_observation_by_id,
                self.get_competition_assessment_snapshot,
            ),
            (
                manifest.demand,
                self.get_observation_by_id,
                self.get_demand_assessment_snapshot,
            ),
        ):
            observation = observation_getter(source.observation_id)
            snapshot = snapshot_getter(source.assessment_id)
            if (
                observation is None
                or snapshot is None
                or getattr(observation, "observation_id", None) != source.observation_id
                or getattr(observation, "identity", None) != manifest.market_identity
                or getattr(snapshot, "snapshot_id", None) != source.assessment_id
                or getattr(snapshot, "source_observation_id", None) != source.observation_id
                or getattr(snapshot, "identity", None) != manifest.market_identity
            ):
                raise ValueError("assessment exact market source lineage is unavailable")

        if manifest.accepted_external_signal_ids:
            signals = self.get_human_verified_external_signals_by_ids(
                manifest.market_identity,
                manifest.accepted_external_signal_ids,
            )
            if tuple(signal.signal_id for signal in signals) != manifest.accepted_external_signal_ids:
                raise ValueError("assessment exact external signal lineage is unavailable")

    def get_assessment(self, assessment_id: str):
        row = self._history_row(assessment_id)
        return None if row is None else self._load_assessment(row)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?", (command_id,)
            ).fetchone()
        except sqlite3.Error as error:
            raise DomesticMarketValidationReceiptError("validation receipt query failed") from error

    def _load_receipt(self, row) -> DomesticMarketValidationReceipt:
        try:
            if row["schema_version"] != DOMESTIC_MARKET_VALIDATION_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedDomesticMarketValidationVersionError("unsupported receipt version")
            result = DomesticMarketValidationReceipt(
                command_id=row["command_id"],
                assessment_id=row["assessment_id"],
                command_fingerprint=row["command_fingerprint"],
                committed_at=_aware(row["committed_at"], "committed_at"),
                schema_version=row["schema_version"],
            )
            if self.get_assessment(result.assessment_id) is None:
                raise ValueError("receipt references missing assessment")
            return result
        except UnsupportedDomesticMarketValidationVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedDomesticMarketValidationPersistenceError):
                raise
            raise MalformedDomesticMarketValidationPersistenceError(
                "persisted domestic market validation receipt is malformed"
            ) from error

    def get_receipt(self, command_id: str):
        row = self._receipt_row(command_id)
        return None if row is None else self._load_receipt(row)

    def validate_replay(self, command_id: str, fingerprint: str):
        receipt = self.get_receipt(command_id)
        if receipt is None:
            return None
        if receipt.command_fingerprint != fingerprint:
            raise DomesticMarketValidationReplayConflictError(
                "domestic market validation command payload conflicts"
            )
        assessment = self.get_assessment(receipt.assessment_id)
        if assessment is None:
            raise MalformedDomesticMarketValidationPersistenceError(
                "receipt references missing assessment"
            )
        return DomesticMarketValidationPublication(assessment, receipt, True)

    @staticmethod
    def _validate_write(command, assessment, receipt) -> None:
        if not isinstance(command, ValidateDomesticMarketCommand):
            raise TypeError("command must be ValidateDomesticMarketCommand")
        if not isinstance(assessment, DomesticMarketValidationAssessment):
            raise TypeError("assessment must be DomesticMarketValidationAssessment")
        if not isinstance(receipt, DomesticMarketValidationReceipt):
            raise TypeError("receipt must be DomesticMarketValidationReceipt")
        manifest = assessment.source_manifest
        if (
            receipt.command_id != command.command_id
            or receipt.command_fingerprint != command.fingerprint
            or receipt.assessment_id != assessment.assessment_id
            or manifest.opportunity_id != command.opportunity_identity.opportunity_id
            or manifest.discovery_reference != command.opportunity_identity.discovery_reference
            or manifest.market_identity != command.market_identity
            or manifest.competition.observation_id != command.competition_observation_id
            or manifest.competition.assessment_id != command.competition_assessment_id
            or manifest.demand.observation_id != command.demand_observation_id
            or manifest.demand.assessment_id != command.demand_assessment_id
            or manifest.accepted_external_signal_ids != command.accepted_external_signal_ids
            or assessment.verification != command.verification
            or assessment.policy_name != command.policy_name
            or assessment.policy_version != command.policy_version
            or assessment.requested_at != command.requested_at
        ):
            raise DomesticMarketValidationReplayConflictError(
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
            try:
                self._connection.execute(f"""INSERT INTO {HISTORY_TABLE}(
                    assessment_id,opportunity_id,discovery_reference,market,state,
                    policy_name,policy_version,payload_json,integrity_fingerprint,
                    schema_version,inserted_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""", (
                    assessment.assessment_id,
                    assessment.source_manifest.opportunity_id,
                    assessment.source_manifest.discovery_reference,
                    assessment.source_manifest.market_identity.market,
                    assessment.state.value,
                    assessment.policy_name,
                    assessment.policy_version,
                    encoded,
                    _integrity(encoded),
                    assessment.schema_version,
                    receipt.committed_at.isoformat(),
                ))
            except sqlite3.Error as error:
                raise DomesticMarketValidationHistoryError("validation assessment insert failed") from error
            try:
                self._connection.execute(f"""INSERT INTO {RECEIPT_TABLE}(
                    command_id,assessment_id,command_fingerprint,committed_at,
                    schema_version,inserted_at
                ) VALUES(?,?,?,?,?,?)""", (
                    receipt.command_id,
                    receipt.assessment_id,
                    receipt.command_fingerprint,
                    receipt.committed_at.isoformat(),
                    receipt.schema_version,
                    receipt.committed_at.isoformat(),
                ))
            except sqlite3.Error as error:
                raise DomesticMarketValidationReceiptError("validation receipt insert failed") from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise DomesticMarketValidationCommitError("validation commit failed") from error
            return DomesticMarketValidationPublication(assessment, receipt, False)
        except DomesticMarketValidationReplayConflictError:
            self._rollback()
            raise
        except DomesticMarketValidationPersistenceError:
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
    "DomesticMarketValidationCommitError",
    "DomesticMarketValidationHistoryError",
    "DomesticMarketValidationPersistenceError",
    "DomesticMarketValidationReceiptError",
    "HISTORY_TABLE",
    "MalformedDomesticMarketValidationPersistenceError",
    "RECEIPT_TABLE",
    "SQLiteDomesticMarketValidationRepository",
    "UnsupportedDomesticMarketValidationVersionError",
]
