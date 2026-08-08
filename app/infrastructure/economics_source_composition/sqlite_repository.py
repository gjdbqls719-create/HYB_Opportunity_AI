"""Append-only SQLite persistence for authoritative Economics source manifests."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.economics_source_composition import (
    ECONOMICS_SOURCE_COMPOSITION_RECEIPT_SCHEMA_VERSION,
    ComposeEconomicsSourcesCommand,
    EconomicsSourceCompositionReceipt,
    EconomicsSourceCompositionReplayConflictError,
    EconomicsSourceCompositionResult,
)
from app.application.verified_economics_snapshot import VerifiedEconomicsSnapshot
from app.domain.decision_engine import OpportunityIdentity
from app.domain.opportunity import (
    ECONOMICS_SOURCE_COMPOSITION_SCHEMA_VERSION,
    EconomicEvidence,
    EconomicsSourceBlockingCode,
    EconomicsSourceBlockingReason,
    EconomicsSourceComposition,
    EconomicsSourceCompositionState,
    EvidenceStatus,
    MoneyInput,
    RateInput,
    VerifiedEconomicsInput,
)
from app.infrastructure.sourcing import SQLiteAcquisitionCostNormalizationRepository


HISTORY_TABLE = "economics_source_composition_history"
RECEIPT_TABLE = "economics_source_composition_receipts"


class EconomicsSourceCompositionPersistenceError(RuntimeError):
    pass


class EconomicsSourceCompositionHistoryError(
    EconomicsSourceCompositionPersistenceError
):
    pass


class EconomicsSourceCompositionReceiptError(
    EconomicsSourceCompositionPersistenceError
):
    pass


class EconomicsSourceCompositionCommitError(
    EconomicsSourceCompositionPersistenceError
):
    pass


class MalformedEconomicsSourceCompositionPersistenceError(
    EconomicsSourceCompositionPersistenceError
):
    pass


class UnsupportedEconomicsSourceCompositionVersionError(
    MalformedEconomicsSourceCompositionPersistenceError
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


def _evidence(value: EconomicEvidence) -> dict[str, object]:
    return {
        "status": value.status.value,
        "source": value.source,
        "observed_at": (
            None if value.observed_at is None else value.observed_at.isoformat()
        ),
        "reference": value.reference,
    }


def _load_evidence(value: object) -> EconomicEvidence:
    if not isinstance(value, dict) or set(value) != {
        "status",
        "source",
        "observed_at",
        "reference",
    }:
        raise ValueError("Economic evidence is malformed")
    observed_at = value["observed_at"]
    return EconomicEvidence(
        status=EvidenceStatus(value["status"]),
        source=value["source"],
        observed_at=(
            None if observed_at is None else _datetime(observed_at, "observed_at")
        ),
        reference=value["reference"],
    )


def _money(value: MoneyInput) -> dict[str, object]:
    return {
        "amount": None if value.amount is None else str(value.amount),
        "currency": value.currency,
        "evidence": _evidence(value.evidence),
    }


def _load_money(value: object) -> MoneyInput:
    if not isinstance(value, dict) or set(value) != {
        "amount",
        "currency",
        "evidence",
    }:
        raise ValueError("money source is malformed")
    amount = value["amount"]
    return MoneyInput(
        None if amount is None else Decimal(str(amount)),
        value["currency"],
        _load_evidence(value["evidence"]),
    )


def _rate(value: RateInput) -> dict[str, object]:
    return {
        "rate": None if value.rate is None else str(value.rate),
        "evidence": _evidence(value.evidence),
    }


def _load_rate(value: object) -> RateInput:
    if not isinstance(value, dict) or set(value) != {"rate", "evidence"}:
        raise ValueError("rate source is malformed")
    rate = value["rate"]
    return RateInput(
        None if rate is None else Decimal(str(rate)),
        _load_evidence(value["evidence"]),
    )


def _reason(value: EconomicsSourceBlockingReason) -> dict[str, object]:
    return {
        "code": value.code.value,
        "category": value.category,
        "source_reference": value.source_reference,
    }


def _load_reason(value: object) -> EconomicsSourceBlockingReason:
    if not isinstance(value, dict) or set(value) != {
        "code",
        "category",
        "source_reference",
    }:
        raise ValueError("blocking reason is malformed")
    return EconomicsSourceBlockingReason(
        EconomicsSourceBlockingCode(value["code"]),
        value["category"],
        value["source_reference"],
    )


_PAYLOAD_KEYS = {
    "composition_id",
    "opportunity_identity",
    "acquisition_normalization_id",
    "acquisition_policy_name",
    "acquisition_policy_version",
    "acquisition_cost_per_unit",
    "economics_currency",
    "verified_economics_opportunity_id",
    "verified_economics_snapshot_at",
    "verified_economics_schema_version",
    "expected_sale_price",
    "marketplace_fee_rate",
    "payment_fee_rate",
    "fixed_fee",
    "tax_rate",
    "duty_cost",
    "other_cost",
    "state",
    "blocking_reasons",
    "policy_name",
    "policy_version",
    "requested_at",
    "composed_at",
    "schema_version",
}


def _payload(value: EconomicsSourceComposition) -> str:
    return _dump(
        {
            "composition_id": value.composition_id,
            "opportunity_identity": {
                "opportunity_id": value.opportunity_identity.opportunity_id,
                "discovery_reference": value.opportunity_identity.discovery_reference,
            },
            "acquisition_normalization_id": value.acquisition_normalization_id,
            "acquisition_policy_name": value.acquisition_policy_name,
            "acquisition_policy_version": value.acquisition_policy_version,
            "acquisition_cost_per_unit": str(value.acquisition_cost_per_unit),
            "economics_currency": value.economics_currency,
            "verified_economics_opportunity_id": value.verified_economics_opportunity_id,
            "verified_economics_snapshot_at": value.verified_economics_snapshot_at.isoformat(),
            "verified_economics_schema_version": value.verified_economics_schema_version,
            "expected_sale_price": _money(value.expected_sale_price),
            "marketplace_fee_rate": _rate(value.marketplace_fee_rate),
            "payment_fee_rate": _rate(value.payment_fee_rate),
            "fixed_fee": _money(value.fixed_fee),
            "tax_rate": _rate(value.tax_rate),
            "duty_cost": _money(value.duty_cost),
            "other_cost": _money(value.other_cost),
            "state": value.state.value,
            "blocking_reasons": [
                _reason(reason) for reason in value.blocking_reasons
            ],
            "policy_name": value.policy_name,
            "policy_version": value.policy_version,
            "requested_at": value.requested_at.isoformat(),
            "composed_at": value.composed_at.isoformat(),
            "schema_version": value.schema_version,
        }
    )


class SQLiteEconomicsSourceCompositionRepository:
    """Persists exact source manifests without latest selection or calculation."""

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
        self._normalizations = SQLiteAcquisitionCostNormalizationRepository(
            connection=self._connection
        )
        self._initialize_schema()

    def _initialize_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {HISTORY_TABLE}(
                    composition_id TEXT PRIMARY KEY,
                    opportunity_id TEXT NOT NULL,
                    discovery_reference TEXT NOT NULL,
                    acquisition_normalization_id TEXT NOT NULL,
                    verified_economics_opportunity_id TEXT NOT NULL,
                    economics_currency TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    integrity_fingerprint TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(acquisition_normalization_id) REFERENCES
                      acquisition_cost_normalization_history(normalization_id),
                    FOREIGN KEY(verified_economics_opportunity_id) REFERENCES
                      verified_economics_snapshots(opportunity_id)
                )"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE}(
                    command_id TEXT PRIMARY KEY,
                    composition_id TEXT NOT NULL,
                    command_fingerprint TEXT NOT NULL,
                    committed_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    inserted_at TEXT NOT NULL,
                    FOREIGN KEY(composition_id) REFERENCES
                      {HISTORY_TABLE}(composition_id)
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

    def get_normalization(self, normalization_id: str):
        return self._normalizations.get_normalization(normalization_id)

    def get_verified_economics_snapshot(self, opportunity_id: str):
        try:
            row = self._connection.execute(
                "SELECT * FROM verified_economics_snapshots WHERE opportunity_id=?",
                (opportunity_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise EconomicsSourceCompositionHistoryError(
                "Verified Economics source query failed"
            ) from error
        if row is None:
            return None
        try:
            evidence_payload = json.loads(row["evidence_metadata"])

            def evidence(name: str) -> EconomicEvidence:
                value = evidence_payload[name]
                return _load_evidence(value)

            def amount(name: str) -> Decimal | None:
                value = row[name]
                return None if value is None else Decimal(value)

            currency = row["currency"]
            inputs = VerifiedEconomicsInput(
                purchase_cost=MoneyInput(
                    amount("purchase_cost"), currency, evidence("purchase_cost")
                ),
                shipping_cost=MoneyInput(
                    amount("shipping_cost"), currency, evidence("shipping_cost")
                ),
                marketplace_fee_rate=RateInput(
                    amount("marketplace_fee_rate"), evidence("marketplace_fee_rate")
                ),
                payment_fee_rate=RateInput(
                    amount("payment_fee_rate"), evidence("payment_fee_rate")
                ),
                fixed_fee=MoneyInput(
                    amount("fixed_fee"), currency, evidence("fixed_fee")
                ),
                tax_rate=RateInput(amount("tax_rate"), evidence("tax_rate")),
                duty_cost=MoneyInput(
                    amount("duty_cost"), currency, evidence("duty_cost")
                ),
                other_cost=MoneyInput(
                    amount("other_cost"), currency, evidence("other_cost")
                ),
                expected_sale_price=MoneyInput(
                    amount("expected_sale_price"),
                    currency,
                    evidence("expected_sale_price"),
                ),
            )
            return VerifiedEconomicsSnapshot(
                row["opportunity_id"],
                inputs,
                _datetime(row["snapshot_at"], "snapshot_at"),
                row["schema_version"],
            )
        except Exception as error:
            raise MalformedEconomicsSourceCompositionPersistenceError(
                "persisted Verified Economics source is malformed"
            ) from error

    def _history_row(self, composition_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {HISTORY_TABLE} WHERE composition_id=?",
                (composition_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise EconomicsSourceCompositionHistoryError(
                "Economics source composition query failed"
            ) from error

    def _load_composition(self, row) -> EconomicsSourceComposition:
        try:
            if row["schema_version"] != ECONOMICS_SOURCE_COMPOSITION_SCHEMA_VERSION:
                raise UnsupportedEconomicsSourceCompositionVersionError(
                    "unsupported Economics source composition version"
                )
            encoded = row["payload_json"]
            if (
                not isinstance(encoded, str)
                or _integrity(encoded) != row["integrity_fingerprint"]
            ):
                raise ValueError("composition integrity fingerprint mismatch")
            payload = json.loads(encoded)
            if not isinstance(payload, dict) or set(payload) != _PAYLOAD_KEYS:
                raise ValueError("composition payload has unsupported fields")
            if payload["schema_version"] != row["schema_version"]:
                raise ValueError("composition payload version differs")
            opportunity = payload["opportunity_identity"]
            if not isinstance(opportunity, dict) or set(opportunity) != {
                "opportunity_id",
                "discovery_reference",
            }:
                raise ValueError("Opportunity identity is malformed")
            value = EconomicsSourceComposition(
                composition_id=payload["composition_id"],
                opportunity_identity=OpportunityIdentity(
                    opportunity["opportunity_id"],
                    opportunity["discovery_reference"],
                ),
                acquisition_normalization_id=payload[
                    "acquisition_normalization_id"
                ],
                acquisition_policy_name=payload["acquisition_policy_name"],
                acquisition_policy_version=payload["acquisition_policy_version"],
                acquisition_cost_per_unit=Decimal(
                    str(payload["acquisition_cost_per_unit"])
                ),
                economics_currency=payload["economics_currency"],
                verified_economics_opportunity_id=payload[
                    "verified_economics_opportunity_id"
                ],
                verified_economics_snapshot_at=_datetime(
                    payload["verified_economics_snapshot_at"],
                    "verified_economics_snapshot_at",
                ),
                verified_economics_schema_version=payload[
                    "verified_economics_schema_version"
                ],
                expected_sale_price=_load_money(payload["expected_sale_price"]),
                marketplace_fee_rate=_load_rate(payload["marketplace_fee_rate"]),
                payment_fee_rate=_load_rate(payload["payment_fee_rate"]),
                fixed_fee=_load_money(payload["fixed_fee"]),
                tax_rate=_load_rate(payload["tax_rate"]),
                duty_cost=_load_money(payload["duty_cost"]),
                other_cost=_load_money(payload["other_cost"]),
                state=EconomicsSourceCompositionState(payload["state"]),
                blocking_reasons=tuple(
                    _load_reason(reason) for reason in payload["blocking_reasons"]
                ),
                policy_name=payload["policy_name"],
                policy_version=payload["policy_version"],
                requested_at=_datetime(payload["requested_at"], "requested_at"),
                composed_at=_datetime(payload["composed_at"], "composed_at"),
                schema_version=payload["schema_version"],
            )
            if (
                value.composition_id != row["composition_id"]
                or value.opportunity_identity.opportunity_id != row["opportunity_id"]
                or value.opportunity_identity.discovery_reference
                != row["discovery_reference"]
                or value.acquisition_normalization_id
                != row["acquisition_normalization_id"]
                or value.verified_economics_opportunity_id
                != row["verified_economics_opportunity_id"]
                or value.economics_currency != row["economics_currency"]
            ):
                raise ValueError("composition columns differ from payload")
            self._validate_sources(value)
            return value
        except UnsupportedEconomicsSourceCompositionVersionError:
            raise
        except Exception as error:
            if isinstance(error, MalformedEconomicsSourceCompositionPersistenceError):
                raise
            raise MalformedEconomicsSourceCompositionPersistenceError(
                "persisted Economics source composition is malformed"
            ) from error

    def get_composition(self, composition_id: str):
        row = self._history_row(composition_id)
        return None if row is None else self._load_composition(row)

    def _receipt_row(self, command_id: str):
        try:
            return self._connection.execute(
                f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?",
                (command_id,),
            ).fetchone()
        except sqlite3.Error as error:
            raise EconomicsSourceCompositionReceiptError(
                "Economics source composition receipt query failed"
            ) from error

    def _load_receipt(self, row):
        try:
            if (
                row["schema_version"]
                != ECONOMICS_SOURCE_COMPOSITION_RECEIPT_SCHEMA_VERSION
            ):
                raise UnsupportedEconomicsSourceCompositionVersionError(
                    "unsupported Economics source composition receipt version"
                )
            value = EconomicsSourceCompositionReceipt(
                row["command_id"],
                row["composition_id"],
                row["command_fingerprint"],
                _datetime(row["committed_at"], "committed_at"),
                row["schema_version"],
            )
            if self.get_composition(value.composition_id) is None:
                raise ValueError("receipt references missing composition")
            return value
        except Exception as error:
            if isinstance(error, MalformedEconomicsSourceCompositionPersistenceError):
                raise
            raise MalformedEconomicsSourceCompositionPersistenceError(
                "persisted Economics source receipt is malformed"
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
            raise EconomicsSourceCompositionReplayConflictError(
                "Economics source composition command payload conflicts"
            )
        composition = self.get_composition(receipt.composition_id)
        if composition is None:
            raise MalformedEconomicsSourceCompositionPersistenceError(
                "receipt references missing composition"
            )
        return EconomicsSourceCompositionResult(composition, receipt, True)

    def _validate_sources(self, value: EconomicsSourceComposition) -> None:
        normalization = self.get_normalization(value.acquisition_normalization_id)
        if (
            normalization is None
            or normalization.opportunity_identity != value.opportunity_identity
            or normalization.policy_name != value.acquisition_policy_name
            or normalization.policy_version != value.acquisition_policy_version
            or normalization.total_per_unit_acquisition_cost
            != value.acquisition_cost_per_unit
            or normalization.target_currency != value.economics_currency
        ):
            raise ValueError("acquisition normalization source differs")
        verified = self.get_verified_economics_snapshot(
            value.verified_economics_opportunity_id
        )
        if (
            verified is None
            or verified.opportunity_id != value.opportunity_identity.opportunity_id
            or verified.snapshot_at != value.verified_economics_snapshot_at
            or verified.schema_version != value.verified_economics_schema_version
        ):
            raise ValueError("Verified Economics exact source differs")
        inputs = verified.inputs
        if (
            value.expected_sale_price != inputs.expected_sale_price
            or value.marketplace_fee_rate != inputs.marketplace_fee_rate
            or value.payment_fee_rate != inputs.payment_fee_rate
            or value.fixed_fee != inputs.fixed_fee
            or value.tax_rate != inputs.tax_rate
            or value.duty_cost != inputs.duty_cost
            or value.other_cost != inputs.other_cost
        ):
            raise ValueError("sale-side facts differ from exact source")

    def _validate_write(self, command, composition, receipt) -> None:
        if not isinstance(command, ComposeEconomicsSourcesCommand):
            raise TypeError("command must be ComposeEconomicsSourcesCommand")
        if not isinstance(composition, EconomicsSourceComposition):
            raise TypeError("composition must be EconomicsSourceComposition")
        if not isinstance(receipt, EconomicsSourceCompositionReceipt):
            raise TypeError("receipt must be EconomicsSourceCompositionReceipt")
        if (
            command.command_id != receipt.command_id
            or command.fingerprint != receipt.command_fingerprint
            or composition.composition_id != receipt.composition_id
            or command.opportunity_identity != composition.opportunity_identity
            or command.acquisition_normalization_id
            != composition.acquisition_normalization_id
            or command.verified_economics_opportunity_id
            != composition.verified_economics_opportunity_id
            or command.verified_economics_snapshot_at
            != composition.verified_economics_snapshot_at
            or command.verified_economics_schema_version
            != composition.verified_economics_schema_version
            or command.requested_at != composition.requested_at
            or command.policy_name != composition.policy_name
            or command.policy_version != composition.policy_version
        ):
            raise EconomicsSourceCompositionReplayConflictError(
                "command, composition, and receipt do not match"
            )
        self._validate_sources(composition)

    def save_composition(self, command, composition, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._commit()
                return replay
            self._validate_write(command, composition, receipt)
            encoded = _payload(composition)
            try:
                self._connection.execute(
                    f"""INSERT INTO {HISTORY_TABLE}(
                        composition_id,opportunity_id,discovery_reference,
                        acquisition_normalization_id,
                        verified_economics_opportunity_id,economics_currency,
                        payload_json,integrity_fingerprint,schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (
                        composition.composition_id,
                        composition.opportunity_identity.opportunity_id,
                        composition.opportunity_identity.discovery_reference,
                        composition.acquisition_normalization_id,
                        composition.verified_economics_opportunity_id,
                        composition.economics_currency,
                        encoded,
                        _integrity(encoded),
                        composition.schema_version,
                        receipt.committed_at.isoformat(),
                    ),
                )
            except sqlite3.Error as error:
                raise EconomicsSourceCompositionHistoryError(
                    "Economics source composition insert failed"
                ) from error
            try:
                self._connection.execute(
                    f"""INSERT INTO {RECEIPT_TABLE}(
                        command_id,composition_id,command_fingerprint,
                        committed_at,schema_version,inserted_at
                    ) VALUES(?,?,?,?,?,?)""",
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
                raise EconomicsSourceCompositionReceiptError(
                    "Economics source composition receipt insert failed"
                ) from error
            try:
                self._commit()
            except sqlite3.Error as error:
                raise EconomicsSourceCompositionCommitError(
                    "Economics source composition commit failed"
                ) from error
            return EconomicsSourceCompositionResult(composition, receipt, False)
        except EconomicsSourceCompositionReplayConflictError:
            self._rollback()
            raise
        except EconomicsSourceCompositionPersistenceError:
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
    "EconomicsSourceCompositionCommitError",
    "EconomicsSourceCompositionHistoryError",
    "EconomicsSourceCompositionPersistenceError",
    "EconomicsSourceCompositionReceiptError",
    "HISTORY_TABLE",
    "MalformedEconomicsSourceCompositionPersistenceError",
    "RECEIPT_TABLE",
    "SQLiteEconomicsSourceCompositionRepository",
    "UnsupportedEconomicsSourceCompositionVersionError",
]
