"""Atomic SQLite persistence for domestic-selling Opportunity admission."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.domestic_selling_opportunity import (
    DOMESTIC_SELLING_OPPORTUNITY_RECEIPT_SCHEMA_VERSION,
    AdmitDomesticSellingOpportunity,
    DomesticSellingOpportunityAdmissionPublication,
    DomesticSellingOpportunityAdmissionReceipt,
    DomesticSellingOpportunityCardinalityConflictError,
    DomesticSellingOpportunityReplayConflictError,
)
from app.application.opportunity_market_identity import OpportunityMarketIdentityBinding
from app.domain.decision_engine import OpportunityIdentity
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.domain.opportunity import (
    DOMESTIC_PRODUCT_EQUIVALENCE_SCHEMA_VERSION,
    DOMESTIC_SELLING_OPPORTUNITY_ADMISSION_SCHEMA_VERSION,
    DomesticProductEquivalenceVerification,
    DomesticSellingOpportunityAdmission,
    OpportunityLifecycle,
    OpportunityLifecycleAction,
    OpportunityLifecycleStatus,
    OpportunityLifecycleTransition,
)
from app.infrastructure.opportunity_validation import SQLiteCandidatePromotionRepository
from app.infrastructure.product_observation import SQLiteProductObservationSnapshotRepository


HISTORY_TABLE = "domestic_selling_opportunity_admission_history"
RECEIPT_TABLE = "domestic_selling_opportunity_admission_receipts"


class DomesticSellingOpportunityPersistenceError(RuntimeError):
    pass


class DomesticSellingOpportunityHistoryError(DomesticSellingOpportunityPersistenceError):
    pass


class DomesticSellingOpportunityReceiptError(DomesticSellingOpportunityPersistenceError):
    pass


class DomesticSellingOpportunityCommitError(DomesticSellingOpportunityPersistenceError):
    pass


class MalformedDomesticSellingOpportunityPersistenceError(
    DomesticSellingOpportunityPersistenceError
):
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


def _identity_payload(value: MarketObservationIdentity) -> dict[str, object]:
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


def _identity(value: object) -> MarketObservationIdentity:
    if not isinstance(value, dict):
        raise ValueError("Market identity payload must be an object")
    expected = {
        "scope", "market", "marketplace", "canonical_product_id",
        "marketplace_item_id", "normalized_query", "category",
        "variant_identity", "condition", "window_started_at", "window_ended_at",
    }
    if set(value) != expected:
        raise ValueError("Market identity payload has unsupported fields")
    return MarketObservationIdentity(
        scope=MarketObservationScope(value["scope"]),
        market=value["market"],
        marketplace=value["marketplace"],
        canonical_product_id=value["canonical_product_id"],
        marketplace_item_id=value["marketplace_item_id"],
        normalized_query=value["normalized_query"],
        category=value["category"],
        variant_identity=value["variant_identity"],
        condition=value["condition"],
        window_started_at=_datetime(value["window_started_at"], "window_started_at"),
        window_ended_at=_datetime(value["window_ended_at"], "window_ended_at"),
    )


def _admission_payload(value: DomesticSellingOpportunityAdmission) -> str:
    return _dump({
        "admission_id": value.admission_id,
        "source_opportunity_identity": {
            "opportunity_id": value.source_opportunity_identity.opportunity_id,
            "discovery_reference": value.source_opportunity_identity.discovery_reference,
        },
        "source_lifecycle_status": value.source_lifecycle_status.value,
        "source_lifecycle_version": value.source_lifecycle_version,
        "domestic_opportunity_identity": {
            "opportunity_id": value.domestic_opportunity_identity.opportunity_id,
            "discovery_reference": value.domestic_opportunity_identity.discovery_reference,
        },
        "source_candidate_id": value.source_candidate_id,
        "source_candidate_opportunity_binding_id": value.source_candidate_opportunity_binding_id,
        "source_promotion_command_id": value.source_promotion_command_id,
        "source_product_snapshot_id": value.source_product_snapshot_id,
        "source_market_identity": _identity_payload(value.source_market_identity),
        "domestic_market_identity": _identity_payload(value.domestic_market_identity),
        "product_equivalence": {
            "operator_id": value.product_equivalence.operator_id,
            "verified_at": value.product_equivalence.verified_at.isoformat(),
            "evidence_reference": value.product_equivalence.evidence_reference,
            "confirmed": value.product_equivalence.confirmed,
            "schema_version": value.product_equivalence.schema_version,
        },
        "policy_name": value.policy_name,
        "policy_version": value.policy_version,
        "requested_at": value.requested_at.isoformat(),
        "admitted_at": value.admitted_at.isoformat(),
        "schema_version": value.schema_version,
    })


class SQLiteDomesticSellingOpportunityAdmissionRepository(
    SQLiteCandidatePromotionRepository
):
    def __init__(
        self,
        database_path: str | Path = "data/hyb_opportunity.db",
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        super().__init__(database_path, connection=connection)
        self._products = SQLiteProductObservationSnapshotRepository(
            connection=self._connection
        )
        self.source_read_count = 0
        self._initialize_domestic_schema()

    def _initialize_domestic_schema(self) -> None:
        with self._connection:
            self._connection.execute(f"""CREATE TABLE IF NOT EXISTS {HISTORY_TABLE}(
                admission_id TEXT PRIMARY KEY,
                source_opportunity_id TEXT NOT NULL UNIQUE,
                domestic_opportunity_id TEXT NOT NULL UNIQUE,
                source_product_snapshot_id TEXT NOT NULL,
                policy_name TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                integrity_fingerprint TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL,
                FOREIGN KEY(source_opportunity_id) REFERENCES opportunity_lifecycles(opportunity_id),
                FOREIGN KEY(domestic_opportunity_id) REFERENCES opportunity_lifecycles(opportunity_id),
                FOREIGN KEY(source_product_snapshot_id) REFERENCES product_observation_snapshot_history(snapshot_id)
            )""")
            self._connection.execute(f"""CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE}(
                command_id TEXT PRIMARY KEY,
                admission_id TEXT NOT NULL,
                domestic_opportunity_id TEXT NOT NULL,
                command_fingerprint TEXT NOT NULL,
                committed_at TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                integrity_fingerprint TEXT NOT NULL,
                inserted_at TEXT NOT NULL,
                FOREIGN KEY(admission_id) REFERENCES {HISTORY_TABLE}(admission_id),
                FOREIGN KEY(domestic_opportunity_id) REFERENCES opportunity_lifecycles(opportunity_id)
            )""")
            for table in (HISTORY_TABLE, RECEIPT_TABLE):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(f"""CREATE TRIGGER IF NOT EXISTS
                        trg_{table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END""")

    def get_source_lifecycle(self, opportunity_id):
        self.source_read_count += 1
        return self._lifecycles.get(opportunity_id)

    def get_candidate_promotion(self, opportunity_id):
        self.source_read_count += 1
        return self.get_promotion_by_opportunity(opportunity_id)

    def get_product_snapshot(self, snapshot_id):
        self.source_read_count += 1
        return self._products.get_snapshot(snapshot_id)

    def get_market_identity_binding(self, opportunity_id):
        self.source_read_count += 1
        return super().get_market_identity_binding(opportunity_id)

    def validate_replay(self, command_id, fingerprint):
        row = self._connection.execute(
            f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?", (command_id,)
        ).fetchone()
        if row is None:
            return None
        self._validate_receipt_integrity(row)
        if row["command_fingerprint"] != fingerprint:
            raise DomesticSellingOpportunityReplayConflictError(
                "domestic selling command payload conflicts"
            )
        return self._publication(row["admission_id"], receipt_row=row)

    def get_admission_by_source(self, opportunity_id):
        row = self._connection.execute(
            f"SELECT admission_id FROM {HISTORY_TABLE} WHERE source_opportunity_id=?",
            (opportunity_id,),
        ).fetchone()
        return None if row is None else self._publication(row["admission_id"])

    def get_admission(self, admission_id):
        row = self._connection.execute(
            f"SELECT admission_id FROM {HISTORY_TABLE} WHERE admission_id=?",
            (admission_id,),
        ).fetchone()
        return None if row is None else self._publication(row["admission_id"])

    def save_admission(self, command, lifecycle, transition, market_binding, admission, receipt):
        candidate = DomesticSellingOpportunityAdmissionPublication(
            lifecycle, transition, market_binding, admission, receipt, False
        )
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._connection.rollback()
                return DomesticSellingOpportunityAdmissionPublication(
                    replay.lifecycle, replay.creation_transition, replay.market_binding,
                    replay.admission, replay.receipt, True,
                )
            source = self._lifecycles.get(command.source_opportunity_id)
            promotion = self.get_promotion_by_opportunity(command.source_opportunity_id)
            snapshot = self._products.get_snapshot(command.source_product_snapshot_id)
            source_binding = super().get_market_identity_binding(command.source_opportunity_id)
            if None in (source, promotion, snapshot, source_binding):
                raise DomesticSellingOpportunityHistoryError(
                    "authoritative source publication is incomplete"
                )
            AdmitDomesticSellingOpportunity._validate_source(
                command, source, promotion, snapshot, source_binding
            )
            existing = self._connection.execute(
                f"SELECT 1 FROM {HISTORY_TABLE} WHERE source_opportunity_id=?",
                (command.source_opportunity_id,),
            ).fetchone()
            if existing is not None:
                raise DomesticSellingOpportunityCardinalityConflictError(
                    "source Opportunity already has a domestic-selling Opportunity"
                )
            self._write("lifecycle", self._lifecycles._insert_current, lifecycle)
            self._write("transition", self._lifecycles._insert_transition, transition)
            self._write("market", self._insert_market_identity_binding, market_binding)
            self._write("admission", self._insert_admission, admission)
            self._write("receipt", self._insert_domestic_receipt, receipt)
            try:
                self._commit()
            except sqlite3.Error as error:
                raise DomesticSellingOpportunityCommitError(
                    "domestic selling admission commit failed"
                ) from error
            return candidate
        except sqlite3.IntegrityError as error:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise DomesticSellingOpportunityCardinalityConflictError(
                "domestic selling Opportunity cardinality conflicts"
            ) from error
        except sqlite3.Error as error:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise DomesticSellingOpportunityHistoryError(
                "domestic selling admission history insert failed"
            ) from error
        except Exception:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise

    def _write(self, phase, operation, value):
        try:
            operation(value)
        except sqlite3.Error as error:
            if phase == "receipt":
                raise DomesticSellingOpportunityReceiptError(
                    "domestic selling receipt insert failed"
                ) from error
            raise DomesticSellingOpportunityHistoryError(
                f"domestic selling {phase} insert failed"
            ) from error

    def _commit(self):
        self._connection.commit()

    def _insert_admission(self, admission):
        payload = _admission_payload(admission)
        self._connection.execute(
            f"INSERT INTO {HISTORY_TABLE} VALUES(?,?,?,?,?,?,?,?,?,?)",
            (
                admission.admission_id,
                admission.source_opportunity_identity.opportunity_id,
                admission.domestic_opportunity_identity.opportunity_id,
                admission.source_product_snapshot_id,
                admission.policy_name,
                admission.policy_version,
                payload,
                _integrity(payload),
                admission.schema_version,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    def _insert_domestic_receipt(self, receipt):
        payload = _dump({
            "command_id": receipt.command_id,
            "admission_id": receipt.admission_id,
            "domestic_opportunity_id": receipt.domestic_opportunity_id,
            "command_fingerprint": receipt.command_fingerprint,
            "committed_at": receipt.committed_at.isoformat(),
            "schema_version": receipt.schema_version,
        })
        self._connection.execute(
            f"INSERT INTO {RECEIPT_TABLE} VALUES(?,?,?,?,?,?,?,?)",
            (
                receipt.command_id, receipt.admission_id,
                receipt.domestic_opportunity_id, receipt.command_fingerprint,
                receipt.committed_at.isoformat(), receipt.schema_version,
                _integrity(payload), datetime.now(timezone.utc).isoformat(),
            ),
        )

    def _publication(self, admission_id, *, receipt_row=None):
        row = self._connection.execute(
            f"SELECT * FROM {HISTORY_TABLE} WHERE admission_id=?", (admission_id,)
        ).fetchone()
        if row is None:
            raise MalformedDomesticSellingOpportunityPersistenceError(
                "receipt references missing domestic selling admission"
            )
        try:
            payload = row["payload_json"]
            if _integrity(payload) != row["integrity_fingerprint"]:
                raise ValueError("admission integrity fingerprint mismatch")
            data = json.loads(payload)
            admission = self._load_admission(data)
            if (
                admission.admission_id != row["admission_id"]
                or admission.source_opportunity_identity.opportunity_id != row["source_opportunity_id"]
                or admission.domestic_opportunity_identity.opportunity_id != row["domestic_opportunity_id"]
                or admission.source_product_snapshot_id != row["source_product_snapshot_id"]
                or admission.policy_name != row["policy_name"]
                or admission.policy_version != row["policy_version"]
                or admission.schema_version != row["schema_version"]
            ):
                raise ValueError("admission columns differ from payload")
            lifecycle_row = self._connection.execute(
                "SELECT * FROM opportunity_lifecycles WHERE opportunity_id=?",
                (admission.domestic_opportunity_identity.opportunity_id,),
            ).fetchone()
            transition_row = self._connection.execute(
                "SELECT * FROM opportunity_lifecycle_transitions WHERE opportunity_id=? AND version=1",
                (admission.domestic_opportunity_identity.opportunity_id,),
            ).fetchone()
            if lifecycle_row is None or transition_row is None:
                raise ValueError("domestic Opportunity lifecycle is missing")
            if (
                lifecycle_row["discovery_reference"] != admission.domestic_opportunity_identity.discovery_reference
                or lifecycle_row["status"] != OpportunityLifecycleStatus.DISCOVERED.value
                or lifecycle_row["version"] != 1
            ):
                raise ValueError("domestic Opportunity lifecycle is malformed")
            lifecycle = OpportunityLifecycle._reconstitute(
                opportunity_id=lifecycle_row["opportunity_id"],
                discovery_reference=lifecycle_row["discovery_reference"],
                status=OpportunityLifecycleStatus(lifecycle_row["status"]),
                version=lifecycle_row["version"],
                created_at=_datetime(lifecycle_row["created_at"], "created_at"),
                updated_at=_datetime(lifecycle_row["updated_at"], "updated_at"),
                archived_at=None, archived_by=None, archive_reason=None,
            )
            transition = OpportunityLifecycleTransition(
                transition_id=transition_row["transition_id"],
                opportunity_id=transition_row["opportunity_id"],
                action=OpportunityLifecycleAction(transition_row["action"]),
                previous_status=OpportunityLifecycleStatus(transition_row["previous_status"]),
                new_status=OpportunityLifecycleStatus(transition_row["new_status"]),
                version=transition_row["version"],
                occurred_at=_datetime(transition_row["occurred_at"], "occurred_at"),
                operator_id=transition_row["operator_id"], reason=transition_row["reason"],
                note=transition_row["note"], founder_decision_id=transition_row["founder_decision_id"],
            )
            binding = super().get_market_identity_binding(
                admission.domestic_opportunity_identity.opportunity_id
            )
            if binding is None or binding.market_observation_identity != admission.domestic_market_identity:
                raise ValueError("domestic Opportunity Market binding is missing or differs")
            if receipt_row is None:
                receipt_row = self._connection.execute(
                    f"SELECT * FROM {RECEIPT_TABLE} WHERE admission_id=? ORDER BY inserted_at LIMIT 1",
                    (admission_id,),
                ).fetchone()
            if receipt_row is None:
                raise ValueError("domestic selling admission receipt is missing")
            self._validate_receipt_integrity(receipt_row)
            receipt = DomesticSellingOpportunityAdmissionReceipt(
                receipt_row["command_id"], receipt_row["admission_id"],
                receipt_row["domestic_opportunity_id"], receipt_row["command_fingerprint"],
                _datetime(receipt_row["committed_at"], "committed_at"),
                receipt_row["schema_version"],
            )
            return DomesticSellingOpportunityAdmissionPublication(
                lifecycle, transition, binding, admission, receipt, False
            )
        except MalformedDomesticSellingOpportunityPersistenceError:
            raise
        except Exception as error:
            raise MalformedDomesticSellingOpportunityPersistenceError(
                "persisted domestic selling admission is malformed"
            ) from error

    @staticmethod
    def _load_admission(data):
        expected = {
            "admission_id", "source_opportunity_identity", "source_lifecycle_status",
            "source_lifecycle_version", "domestic_opportunity_identity",
            "source_candidate_id", "source_candidate_opportunity_binding_id",
            "source_promotion_command_id", "source_product_snapshot_id",
            "source_market_identity", "domestic_market_identity", "product_equivalence",
            "policy_name", "policy_version", "requested_at", "admitted_at", "schema_version",
        }
        if not isinstance(data, dict) or set(data) != expected:
            raise ValueError("admission payload has unsupported fields")
        source = data["source_opportunity_identity"]
        domestic = data["domestic_opportunity_identity"]
        verification = data["product_equivalence"]
        if not isinstance(source, dict) or set(source) != {"opportunity_id", "discovery_reference"}:
            raise ValueError("source Opportunity identity is malformed")
        if not isinstance(domestic, dict) or set(domestic) != {"opportunity_id", "discovery_reference"}:
            raise ValueError("domestic Opportunity identity is malformed")
        if not isinstance(verification, dict) or set(verification) != {
            "operator_id", "verified_at", "evidence_reference", "confirmed", "schema_version"
        }:
            raise ValueError("product equivalence verification is malformed")
        if verification["schema_version"] != DOMESTIC_PRODUCT_EQUIVALENCE_SCHEMA_VERSION:
            raise ValueError("unsupported product equivalence schema")
        if data["schema_version"] != DOMESTIC_SELLING_OPPORTUNITY_ADMISSION_SCHEMA_VERSION:
            raise ValueError("unsupported domestic selling admission schema")
        return DomesticSellingOpportunityAdmission(
            admission_id=data["admission_id"],
            source_opportunity_identity=OpportunityIdentity(
                source["opportunity_id"], source["discovery_reference"]
            ),
            source_lifecycle_status=OpportunityLifecycleStatus(data["source_lifecycle_status"]),
            source_lifecycle_version=data["source_lifecycle_version"],
            domestic_opportunity_identity=OpportunityIdentity(
                domestic["opportunity_id"], domestic["discovery_reference"]
            ),
            source_candidate_id=data["source_candidate_id"],
            source_candidate_opportunity_binding_id=data["source_candidate_opportunity_binding_id"],
            source_promotion_command_id=data["source_promotion_command_id"],
            source_product_snapshot_id=data["source_product_snapshot_id"],
            source_market_identity=_identity(data["source_market_identity"]),
            domestic_market_identity=_identity(data["domestic_market_identity"]),
            product_equivalence=DomesticProductEquivalenceVerification(
                operator_id=verification["operator_id"],
                verified_at=_datetime(verification["verified_at"], "verified_at"),
                evidence_reference=verification["evidence_reference"],
                confirmed=verification["confirmed"],
                schema_version=verification["schema_version"],
            ),
            policy_name=data["policy_name"], policy_version=data["policy_version"],
            requested_at=_datetime(data["requested_at"], "requested_at"),
            admitted_at=_datetime(data["admitted_at"], "admitted_at"),
            schema_version=data["schema_version"],
        )

    @staticmethod
    def _validate_receipt_integrity(row):
        if row["schema_version"] != DOMESTIC_SELLING_OPPORTUNITY_RECEIPT_SCHEMA_VERSION:
            raise MalformedDomesticSellingOpportunityPersistenceError(
                "unsupported domestic selling receipt schema"
            )
        payload = _dump({
            "command_id": row["command_id"], "admission_id": row["admission_id"],
            "domestic_opportunity_id": row["domestic_opportunity_id"],
            "command_fingerprint": row["command_fingerprint"],
            "committed_at": row["committed_at"], "schema_version": row["schema_version"],
        })
        if _integrity(payload) != row["integrity_fingerprint"]:
            raise MalformedDomesticSellingOpportunityPersistenceError(
                "domestic selling receipt integrity fingerprint mismatch"
            )


__all__ = [
    "DomesticSellingOpportunityCommitError",
    "DomesticSellingOpportunityHistoryError",
    "DomesticSellingOpportunityPersistenceError",
    "DomesticSellingOpportunityReceiptError",
    "MalformedDomesticSellingOpportunityPersistenceError",
    "SQLiteDomesticSellingOpportunityAdmissionRepository",
]
