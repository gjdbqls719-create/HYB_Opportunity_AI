"""Append-only SQLite history and replay receipts for DMV v2."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import sqlite3

from app.application.domestic_market_validation_v2 import (
    DOMESTIC_MARKET_VALIDATION_V2_RECEIPT_SCHEMA_VERSION,
    DomesticMarketValidationV2Publication,
    DomesticMarketValidationV2Receipt,
    DomesticMarketValidationV2ReplayConflictError,
    ValidateDomesticMarketV2Command,
)
from app.domain.market_intelligence.competition_v2 import (
    CompetitionV2Availability,
    CompetitionV2ObservationIdentity,
    CompetitionV2ObservationIdentityKind,
)
from app.domain.market_intelligence.demand_v2 import (
    CompetitionCohortReference,
    DemandFamilyStatus,
    DemandV2Availability,
)
from app.domain.market_intelligence.domestic_market_validation import (
    DomesticMarketValidationState,
)
from app.domain.market_intelligence.domestic_market_validation_v2 import (
    DOMESTIC_MARKET_VALIDATION_V2_SCHEMA_VERSION,
    DOMESTIC_MARKET_VALIDATION_V2_SOURCE_MANIFEST_SCHEMA_VERSION,
    DOMESTIC_MARKET_VERIFICATION_V2_SCHEMA_VERSION,
    DomesticMarketCompetitionV2Source,
    DomesticMarketDemandV2Source,
    DomesticMarketValidationV2Assessment,
    DomesticMarketValidationV2Reason,
    DomesticMarketValidationV2ReasonCode,
    DomesticMarketValidationV2SourceManifest,
    DomesticMarketVerificationV2,
)
from app.domain.opportunity import (
    NewToMarketDomesticSellingTargetIdentity,
    NewToMarketDomesticSellingTargetKind,
    OpportunityDomesticSellingTargetBinding,
)


HISTORY_TABLE = "domestic_market_validation_v2_history"
RECEIPT_TABLE = "domestic_market_validation_v2_receipts"
DOMESTIC_MARKET_VALIDATION_V2_HISTORY_SCHEMA_VERSION = (
    "domestic-market-validation-history-v2"
)
DOMESTIC_MARKET_VALIDATION_V2_INTEGRITY_VERSION = "sha256-canonical-json-v1"

_HASH = re.compile(r"^[0-9a-f]{64}$")
_OBJECTS = {
    HISTORY_TABLE: "table",
    RECEIPT_TABLE: "table",
    f"trg_{HISTORY_TABLE}_no_update": "trigger",
    f"trg_{HISTORY_TABLE}_no_delete": "trigger",
    f"trg_{RECEIPT_TABLE}_no_update": "trigger",
    f"trg_{RECEIPT_TABLE}_no_delete": "trigger",
}
_SCHEMA = f"""
CREATE TABLE {HISTORY_TABLE} (
 assessment_id TEXT PRIMARY KEY,
 opportunity_id TEXT NOT NULL,
 discovery_reference TEXT NOT NULL,
 domestic_selling_target_id TEXT NOT NULL,
 state TEXT NOT NULL,
 source_manifest_fingerprint TEXT NOT NULL,
 policy_name TEXT NOT NULL,
 policy_version TEXT NOT NULL,
 payload_json TEXT NOT NULL,
 integrity_fingerprint TEXT NOT NULL,
 integrity_version TEXT NOT NULL,
 schema_version TEXT NOT NULL,
 inserted_at TEXT NOT NULL
);
CREATE TABLE {RECEIPT_TABLE} (
 command_id TEXT PRIMARY KEY,
 assessment_id TEXT NOT NULL,
 command_fingerprint TEXT NOT NULL,
 source_manifest_fingerprint TEXT NOT NULL,
 committed_at TEXT NOT NULL,
 integrity_fingerprint TEXT NOT NULL,
 integrity_version TEXT NOT NULL,
 schema_version TEXT NOT NULL,
 inserted_at TEXT NOT NULL,
 FOREIGN KEY(assessment_id) REFERENCES {HISTORY_TABLE}(assessment_id)
);
CREATE TRIGGER trg_{HISTORY_TABLE}_no_update BEFORE UPDATE ON {HISTORY_TABLE}
 BEGIN SELECT RAISE(ABORT, '{HISTORY_TABLE} is append-only'); END;
