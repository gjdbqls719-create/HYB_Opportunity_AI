"""Atomic append-only SQLite persistence for one Shadow registration boundary."""

from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
import sqlite3

from app.application.shadow_validation_persistence import (
    SHADOW_REGISTRATION_RECEIPT_SCHEMA_VERSION,
    SHADOW_REGISTRATION_REQUEST_RECEIPT_SCHEMA_VERSION,
    MalformedShadowRegistrationPersistenceError,
    PersistShadowRegistrationCommand,
    ShadowRegistrationCommitError,
    ShadowRegistrationHistoryError,
    ShadowRegistrationPersistenceResult,
    ShadowRegistrationReceipt,
    ShadowRegistrationRequestReceipt,
    ShadowRegistrationReceiptError,
    ShadowRegistrationReplayConflictError,
    UnsupportedShadowRegistrationPersistenceVersionError,
)
from app.domain.opportunity import (
    SHADOW_BASELINE_SNAPSHOT_SCHEMA_VERSION,
    SHADOW_VALIDATION_REGISTRATION_SCHEMA_VERSION,
    ShadowBaselineSnapshot,
    ShadowValidationRegistration,
    serialize_shadow_baseline_snapshot,
    serialize_shadow_validation_registration,
)
from app.infrastructure.shadow_validation.serialization import (
    deserialize_shadow_baseline_snapshot,
    deserialize_shadow_validation_registration,
)


REGISTRATION_HISTORY_TABLE = "shadow_validation_registration_history"
BASELINE_HISTORY_TABLE = "shadow_baseline_snapshot_history"
RECEIPT_TABLE = "shadow_registration_receipts"
REQUEST_RECEIPT_TABLE = "shadow_registration_request_receipts"


