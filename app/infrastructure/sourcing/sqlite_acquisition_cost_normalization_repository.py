"""Append-only SQLite persistence for acquisition-cost normalizations."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.sourcing.acquisition_cost_normalization import (
    ACQUISITION_COST_NORMALIZATION_RECEIPT_SCHEMA_VERSION,
    AcquisitionCostNormalizationReceipt,
    AcquisitionCostNormalizationReplayConflictError,
    AcquisitionCostNormalizationResult,
    NormalizeAcquisitionCostsCommand,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.sourcing import (
    ACQUISITION_COST_NORMALIZATION_SCHEMA_VERSION,
    AcquisitionCostNormalization,
    CommercialFactAvailability,
    CostAllocationBasis,
    FXConversionDirection,
    LandedCostComponentKind,
    NormalizedAcquisitionCostComponent,
    ShippingAllocationAuthorityDenominatorSource,
)
from app.infrastructure.sourcing.sqlite_fx_observation_repository import (
    SQLiteFXObservationRepository,
)
from app.infrastructure.sourcing.sqlite_landed_cost_repository import (
    SQLiteLandedCostCompositionRepository,
)
from app.infrastructure.sourcing.sqlite_shipping_allocation_repository import (
    SQLiteShippingAllocationAuthorityRepository,
)


HISTORY_TABLE = "acquisition_cost_normalization_history"
RECEIPT_TABLE = "acquisition_cost_normalization_receipts"


class AcquisitionCostNormalizationPersistenceError(RuntimeError):
    pass


class AcquisitionCostNormalizationHistoryError(
    AcquisitionCostNormalizationPersistenceError
):
    pass


class AcquisitionCostNormalizationReceiptError(
    AcquisitionCostNormalizationPersistenceError
):
    pass


class AcquisitionCostNormalizationCommitError(
    AcquisitionCostNormalizationPersistenceError
):
    pass


class MalformedAcquisitionCostNormalizationPersistenceError(
    AcquisitionCostNormalizationPersistenceError
):
    pass


class UnsupportedAcquisitionCostNormalizationVersionError(
    MalformedAcquisitionCostNormalizationPersistenceError
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


def _component(value: NormalizedAcquisitionCostComponent) -> dict[str, object]:
    return {
        "kind": value.kind.value,
        "original_availability": value.original_availability.value,
        "original_amount": (
            None if value.original_amount is None else str(value.original_amount)
        ),
        "original_currency": value.original_currency,
        "original_allocation_basis": value.original_allocation_basis.value,
        "effective_allocation_basis": value.effective_allocation_basis.value,
        "allocation_authority_id": value.allocation_authority_id,
        "denominator_quantity": value.denominator_quantity,
        "denominator_source": (
            None if value.denominator_source is None else value.denominator_source.value
        ),
        "fx_observation_id": value.fx_observation_id,
        "fx_direction": value.fx_direction.value,
        "target_currency": value.target_currency,
        "normalized_per_unit_amount": str(value.normalized_per_unit_amount),
    }


def _load_component(value: object) -> NormalizedAcquisitionCostComponent:
    if not isinstance(value, dict):
        raise ValueError("normalization component must be an object")
    denominator_source = value["denominator_source"]
    original_amount = value["original_amount"]
    return NormalizedAcquisitionCostComponent(
        kind=LandedCostComponentKind(value["kind"]),
        original_availability=CommercialFactAvailability(
            value["original_availability"]
        ),
        original_amount=(
            None if original_amount is None else Decimal(str(original_amount))
        ),
        original_currency=value["original_currency"],
        original_allocation_basis=CostAllocationBasis(
            value["original_allocation_basis"]
        ),
        effective_allocation_basis=CostAllocationBasis(
            value["effective_allocation_basis"]
        ),
        allocation_authority_id=value["allocation_authority_id"],
        denominator_quantity=value["denominator_quantity"],
        denominator_source=(
            None
            if denominator_source is None
            else ShippingAllocationAuthorityDenominatorSource(denominator_source)
        ),
        fx_observation_id=value["fx_observation_id"],
        fx_direction=FXConversionDirection(value["fx_direction"]),
        target_currency=value["target_currency"],
        normalized_per_unit_amount=Decimal(
            str(value["normalized_per_unit_amount"])
        ),
    )


def _payload(value: AcquisitionCostNormalization) -> str:
    return _dump(
        {
            "normalization_id": value.normalization_id,
            "opportunity_identity": {
                "opportunity_id": value.opportunity_identity.opportunity_id,
                "discovery_reference": value.opportunity_identity.discovery_reference,
            },
            "composition_id": value.composition_id,
            "allocation_authority_ids": list(value.allocation_authority_ids),
            "fx_observation_ids": list(value.fx_observation_ids),
            "target_currency": value.target_currency,
            "components": [_component(component) for component in value.components],
            "total_per_unit_acquisition_cost": str(
                value.total_per_unit_acquisition_cost
            ),
            "policy_name": value.policy_name,
            "policy_version": value.policy_version,
            "policy_precision": value.policy_precision,
            "policy_rounding": value.policy_rounding,
            "requested_at": value.requested_at.isoformat(),
            "normalized_at": value.normalized_at.isoformat(),
            "schema_version": value.schema_version,
        }
    )


class SQLiteAcquisitionCostNormalizationRepository:
    """Stores exact-source normalization results without selecting latest facts."""

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
        self._allocation = SQLiteShippingAllocationAuthorityRepository(
            connection=self._connection
        )
        self._fx = SQLiteFXObservationRepository(connection=self._connection)
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {HISTORY_TABLE}(
                    normalization_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    discovery_reference TEXT NOT NULL,
                    composition_id TEXT NOT NULL,
                    target_currency TEXT NOT NULL,
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
                    normalization_id TEXT NOT NULL,
                    command_fingerprint TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(normalization_id) REFERENCES
                      {HISTORY_TABLE}(normalization_id)
                )"""
            )
            for table in (HISTORY_TABLE, RECEIPT_TABLE):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS
                        trg_{table}_no_{operation.lower()}
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

    def get_allocation_authority(self, authority_id: str):
        return self._allocation.get_authority(authority_id)

    def get_fx_observation(self, observation_id: str):
        return self._fx.get_observation(observation_id)

    def _history_row(self, normalization_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE normalization_id=?",
                (normalization_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise AcquisitionCostNormalizationHistoryError(
                "acquisition normalization query failed"
            ) from error

    def _load_normalization(self, row) -> AcquisitionCostNormalization:
        try:
            if row["schema_version"] != ACQUISITION_COST_NORMALIZATION_SCHEMA_VERSION:
                raise UnsupportedAcquisitionCostNormalizationVersionError(
                    "unsupported acquisition normalization version"
                )
            encoded = row["payload_json"]
            if (
                not isinstance(encoded, str)
                or _integrity(encoded) != row["integrity_fingerprint"]
            ):
                raise ValueError("normalization integrity fingerprint mismatch")
            payload = json.loads(encoded)
            if not isinstance(payload, dict):
                raise ValueError("normalization payload must be an object")
            if payload.get("schema_version") != row["schema_version"]:
                raise ValueError("normalization payload version differs")
            opportunity = payload["opportunity_identity"]
            if not isinstance(opportunity, dict):
                raise ValueError("Opportunity identity is malformed")
            value = AcquisitionCostNormalization(
                normalization_id=payload["normalization_id"],
                opportunity_identity=OpportunityIdentity(
                    opportunity["opportunity_id"],
                    opportunity["discovery_reference"],
                ),
                composition_id=payload["composition_id"],
                allocation_authority_ids=tuple(
                    payload["allocation_authority_ids"]
                ),
                fx_observation_ids=tuple(payload["fx_observation_ids"]),
                target_currency=payload["target_currency"],
                components=tuple(
                    _load_component(component) for component in payload["components"]
                ),
                total_per_unit_acquisition_cost=Decimal(
                    str(payload["total_per_unit_acquisition_cost"])
                ),
                policy_name=payload["policy_name"],
                policy_version=payload["policy_version"],
                policy_precision=payload["policy_precision"],
                policy_rounding=payload["policy_rounding"],
                requested_at=_datetime(payload["requested_at"], "requested_at"),
                normalized_at=_datetime(payload["normalized_at"], "normalized_at"),
                schema_version=payload["schema_version"],
            )
            if (
                value.normalization_id != row["normalization_id"]
                or value.composition_id != row["composition_id"]
                or value.opportunity_identity.opportunity_id != row["opportunity_id"]
                or value.opportunity_identity.discovery_reference
                != row["discovery_reference"]
                or value.target_currency != row["target_currency"]
            ):
                raise ValueError("normalization columns differ from payload")
            self._validate_sources(value)
            return value
        except UnsupportedAcquisitionCostNormalizationVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedAcquisitionCostNormalizationPersistenceError):
                raise
            raise MalformedAcquisitionCostNormalizationPersistenceError(
                "acquisition normalization persistence is malformed"
            ) from error

    def get_normalization(
        self, normalization_id: str
    ) -> AcquisitionCostNormalization | None:
        row = self._history_row(normalization_id)
        return None if row is None else self._load_normalization(row)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?",
                (command_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise AcquisitionCostNormalizationReceiptError(
                "acquisition normalization receipt query failed"
            ) from error

    def _load_receipt(self, row) -> AcquisitionCostNormalizationReceipt:
        try:
            if (
                row["schema_version"]
                != ACQUISITION_COST_NORMALIZATION_RECEIPT_SCHEMA_VERSION
            ):
                raise UnsupportedAcquisitionCostNormalizationVersionError(
                    "unsupported acquisition normalization receipt version"
                )
            value = AcquisitionCostNormalizationReceipt(
                command_id=row["command_id"],
                normalization_id=row["normalization_id"],
                command_fingerprint=row["command_fingerprint"],
                committed_at=_datetime(row["committed_at"], "committed_at"),
                schema_version=row["schema_version"],
            )
            if self.get_normalization(value.normalization_id) is None:
                raise ValueError("receipt references missing normalization")
            return value
        except Exception as error:
            if isinstance(error, MalformedAcquisitionCostNormalizationPersistenceError):
                raise
            raise MalformedAcquisitionCostNormalizationPersistenceError(
                "acquisition normalization receipt is malformed"
            ) from error

    def get_receipt(
        self, command_id: str
    ) -> AcquisitionCostNormalizationReceipt | None:
        row = self._receipt_row(command_id)
        return None if row is None else self._load_receipt(row)

    def validate_replay(
        self, command_id: str, fingerprint: str
    ) -> AcquisitionCostNormalizationResult | None:
        row = self._receipt_row(command_id)
        if row is None:
            return None
        receipt = self._load_receipt(row)
        if receipt.command_fingerprint != fingerprint:
            raise AcquisitionCostNormalizationReplayConflictError(
                "acquisition normalization command payload conflicts"
            )
        normalization = self.get_normalization(receipt.normalization_id)
        if normalization is None:
            raise MalformedAcquisitionCostNormalizationPersistenceError(
                "receipt references missing normalization"
            )
        return AcquisitionCostNormalizationResult(normalization, receipt, True)

    def _validate_sources(self, value: AcquisitionCostNormalization) -> None:
        composition = self.get_composition(value.composition_id)
        if composition is None or composition.opportunity_identity != value.opportunity_identity:
            raise ValueError("normalization composition source is missing or mismatched")
        for source, result in zip(composition.components, value.components, strict=True):
            if (
                source.kind is not result.kind
                or source.availability is not result.original_availability
                or source.amount != result.original_amount
                or source.currency != result.original_currency
                or source.allocation_basis is not result.original_allocation_basis
            ):
                raise ValueError("normalized component differs from exact composition")
            if result.allocation_authority_id is not None:
                authority = self.get_allocation_authority(
                    result.allocation_authority_id
                )
                if (
                    authority is None
                    or authority.composition_id != value.composition_id
                    or authority.opportunity_identity != value.opportunity_identity
                    or authority.component_kind is not result.kind
                    or authority.allocation_basis
                    is not result.effective_allocation_basis
                    or (None if authority.denominator is None else authority.denominator.quantity)
                    != result.denominator_quantity
                    or (None if authority.denominator is None else authority.denominator.source)
                    != result.denominator_source
                ):
                    raise ValueError("normalized allocation source is mismatched")
            if result.fx_observation_id is not None:
                observation = self.get_fx_observation(result.fx_observation_id)
                if observation is None:
                    raise ValueError("normalized FX source is missing")
                if result.fx_direction is FXConversionDirection.DIRECT:
                    pair = (observation.base_currency, observation.quote_currency)
                elif result.fx_direction is FXConversionDirection.INVERSE:
                    pair = (observation.quote_currency, observation.base_currency)
                else:
                    raise ValueError("normalized FX direction is malformed")
                if pair != (result.original_currency, value.target_currency):
                    raise ValueError("normalized FX pair is mismatched")

    def _validate_write(self, command, normalization, receipt) -> None:
        if not isinstance(command, NormalizeAcquisitionCostsCommand):
            raise TypeError("command must be NormalizeAcquisitionCostsCommand")
        if not isinstance(normalization, AcquisitionCostNormalization):
            raise TypeError("normalization must be AcquisitionCostNormalization")
        if not isinstance(receipt, AcquisitionCostNormalizationReceipt):
            raise TypeError("receipt must be AcquisitionCostNormalizationReceipt")
        if (
            command.command_id != receipt.command_id
            or command.fingerprint != receipt.command_fingerprint
            or normalization.normalization_id != receipt.normalization_id
            or command.opportunity_identity != normalization.opportunity_identity
            or command.composition_id != normalization.composition_id
            or command.allocation_authority_ids
            != normalization.allocation_authority_ids
            or command.fx_observation_ids != normalization.fx_observation_ids
            or command.target_currency != normalization.target_currency
            or command.requested_at != normalization.requested_at
            or command.policy_name != normalization.policy_name
            or command.policy_version != normalization.policy_version
        ):
            raise AcquisitionCostNormalizationReplayConflictError(
                "command, normalization, and receipt do not match"
            )
        self._validate_sources(normalization)

    def save_normalization(self, command, normalization, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            self._validate_write(command, normalization, receipt)
            encoded = _payload(normalization)
            try:
                self._connection.execute(
                    f"""INSERT INTO {HISTORY_TABLE}(
                        normalization_id,opportunity_id,discovery_reference,
                        composition_id,target_currency,payload_json,
                        integrity_fingerprint,schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?,?,?,?)""",
                    (
                        normalization.normalization_id,
                        normalization.opportunity_identity.opportunity_id,
                        normalization.opportunity_identity.discovery_reference,
                        normalization.composition_id,
                        normalization.target_currency,
                        encoded,
                        _integrity(encoded),
                        normalization.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise AcquisitionCostNormalizationHistoryError(
                    "acquisition normalization insert failed"
                ) from error
            try:
                self._connection.execute(
                    f"""INSERT INTO {RECEIPT_TABLE}(
                        command_id,normalization_id,command_fingerprint,
                        committed_at,schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?)""",
                    (
                        receipt.command_id,
                        receipt.normalization_id,
                        receipt.command_fingerprint,
                        receipt.committed_at.isoformat(),
                        receipt.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise AcquisitionCostNormalizationReceiptError(
                    "acquisition normalization receipt insert failed"
                ) from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise AcquisitionCostNormalizationCommitError(
                    "acquisition normalization commit failed"
                ) from error
            return AcquisitionCostNormalizationResult(normalization, receipt, False)
        except AcquisitionCostNormalizationReplayConflictError:
            self._rollback()
            raise
        except AcquisitionCostNormalizationPersistenceError:
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
    "AcquisitionCostNormalizationCommitError",
    "AcquisitionCostNormalizationHistoryError",
    "AcquisitionCostNormalizationPersistenceError",
    "AcquisitionCostNormalizationReceiptError",
    "HISTORY_TABLE",
    "MalformedAcquisitionCostNormalizationPersistenceError",
    "RECEIPT_TABLE",
    "SQLiteAcquisitionCostNormalizationRepository",
    "UnsupportedAcquisitionCostNormalizationVersionError",
]
