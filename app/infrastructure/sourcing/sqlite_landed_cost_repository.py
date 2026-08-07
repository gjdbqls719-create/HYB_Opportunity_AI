"""Append-only SQLite persistence for authoritative Landed Cost compositions."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.sourcing.landed_cost import (
    ComposeLandedCostCommand,
    LANDED_COST_COMPOSITION_RECEIPT_SCHEMA_VERSION,
    LandedCostCompositionOpportunityMismatchError,
    LandedCostCompositionReceipt,
    LandedCostCompositionReplayConflictError,
    LandedCostCompositionResult,
    SourcingEconomicsBindingNotFoundError,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.market_intelligence import (
    ArtifactOrigin,
    ArtifactReference,
    ArtifactType,
    ExternalSignalSourceType,
)
from app.domain.sourcing import (
    CostAllocationBasis,
    LANDED_COST_COMPOSITION_SCHEMA_VERSION,
    CommercialFactAvailability,
    LandedCostComponent,
    LandedCostComponentKind,
    LandedCostComposition,
    SourcingEconomicsBindingReference,
    SourcingEvidenceKind,
    SourcingEvidenceReference,
    SourcingQuantityFact,
    SOURCING_EVIDENCE_SCHEMA_VERSION,
)
from app.infrastructure.sourcing.sqlite_economics_binding_repository import (
    SQLiteSourcingEconomicsBindingRepository,
)


class LandedCostCompositionPersistenceError(RuntimeError):
    pass


class LandedCostCompositionHistoryError(LandedCostCompositionPersistenceError):
    pass


class LandedCostCompositionReceiptError(LandedCostCompositionPersistenceError):
    pass


class LandedCostCompositionCommitError(LandedCostCompositionPersistenceError):
    pass


class MalformedLandedCostCompositionPersistenceError(
    LandedCostCompositionPersistenceError
):
    pass


class UnsupportedLandedCostCompositionVersionError(
    MalformedLandedCostCompositionPersistenceError
):
    pass


def _dump(value: dict[str, object]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _fingerprint(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _datetime(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return result


def _artifact(value: ArtifactReference | None) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "artifact_id": value.artifact_id,
        "artifact_type": value.artifact_type.value,
        "artifact_origin": value.artifact_origin.value,
        "source_type": value.source_type.value,
        "sha256": value.sha256,
        "captured_at": value.captured_at.isoformat(),
        "width": value.width,
        "height": value.height,
        "mime_type": value.mime_type,
        "file_size": value.file_size,
        "schema_version": value.schema_version,
    }


def _load_artifact(value: object) -> ArtifactReference | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("artifact_reference must be an object")
    return ArtifactReference(
        artifact_id=value["artifact_id"],
        artifact_type=ArtifactType(value["artifact_type"]),
        artifact_origin=ArtifactOrigin(value["artifact_origin"]),
        source_type=ExternalSignalSourceType(value["source_type"]),
        sha256=value["sha256"],
        captured_at=_datetime(value["captured_at"], "artifact captured_at"),
        width=value["width"],
        height=value["height"],
        mime_type=value["mime_type"],
        file_size=value["file_size"],
        schema_version=value["schema_version"],
    )


def _evidence(value: SourcingEvidenceReference) -> dict[str, object]:
    return {
        "kind": value.kind.value,
        "source_reference": value.source_reference,
        "observed_at": value.observed_at.isoformat(),
        "artifact_reference": _artifact(value.artifact_reference),
        "schema_version": value.schema_version,
    }


def _load_evidence(value: object) -> SourcingEvidenceReference:
    if not isinstance(value, dict):
        raise ValueError("evidence_reference must be an object")
    if value.get("schema_version") != SOURCING_EVIDENCE_SCHEMA_VERSION:
        raise UnsupportedLandedCostCompositionVersionError(
            "unsupported Sourcing evidence version"
        )
    return SourcingEvidenceReference(
        kind=SourcingEvidenceKind(value["kind"]),
        source_reference=value["source_reference"],
        observed_at=_datetime(value["observed_at"], "evidence observed_at"),
        artifact_reference=_load_artifact(value["artifact_reference"]),
        schema_version=value["schema_version"],
    )


def _quantity(value: SourcingQuantityFact) -> dict[str, object]:
    return {"availability": value.availability.value, "quantity": value.quantity}


def _load_quantity(value: object) -> SourcingQuantityFact:
    if not isinstance(value, dict):
        raise ValueError("quantity must be an object")
    return SourcingQuantityFact(
        CommercialFactAvailability(value["availability"]), value["quantity"]
    )


def _component(value: LandedCostComponent, ordinal: int) -> dict[str, object]:
    return {
        "ordinal": ordinal,
        "kind": value.kind.value,
        "availability": value.availability.value,
        "amount": None if value.amount is None else str(value.amount),
        "currency": value.currency,
        "allocation_basis": value.allocation_basis.value,
    }


def _load_component(value: object, ordinal: int) -> LandedCostComponent:
    if not isinstance(value, dict) or value.get("ordinal") != ordinal:
        raise ValueError("component ordinal is malformed")
    amount = value["amount"]
    if amount is not None and not isinstance(amount, str):
        raise ValueError("component amount must be decimal text or null")
    return LandedCostComponent(
        kind=LandedCostComponentKind(value["kind"]),
        availability=CommercialFactAvailability(value["availability"]),
        amount=None if amount is None else Decimal(amount),
        currency=value["currency"],
        allocation_basis=CostAllocationBasis(value["allocation_basis"]),
    )


def _payload(value: LandedCostComposition) -> str:
    return _dump({
        "composition_id": value.composition_id,
        "opportunity_identity": {
            "opportunity_id": value.opportunity_identity.opportunity_id,
            "discovery_reference": value.opportunity_identity.discovery_reference,
        },
        "binding_reference": {
            "binding_id": value.binding_reference.binding_id,
            "schema_version": value.binding_reference.schema_version,
        },
        "components": [
            _component(component, ordinal)
            for ordinal, component in enumerate(value.components)
        ],
        "minimum_order_quantity": _quantity(value.minimum_order_quantity),
        "quoted_quantity": _quantity(value.quoted_quantity),
        "evidence_reference": _evidence(value.evidence_reference),
        "requested_at": value.requested_at.isoformat(),
        "composed_at": value.composed_at.isoformat(),
        "schema_version": value.schema_version,
    })


class SQLiteLandedCostCompositionRepository:
    """Persists lossless acquisition facts without calculation or latest selection."""

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
        self._bindings = SQLiteSourcingEconomicsBindingRepository(
            connection=self._connection
        )
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS landed_cost_composition_history(
                    composition_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    discovery_reference TEXT NOT NULL,
                    binding_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(binding_id) REFERENCES
                      sourcing_economics_binding_history(binding_id)
                )"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS landed_cost_composition_receipts(
                    command_id TEXT PRIMARY KEY,
                    composition_id TEXT NOT NULL,
                    command_fingerprint TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(composition_id) REFERENCES
                      landed_cost_composition_history(composition_id)
                )"""
            )
            for table in (
                "landed_cost_composition_history",
                "landed_cost_composition_receipts",
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

    def get_binding(self, reference: SourcingEconomicsBindingReference):
        return self._bindings.get_binding(reference.binding_id)

    def get_source_admission(self, reference):
        return self._bindings.get_source_admission(reference)

    def _composition_row(self, composition_id: str):
        try:
            return self._connection.execute(
                "SELECT * FROM landed_cost_composition_history WHERE composition_id=?",
                (composition_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise LandedCostCompositionHistoryError(
                "Landed Cost Composition query failed"
            ) from error

    def _composition(self, row) -> LandedCostComposition:
        try:
            if row["schema_version"] != LANDED_COST_COMPOSITION_SCHEMA_VERSION:
                raise UnsupportedLandedCostCompositionVersionError(
                    "unsupported Landed Cost Composition version"
                )
            encoded = row["payload_json"]
            if (
                not isinstance(encoded, str)
                or _fingerprint(encoded) != row["integrity_fingerprint"]
            ):
                raise ValueError("composition integrity fingerprint mismatch")
            payload = json.loads(encoded)
            if not isinstance(payload, dict):
                raise ValueError("composition payload must be an object")
            if payload.get("schema_version") != row["schema_version"]:
                raise ValueError("composition payload version differs")
            opportunity = payload["opportunity_identity"]
            reference = payload["binding_reference"]
            components = payload["components"]
            if not isinstance(opportunity, dict) or not isinstance(reference, dict):
                raise ValueError("composition lineage is malformed")
            if not isinstance(components, list):
                raise ValueError("components must be an ordered list")
            value = LandedCostComposition(
                composition_id=payload["composition_id"],
                opportunity_identity=OpportunityIdentity(
                    opportunity["opportunity_id"], opportunity["discovery_reference"]
                ),
                binding_reference=SourcingEconomicsBindingReference(
                    reference["binding_id"], reference["schema_version"]
                ),
                components=tuple(
                    _load_component(component, ordinal)
                    for ordinal, component in enumerate(components)
                ),
                minimum_order_quantity=_load_quantity(
                    payload["minimum_order_quantity"]
                ),
                quoted_quantity=_load_quantity(payload["quoted_quantity"]),
                evidence_reference=_load_evidence(payload["evidence_reference"]),
                requested_at=_datetime(payload["requested_at"], "requested_at"),
                composed_at=_datetime(payload["composed_at"], "composed_at"),
                schema_version=payload["schema_version"],
            )
            if (
                value.composition_id != row["composition_id"]
                or value.opportunity_identity.opportunity_id != row["opportunity_id"]
                or value.opportunity_identity.discovery_reference
                != row["discovery_reference"]
                or value.binding_reference.binding_id != row["binding_id"]
            ):
                raise ValueError("composition columns differ from payload")
            binding = self._bindings.get_binding(value.binding_reference.binding_id)
            if (
                binding is None
                or binding.reference != value.binding_reference
                or binding.opportunity_identity != value.opportunity_identity
            ):
                raise ValueError("composition references malformed binding lineage")
            return value
        except UnsupportedLandedCostCompositionVersionError:
            raise
        except Exception as error:
            raise MalformedLandedCostCompositionPersistenceError(
                "persisted Landed Cost Composition is malformed"
            ) from error

    def get_composition(self, composition_id: str) -> LandedCostComposition | None:
        row = self._composition_row(composition_id)
        return None if row is None else self._composition(row)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                "SELECT * FROM landed_cost_composition_receipts WHERE command_id=?",
                (command_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise LandedCostCompositionReceiptError(
                "Landed Cost Composition receipt query failed"
            ) from error

    def _receipt(self, row) -> LandedCostCompositionReceipt:
        try:
            if row["schema_version"] != LANDED_COST_COMPOSITION_RECEIPT_SCHEMA_VERSION:
                raise UnsupportedLandedCostCompositionVersionError(
                    "unsupported Landed Cost Composition receipt version"
                )
            fingerprint = row["command_fingerprint"]
            if (
                not isinstance(fingerprint, str)
                or len(fingerprint) != 64
                or any(value not in "0123456789abcdef" for value in fingerprint)
            ):
                raise ValueError("receipt command fingerprint is malformed")
            return LandedCostCompositionReceipt(
                row["command_id"],
                row["composition_id"],
                fingerprint,
                _datetime(row["committed_at"], "committed_at"),
                row["schema_version"],
            )
        except UnsupportedLandedCostCompositionVersionError:
            raise
        except Exception as error:
            raise MalformedLandedCostCompositionPersistenceError(
                "persisted Landed Cost Composition receipt is malformed"
            ) from error

    def get_receipt(self, command_id: str) -> LandedCostCompositionReceipt | None:
        row = self._receipt_row(command_id)
        return None if row is None else self._receipt(row)

    def validate_replay(
        self, command_id: str, fingerprint: str
    ) -> LandedCostCompositionResult | None:
        row = self._receipt_row(command_id)
        if row is None:
            return None
        receipt = self._receipt(row)
        if receipt.command_fingerprint != fingerprint:
            raise LandedCostCompositionReplayConflictError(
                "Landed Cost Composition command payload conflicts"
            )
        composition = self.get_composition(receipt.composition_id)
        if composition is None:
            raise MalformedLandedCostCompositionPersistenceError(
                "receipt references missing Landed Cost Composition"
            )
        return LandedCostCompositionResult(composition, receipt, True)

    @staticmethod
    def _validate_write(command, composition, receipt) -> None:
        if not isinstance(command, ComposeLandedCostCommand):
            raise TypeError("command must be ComposeLandedCostCommand")
        if not isinstance(composition, LandedCostComposition):
            raise TypeError("composition must be LandedCostComposition")
        if not isinstance(receipt, LandedCostCompositionReceipt):
            raise TypeError("receipt must be LandedCostCompositionReceipt")
        if (
            composition.opportunity_identity != command.opportunity_identity
            or composition.binding_reference != command.binding_reference
            or composition.requested_at != command.requested_at
            or receipt.command_id != command.command_id
            or receipt.composition_id != composition.composition_id
            or receipt.command_fingerprint != command.fingerprint
        ):
            raise LandedCostCompositionReplayConflictError(
                "command, composition, and receipt do not match"
            )

    def save_composition(self, command, composition, receipt):
        self._validate_write(command, composition, receipt)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            binding = self._bindings.get_binding(command.binding_reference.binding_id)
            if binding is None:
                raise SourcingEconomicsBindingNotFoundError(
                    "exact persisted binding is missing"
                )
            if binding.opportunity_identity != command.opportunity_identity:
                raise LandedCostCompositionOpportunityMismatchError(
                    "persisted binding Opportunity differs"
                )
            encoded = _payload(composition)
            try:
                self._connection.execute(
                    """INSERT INTO landed_cost_composition_history
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (
                        composition.composition_id,
                        composition.opportunity_identity.opportunity_id,
                        composition.opportunity_identity.discovery_reference,
                        composition.binding_reference.binding_id,
                        encoded,
                        _fingerprint(encoded),
                        composition.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise LandedCostCompositionHistoryError(
                    "Landed Cost Composition insert failed"
                ) from error
            try:
                self._connection.execute(
                    """INSERT INTO landed_cost_composition_receipts
                    VALUES(?,?,?,?,?,?)""",
                    (
                        receipt.command_id,
                        receipt.composition_id,
                        receipt.command_fingerprint,
                        receipt.committed_at.isoformat(),
                        receipt.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise LandedCostCompositionReceiptError(
                    "Landed Cost Composition receipt insert failed"
                ) from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise LandedCostCompositionCommitError(
                    "Landed Cost Composition commit failed"
                ) from error
            return LandedCostCompositionResult(composition, receipt, False)
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
    if name.startswith("SQLite")
    or name.startswith("Landed")
    or name.startswith("Malformed")
    or name.startswith("Unsupported")
]
