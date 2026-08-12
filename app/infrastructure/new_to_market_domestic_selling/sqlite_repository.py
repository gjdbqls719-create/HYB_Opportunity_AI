"""Atomic SQLite authority for new-to-market KR selling target admission."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.candidate_promotion import PROMOTION_BINDING_V2_SCHEMA_VERSION
from app.application.new_to_market_domestic_selling import (
    NEW_TO_MARKET_RECEIPT_SCHEMA_VERSION,
    NewToMarketDomesticSellingAdmissionPublication,
    NewToMarketDomesticSellingAdmissionReceipt,
    NewToMarketDomesticSellingCardinalityConflictError,
    NewToMarketDomesticSellingLineageError,
    NewToMarketDomesticSellingReplayConflictError,
)
from app.application.opportunity_validation import FounderSelectedAdmissionBasis
from app.domain.decision_engine import OpportunityIdentity
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.domain.opportunity import (
    BOUNDED_KR_SEARCH_MANIFEST_SCHEMA_VERSION,
    NEW_TO_MARKET_ADMISSION_SCHEMA_VERSION,
    NEW_TO_MARKET_SOURCE_MANIFEST_SCHEMA_VERSION,
    NEW_TO_MARKET_TARGET_IDENTITY_SCHEMA_VERSION,
    OPPORTUNITY_DOMESTIC_SELLING_TARGET_BINDING_SCHEMA_VERSION,
    BoundedKRSearchConclusion,
    BoundedKRSearchManifest,
    BoundedKRSearchScopeKind,
    NewToMarketDomesticSellingOpportunityAdmission,
    NewToMarketDomesticSellingSourceManifest,
    NewToMarketDomesticSellingTargetIdentity,
    NewToMarketDomesticSellingTargetKind,
    OpportunityDomesticSellingTargetBinding,
    OpportunityLifecycle,
    OpportunityLifecycleAction,
    OpportunityLifecycleStatus,
    OpportunityLifecycleTransition,
)
from app.infrastructure.domestic_selling_opportunity.sqlite_repository import (
    HISTORY_TABLE as EXISTING_PRODUCT_HISTORY_TABLE,
    SQLiteDomesticSellingOpportunityAdmissionRepository,
    _identity,
    _identity_payload,
)
from app.infrastructure.product_observation import SQLiteProductSnapshotCaptureRepository


TARGET_TABLE = "new_to_market_domestic_selling_target_history"
BINDING_TABLE = "opportunity_domestic_selling_target_bindings"
ADMISSION_TABLE = "new_to_market_domestic_selling_admission_history"
RECEIPT_TABLE = "new_to_market_domestic_selling_admission_receipts"


class NewToMarketDomesticSellingPersistenceError(RuntimeError):
    pass


class NewToMarketDomesticSellingHistoryError(
    NewToMarketDomesticSellingPersistenceError
):
    pass


class NewToMarketDomesticSellingReceiptError(
    NewToMarketDomesticSellingPersistenceError
):
    pass


class NewToMarketDomesticSellingCommitError(
    NewToMarketDomesticSellingPersistenceError
):
    pass


class MalformedNewToMarketDomesticSellingPersistenceError(
    NewToMarketDomesticSellingPersistenceError
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


def _target_payload(value: NewToMarketDomesticSellingTargetIdentity) -> dict[str, str]:
    return {
        "domestic_selling_target_id": value.domestic_selling_target_id,
        "market": value.market,
        "kind": value.kind.value,
        "schema_version": value.schema_version,
    }


def _search_payload(value: BoundedKRSearchManifest) -> dict[str, object]:
    return {
        "searched_channels": list(value.searched_channels),
        "scope_kind": value.scope_kind.value,
        "scope_value": value.scope_value,
        "performed_at": value.performed_at.isoformat(),
        "operator_id": value.operator_id,
        "evidence_references": list(value.evidence_references),
        "conclusion": value.conclusion.value,
        "market": value.market,
        "schema_version": value.schema_version,
    }


def _source_payload(value: NewToMarketDomesticSellingSourceManifest) -> dict[str, object]:
    source = value.source_opportunity_identity
    return {
        "source_opportunity_identity": {
            "opportunity_id": source.opportunity_id,
            "discovery_reference": source.discovery_reference,
        },
        "source_lifecycle_status": value.source_lifecycle_status.value,
        "source_lifecycle_version": value.source_lifecycle_version,
        "source_market_identity": _identity_payload(value.source_market_identity),
        "candidate_id": value.candidate_id,
        "candidate_opportunity_binding_id": value.candidate_opportunity_binding_id,
        "promotion_command_id": value.promotion_command_id,
        "promotion_admission_id": value.promotion_admission_id,
        "finalized_group_id": value.finalized_group_id,
        "product_snapshot_capture_command_id": value.product_snapshot_capture_command_id,
        "product_snapshot_ids": list(value.product_snapshot_ids),
        "representative_product_snapshot_id": value.representative_product_snapshot_id,
        "selected_product_snapshot_id": value.selected_product_snapshot_id,
        "selected_source_observation_id": value.selected_source_observation_id,
        "schema_version": value.schema_version,
    }


def _admission_payload(value: NewToMarketDomesticSellingOpportunityAdmission) -> str:
    domestic = value.domestic_opportunity_identity
    return _dump(
        {
            "admission_id": value.admission_id,
            "source_manifest": _source_payload(value.source_manifest),
            "domestic_opportunity_identity": {
                "opportunity_id": domestic.opportunity_id,
                "discovery_reference": domestic.discovery_reference,
            },
            "target_identity": _target_payload(value.target_identity),
            "search_manifest": _search_payload(value.search_manifest),
            "operator_id": value.operator_id,
            "decision_reason": value.decision_reason,
            "verified_at": value.verified_at.isoformat(),
            "requested_at": value.requested_at.isoformat(),
            "admitted_at": value.admitted_at.isoformat(),
            "policy_name": value.policy_name,
            "policy_version": value.policy_version,
            "schema_version": value.schema_version,
        }
    )


class SQLiteNewToMarketDomesticSellingAdmissionRepository(
    SQLiteDomesticSellingOpportunityAdmissionRepository
):
    def __init__(
        self,
        database_path: str | Path = "data/hyb_opportunity.db",
        *,
        connection: sqlite3.Connection | None = None,
    ) -> None:
        super().__init__(database_path, connection=connection)
        self._captures = SQLiteProductSnapshotCaptureRepository(
            connection=self._connection
        )
        self._initialize_new_to_market_schema()

    def _initialize_new_to_market_schema(self) -> None:
        with self._connection:
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {TARGET_TABLE}(
                domestic_selling_target_id TEXT PRIMARY KEY,
                market TEXT NOT NULL,
                kind TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL)"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {BINDING_TABLE}(
                opportunity_id TEXT PRIMARY KEY,
                discovery_reference TEXT NOT NULL UNIQUE,
                domestic_selling_target_id TEXT NOT NULL UNIQUE,
                bound_at TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL,
                FOREIGN KEY(opportunity_id) REFERENCES opportunity_lifecycles(opportunity_id),
                FOREIGN KEY(domestic_selling_target_id) REFERENCES {TARGET_TABLE}(domestic_selling_target_id))"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {ADMISSION_TABLE}(
                admission_id TEXT PRIMARY KEY,
                source_opportunity_id TEXT NOT NULL UNIQUE,
                domestic_opportunity_id TEXT NOT NULL UNIQUE,
                domestic_selling_target_id TEXT NOT NULL UNIQUE,
                subject_fingerprint TEXT NOT NULL,
                policy_name TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                integrity_fingerprint TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL,
                FOREIGN KEY(source_opportunity_id) REFERENCES opportunity_lifecycles(opportunity_id),
                FOREIGN KEY(domestic_opportunity_id) REFERENCES opportunity_lifecycles(opportunity_id),
                FOREIGN KEY(domestic_selling_target_id) REFERENCES {TARGET_TABLE}(domestic_selling_target_id))"""
            )
            self._connection.execute(
                f"""CREATE TABLE IF NOT EXISTS {RECEIPT_TABLE}(
                command_id TEXT PRIMARY KEY,
                admission_id TEXT NOT NULL,
                domestic_selling_target_id TEXT NOT NULL,
                domestic_opportunity_id TEXT NOT NULL,
                command_fingerprint TEXT NOT NULL,
                subject_fingerprint TEXT NOT NULL,
                committed_at TEXT NOT NULL,
                schema_version TEXT NOT NULL,
                integrity_fingerprint TEXT NOT NULL,
                inserted_at TEXT NOT NULL,
                FOREIGN KEY(admission_id) REFERENCES {ADMISSION_TABLE}(admission_id),
                FOREIGN KEY(domestic_selling_target_id) REFERENCES {TARGET_TABLE}(domestic_selling_target_id),
                FOREIGN KEY(domestic_opportunity_id) REFERENCES opportunity_lifecycles(opportunity_id))"""
            )
            for table in (TARGET_TABLE, BINDING_TABLE, ADMISSION_TABLE, RECEIPT_TABLE):
                for operation in ("UPDATE", "DELETE"):
                    self._connection.execute(
                        f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{operation.lower()}
                        BEFORE {operation} ON {table}
                        BEGIN SELECT RAISE(ABORT,'{table} is append-only'); END"""
                    )

    def get_promotion_v2_admission(self, opportunity_id):
        row = self._connection.execute(
            "SELECT * FROM candidate_promotion_v2_admission_history WHERE opportunity_id=?",
            (opportunity_id,),
        ).fetchone()
        if row is None:
            return None
        try:
            return FounderSelectedAdmissionBasis(
                admission_id=row["admission_id"],
                candidate_id=row["candidate_id"],
                candidate_opportunity_binding_id=row["binding_id"],
                discovery_command_id=row["discovery_command_id"],
                discovery_execution_id=row["discovery_execution_id"],
                finalized_group_id=row["finalized_group_id"],
                product_snapshot_capture_command_id=row["capture_command_id"],
                product_snapshot_ids=tuple(
                    json.loads(row["ordered_product_snapshot_ids_json"])
                ),
                representative_product_snapshot_id=row[
                    "representative_product_snapshot_id"
                ],
                operator_id=row["operator_id"],
                reason=row["reason"],
                requested_at=_datetime(row["requested_at"], "requested_at"),
                promoted_at=_datetime(row["promoted_at"], "promoted_at"),
                committed_at=_datetime(row["committed_at"], "committed_at"),
                admission_kind=row["admission_kind"],
                policy_name=row["policy_name"],
                policy_version=row["policy_version"],
                schema_version=row["schema_version"],
            )
        except Exception as error:
            raise MalformedNewToMarketDomesticSellingPersistenceError(
                "persisted Candidate Promotion v2 admission is malformed"
            ) from error

    def get_capture_receipt(self, command_id):
        return self._captures.get_receipt(command_id)

    def get_capture_result(self, receipt):
        return self._captures.get_result(receipt)

    def get_snapshot_source_binding(self, snapshot_id):
        return self._captures.get_binding(snapshot_id)

    def get_finalized_group(self, finalized_group_id):
        return self._captures.get_group(finalized_group_id)

    def get_source_observation(self, observation_id):
        return self._captures.get_observation(observation_id)

    def get_existing_product_admission_by_source(self, opportunity_id):
        row = self._connection.execute(
            "SELECT admission_id FROM domestic_selling_opportunity_admission_history "
            "WHERE source_opportunity_id=?",
            (opportunity_id,),
        ).fetchone()
        return None if row is None else row["admission_id"]

    def validate_replay(self, command_id, fingerprint):
        row = self._connection.execute(
            f"SELECT * FROM {RECEIPT_TABLE} WHERE command_id=?", (command_id,)
        ).fetchone()
        if row is None:
            return None
        self._validate_receipt(row)
        if row["command_fingerprint"] != fingerprint:
            raise NewToMarketDomesticSellingReplayConflictError(
                "new-to-market command payload conflicts"
            )
        return self._publication(row["admission_id"], receipt_row=row)

    def get_admission_by_source(self, opportunity_id):
        row = self._connection.execute(
            f"SELECT admission_id FROM {ADMISSION_TABLE} WHERE source_opportunity_id=?",
            (opportunity_id,),
        ).fetchone()
        return None if row is None else self._publication(row["admission_id"])

    def get_admission(self, admission_id):
        row = self._connection.execute(
            f"SELECT admission_id FROM {ADMISSION_TABLE} WHERE admission_id=?",
            (admission_id,),
        ).fetchone()
        return None if row is None else self._publication(row["admission_id"])

    def get_target_binding(self, opportunity_id):
        row = self._connection.execute(
            f"SELECT * FROM {BINDING_TABLE} WHERE opportunity_id=?", (opportunity_id,)
        ).fetchone()
        if row is None:
            return None
        target = self._load_target(row["domestic_selling_target_id"])
        try:
            return OpportunityDomesticSellingTargetBinding(
                row["opportunity_id"],
                row["discovery_reference"],
                target,
                _datetime(row["bound_at"], "bound_at"),
                row["schema_version"],
            )
        except Exception as error:
            raise MalformedNewToMarketDomesticSellingPersistenceError(
                "persisted target binding is malformed"
            ) from error

    def save_admission(
        self, command, lifecycle, transition, target_binding, admission, receipt
    ):
        candidate = NewToMarketDomesticSellingAdmissionPublication(
            lifecycle, transition, target_binding, admission, receipt, False
        )
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self.validate_replay(command.command_id, command.fingerprint)
            if replay is not None:
                self._connection.rollback()
                return NewToMarketDomesticSellingAdmissionPublication(
                    replay.lifecycle,
                    replay.creation_transition,
                    replay.target_binding,
                    replay.admission,
                    replay.receipt,
                    True,
                )
            self._validate_source(admission)
            existing = self._connection.execute(
                f"SELECT admission_id,subject_fingerprint FROM {ADMISSION_TABLE} WHERE source_opportunity_id=?",
                (command.source_opportunity_id,),
            ).fetchone()
            if existing is not None:
                if existing["subject_fingerprint"] != command.subject_fingerprint:
                    raise NewToMarketDomesticSellingCardinalityConflictError(
                        "source Opportunity already has a conflicting new-to-market admission"
                    )
                persisted = self._publication(existing["admission_id"])
                if (
                    persisted.admission != admission
                    or persisted.target_binding != target_binding
                    or persisted.lifecycle != lifecycle
                ):
                    raise NewToMarketDomesticSellingCardinalityConflictError(
                        "new-to-market alias differs from persisted authority"
                    )
                self._insert_receipt(receipt)
                self._commit()
                return NewToMarketDomesticSellingAdmissionPublication(
                    persisted.lifecycle,
                    persisted.creation_transition,
                    persisted.target_binding,
                    persisted.admission,
                    receipt,
                    True,
                )
            if self._connection.execute(
                f"SELECT 1 FROM {EXISTING_PRODUCT_HISTORY_TABLE} WHERE source_opportunity_id=?",
                (command.source_opportunity_id,),
            ).fetchone() is not None:
                raise NewToMarketDomesticSellingCardinalityConflictError(
                    "source Opportunity already has an ADR-0049 domestic-selling Opportunity"
                )
            if super().get_market_identity_binding(lifecycle.opportunity_id) is not None:
                raise NewToMarketDomesticSellingCardinalityConflictError(
                    "domestic Opportunity already has a Market binding variant"
                )
            self._lifecycles._insert_current(lifecycle)
            self._lifecycles._insert_transition(transition)
            self._insert_target(admission.target_identity)
            self._insert_target_binding(target_binding)
            self._insert_admission(admission, command.subject_fingerprint)
            self._insert_receipt(receipt)
            self._commit()
            return candidate
        except sqlite3.IntegrityError as error:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise NewToMarketDomesticSellingCardinalityConflictError(
                "new-to-market domestic selling cardinality conflicts"
            ) from error
        except NewToMarketDomesticSellingCardinalityConflictError:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise
        except sqlite3.Error as error:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise NewToMarketDomesticSellingHistoryError(
                "new-to-market admission history write failed"
            ) from error
        except Exception:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise

    def _commit(self):
        try:
            self._connection.commit()
        except sqlite3.Error as error:
            raise NewToMarketDomesticSellingCommitError(
                "new-to-market admission commit failed"
            ) from error

    def _insert_target(self, target):
        self._connection.execute(
            f"INSERT INTO {TARGET_TABLE} VALUES(?,?,?,?,?)",
            (
                target.domestic_selling_target_id,
                target.market,
                target.kind.value,
                target.schema_version,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    def _insert_target_binding(self, binding):
        self._connection.execute(
            f"INSERT INTO {BINDING_TABLE} VALUES(?,?,?,?,?,?)",
            (
                binding.opportunity_id,
                binding.discovery_reference,
                binding.target_identity.domestic_selling_target_id,
                binding.bound_at.isoformat(),
                binding.schema_version,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    def _insert_admission(self, admission, subject_fingerprint):
        payload = _admission_payload(admission)
        self._connection.execute(
            f"INSERT INTO {ADMISSION_TABLE} VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (
                admission.admission_id,
                admission.source_manifest.source_opportunity_identity.opportunity_id,
                admission.domestic_opportunity_identity.opportunity_id,
                admission.target_identity.domestic_selling_target_id,
                subject_fingerprint,
                admission.policy_name,
                admission.policy_version,
                payload,
                _integrity(payload),
                admission.schema_version,
                datetime.now(timezone.utc).isoformat(),
            ),
        )

    def _insert_receipt(self, receipt):
        payload = _dump(
            {
                "command_id": receipt.command_id,
                "admission_id": receipt.admission_id,
                "domestic_selling_target_id": receipt.domestic_selling_target_id,
                "domestic_opportunity_id": receipt.domestic_opportunity_id,
                "command_fingerprint": receipt.command_fingerprint,
                "subject_fingerprint": receipt.subject_fingerprint,
                "committed_at": receipt.committed_at.isoformat(),
                "schema_version": receipt.schema_version,
            }
        )
        try:
            self._connection.execute(
                f"INSERT INTO {RECEIPT_TABLE} VALUES(?,?,?,?,?,?,?,?,?,?)",
                (
                    receipt.command_id,
                    receipt.admission_id,
                    receipt.domestic_selling_target_id,
                    receipt.domestic_opportunity_id,
                    receipt.command_fingerprint,
                    receipt.subject_fingerprint,
                    receipt.committed_at.isoformat(),
                    receipt.schema_version,
                    _integrity(payload),
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        except sqlite3.Error as error:
            raise NewToMarketDomesticSellingReceiptError(
                "new-to-market admission receipt insert failed"
            ) from error

    def _load_target(self, target_id):
        row = self._connection.execute(
            f"SELECT * FROM {TARGET_TABLE} WHERE domestic_selling_target_id=?",
            (target_id,),
        ).fetchone()
        if row is None:
            raise MalformedNewToMarketDomesticSellingPersistenceError(
                "target binding references a missing target"
            )
        try:
            return NewToMarketDomesticSellingTargetIdentity(
                row["domestic_selling_target_id"],
                row["market"],
                NewToMarketDomesticSellingTargetKind(row["kind"]),
                row["schema_version"],
            )
        except Exception as error:
            raise MalformedNewToMarketDomesticSellingPersistenceError(
                "persisted new-to-market target is malformed"
            ) from error

    def _publication(self, admission_id, *, receipt_row=None):
        row = self._connection.execute(
            f"SELECT * FROM {ADMISSION_TABLE} WHERE admission_id=?", (admission_id,)
        ).fetchone()
        if row is None:
            raise MalformedNewToMarketDomesticSellingPersistenceError(
                "receipt references missing new-to-market admission"
            )
        try:
            payload = row["payload_json"]
            if _integrity(payload) != row["integrity_fingerprint"]:
                raise ValueError("admission integrity fingerprint mismatch")
            admission = self._load_admission(json.loads(payload))
            if (
                admission.admission_id != row["admission_id"]
                or admission.source_manifest.source_opportunity_identity.opportunity_id
                != row["source_opportunity_id"]
                or admission.domestic_opportunity_identity.opportunity_id
                != row["domestic_opportunity_id"]
                or admission.target_identity.domestic_selling_target_id
                != row["domestic_selling_target_id"]
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
            lifecycle = OpportunityLifecycle._reconstitute(
                opportunity_id=lifecycle_row["opportunity_id"],
                discovery_reference=lifecycle_row["discovery_reference"],
                status=OpportunityLifecycleStatus(lifecycle_row["status"]),
                version=lifecycle_row["version"],
                created_at=_datetime(lifecycle_row["created_at"], "created_at"),
                updated_at=_datetime(lifecycle_row["updated_at"], "updated_at"),
                archived_at=None,
                archived_by=None,
                archive_reason=None,
            )
            transition = OpportunityLifecycleTransition(
                transition_id=transition_row["transition_id"],
                opportunity_id=transition_row["opportunity_id"],
                action=OpportunityLifecycleAction(transition_row["action"]),
                previous_status=OpportunityLifecycleStatus(
                    transition_row["previous_status"]
                ),
                new_status=OpportunityLifecycleStatus(transition_row["new_status"]),
                version=transition_row["version"],
                occurred_at=_datetime(transition_row["occurred_at"], "occurred_at"),
                operator_id=transition_row["operator_id"],
                reason=transition_row["reason"],
                note=transition_row["note"],
                founder_decision_id=transition_row["founder_decision_id"],
            )
            binding = self.get_target_binding(
                admission.domestic_opportunity_identity.opportunity_id
            )
            if binding is None or binding.target_identity != admission.target_identity:
                raise ValueError("domestic Opportunity target binding is missing or differs")
            if super().get_market_identity_binding(lifecycle.opportunity_id) is not None:
                raise ValueError("domestic Opportunity has conflicting binding variants")
            if receipt_row is None:
                receipt_row = self._connection.execute(
                    f"SELECT * FROM {RECEIPT_TABLE} WHERE admission_id=? ORDER BY inserted_at,command_id LIMIT 1",
                    (admission_id,),
                ).fetchone()
            if receipt_row is None:
                raise ValueError("new-to-market admission receipt is missing")
            self._validate_receipt(receipt_row)
            receipt = self._receipt(receipt_row)
            self._validate_source(admission)
            if self._connection.execute(
                f"SELECT 1 FROM {EXISTING_PRODUCT_HISTORY_TABLE} WHERE source_opportunity_id=?",
                (admission.source_manifest.source_opportunity_identity.opportunity_id,),
            ).fetchone() is not None:
                raise ValueError("source has conflicting authority modes")
            return NewToMarketDomesticSellingAdmissionPublication(
                lifecycle, transition, binding, admission, receipt, False
            )
        except MalformedNewToMarketDomesticSellingPersistenceError:
            raise
        except Exception as error:
            raise MalformedNewToMarketDomesticSellingPersistenceError(
                "persisted new-to-market admission is malformed"
            ) from error

    def _validate_source(self, admission):
        manifest = admission.source_manifest
        source_id = manifest.source_opportunity_identity.opportunity_id
        lifecycle = self._lifecycles.get(source_id)
        promotion = self.get_promotion_by_opportunity(source_id)
        promotion_admission = self.get_promotion_v2_admission(source_id)
        market_binding = super().get_market_identity_binding(source_id)
        selected = self._products.get_snapshot(manifest.selected_product_snapshot_id)
        capture_receipt = self._captures.get_receipt(
            manifest.product_snapshot_capture_command_id
        )
        if None in (
            lifecycle, promotion, promotion_admission, market_binding,
            selected, capture_receipt,
        ):
            raise NewToMarketDomesticSellingLineageError(
                "authoritative source publication is incomplete"
            )
        capture = self._captures.get_result(capture_receipt)
        selected_binding = self._captures.get_binding(
            manifest.selected_product_snapshot_id
        )
        group = self._captures.get_group(manifest.finalized_group_id)
        observation = self._captures.get_observation(
            manifest.selected_source_observation_id
        )
        observation_ids = tuple(
            value.collected_observation_id for value in capture.bindings
        )
        representative_observation_id = next(
            (
                value.collected_observation_id
                for value in capture.bindings
                if value.product_snapshot_id
                == manifest.representative_product_snapshot_id
            ),
            None,
        )
        if (
            lifecycle.opportunity_id != source_id
            or lifecycle.discovery_reference
            != manifest.source_opportunity_identity.discovery_reference
            or lifecycle.status != manifest.source_lifecycle_status
            or lifecycle.version != manifest.source_lifecycle_version
            or lifecycle.is_archived
            or promotion.schema_version != PROMOTION_BINDING_V2_SCHEMA_VERSION
            or promotion.binding_id != manifest.candidate_opportunity_binding_id
            or promotion.candidate_id != manifest.candidate_id
            or promotion.promotion_command_id != manifest.promotion_command_id
            or promotion.finalized_group_id != manifest.finalized_group_id
            or promotion.product_snapshot_capture_command_id
            != manifest.product_snapshot_capture_command_id
            or promotion.product_snapshot_ids != manifest.product_snapshot_ids
            or promotion.representative_product_snapshot_id
            != manifest.representative_product_snapshot_id
            or promotion_admission.admission_id != manifest.promotion_admission_id
            or promotion_admission.candidate_opportunity_binding_id
            != manifest.candidate_opportunity_binding_id
            or market_binding.market_observation_identity
            != manifest.source_market_identity
            or capture_receipt.product_snapshot_ids != manifest.product_snapshot_ids
            or tuple(value.snapshot_id for value in capture.snapshots)
            != manifest.product_snapshot_ids
            or tuple(value.product_snapshot_id for value in capture.bindings)
            != manifest.product_snapshot_ids
            or group is None
            or group.observation_ids != observation_ids
            or group.representative_observation_id != representative_observation_id
            or selected_binding is None
            or selected_binding.collected_observation_id
            != manifest.selected_source_observation_id
            or selected_binding.capture_command_id
            != manifest.product_snapshot_capture_command_id
            or observation is None
            or observation.observation_id != manifest.selected_source_observation_id
            or observation.product != selected.product
            or observation.collector_provenance != selected.collector_provenance
            or observation.observed_at != selected.observed_at
        ):
            raise NewToMarketDomesticSellingLineageError(
                "persisted new-to-market source lineage differs"
            )

    @staticmethod
    def _load_admission(data):
        expected = {
            "admission_id", "source_manifest", "domestic_opportunity_identity",
            "target_identity", "search_manifest", "operator_id", "decision_reason",
            "verified_at", "requested_at", "admitted_at", "policy_name",
            "policy_version", "schema_version",
        }
        if not isinstance(data, dict) or set(data) != expected:
            raise ValueError("admission payload has unsupported fields")
        source = data["source_manifest"]
        domestic = data["domestic_opportunity_identity"]
        target = data["target_identity"]
        search = data["search_manifest"]
        source_identity = source["source_opportunity_identity"]
        source_manifest = NewToMarketDomesticSellingSourceManifest(
            source_opportunity_identity=OpportunityIdentity(
                source_identity["opportunity_id"],
                source_identity["discovery_reference"],
            ),
            source_lifecycle_status=OpportunityLifecycleStatus(
                source["source_lifecycle_status"]
            ),
            source_lifecycle_version=source["source_lifecycle_version"],
            source_market_identity=_identity(source["source_market_identity"]),
            candidate_id=source["candidate_id"],
            candidate_opportunity_binding_id=source[
                "candidate_opportunity_binding_id"
            ],
            promotion_command_id=source["promotion_command_id"],
            promotion_admission_id=source["promotion_admission_id"],
            finalized_group_id=source["finalized_group_id"],
            product_snapshot_capture_command_id=source[
                "product_snapshot_capture_command_id"
            ],
            product_snapshot_ids=tuple(source["product_snapshot_ids"]),
            representative_product_snapshot_id=source[
                "representative_product_snapshot_id"
            ],
            selected_product_snapshot_id=source["selected_product_snapshot_id"],
            selected_source_observation_id=source["selected_source_observation_id"],
            schema_version=source["schema_version"],
        )
        target_identity = NewToMarketDomesticSellingTargetIdentity(
            target["domestic_selling_target_id"],
            target["market"],
            NewToMarketDomesticSellingTargetKind(target["kind"]),
            target["schema_version"],
        )
        search_manifest = BoundedKRSearchManifest(
            searched_channels=tuple(search["searched_channels"]),
            scope_kind=BoundedKRSearchScopeKind(search["scope_kind"]),
            scope_value=search["scope_value"],
            performed_at=_datetime(search["performed_at"], "performed_at"),
            operator_id=search["operator_id"],
            evidence_references=tuple(search["evidence_references"]),
            conclusion=BoundedKRSearchConclusion(search["conclusion"]),
            market=search["market"],
            schema_version=search["schema_version"],
        )
        return NewToMarketDomesticSellingOpportunityAdmission(
            admission_id=data["admission_id"],
            source_manifest=source_manifest,
            domestic_opportunity_identity=OpportunityIdentity(
                domestic["opportunity_id"], domestic["discovery_reference"]
            ),
            target_identity=target_identity,
            search_manifest=search_manifest,
            operator_id=data["operator_id"],
            decision_reason=data["decision_reason"],
            verified_at=_datetime(data["verified_at"], "verified_at"),
            requested_at=_datetime(data["requested_at"], "requested_at"),
            admitted_at=_datetime(data["admitted_at"], "admitted_at"),
            policy_name=data["policy_name"],
            policy_version=data["policy_version"],
            schema_version=data["schema_version"],
        )

    @staticmethod
    def _receipt(row):
        return NewToMarketDomesticSellingAdmissionReceipt(
            row["command_id"],
            row["admission_id"],
            row["domestic_selling_target_id"],
            row["domestic_opportunity_id"],
            row["command_fingerprint"],
            row["subject_fingerprint"],
            _datetime(row["committed_at"], "committed_at"),
            row["schema_version"],
        )

    @staticmethod
    def _validate_receipt(row):
        if row["schema_version"] != NEW_TO_MARKET_RECEIPT_SCHEMA_VERSION:
            raise MalformedNewToMarketDomesticSellingPersistenceError(
                "unsupported new-to-market receipt schema"
            )
        payload = _dump(
            {
                "command_id": row["command_id"],
                "admission_id": row["admission_id"],
                "domestic_selling_target_id": row["domestic_selling_target_id"],
                "domestic_opportunity_id": row["domestic_opportunity_id"],
                "command_fingerprint": row["command_fingerprint"],
                "subject_fingerprint": row["subject_fingerprint"],
                "committed_at": row["committed_at"],
                "schema_version": row["schema_version"],
            }
        )
        if _integrity(payload) != row["integrity_fingerprint"]:
            raise MalformedNewToMarketDomesticSellingPersistenceError(
                "new-to-market receipt integrity fingerprint mismatch"
            )


__all__ = [
    "ADMISSION_TABLE",
    "BINDING_TABLE",
    "RECEIPT_TABLE",
    "TARGET_TABLE",
    "MalformedNewToMarketDomesticSellingPersistenceError",
    "NewToMarketDomesticSellingCommitError",
    "NewToMarketDomesticSellingHistoryError",
    "NewToMarketDomesticSellingPersistenceError",
    "NewToMarketDomesticSellingReceiptError",
    "SQLiteNewToMarketDomesticSellingAdmissionRepository",
]
