"""Append-only SQLite persistence for authoritative FX observations."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
from decimal import Decimal

from app.application.sourcing.fx_observation import (
    AdmitFXObservationCommand,
    FXObservationReceipt,
    FX_OBSERVATION_RECEIPT_SCHEMA_VERSION,
    FXObservationAdmissionResult,
    FXObservationReceiptIntegrityError,
    FXObservationReplayConflictError,
)
from app.domain.sourcing import (
    FXObservation,
    FXObservationProvenance,
    FX_OBSERVATION_SCHEMA_VERSION,
)


class FXObservationPersistenceError(RuntimeError):
    pass


class FXObservationHistoryError(FXObservationPersistenceError):
    pass


class FXObservationReceiptError(FXObservationPersistenceError):
    pass


class FXObservationCommitError(FXObservationPersistenceError):
    pass


class MalformedFXObservationPersistenceError(FXObservationPersistenceError):
    pass


class UnsupportedFXObservationVersionError(MalformedFXObservationPersistenceError):
    pass


HISTORY_TABLE = "fx_observation_history"
RECEIPT_TABLE = "fx_observation_receipts"


def _dump(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return parsed


def _provenance(value: FXObservationProvenance) -> dict[str, object]:
    return {
        "provider": value.provider,
        "source_reference": value.source_reference,
        "collection_method": value.collection_method,
    }


def _load_provenance(value: object) -> FXObservationProvenance:
    if not isinstance(value, dict):
        raise ValueError("provenance must be an object")
    return FXObservationProvenance(
        provider=value["provider"],
        source_reference=value["source_reference"],
        collection_method=value["collection_method"],
    )


def _payload(value: FXObservation) -> str:
    return _dump({
        "observation_id": value.observation_id,
        "base_currency": value.base_currency,
        "quote_currency": value.quote_currency,
        "rate": str(value.rate),
        "observed_at": value.observed_at.isoformat(),
        "admitted_at": value.admitted_at.isoformat(),
        "provenance": _provenance(value.provenance),
        "schema_version": value.schema_version,
    })


def _load(row) -> FXObservation:
    try:
        if row["schema_version"] != FX_OBSERVATION_SCHEMA_VERSION:
            raise UnsupportedFXObservationVersionError("unsupported FX observation version")
        encoded = row["payload_json"]
        if not isinstance(encoded, str) or _sha256(encoded) != row["integrity_fingerprint"]:
            raise ValueError("FX observation integrity fingerprint mismatch")
        payload = json.loads(encoded)
        if not isinstance(payload, dict):
            raise ValueError("FX observation payload is malformed")
        if payload.get("schema_version") != FX_OBSERVATION_SCHEMA_VERSION:
            raise UnsupportedFXObservationVersionError("unsupported FX observation payload schema")
        if row["observation_id"] != payload["observation_id"]:
            raise ValueError("observation id differs from stored payload")
        return FXObservation(
            observation_id=payload["observation_id"],
            base_currency=payload["base_currency"],
            quote_currency=payload["quote_currency"],
            rate=Decimal(str(payload["rate"])),
            observed_at=_datetime(payload["observed_at"], "observed_at"),
            admitted_at=_datetime(payload["admitted_at"], "admitted_at"),
            provenance=_load_provenance(payload["provenance"]),
            schema_version=payload["schema_version"],
        )
    except UnsupportedFXObservationVersionError:
        raise
    except Exception as error:
        raise MalformedFXObservationPersistenceError(
            "persisted FX observation is malformed"
        ) from error


def _load_receipt(row) -> FXObservationReceipt:
    try:
        if row["schema_version"] != FX_OBSERVATION_RECEIPT_SCHEMA_VERSION:
            raise UnsupportedFXObservationVersionError("unsupported FX observation receipt version")
        return FXObservationReceipt(
            command_id=row["command_id"],
            observation_id=row["observation_id"],
            command_fingerprint=row["command_fingerprint"],
            committed_at=_datetime(row["committed_at"], "committed_at"),
            schema_version=row["schema_version"],
        )
    except UnsupportedFXObservationVersionError:
        raise
    except Exception as error:
        raise FXObservationReceiptIntegrityError(
            "persisted FX observation receipt is malformed"
        ) from error


class SQLiteFXObservationRepository:
    """Persists authoritative FX observations only; no normalization is performed."""

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
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {HISTORY_TABLE}(
                    observation_id TEXT PRIMARY KEY,
                    base_currency TEXT NOT NULL,
                    quote_currency TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL
                )"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE}(
                    command_id TEXT PRIMARY KEY,
                    observation_id TEXT NOT NULL,
                    command_fingerprint TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(observation_id) REFERENCES {HISTORY_TABLE}(observation_id)
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

    def _history_row(self, observation_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE observation_id=?",
                (observation_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise FXObservationHistoryError("FX observation query failed") from error

    def get_observation(self, observation_id: str) -> FXObservation | None:
        row = self._history_row(observation_id)
        return None if row is None else _load(row)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?",
                (command_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise FXObservationReceiptError("FX observation receipt query failed") from error

    def get_receipt(self, command_id: str) -> FXObservationReceipt | None:
        row = self._receipt_row(command_id)
        return None if row is None else _load_receipt(row)

    def validate_replay(
        self, command_id: str, fingerprint: str
    ) -> FXObservationAdmissionResult | None:
        row = self._receipt_row(command_id)
        if row is None:
            return None
        receipt = _load_receipt(row)
        if receipt.command_fingerprint != fingerprint:
            raise FXObservationReplayConflictError(
                "FX observation command payload conflicts"
            )
        observation = self.get_observation(receipt.observation_id)
        if observation is None:
            raise MalformedFXObservationPersistenceError(
                "receipt references missing FX observation"
            )
        return FXObservationAdmissionResult(
            observation=observation,
            receipt=receipt,
            replayed=True,
        )

    @staticmethod
    def _validate_write(
        command: AdmitFXObservationCommand,
        observation: FXObservation,
        receipt: FXObservationReceipt,
    ) -> None:
        if not isinstance(command, AdmitFXObservationCommand):
            raise TypeError("command must be AdmitFXObservationCommand")
        if not isinstance(observation, FXObservation):
            raise TypeError("observation must be FXObservation")
        if not isinstance(receipt, FXObservationReceipt):
            raise TypeError("receipt must be FXObservationReceipt")
        if (
            observation.base_currency != command.base_currency
            or observation.quote_currency != command.quote_currency
            or observation.rate != command.rate
            or observation.observed_at != command.observed_at
            or receipt.command_fingerprint != command.fingerprint
            or receipt.command_id != command.command_id
            or receipt.observation_id != observation.observation_id
            or observation.provenance.provider != command.provider
            or observation.provenance.source_reference != command.source_reference
            or observation.provenance.collection_method != command.collection_method
        ):
            raise FXObservationReplayConflictError(
                "command, observation, and receipt do not match"
            )

    def save_observation(
        self, command: AdmitFXObservationCommand, observation: FXObservation, receipt: FXObservationReceipt
    ) -> FXObservationAdmissionResult:
        self._validate_write(command, observation, receipt)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            encoded = _payload(observation)
            try:
                self._connection.execute(
                    f"""INSERT INTO {HISTORY_TABLE}
                    VALUES(?,?,?,?,?,?,?)""",
                    (
                        observation.observation_id,
                        observation.base_currency,
                        observation.quote_currency,
                        encoded,
                        _sha256(encoded),
                        FX_OBSERVATION_SCHEMA_VERSION,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise FXObservationHistoryError("FX observation insert failed") from error
            try:
                self._connection.execute(
                    f"""INSERT INTO {RECEIPT_TABLE}
                    VALUES(?,?,?,?,?,?)""",
                    (
                        receipt.command_id,
                        receipt.observation_id,
                        receipt.command_fingerprint,
                        receipt.committed_at.isoformat(),
                        FX_OBSERVATION_RECEIPT_SCHEMA_VERSION,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise FXObservationReceiptError("FX observation receipt insert failed") from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise FXObservationCommitError("FX observation commit failed") from error
            return FXObservationAdmissionResult(observation=observation, receipt=receipt, replayed=False)
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
    "HISTORY_TABLE",
    "MalformedFXObservationPersistenceError",
    "FXObservationCommitError",
    "FXObservationHistoryError",
    "FXObservationReceiptError",
    "SQLiteFXObservationRepository",
    "UnsupportedFXObservationVersionError",
]
