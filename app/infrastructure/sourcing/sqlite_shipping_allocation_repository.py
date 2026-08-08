"""Append-only SQLite persistence for Shipping Allocation Authority facts."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.sourcing.shipping_allocation_authority import (
    SHIPPING_ALLOCATION_AUTHORITY_RECEIPT_SCHEMA_VERSION,
    ShippingAllocationAuthorityReceipt,
    ShippingAllocationAuthorityReplayConflictError,
    ShippingAllocationAuthorityResult,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing import (
    SHIPPING_ALLOCATION_AUTHORITY_SCHEMA_VERSION,
    CommercialFactAvailability,
    CostAllocationBasis,
    LandedCostComponentKind,
    ShippingAllocationAuthority,
    ShippingAllocationAuthorityCode,
    ShippingAllocationAuthorityCommand,
    ShippingAllocationAuthorityDenominatorSource,
    ShippingAllocationAuthorityStatus,
    ShippingAllocationBasisAuthoritySource,
    ShippingAllocationDenominator,
)
from app.infrastructure.sourcing.sqlite_landed_cost_repository import (
    SQLiteLandedCostCompositionRepository,
    _evidence,
    _load_evidence,
)


HISTORY_TABLE = "shipping_allocation_authority_history"
RECEIPT_TABLE = "shipping_allocation_authority_receipts"


class ShippingAllocationAuthorityPersistenceError(RuntimeError):
    pass


class ShippingAllocationAuthorityHistoryError(
    ShippingAllocationAuthorityPersistenceError
):
    pass


class ShippingAllocationAuthorityReceiptError(
    ShippingAllocationAuthorityPersistenceError
):
    pass


class ShippingAllocationAuthorityCommitError(
    ShippingAllocationAuthorityPersistenceError
):
    pass


class MalformedShippingAllocationAuthorityPersistenceError(
    ShippingAllocationAuthorityPersistenceError
):
    pass


class UnsupportedShippingAllocationAuthorityVersionError(
    MalformedShippingAllocationAuthorityPersistenceError
):
    pass


def _dump(value: dict[str, object]) -> str:
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


def _denominator(value: ShippingAllocationDenominator | None):
    if value is None:
        return None
    return {
        "quantity": value.quantity,
        "source": value.source.value,
        "source_reference": value.source_reference,
        "quantity_unit": value.quantity_unit,
    }


def _load_denominator(value: object):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("denominator must be an object or null")
    return ShippingAllocationDenominator(
        quantity=value["quantity"],
        source=ShippingAllocationAuthorityDenominatorSource(value["source"]),
        source_reference=value["source_reference"],
        quantity_unit=value["quantity_unit"],
    )


def _payload(value: ShippingAllocationAuthority) -> str:
    return _dump(
        {
            "authority_id": value.authority_id,
            "composition_id": value.composition_id,
            "opportunity_identity": {
                "opportunity_id": value.opportunity_identity.opportunity_id,
                "discovery_reference": value.opportunity_identity.discovery_reference,
            },
            "component_kind": value.component_kind.value,
            "original_allocation_basis": value.original_allocation_basis.value,
            "allocation_basis": value.allocation_basis.value,
            "basis_authority_source": value.basis_authority_source.value,
            "status": value.status.value,
            "evidence_reference": _evidence(value.evidence_reference),
            "requested_at": value.requested_at.isoformat(),
            "admitted_at": value.admitted_at.isoformat(),
            "operator_id": value.operator_id,
            "verified_at": (
                None if value.verified_at is None else value.verified_at.isoformat()
            ),
            "denominator": _denominator(value.denominator),
            "unresolved_code": (
                None if value.unresolved_code is None else value.unresolved_code.value
            ),
            "schema_version": value.schema_version,
        }
    )


class SQLiteShippingAllocationAuthorityRepository:
    """Stores exact allocation facts without dividing or selecting latest values."""

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
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {HISTORY_TABLE}(
                    authority_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    discovery_reference TEXT NOT NULL,
                    composition_id TEXT NOT NULL,
                    component_kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(composition_id) REFERENCES
                      landed_cost_composition_history(composition_id)
                )"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE}(
                    command_id TEXT PRIMARY KEY,
                    authority_id TEXT NOT NULL,
                    command_fingerprint TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(authority_id) REFERENCES {HISTORY_TABLE}(authority_id)
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

    def get_composition(self, composition_id: str):
        return self._landed_cost.get_composition(composition_id)

    def _history_row(self, authority_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE authority_id=?",
                (authority_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise ShippingAllocationAuthorityHistoryError(
                "Shipping Allocation Authority query failed"
            ) from error

    def _load_authority(self, row) -> ShippingAllocationAuthority:
        try:
            if row["schema_version"] != SHIPPING_ALLOCATION_AUTHORITY_SCHEMA_VERSION:
                raise UnsupportedShippingAllocationAuthorityVersionError(
                    "unsupported Shipping Allocation Authority version"
                )
            encoded = row["payload_json"]
            if not isinstance(encoded, str) or _integrity(encoded) != row["integrity_fingerprint"]:
                raise ValueError("authority integrity fingerprint mismatch")
            payload = json.loads(encoded)
            if not isinstance(payload, dict):
                raise ValueError("authority payload must be an object")
            if payload.get("schema_version") != row["schema_version"]:
                raise ValueError("authority payload version differs")
            opportunity = payload["opportunity_identity"]
            if not isinstance(opportunity, dict):
                raise ValueError("Opportunity identity is malformed")
            verified_at = payload["verified_at"]
            unresolved = payload["unresolved_code"]
            value = ShippingAllocationAuthority(
                authority_id=payload["authority_id"],
                composition_id=payload["composition_id"],
                opportunity_identity=OpportunityIdentity(
                    opportunity["opportunity_id"],
                    opportunity["discovery_reference"],
                ),
                component_kind=LandedCostComponentKind(payload["component_kind"]),
                original_allocation_basis=CostAllocationBasis(
                    payload["original_allocation_basis"]
                ),
                allocation_basis=CostAllocationBasis(payload["allocation_basis"]),
                basis_authority_source=ShippingAllocationBasisAuthoritySource(
                    payload["basis_authority_source"]
                ),
                status=ShippingAllocationAuthorityStatus(payload["status"]),
                evidence_reference=_load_evidence(payload["evidence_reference"]),
                requested_at=_datetime(payload["requested_at"], "requested_at"),
                admitted_at=_datetime(payload["admitted_at"], "admitted_at"),
                operator_id=payload["operator_id"],
                verified_at=(
                    None if verified_at is None else _datetime(verified_at, "verified_at")
                ),
                denominator=_load_denominator(payload["denominator"]),
                unresolved_code=(
                    None if unresolved is None else ShippingAllocationAuthorityCode(unresolved)
                ),
                schema_version=payload["schema_version"],
            )
            if (
                value.authority_id != row["authority_id"]
                or value.composition_id != row["composition_id"]
                or value.opportunity_identity.opportunity_id != row["opportunity_id"]
                or value.opportunity_identity.discovery_reference != row["discovery_reference"]
                or value.component_kind.value != row["component_kind"]
            ):
                raise ValueError("authority columns differ from payload")
            self._validate_source(value)
            return value
        except UnsupportedShippingAllocationAuthorityVersionError:
            raise
        except Exception as error:
            raise MalformedShippingAllocationAuthorityPersistenceError(
                "Shipping Allocation Authority persistence is malformed"
            ) from error

    def get_authority(self, authority_id: str) -> ShippingAllocationAuthority | None:
        row = self._history_row(authority_id)
        return None if row is None else self._load_authority(row)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?",
                (command_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise ShippingAllocationAuthorityReceiptError(
                "Shipping Allocation Authority receipt query failed"
            ) from error

    def _load_receipt(self, row) -> ShippingAllocationAuthorityReceipt:
        try:
            value = ShippingAllocationAuthorityReceipt(
                command_id=row["command_id"],
                authority_id=row["authority_id"],
                command_fingerprint=row["command_fingerprint"],
                committed_at=_datetime(row["committed_at"], "committed_at"),
                schema_version=row["schema_version"],
            )
            if self.get_authority(value.authority_id) is None:
                raise ValueError("receipt references missing authority")
            return value
        except Exception as error:
            if isinstance(error, MalformedShippingAllocationAuthorityPersistenceError):
                raise
            raise MalformedShippingAllocationAuthorityPersistenceError(
                "Shipping Allocation Authority receipt is malformed"
            ) from error

    def get_receipt(self, command_id: str) -> ShippingAllocationAuthorityReceipt | None:
        row = self._receipt_row(command_id)
        return None if row is None else self._load_receipt(row)

    def validate_replay(
        self,
        command_id: str,
        fingerprint: str,
    ) -> ShippingAllocationAuthorityResult | None:
        row = self._receipt_row(command_id)
        if row is None:
            return None
        receipt = self._load_receipt(row)
        if receipt.command_fingerprint != fingerprint:
            raise ShippingAllocationAuthorityReplayConflictError(
                "Shipping Allocation Authority command payload conflicts"
            )
        authority = self.get_authority(receipt.authority_id)
        if authority is None:
            raise MalformedShippingAllocationAuthorityPersistenceError(
                "receipt references missing authority"
            )
        return ShippingAllocationAuthorityResult(authority, receipt, True)

    def _validate_source(self, authority: ShippingAllocationAuthority) -> None:
        composition = self.get_composition(authority.composition_id)
        if composition is None:
            raise ValueError("authority references missing composition")
        if composition.opportunity_identity != authority.opportunity_identity:
            raise ValueError("authority Opportunity differs from composition")
        component = next(
            (
                value
                for value in composition.components
                if value.kind is authority.component_kind
            ),
            None,
        )
        if component is None or component.kind is LandedCostComponentKind.UNIT_PURCHASE:
            raise ValueError("authority references invalid shipping component")
        if component.allocation_basis is not authority.original_allocation_basis:
            raise ValueError("authority original basis differs from composition")
        if (
            authority.basis_authority_source
            is ShippingAllocationBasisAuthoritySource.SOURCE_DECLARED
            and authority.evidence_reference != composition.evidence_reference
        ):
            raise ValueError("source-declared authority evidence differs")
        if (
            authority.status is ShippingAllocationAuthorityStatus.RESOLVED
            and authority.allocation_basis is CostAllocationBasis.PER_QUOTED_QUANTITY
        ):
            quantity = composition.quoted_quantity
            if (
                quantity.availability is not CommercialFactAvailability.KNOWN
                or quantity.quantity is None
                or authority.denominator is None
                or authority.denominator.quantity != quantity.quantity
                or authority.denominator.source
                is not ShippingAllocationAuthorityDenominatorSource.SOURCE_DERIVED
            ):
                raise ValueError("quoted-quantity denominator differs from exact source")

    def _validate_write(self, command, authority, receipt) -> None:
        if command.fingerprint != receipt.command_fingerprint:
            raise ValueError("receipt fingerprint differs from command")
        if command.command_id != receipt.command_id:
            raise ValueError("receipt command differs")
        if command.composition_id != authority.composition_id:
            raise ValueError("authority composition differs from command")
        if command.opportunity_identity != authority.opportunity_identity:
            raise ValueError("authority Opportunity differs from command")
        if command.component_kind is not authority.component_kind:
            raise ValueError("authority component differs from command")
        if authority.authority_id != receipt.authority_id:
            raise ValueError("receipt authority differs")
        self._validate_source(authority)

    def save_authority(self, command, authority, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._connection.commit()
                return replay
            self._validate_write(command, authority, receipt)
            encoded = _payload(authority)
            try:
                self._connection.execute(
                    f"""INSERT INTO {HISTORY_TABLE}(
                        authority_id,opportunity_id,discovery_reference,composition_id,
                        component_kind,payload_json,integrity_fingerprint,schema_version,
                        inserted_at) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        authority.authority_id,
                        authority.opportunity_identity.opportunity_id,
                        authority.opportunity_identity.discovery_reference,
                        authority.composition_id,
                        authority.component_kind.value,
                        encoded,
                        _integrity(encoded),
                        authority.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise ShippingAllocationAuthorityHistoryError(
                    "Shipping Allocation Authority insert failed"
                ) from error
            try:
                self._connection.execute(
                    f"""INSERT INTO {RECEIPT_TABLE}(
                        command_id,authority_id,command_fingerprint,committed_at,
                        schema_version,inserted_at) VALUES(?,?,?,?,?,?)""",
                    (
                        receipt.command_id,
                        receipt.authority_id,
                        receipt.command_fingerprint,
                        receipt.committed_at.isoformat(),
                        receipt.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise ShippingAllocationAuthorityReceiptError(
                    "Shipping Allocation Authority receipt insert failed"
                ) from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise ShippingAllocationAuthorityCommitError(
                    "Shipping Allocation Authority commit failed"
                ) from error
            return ShippingAllocationAuthorityResult(authority, receipt, False)
        except ShippingAllocationAuthorityReplayConflictError:
            self._rollback()
            raise
        except ShippingAllocationAuthorityPersistenceError:
            self._rollback()
            raise
        except Exception as error:
            self._rollback()
            raise MalformedShippingAllocationAuthorityPersistenceError(
                "Shipping Allocation Authority write is invalid"
            ) from error

    def close(self) -> None:
        self._rollback()
        if self._owns_connection:
            self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()


__all__ = [name for name in globals() if name.startswith("SQLiteShipping") or name.startswith("Shipping") or name.startswith("Malformed") or name.startswith("Unsupported")]