def _payload_fingerprint(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed


class SQLiteShadowRegistrationBaselineRepository:
    """Own the Registration + Baseline + receipt transaction on one connection."""

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
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {REGISTRATION_HISTORY_TABLE}(
                    shadow_validation_id TEXT PRIMARY KEY,
                    baseline_snapshot_id TEXT NOT NULL UNIQUE,
                    o2_opportunity_id TEXT NOT NULL,
                    domestic_selling_target_id TEXT NOT NULL,
                    discovery_execution_id TEXT NOT NULL,
                    finalized_group_id TEXT NOT NULL,
                    screening_evaluation_id TEXT NOT NULL,
                    screening_ranking_publication_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_fingerprint TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    knowledge_cutoff_at TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    UNIQUE(shadow_validation_id, baseline_snapshot_id)
                )"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {BASELINE_HISTORY_TABLE}(
                    baseline_snapshot_id TEXT PRIMARY KEY,
                    shadow_validation_id TEXT NOT NULL UNIQUE,
                    source_manifest_fingerprint TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_fingerprint TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    knowledge_cutoff_at TEXT NOT NULL,
                    baseline_created_at TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    UNIQUE(baseline_snapshot_id, shadow_validation_id),
                    FOREIGN KEY(shadow_validation_id, baseline_snapshot_id)
                        REFERENCES {REGISTRATION_HISTORY_TABLE}(
                            shadow_validation_id, baseline_snapshot_id
                        )
                )"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE}(
                    command_id TEXT PRIMARY KEY,
                    shadow_validation_id TEXT NOT NULL,
                    baseline_snapshot_id TEXT NOT NULL,
                    command_fingerprint TEXT NOT NULL,
                    registration_fingerprint TEXT NOT NULL,
                    baseline_fingerprint TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(shadow_validation_id, baseline_snapshot_id)
                        REFERENCES {REGISTRATION_HISTORY_TABLE}(
                            shadow_validation_id, baseline_snapshot_id
                        ),
                    FOREIGN KEY(baseline_snapshot_id, shadow_validation_id)
                        REFERENCES {BASELINE_HISTORY_TABLE}(
                            baseline_snapshot_id, shadow_validation_id
                        )
                )"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {REQUEST_RECEIPT_TABLE}(
                    command_id TEXT PRIMARY KEY,
                    request_fingerprint TEXT NOT NULL,
                    shadow_validation_id TEXT NOT NULL,
                    baseline_snapshot_id TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(command_id) REFERENCES {RECEIPT_TABLE}(command_id),
                    FOREIGN KEY(shadow_validation_id, baseline_snapshot_id)
                        REFERENCES {REGISTRATION_HISTORY_TABLE}(
                            shadow_validation_id, baseline_snapshot_id
                        ),
                    FOREIGN KEY(baseline_snapshot_id, shadow_validation_id)
                        REFERENCES {BASELINE_HISTORY_TABLE}(
                            baseline_snapshot_id, shadow_validation_id
                        )
                )"""
            )
            for table in (
                REGISTRATION_HISTORY_TABLE,
                BASELINE_HISTORY_TABLE,
                RECEIPT_TABLE,
                REQUEST_RECEIPT_TABLE,
            ):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS
                            trg_{table}_no_{operation.lower()}
                            BEFORE {operation} ON {table}
                            BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END"""
                    )

    def _fault_point(self, name: str) -> None:
        """Fault-injection seam used by atomicity tests."""

    def _registration_row(self, shadow_validation_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {REGISTRATION_HISTORY_TABLE} "
                "WHERE shadow_validation_id=?",
                (shadow_validation_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise ShadowRegistrationHistoryError(
                "Shadow registration query failed"
            ) from error

    def _baseline_row(self, baseline_snapshot_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {BASELINE_HISTORY_TABLE} "
                "WHERE baseline_snapshot_id=?",
                (baseline_snapshot_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise ShadowRegistrationHistoryError("Shadow baseline query failed") from error

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?",
                (command_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise ShadowRegistrationReceiptError("Shadow receipt query failed") from error

    def _request_receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {REQUEST_RECEIPT_TABLE} WHERE command_id=?",
                (command_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise ShadowRegistrationReceiptError(
                "Shadow registration request receipt query failed"
            ) from error

    def _receipt_rows_for_registration(self, shadow_validation_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE shadow_validation_id=? "
                "ORDER BY inserted_at, command_id",
                (shadow_validation_id,),
            ).fetchall()
        except sqlite3.Error as error:
            raise ShadowRegistrationReceiptError("Shadow receipt query failed") from error

    @staticmethod
    def _load_registration(row: sqlite3.Row) -> ShadowValidationRegistration:
        try:
            if row["schema_version"] != SHADOW_VALIDATION_REGISTRATION_SCHEMA_VERSION:
                raise UnsupportedShadowRegistrationPersistenceVersionError(
                    "unsupported persisted Shadow registration version"
                )
            payload = row["payload_json"]
            if (
                not isinstance(payload, str)
                or _payload_fingerprint(payload) != row["payload_fingerprint"]
            ):
                raise ValueError("Shadow registration payload integrity differs")
            value = deserialize_shadow_validation_registration(payload)
            subject = value.subject
            screening = value.screening_lineage
            if any(
                (
                    value.shadow_validation_id != row["shadow_validation_id"],
                    value.baseline_snapshot_id != row["baseline_snapshot_id"],
                    subject.o2_opportunity_identity.opportunity_id
                    != row["o2_opportunity_id"],
                    subject.target_identity.domestic_selling_target_id
                    != row["domestic_selling_target_id"],
                    screening.discovery_execution_id != row["discovery_execution_id"],
                    screening.finalized_group_id != row["finalized_group_id"],
                    screening.screening_evaluation_id != row["screening_evaluation_id"],
                    screening.screening_ranking_publication_id
                    != row["screening_ranking_publication_id"],
                    value.integrity_fingerprint != row["integrity_fingerprint"],
                    value.registered_at != _datetime(row["registered_at"], "registered_at"),
                    value.knowledge_cutoff_at
                    != _datetime(row["knowledge_cutoff_at"], "knowledge_cutoff_at"),
                )
            ):
                raise ValueError("Shadow registration columns differ from payload")
            return value
        except UnsupportedShadowRegistrationPersistenceVersionError:
            raise
        except Exception as error:
            raise MalformedShadowRegistrationPersistenceError(
                "persisted Shadow registration is malformed"
            ) from error

    @staticmethod
    def _load_baseline(row: sqlite3.Row) -> ShadowBaselineSnapshot:
        try:
            if row["schema_version"] != SHADOW_BASELINE_SNAPSHOT_SCHEMA_VERSION:
                raise UnsupportedShadowRegistrationPersistenceVersionError(
                    "unsupported persisted Shadow baseline version"
                )
            payload = row["payload_json"]
            if (
                not isinstance(payload, str)
                or _payload_fingerprint(payload) != row["payload_fingerprint"]
            ):
                raise ValueError("Shadow baseline payload integrity differs")
            value = deserialize_shadow_baseline_snapshot(payload)
            if any(
                (
                    value.baseline_snapshot_id != row["baseline_snapshot_id"],
                    value.shadow_validation_id != row["shadow_validation_id"],
                    value.source_manifest.integrity_fingerprint
                    != row["source_manifest_fingerprint"],
                    value.integrity_fingerprint != row["integrity_fingerprint"],
                    value.knowledge_cutoff_at
                    != _datetime(row["knowledge_cutoff_at"], "knowledge_cutoff_at"),
                    value.baseline_created_at
                    != _datetime(row["baseline_created_at"], "baseline_created_at"),
                )
            ):
                raise ValueError("Shadow baseline columns differ from payload")
            return value
        except UnsupportedShadowRegistrationPersistenceVersionError:
            raise
        except Exception as error:
            raise MalformedShadowRegistrationPersistenceError(
                "persisted Shadow baseline is malformed"
            ) from error

    @staticmethod
    def _validate_bundle(
        registration: ShadowValidationRegistration,
        baseline: ShadowBaselineSnapshot,
    ) -> None:
        reference = baseline.registration
        if any(
            (
                reference.shadow_validation_id != registration.shadow_validation_id,
                reference.baseline_snapshot_id != registration.baseline_snapshot_id,
                reference.registration_fingerprint
                != registration.integrity_fingerprint,
                reference.o2_opportunity_id
                != registration.subject.o2_opportunity_identity.opportunity_id,
                reference.domestic_selling_target_id
                != registration.subject.target_identity.domestic_selling_target_id,
                reference.subject_lineage_fingerprint
                != registration.subject.integrity_fingerprint,
                reference.screening_evaluation_id
                != registration.screening_lineage.screening_evaluation_id,
                reference.screening_evaluation_fingerprint
                != registration.screening_lineage.screening_evaluation_fingerprint,
                reference.screening_ranking_publication_id
                != registration.screening_lineage.screening_ranking_publication_id,
                reference.screening_ranking_publication_fingerprint
                != registration.screening_lineage.screening_ranking_publication_fingerprint,
                reference.screening_input_manifest_fingerprint
                != registration.screening_lineage.screening_input_manifest_fingerprint,
                reference.screening_lineage_fingerprint
                != registration.screening_lineage.integrity_fingerprint,
                reference.discovery_execution_id
                != registration.screening_lineage.discovery_execution_id,
                reference.finalized_group_id
                != registration.screening_lineage.finalized_group_id,
            )
        ):
            raise MalformedShadowRegistrationPersistenceError(
                "persisted Shadow Registration/Baseline binding differs"
            )

    @staticmethod
    def _load_receipt(row: sqlite3.Row) -> ShadowRegistrationReceipt:
        try:
            if row["schema_version"] != SHADOW_REGISTRATION_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedShadowRegistrationPersistenceVersionError(
                    "unsupported persisted Shadow receipt version"
                )
            value = ShadowRegistrationReceipt(
                command_id=row["command_id"],
                shadow_validation_id=row["shadow_validation_id"],
                baseline_snapshot_id=row["baseline_snapshot_id"],
                command_fingerprint=row["command_fingerprint"],
                registration_fingerprint=row["registration_fingerprint"],
                baseline_fingerprint=row["baseline_fingerprint"],
                committed_at=_datetime(row["committed_at"], "committed_at"),
                schema_version=row["schema_version"],
            )
            if value.committed_at != _datetime(row["inserted_at"], "inserted_at"):
                raise ValueError("Shadow receipt insertion time differs")
            return value
        except UnsupportedShadowRegistrationPersistenceVersionError:
            raise
        except Exception as error:
            raise MalformedShadowRegistrationPersistenceError(
                "persisted Shadow receipt is malformed"
            ) from error

    @staticmethod
    def _load_request_receipt(
        row: sqlite3.Row,
    ) -> ShadowRegistrationRequestReceipt:
        try:
            if (
                row["schema_version"]
                != SHADOW_REGISTRATION_REQUEST_RECEIPT_SCHEMA_VERSION
            ):
                raise UnsupportedShadowRegistrationPersistenceVersionError(
                    "unsupported persisted Shadow request receipt version"
                )
            value = ShadowRegistrationRequestReceipt(
                command_id=row["command_id"],
                request_fingerprint=row["request_fingerprint"],
                shadow_validation_id=row["shadow_validation_id"],
                baseline_snapshot_id=row["baseline_snapshot_id"],
                committed_at=_datetime(row["committed_at"], "committed_at"),
                schema_version=row["schema_version"],
            )
            if value.committed_at != _datetime(row["inserted_at"], "inserted_at"):
                raise ValueError("Shadow request receipt insertion time differs")
            return value
        except UnsupportedShadowRegistrationPersistenceVersionError:
            raise
        except Exception as error:
            raise MalformedShadowRegistrationPersistenceError(
                "persisted Shadow request receipt is malformed"
            ) from error

    def _load_exact_bundle(
        self,
        registration_row: sqlite3.Row,
        baseline_row: sqlite3.Row,
    ) -> tuple[ShadowValidationRegistration, ShadowBaselineSnapshot]:
        registration = self._load_registration(registration_row)
        baseline = self._load_baseline(baseline_row)
        self._validate_bundle(registration, baseline)
        return registration, baseline

    def get_registration(
        self, shadow_validation_id: str
    ) -> ShadowValidationRegistration | None:
        row = self._registration_row(shadow_validation_id)
        if row is None:
            return None
        baseline_row = self._baseline_row(row["baseline_snapshot_id"])
        if baseline_row is None:
            raise MalformedShadowRegistrationPersistenceError(
                "persisted Shadow registration is orphaned"
            )
        registration, _ = self._load_exact_bundle(row, baseline_row)
        return registration

    def get_baseline(
        self, baseline_snapshot_id: str
    ) -> ShadowBaselineSnapshot | None:
        row = self._baseline_row(baseline_snapshot_id)
        if row is None:
            return None
        registration_row = self._registration_row(row["shadow_validation_id"])
        if registration_row is None:
            raise MalformedShadowRegistrationPersistenceError(
                "persisted Shadow baseline is orphaned"
            )
        _, baseline = self._load_exact_bundle(registration_row, row)
        return baseline

    def get_bundle(
        self, shadow_validation_id: str
    ) -> ShadowRegistrationPersistenceResult | None:
        registration_row = self._registration_row(shadow_validation_id)
        if registration_row is None:
            return None
        baseline_row = self._baseline_row(registration_row["baseline_snapshot_id"])
        if baseline_row is None:
            raise MalformedShadowRegistrationPersistenceError(
                "persisted Shadow registration is orphaned"
            )
        registration, baseline = self._load_exact_bundle(
            registration_row, baseline_row
        )
        rows = self._receipt_rows_for_registration(shadow_validation_id)
        if not rows:
            raise MalformedShadowRegistrationPersistenceError(
                "persisted Shadow bundle has no receipt"
            )
        receipts = tuple(self._load_receipt(row) for row in rows)
        for receipt in receipts:
            if any(
                (
                    receipt.shadow_validation_id != registration.shadow_validation_id,
                    receipt.baseline_snapshot_id != baseline.baseline_snapshot_id,
                    receipt.registration_fingerprint
                    != registration.integrity_fingerprint,
                    receipt.baseline_fingerprint != baseline.integrity_fingerprint,
                )
            ):
                raise MalformedShadowRegistrationPersistenceError(
                    "persisted Shadow receipt differs from bundle"
                )
        return ShadowRegistrationPersistenceResult(
            registration, baseline, receipts[0], replayed=True
        )

    def validate_replay(
        self, command_id: str, fingerprint: str
    ) -> ShadowRegistrationPersistenceResult | None:
        row = self._receipt_row(command_id)
        if row is None:
            return None
        receipt = self._load_receipt(row)
        if receipt.command_fingerprint != fingerprint:
            raise ShadowRegistrationReplayConflictError(
                "Shadow registration command payload conflicts"
            )
        bundle = self.get_bundle(receipt.shadow_validation_id)
        if bundle is None or bundle.receipt.command_id != receipt.command_id:
            # An alias receipt may not be the first receipt returned by get_bundle.
            registration = self.get_registration(receipt.shadow_validation_id)
            baseline = self.get_baseline(receipt.baseline_snapshot_id)
            if registration is None or baseline is None:
                raise MalformedShadowRegistrationPersistenceError(
                    "persisted Shadow receipt is orphaned"
                )
            if any(
                (
                    receipt.registration_fingerprint
                    != registration.integrity_fingerprint,
                    receipt.baseline_fingerprint != baseline.integrity_fingerprint,
                )
            ):
                raise MalformedShadowRegistrationPersistenceError(
                    "persisted Shadow receipt differs from bundle"
                )
            return ShadowRegistrationPersistenceResult(
                registration, baseline, receipt, replayed=True
            )
        return bundle

    def validate_request_replay(
        self, command_id: str, request_fingerprint: str
    ) -> ShadowRegistrationPersistenceResult | None:
        row = self._request_receipt_row(command_id)
        if row is None:
            return None
        request_receipt = self._load_request_receipt(row)
        if request_receipt.request_fingerprint != request_fingerprint:
            raise ShadowRegistrationReplayConflictError(
                "Shadow registration request payload conflicts"
            )
        receipt_row = self._receipt_row(command_id)
        if receipt_row is None:
            raise MalformedShadowRegistrationPersistenceError(
                "persisted Shadow request receipt is orphaned"
            )
        receipt = self._load_receipt(receipt_row)
        if any(
            (
                request_receipt.shadow_validation_id
                != receipt.shadow_validation_id,
                request_receipt.baseline_snapshot_id
                != receipt.baseline_snapshot_id,
                request_receipt.committed_at != receipt.committed_at,
            )
        ):
            raise MalformedShadowRegistrationPersistenceError(
                "persisted Shadow request receipt differs from receipt"
            )
        registration = self.get_registration(receipt.shadow_validation_id)
        baseline = self.get_baseline(receipt.baseline_snapshot_id)
        if registration is None or baseline is None:
            raise MalformedShadowRegistrationPersistenceError(
                "persisted Shadow request receipt is orphaned"
            )
        if any(
            (
                receipt.registration_fingerprint
                != registration.integrity_fingerprint,
                receipt.baseline_fingerprint != baseline.integrity_fingerprint,
            )
        ):
            raise MalformedShadowRegistrationPersistenceError(
                "persisted Shadow request receipt differs from bundle"
            )
        return ShadowRegistrationPersistenceResult(
            registration, baseline, receipt, replayed=True
        )

    @staticmethod
    def _validate_command(command: PersistShadowRegistrationCommand) -> None:
        if not isinstance(command, PersistShadowRegistrationCommand):
            raise TypeError("command must be PersistShadowRegistrationCommand")
        SQLiteShadowRegistrationBaselineRepository._validate_bundle(
            command.registration, command.baseline
        )

    def _insert_registration(
        self,
        registration: ShadowValidationRegistration,
        inserted_at: datetime,
    ) -> None:
        payload = serialize_shadow_validation_registration(registration)
        subject = registration.subject
        screening = registration.screening_lineage
        try:
            self._connection.execute(
                f"INSERT INTO {REGISTRATION_HISTORY_TABLE} VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    registration.shadow_validation_id,
                    registration.baseline_snapshot_id,
                    subject.o2_opportunity_identity.opportunity_id,
                    subject.target_identity.domestic_selling_target_id,
                    screening.discovery_execution_id,
                    screening.finalized_group_id,
                    screening.screening_evaluation_id,
                    screening.screening_ranking_publication_id,
                    payload,
                    _payload_fingerprint(payload),
                    registration.integrity_fingerprint,
                    registration.schema_version,
                    registration.registered_at.isoformat(),
                    registration.knowledge_cutoff_at.isoformat(),
                    inserted_at.isoformat(),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise ShadowRegistrationReplayConflictError(
                "Shadow registration identity already exists"
            ) from error
        except sqlite3.Error as error:
            raise ShadowRegistrationHistoryError(
                "Shadow registration insert failed"
            ) from error

    def _insert_baseline(
        self,
        baseline: ShadowBaselineSnapshot,
        inserted_at: datetime,
    ) -> None:
        payload = serialize_shadow_baseline_snapshot(baseline)
        try:
            self._connection.execute(
                f"INSERT INTO {BASELINE_HISTORY_TABLE} VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    baseline.baseline_snapshot_id,
                    baseline.shadow_validation_id,
                    baseline.source_manifest.integrity_fingerprint,
                    payload,
                    _payload_fingerprint(payload),
                    baseline.integrity_fingerprint,
                    baseline.schema_version,
                    baseline.knowledge_cutoff_at.isoformat(),
                    baseline.baseline_created_at.isoformat(),
                    inserted_at.isoformat(),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise ShadowRegistrationReplayConflictError(
                "Shadow baseline identity already exists"
            ) from error
        except sqlite3.Error as error:
            raise ShadowRegistrationHistoryError("Shadow baseline insert failed") from error

    def _insert_receipt(self, receipt: ShadowRegistrationReceipt) -> None:
        try:
            self._connection.execute(
                f"INSERT INTO {RECEIPT_TABLE} VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    receipt.command_id,
                    receipt.shadow_validation_id,
                    receipt.baseline_snapshot_id,
                    receipt.command_fingerprint,
                    receipt.registration_fingerprint,
                    receipt.baseline_fingerprint,
                    receipt.committed_at.isoformat(),
                    receipt.schema_version,
                    receipt.committed_at.isoformat(),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise ShadowRegistrationReplayConflictError(
                "Shadow receipt identity already exists"
            ) from error
        except sqlite3.Error as error:
            raise ShadowRegistrationReceiptError("Shadow receipt insert failed") from error

    def _insert_request_receipt(
        self, receipt: ShadowRegistrationRequestReceipt
    ) -> None:
        try:
            self._connection.execute(
                f"INSERT INTO {REQUEST_RECEIPT_TABLE} VALUES(?,?,?,?,?,?,?)",
                (
                    receipt.command_id,
                    receipt.request_fingerprint,
                    receipt.shadow_validation_id,
                    receipt.baseline_snapshot_id,
                    receipt.committed_at.isoformat(),
                    receipt.schema_version,
                    receipt.committed_at.isoformat(),
                ),
            )
        except sqlite3.IntegrityError as error:
            raise ShadowRegistrationReplayConflictError(
                "Shadow registration request receipt identity already exists"
            ) from error
        except sqlite3.Error as error:
            raise ShadowRegistrationReceiptError(
                "Shadow registration request receipt insert failed"
            ) from error

    def _existing_for_command(
        self, command: PersistShadowRegistrationCommand
    ) -> tuple[ShadowValidationRegistration, ShadowBaselineSnapshot] | None:
        requested_registration = command.registration
        requested_baseline = command.baseline
        registration_row = self._registration_row(
            requested_registration.shadow_validation_id
        )
        baseline_row = self._baseline_row(requested_baseline.baseline_snapshot_id)
        if registration_row is None and baseline_row is None:
            return None
        if registration_row is not None:
            linked_baseline_row = self._baseline_row(
                registration_row["baseline_snapshot_id"]
            )
            if linked_baseline_row is None:
                raise MalformedShadowRegistrationPersistenceError(
                    "persisted Shadow registration is orphaned"
                )
            persisted = self._load_exact_bundle(
                registration_row, linked_baseline_row
            )
        else:
            linked_registration_row = self._registration_row(
                baseline_row["shadow_validation_id"]
            )
            if linked_registration_row is None:
                raise MalformedShadowRegistrationPersistenceError(
                    "persisted Shadow baseline is orphaned"
                )
            persisted = self._load_exact_bundle(
                linked_registration_row, baseline_row
            )
        registration, baseline = persisted
        if (
            registration != requested_registration
            or baseline != requested_baseline
            or registration.shadow_validation_id
            != requested_registration.shadow_validation_id
            or baseline.baseline_snapshot_id != requested_baseline.baseline_snapshot_id
        ):
            raise ShadowRegistrationReplayConflictError(
                "Shadow authoritative identity payload conflicts"
            )
        return persisted

    def _commit(self) -> None:
        self._connection.commit()

    def save(
        self, command: PersistShadowRegistrationCommand
    ) -> ShadowRegistrationPersistenceResult:
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            if command.request_fingerprint is not None:
                request_replay = self.validate_request_replay(
                    command.command_id, command.request_fingerprint
                )
                if request_replay is not None:
                    self._connection.commit()
                    return request_replay
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._connection.commit()
                return replay
            self._validate_command(command)
            receipt = ShadowRegistrationReceipt.from_command(command)
            existing = self._existing_for_command(command)
            aliased = existing is not None
            if existing is None:
                self._fault_point("before_registration")
                self._insert_registration(command.registration, command.committed_at)
                self._fault_point("after_registration")
                self._insert_baseline(command.baseline, command.committed_at)
                self._fault_point("after_baseline")
                registration = command.registration
                baseline = command.baseline
            else:
                registration, baseline = existing
            self._fault_point("before_receipt")
            self._insert_receipt(receipt)
            self._fault_point("after_receipt")
            if command.request_fingerprint is not None:
                self._fault_point("before_request_receipt")
                self._insert_request_receipt(
                    ShadowRegistrationRequestReceipt.from_command(command)
                )
                self._fault_point("after_request_receipt")
            self._fault_point("before_commit")
            try:
                self._commit()
            except sqlite3.Error as error:
                raise ShadowRegistrationCommitError(
                    "Shadow registration commit failed"
                ) from error
            return ShadowRegistrationPersistenceResult(
                registration, baseline, receipt, replayed=False, aliased=aliased
            )
        except Exception:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise

    def close(self) -> None:
        if self._connection.in_transaction:
            self._connection.rollback()
        if self._owns_connection:
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        return False


__all__ = [
    "BASELINE_HISTORY_TABLE",
    "RECEIPT_TABLE",
    "REGISTRATION_HISTORY_TABLE",
    "REQUEST_RECEIPT_TABLE",
    "SQLiteShadowRegistrationBaselineRepository",
]