CREATE TRIGGER trg_{HISTORY_TABLE}_no_delete BEFORE DELETE ON {HISTORY_TABLE}
 BEGIN SELECT RAISE(ABORT, '{HISTORY_TABLE} is append-only'); END;
CREATE TRIGGER trg_{RECEIPT_TABLE}_no_update BEFORE UPDATE ON {RECEIPT_TABLE}
 BEGIN SELECT RAISE(ABORT, '{RECEIPT_TABLE} is append-only'); END;
CREATE TRIGGER trg_{RECEIPT_TABLE}_no_delete BEFORE DELETE ON {RECEIPT_TABLE}
 BEGIN SELECT RAISE(ABORT, '{RECEIPT_TABLE} is append-only'); END;
"""


class DomesticMarketValidationV2PersistenceError(RuntimeError):
    pass


class DomesticMarketValidationV2HistoryError(DomesticMarketValidationV2PersistenceError):
    pass


class DomesticMarketValidationV2ReceiptError(DomesticMarketValidationV2PersistenceError):
    pass


class DomesticMarketValidationV2CommitError(DomesticMarketValidationV2PersistenceError):
    pass


class DomesticMarketValidationV2CorruptionError(ValueError):
    pass


class DomesticMarketValidationV2UnsupportedVersionError(
    DomesticMarketValidationV2CorruptionError
):
    pass


def _canonical(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    )


def _digest(value: object) -> str:
    encoded = value if isinstance(value, str) else _canonical(value)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _aware(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return result


def _exact(value: object, keys: set[str], name: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{name} is malformed")
    return value


def _hash_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not _HASH.fullmatch(value):
        raise ValueError(f"{name} must be SHA-256 text")
    return value


def _target_identity(value: NewToMarketDomesticSellingTargetIdentity):
    return {
        "domestic_selling_target_id": value.domestic_selling_target_id,
        "market": value.market,
        "kind": value.kind.value,
        "schema_version": value.schema_version,
    }


_TARGET_IDENTITY_KEYS = {
    "domestic_selling_target_id", "market", "kind", "schema_version",
}


def _load_target_identity(value: object):
    data = _exact(value, _TARGET_IDENTITY_KEYS, "target identity")
    return NewToMarketDomesticSellingTargetIdentity(
        domestic_selling_target_id=data["domestic_selling_target_id"],
        market=data["market"],
        kind=NewToMarketDomesticSellingTargetKind(data["kind"]),
        schema_version=data["schema_version"],
    )


def _target_binding(value: OpportunityDomesticSellingTargetBinding):
    return {
        "opportunity_id": value.opportunity_id,
        "discovery_reference": value.discovery_reference,
        "target_identity": _target_identity(value.target_identity),
        "bound_at": value.bound_at.isoformat(),
        "schema_version": value.schema_version,
    }


_TARGET_BINDING_KEYS = {
    "opportunity_id", "discovery_reference", "target_identity", "bound_at",
    "schema_version",
}


def _load_target_binding(value: object):
    data = _exact(value, _TARGET_BINDING_KEYS, "target binding")
    return OpportunityDomesticSellingTargetBinding(
        opportunity_id=data["opportunity_id"],
        discovery_reference=data["discovery_reference"],
        target_identity=_load_target_identity(data["target_identity"]),
        bound_at=_aware(data["bound_at"], "bound_at"),
        schema_version=data["schema_version"],
    )


def _competition_identity(value: CompetitionV2ObservationIdentity):
    return {
        "observation_id": value.observation_id,
        "identity_kind": value.identity_kind.value,
        "identity_version": value.identity_version,
    }


_COMPETITION_IDENTITY_KEYS = {
    "observation_id", "identity_kind", "identity_version",
}


def _load_competition_identity(value: object):
    data = _exact(value, _COMPETITION_IDENTITY_KEYS, "Competition identity")
    return CompetitionV2ObservationIdentity(
        observation_id=data["observation_id"],
        identity_kind=CompetitionV2ObservationIdentityKind(data["identity_kind"]),
        identity_version=data["identity_version"],
    )


def _competition_source(value: DomesticMarketCompetitionV2Source):
    return {
        "observation_identity": _competition_identity(value.observation_identity),
        "cohort_id": value.cohort_id,
        "authority_fingerprint": value.authority_fingerprint,
        "observation_schema_version": value.observation_schema_version,
        "cohort_policy_version": value.cohort_policy_version,
        "assessment_schema_version": value.assessment_schema_version,
        "assessment_policy_version": value.assessment_policy_version,
        "availability": value.availability.value,
        "generated_at": value.generated_at.isoformat(),
        "committed_at": value.committed_at.isoformat(),
        "artifact_reference": value.artifact_reference,
        "artifact_sha256": value.artifact_sha256,
    }


_COMPETITION_SOURCE_KEYS = {
    "observation_identity", "cohort_id", "authority_fingerprint",
    "observation_schema_version", "cohort_policy_version",
    "assessment_schema_version", "assessment_policy_version", "availability",
    "generated_at", "committed_at", "artifact_reference", "artifact_sha256",
}


def _load_competition_source(value: object):
    data = _exact(value, _COMPETITION_SOURCE_KEYS, "Competition v2 source")
    return DomesticMarketCompetitionV2Source(
        observation_identity=_load_competition_identity(data["observation_identity"]),
        cohort_id=data["cohort_id"],
        authority_fingerprint=data["authority_fingerprint"],
        observation_schema_version=data["observation_schema_version"],
        cohort_policy_version=data["cohort_policy_version"],
        assessment_schema_version=data["assessment_schema_version"],
        assessment_policy_version=data["assessment_policy_version"],
        availability=CompetitionV2Availability(data["availability"]),
        generated_at=_aware(data["generated_at"], "Competition generated_at"),
        committed_at=_aware(data["committed_at"], "Competition committed_at"),
        artifact_reference=data["artifact_reference"],
        artifact_sha256=data["artifact_sha256"],
    )


def _competition_reference(value: CompetitionCohortReference | None):
    if value is None:
        return None
    return {
        "competition_observation_id": value.competition_observation_id,
        "observation_identity_kind": value.observation_identity_kind,
        "observation_identity_version": value.observation_identity_version,
        "cohort_id": value.cohort_id,
        "authority_fingerprint": value.authority_fingerprint,
        "observation_schema_version": value.observation_schema_version,
        "cohort_policy_version": value.cohort_policy_version,
        "artifact_reference": value.artifact_reference,
        "artifact_sha256": value.artifact_sha256,
    }


_COMPETITION_REFERENCE_KEYS = {
    "competition_observation_id", "observation_identity_kind",
    "observation_identity_version", "cohort_id", "authority_fingerprint",
    "observation_schema_version", "cohort_policy_version", "artifact_reference",
    "artifact_sha256",
}


def _load_competition_reference(value: object):
    if value is None:
        return None
    data = _exact(value, _COMPETITION_REFERENCE_KEYS, "Competition cohort reference")
    return CompetitionCohortReference(
        competition_observation_id=data["competition_observation_id"],
        observation_identity_kind=data["observation_identity_kind"],
        observation_identity_version=data["observation_identity_version"],
        cohort_id=data["cohort_id"],
        authority_fingerprint=data["authority_fingerprint"],
        observation_schema_version=data["observation_schema_version"],
        cohort_policy_version=data["cohort_policy_version"],
        artifact_reference=data["artifact_reference"],
        artifact_sha256=data["artifact_sha256"],
    )


def _demand_source(value: DomesticMarketDemandV2Source):
    return {
        "observation_id": value.observation_id,
        "assessment_id": value.assessment_id,
        "comparable_cohort_id": value.comparable_cohort_id,
        "authority_fingerprint": value.authority_fingerprint,
        "observation_schema_version": value.observation_schema_version,
        "assessment_schema_version": value.assessment_schema_version,
        "assessment_policy_version": value.assessment_policy_version,
        "comparable_cohort_version": value.comparable_cohort_version,
        "market_intent_status": value.market_intent_status.value,
        "comparable_response_status": value.comparable_response_status.value,
        "availability": value.availability.value,
        "generated_at": value.generated_at.isoformat(),
        "committed_at": value.committed_at.isoformat(),
        "source_competition_cohort": _competition_reference(
            value.source_competition_cohort
        ),
    }


_DEMAND_SOURCE_KEYS = {
    "observation_id", "assessment_id", "comparable_cohort_id",
    "authority_fingerprint", "observation_schema_version",
    "assessment_schema_version", "assessment_policy_version",
    "comparable_cohort_version", "market_intent_status",
    "comparable_response_status", "availability", "generated_at", "committed_at",
    "source_competition_cohort",
}


def _load_demand_source(value: object):
    data = _exact(value, _DEMAND_SOURCE_KEYS, "Demand v2 source")
    return DomesticMarketDemandV2Source(
        observation_id=data["observation_id"],
        assessment_id=data["assessment_id"],
        comparable_cohort_id=data["comparable_cohort_id"],
        authority_fingerprint=data["authority_fingerprint"],
        observation_schema_version=data["observation_schema_version"],
        assessment_schema_version=data["assessment_schema_version"],
        assessment_policy_version=data["assessment_policy_version"],
        comparable_cohort_version=data["comparable_cohort_version"],
        market_intent_status=DemandFamilyStatus(data["market_intent_status"]),
        comparable_response_status=DemandFamilyStatus(
            data["comparable_response_status"]
        ),
        availability=DemandV2Availability(data["availability"]),
        generated_at=_aware(data["generated_at"], "Demand generated_at"),
        committed_at=_aware(data["committed_at"], "Demand committed_at"),
        source_competition_cohort=_load_competition_reference(
            data["source_competition_cohort"]
        ),
    )


def _manifest(value: DomesticMarketValidationV2SourceManifest):
    return {
        "target_binding": _target_binding(value.target_binding),
        "competition": _competition_source(value.competition),
        "demand": _demand_source(value.demand),
        "schema_version": value.schema_version,
    }


_MANIFEST_KEYS = {"target_binding", "competition", "demand", "schema_version"}


def _load_manifest(value: object):
    data = _exact(value, _MANIFEST_KEYS, "DMV v2 source manifest")
    if data["schema_version"] != DOMESTIC_MARKET_VALIDATION_V2_SOURCE_MANIFEST_SCHEMA_VERSION:
        raise DomesticMarketValidationV2UnsupportedVersionError(
            "unsupported DMV v2 source manifest version"
        )
    return DomesticMarketValidationV2SourceManifest(
        target_binding=_load_target_binding(data["target_binding"]),
        competition=_load_competition_source(data["competition"]),
        demand=_load_demand_source(data["demand"]),
        schema_version=data["schema_version"],
    )


def _verification(value: DomesticMarketVerificationV2):
    return {
        "operator_id": value.operator_id,
        "verified_at": value.verified_at.isoformat(),
        "current_use_confirmed": value.current_use_confirmed,
        "reviewed_source_manifest_fingerprint": (
            value.reviewed_source_manifest_fingerprint
        ),
        "schema_version": value.schema_version,
    }


_VERIFICATION_KEYS = {
    "operator_id", "verified_at", "current_use_confirmed",
    "reviewed_source_manifest_fingerprint", "schema_version",
}


def _load_verification(value: object):
    data = _exact(value, _VERIFICATION_KEYS, "DMV v2 verification")
    if data["schema_version"] != DOMESTIC_MARKET_VERIFICATION_V2_SCHEMA_VERSION:
        raise DomesticMarketValidationV2UnsupportedVersionError(
            "unsupported DMV v2 verification version"
        )
    return DomesticMarketVerificationV2(
        operator_id=data["operator_id"],
        verified_at=_aware(data["verified_at"], "verified_at"),
        current_use_confirmed=data["current_use_confirmed"],
        reviewed_source_manifest_fingerprint=data[
            "reviewed_source_manifest_fingerprint"
        ],
        schema_version=data["schema_version"],
    )


def _assessment_payload(value: DomesticMarketValidationV2Assessment):
    return {
        "assessment_id": value.assessment_id,
        "source_manifest": _manifest(value.source_manifest),
        "source_manifest_fingerprint": value.source_manifest_fingerprint,
        "verification": _verification(value.verification),
        "state": value.state.value,
        "blocking_reasons": [reason.code.value for reason in value.blocking_reasons],
        "policy_name": value.policy_name,
        "policy_version": value.policy_version,
        "requested_at": value.requested_at.isoformat(),
        "evaluated_at": value.evaluated_at.isoformat(),
        "schema_version": value.schema_version,
    }


_ASSESSMENT_KEYS = {
    "assessment_id", "source_manifest", "source_manifest_fingerprint",
    "verification", "state", "blocking_reasons", "policy_name", "policy_version",
    "requested_at", "evaluated_at", "schema_version",
}


def _load_assessment_payload(value: object):
    data = _exact(value, _ASSESSMENT_KEYS, "DMV v2 assessment")
    if data["schema_version"] != DOMESTIC_MARKET_VALIDATION_V2_SCHEMA_VERSION:
        raise DomesticMarketValidationV2UnsupportedVersionError(
            "unsupported DMV v2 assessment version"
        )
    reasons = data["blocking_reasons"]
    if not isinstance(reasons, list):
        raise ValueError("blocking_reasons must be a list")
    manifest = _load_manifest(data["source_manifest"])
    if _hash_text(
        data["source_manifest_fingerprint"], "source_manifest_fingerprint"
    ) != manifest.fingerprint:
        raise ValueError("payload source manifest fingerprint mismatch")
    return DomesticMarketValidationV2Assessment(
        assessment_id=data["assessment_id"],
        source_manifest=manifest,
        verification=_load_verification(data["verification"]),
        state=DomesticMarketValidationState(data["state"]),
        blocking_reasons=tuple(
            DomesticMarketValidationV2Reason(DomesticMarketValidationV2ReasonCode(reason))
            for reason in reasons
        ),
        policy_name=data["policy_name"],
        policy_version=data["policy_version"],
        requested_at=_aware(data["requested_at"], "requested_at"),
        evaluated_at=_aware(data["evaluated_at"], "evaluated_at"),
        schema_version=data["schema_version"],
    )


def _receipt_integrity_data(row: dict[str, object]):
    return {
        "command_id": row["command_id"],
        "assessment_id": row["assessment_id"],
        "command_fingerprint": row["command_fingerprint"],
        "source_manifest_fingerprint": row["source_manifest_fingerprint"],
        "committed_at": row["committed_at"],
        "integrity_version": row["integrity_version"],
        "schema_version": row["schema_version"],
        "inserted_at": row["inserted_at"],
    }


class SQLiteDomesticMarketValidationV2Repository:
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
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        rows = self._connection.execute(
            "SELECT name,type FROM sqlite_master WHERE name IN (%s)"
            % ",".join("?" for _ in _OBJECTS),
            tuple(_OBJECTS),
        ).fetchall()
        found = {row["name"]: row["type"] for row in rows}
        if found == _OBJECTS:
            return
        if found:
            raise DomesticMarketValidationV2PersistenceError(
                "partial DMV v2 schema is malformed"
            )
        self._connection.executescript(_SCHEMA)

    def _history_row(self, assessment_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE assessment_id=?",
                (assessment_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise DomesticMarketValidationV2HistoryError(
                "DMV v2 history query failed"
            ) from error

    def _load_assessment(self, row):
        try:
            if row["schema_version"] != DOMESTIC_MARKET_VALIDATION_V2_HISTORY_SCHEMA_VERSION:
                raise DomesticMarketValidationV2UnsupportedVersionError(
                    "unsupported DMV v2 history version"
                )
            if row["integrity_version"] != DOMESTIC_MARKET_VALIDATION_V2_INTEGRITY_VERSION:
                raise DomesticMarketValidationV2UnsupportedVersionError(
                    "unsupported DMV v2 integrity version"
                )
            _aware(row["inserted_at"], "history inserted_at")
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _digest(encoded) != row["integrity_fingerprint"]:
                raise ValueError("DMV v2 payload integrity fingerprint mismatch")
            assessment = _load_assessment_payload(json.loads(encoded))
            manifest = assessment.source_manifest
            target = manifest.target_binding
            if (
                assessment.assessment_id != row["assessment_id"]
                or target.opportunity_id != row["opportunity_id"]
                or target.discovery_reference != row["discovery_reference"]
                or target.target_identity.domestic_selling_target_id
                != row["domestic_selling_target_id"]
                or assessment.state.value != row["state"]
                or assessment.source_manifest_fingerprint
                != row["source_manifest_fingerprint"]
                or assessment.policy_name != row["policy_name"]
                or assessment.policy_version != row["policy_version"]
            ):
                raise ValueError("DMV v2 history columns differ from payload")
            return assessment
        except DomesticMarketValidationV2CorruptionError:
            raise
        except Exception as error:
            raise DomesticMarketValidationV2CorruptionError(
                "persisted DMV v2 assessment is malformed"
            ) from error

    def get_assessment(self, assessment_id: str):
        row = self._history_row(assessment_id)
        return None if row is None else self._load_assessment(row)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?", (command_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise DomesticMarketValidationV2ReceiptError(
                "DMV v2 receipt query failed"
            ) from error

    def _load_receipt(self, row):
        try:
            data = dict(row)
            if data["schema_version"] != DOMESTIC_MARKET_VALIDATION_V2_RECEIPT_SCHEMA_VERSION:
                raise DomesticMarketValidationV2UnsupportedVersionError(
                    "unsupported DMV v2 receipt version"
                )
            if data["integrity_version"] != DOMESTIC_MARKET_VALIDATION_V2_INTEGRITY_VERSION:
                raise DomesticMarketValidationV2UnsupportedVersionError(
                    "unsupported DMV v2 receipt integrity version"
                )
            _hash_text(data["command_fingerprint"], "command_fingerprint")
            _hash_text(
                data["source_manifest_fingerprint"], "source_manifest_fingerprint"
            )
            if _digest(_receipt_integrity_data(data)) != data["integrity_fingerprint"]:
                raise ValueError("DMV v2 receipt integrity fingerprint mismatch")
            receipt = DomesticMarketValidationV2Receipt(
                command_id=data["command_id"],
                assessment_id=data["assessment_id"],
                command_fingerprint=data["command_fingerprint"],
                source_manifest_fingerprint=data["source_manifest_fingerprint"],
                committed_at=_aware(data["committed_at"], "committed_at"),
                schema_version=data["schema_version"],
            )
            assessment = self.get_assessment(receipt.assessment_id)
            history = self._history_row(receipt.assessment_id)
            if (
                assessment is None
                or history is None
                or assessment.source_manifest_fingerprint
                != receipt.source_manifest_fingerprint
                or data["inserted_at"] != data["committed_at"]
                or history["inserted_at"] != data["committed_at"]
            ):
                raise ValueError("DMV v2 receipt relationship is malformed")
            return receipt
        except DomesticMarketValidationV2CorruptionError:
            raise
        except Exception as error:
            raise DomesticMarketValidationV2CorruptionError(
                "persisted DMV v2 receipt is malformed"
            ) from error

    def get_receipt(self, command_id: str):
        row = self._receipt_row(command_id)
        return None if row is None else self._load_receipt(row)

    def validate_replay(self, command_id: str, command_fingerprint: str):
        receipt = self.get_receipt(command_id)
        if receipt is None:
            return None
        if receipt.command_fingerprint != command_fingerprint:
            raise DomesticMarketValidationV2ReplayConflictError(
                "DMV v2 command payload conflicts with persisted receipt"
            )
        assessment = self.get_assessment(receipt.assessment_id)
        if assessment is None:
            raise DomesticMarketValidationV2CorruptionError(
                "DMV v2 receipt references missing assessment"
            )
        return DomesticMarketValidationV2Publication(assessment, receipt, True)

    @staticmethod
    def _validate_write(command, assessment, receipt):
        if not isinstance(command, ValidateDomesticMarketV2Command):
            raise TypeError("command must be ValidateDomesticMarketV2Command")
        if not isinstance(assessment, DomesticMarketValidationV2Assessment):
            raise TypeError("assessment must be DomesticMarketValidationV2Assessment")
        if not isinstance(receipt, DomesticMarketValidationV2Receipt):
            raise TypeError("receipt must be DomesticMarketValidationV2Receipt")
        manifest = assessment.source_manifest
        if (
            receipt.command_id != command.command_id
            or receipt.command_fingerprint != command.fingerprint
            or receipt.assessment_id != assessment.assessment_id
            or receipt.source_manifest_fingerprint
            != assessment.source_manifest_fingerprint
            or manifest.target_binding.opportunity_id != command.opportunity_id
            or manifest.competition.observation_identity.observation_id
            != command.competition_observation_id
            or manifest.demand.observation_id != command.demand_observation_id
            or assessment.verification != command.verification
            or assessment.policy_name != command.policy_name
            or assessment.policy_version != command.policy_version
            or assessment.requested_at != command.requested_at
        ):
            raise DomesticMarketValidationV2ReplayConflictError(
                "DMV v2 command, assessment, and receipt do not match"
            )

    def _rollback(self):
        if self._connection.in_transaction:
            self._connection.rollback()

    def _commit(self):
        self._connection.commit()

    def save_assessment(self, command, assessment, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            self._validate_write(command, assessment, receipt)
            payload = _assessment_payload(assessment)
            encoded = _canonical(payload)
            try:
                self._connection.execute(
                    f"""INSERT INTO {HISTORY_TABLE}(
                     assessment_id,opportunity_id,discovery_reference,
                     domestic_selling_target_id,state,source_manifest_fingerprint,
                     policy_name,policy_version,payload_json,integrity_fingerprint,
                     integrity_version,schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        assessment.assessment_id,
                        assessment.source_manifest.target_binding.opportunity_id,
                        assessment.source_manifest.target_binding.discovery_reference,
                        assessment.source_manifest.target_binding.target_identity.domestic_selling_target_id,
                        assessment.state.value,
                        assessment.source_manifest_fingerprint,
                        assessment.policy_name,
                        assessment.policy_version,
                        encoded,
                        _digest(encoded),
                        DOMESTIC_MARKET_VALIDATION_V2_INTEGRITY_VERSION,
                        DOMESTIC_MARKET_VALIDATION_V2_HISTORY_SCHEMA_VERSION,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise DomesticMarketValidationV2HistoryError(
                    "DMV v2 assessment insert failed"
                ) from error
            receipt_data = {
                "command_id": receipt.command_id,
                "assessment_id": receipt.assessment_id,
                "command_fingerprint": receipt.command_fingerprint,
                "source_manifest_fingerprint": receipt.source_manifest_fingerprint,
                "committed_at": receipt.committed_at.isoformat(),
                "integrity_version": DOMESTIC_MARKET_VALIDATION_V2_INTEGRITY_VERSION,
                "schema_version": receipt.schema_version,
                "inserted_at": receipt.committed_at.isoformat(),
            }
            try:
                self._connection.execute(
                    f"""INSERT INTO {RECEIPT_TABLE}(
                     command_id,assessment_id,command_fingerprint,
                     source_manifest_fingerprint,committed_at,integrity_fingerprint,
                     integrity_version,schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        receipt_data["command_id"],
                        receipt_data["assessment_id"],
                        receipt_data["command_fingerprint"],
                        receipt_data["source_manifest_fingerprint"],
                        receipt_data["committed_at"],
                        _digest(receipt_data),
                        receipt_data["integrity_version"],
                        receipt_data["schema_version"],
                        receipt_data["inserted_at"],
                    ),
                )
            except sqlite3.Error as error:
                raise DomesticMarketValidationV2ReceiptError(
                    "DMV v2 receipt insert failed"
                ) from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise DomesticMarketValidationV2CommitError(
                    "DMV v2 commit failed"
                ) from error
            return DomesticMarketValidationV2Publication(assessment, receipt, False)
        except DomesticMarketValidationV2ReplayConflictError:
            self._rollback()
            raise
        except DomesticMarketValidationV2PersistenceError:
            self._rollback()
            raise
        except Exception:
            self._rollback()
            raise

    def close(self):
        self._rollback()
        if self._owns_connection:
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


__all__ = [
    "DOMESTIC_MARKET_VALIDATION_V2_HISTORY_SCHEMA_VERSION",
    "DOMESTIC_MARKET_VALIDATION_V2_INTEGRITY_VERSION",
    "DomesticMarketValidationV2CommitError",
    "DomesticMarketValidationV2CorruptionError",
    "DomesticMarketValidationV2HistoryError",
    "DomesticMarketValidationV2PersistenceError",
    "DomesticMarketValidationV2ReceiptError",
    "DomesticMarketValidationV2UnsupportedVersionError",
    "HISTORY_TABLE",
    "RECEIPT_TABLE",
    "SQLiteDomesticMarketValidationV2Repository",
]
