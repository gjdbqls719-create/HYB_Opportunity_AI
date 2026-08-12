"""Atomic Candidate-to-Opportunity admission persistence."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import sqlite3

from app.application.candidate_promotion import (
    PROMOTION_BINDING_SCHEMA_VERSION, CandidateAlreadyPromotedError,
    PROMOTION_BINDING_V2_SCHEMA_VERSION, PROMOTION_RECEIPT_V2_SCHEMA_VERSION,
    PROMOTION_SOURCE_V2_SCHEMA_VERSION, PROMOTION_ADMISSION_V2_SCHEMA_VERSION,
    PROMOTION_V2_POLICY_NAME, PROMOTION_V2_POLICY_VERSION,
    PROMOTION_V2_ADMISSION_KIND,
    CandidateOpportunityBinding, CandidatePromotionCommandConflictError,
    CandidatePromotionCommitError, CandidatePromotionHistoryError,
    CandidatePromotionReceipt, CandidatePromotionReceiptError,
    CandidatePromotionResult, MalformedCandidatePromotionPersistenceError,
    OpportunityAlreadyBoundToCandidateError, UnsupportedCandidatePromotionVersionError,
    CandidatePromotionPersistenceError,
)
from app.application.opportunity_validation import FounderSelectedAdmissionBasis
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.infrastructure.opportunity_validation.sqlite_repository import SQLiteValidationQueueRepository


class SQLiteCandidatePromotionRepository(SQLiteValidationQueueRepository):
    def promote_candidate(self, *, lifecycle, transition, snapshot, market_binding,
                          candidate_binding, receipt, command_fingerprint, subject_fingerprint):
        self._validate_admission(lifecycle,transition,snapshot); self._validate_binding(lifecycle,snapshot,market_binding)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay=self._validate_promotion_replay_locked(receipt.promotion_command_id,command_fingerprint)
            if replay:self._connection.rollback();return replay
            self._validate_source(candidate_binding)
            existing=self.get_promotion_by_candidate(candidate_binding.candidate_id)
            if existing:
                if existing.opportunity_id!=candidate_binding.opportunity_id or self._subject(existing.candidate_id)!=subject_fingerprint:
                    raise CandidateAlreadyPromotedError("Candidate promotion conflicts")
                self._insert_receipt(receipt);self._connection.commit()
                return CandidatePromotionResult(self.get_queue_item(existing.opportunity_id),existing,receipt,True)
            if self.get_promotion_by_opportunity(candidate_binding.opportunity_id):
                raise OpportunityAlreadyBoundToCandidateError("Opportunity is already bound")
            try:self._lifecycles._insert_current(lifecycle)
            except sqlite3.Error as e:raise CandidatePromotionPersistenceError("lifecycle current insert failed") from e
            try:self._lifecycles._insert_transition(transition)
            except sqlite3.Error as e:raise CandidatePromotionPersistenceError("lifecycle history insert failed") from e
            try:self._insert_admission_snapshot(snapshot)
            except sqlite3.Error as e:raise CandidatePromotionPersistenceError("admission snapshot insert failed") from e
            try:self._insert_market_identity_binding(market_binding)
            except sqlite3.Error as e:raise CandidatePromotionPersistenceError("market identity binding insert failed") from e
            try:self._insert_promotion(candidate_binding,subject_fingerprint)
            except sqlite3.Error as e:raise CandidatePromotionHistoryError("promotion history insert failed") from e
            try:self._insert_receipt(receipt)
            except sqlite3.Error as e:raise CandidatePromotionReceiptError("promotion receipt insert failed") from e
            try:self._connection.commit()
            except sqlite3.Error as e:raise CandidatePromotionCommitError("promotion commit failed") from e
            return CandidatePromotionResult(self.get_queue_item(lifecycle.opportunity_id),candidate_binding,receipt,False)
        except Exception:
            if self._connection.in_transaction:self._connection.rollback()
            raise

    def save_promotion_alias(self,binding,receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay=self._validate_promotion_replay_locked(receipt.promotion_command_id,receipt.command_fingerprint)
            if replay:self._connection.rollback();return replay
            existing=self.get_promotion_by_candidate(binding.candidate_id)
            if not existing or existing.opportunity_id!=receipt.opportunity_id or self._subject(binding.candidate_id)!=receipt.subject_fingerprint:
                raise CandidateAlreadyPromotedError("promotion alias conflicts")
            try:self._insert_receipt(receipt)
            except sqlite3.Error as e:raise CandidatePromotionReceiptError("alias receipt insert failed") from e
            try:self._connection.commit()
            except sqlite3.Error as e:raise CandidatePromotionCommitError("alias commit failed") from e
            return CandidatePromotionResult(self.get_queue_item(existing.opportunity_id),existing,receipt,True)
        except Exception:
            if self._connection.in_transaction:self._connection.rollback()
            raise

    def promote_candidate_v2(self, *, command, lifecycle, transition, market_binding,
                             candidate_binding, source_manifest, admission, receipt,
                             command_fingerprint, subject_fingerprint):
        self._validate_v2_models(candidate_binding, source_manifest, admission, receipt)
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self._validate_promotion_replay_locked(
                receipt.promotion_command_id, command_fingerprint
            )
            if replay:
                self._connection.rollback()
                return replay
            self._validate_source(candidate_binding)
            self._validate_v2_source_locked(candidate_binding, source_manifest)
            existing = self.get_promotion_by_candidate(candidate_binding.candidate_id)
            if existing is not None:
                if (
                    existing.schema_version != PROMOTION_BINDING_V2_SCHEMA_VERSION
                    or self._subject(existing.candidate_id) != subject_fingerprint
                    or existing.finalized_group_id != source_manifest.finalized_group_id
                    or existing.product_snapshot_capture_command_id
                    != source_manifest.product_snapshot_capture_command_id
                    or existing.product_snapshot_ids != source_manifest.product_snapshot_ids
                    or existing.representative_product_snapshot_id
                    != source_manifest.representative_product_snapshot_id
                ):
                    raise CandidateAlreadyPromotedError(
                        "Candidate is already promoted under a different subject or version"
                    )
                alias_receipt = replace(receipt, opportunity_id=existing.opportunity_id)
                self._insert_receipt(alias_receipt)
                self._commit_promotion()
                return CandidatePromotionResult(
                    self.get_queue_item(existing.opportunity_id), existing,
                    alias_receipt, True
                )
            if self.get_promotion_by_opportunity(candidate_binding.opportunity_id):
                raise OpportunityAlreadyBoundToCandidateError("Opportunity is already bound")
            self._lifecycles._insert_current(lifecycle)
            self._lifecycles._insert_transition(transition)
            self._insert_market_identity_binding(market_binding)
            self._insert_promotion(candidate_binding, subject_fingerprint)
            self._insert_v2_source(source_manifest)
            self._insert_v2_admission(
                admission, command.note, command_fingerprint, subject_fingerprint
            )
            self._insert_receipt(receipt)
            self._commit_promotion()
            return CandidatePromotionResult(
                self.get_queue_item(lifecycle.opportunity_id), candidate_binding,
                receipt, False
            )
        except sqlite3.IntegrityError as error:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise CandidatePromotionPersistenceError(
                "Candidate Promotion v2 persistence conflicts"
            ) from error
        except Exception:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise

    def save_promotion_v2_alias(self, command, binding, source_manifest, receipt):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            replay = self._validate_promotion_replay_locked(
                receipt.promotion_command_id, receipt.command_fingerprint
            )
            if replay:
                self._connection.rollback()
                return replay
            existing = self.get_promotion_by_candidate(binding.candidate_id)
            if (
                existing is None
                or existing.schema_version != PROMOTION_BINDING_V2_SCHEMA_VERSION
                or existing.opportunity_id != receipt.opportunity_id
                or existing.product_snapshot_capture_command_id
                != source_manifest.product_snapshot_capture_command_id
                or existing.product_snapshot_ids != source_manifest.product_snapshot_ids
                or existing.representative_product_snapshot_id
                != source_manifest.representative_product_snapshot_id
                or self._subject(binding.candidate_id) != receipt.subject_fingerprint
            ):
                raise CandidateAlreadyPromotedError("Candidate Promotion v2 alias conflicts")
            self._validate_v2_source_locked(existing, source_manifest)
            self._insert_receipt(receipt)
            self._commit_promotion()
            return CandidatePromotionResult(
                self.get_queue_item(existing.opportunity_id), existing, receipt, True
            )
        except Exception:
            if self._connection.in_transaction:
                self._connection.rollback()
            raise

    @staticmethod
    def _validate_v2_models(binding, source, admission, receipt):
        if binding.schema_version != PROMOTION_BINDING_V2_SCHEMA_VERSION:
            raise UnsupportedCandidatePromotionVersionError("v2 binding is required")
        if source.schema_version != PROMOTION_SOURCE_V2_SCHEMA_VERSION:
            raise UnsupportedCandidatePromotionVersionError("v2 source is required")
        if admission.schema_version != PROMOTION_ADMISSION_V2_SCHEMA_VERSION:
            raise UnsupportedCandidatePromotionVersionError("v2 admission is required")
        if receipt.schema_version != PROMOTION_RECEIPT_V2_SCHEMA_VERSION:
            raise UnsupportedCandidatePromotionVersionError("v2 receipt is required")

    def _validate_v2_source_locked(self, binding, source):
        receipt = self._connection.execute(
            "SELECT * FROM product_snapshot_capture_receipts WHERE command_id=?",
            (source.product_snapshot_capture_command_id,),
        ).fetchone()
        if receipt is None:
            raise CandidatePromotionHistoryError("Product Snapshot capture is missing")
        try:
            persisted_ids = tuple(json.loads(receipt["ordered_product_snapshot_ids_json"]))
        except Exception as error:
            raise MalformedCandidatePromotionPersistenceError(
                "Product Snapshot capture receipt is malformed"
            ) from error
        if receipt["candidate_id"] != binding.candidate_id or persisted_ids != source.product_snapshot_ids:
            raise MalformedCandidatePromotionPersistenceError(
                "Product Snapshot capture cohort differs"
            )
        group = self._connection.execute(
            "SELECT * FROM discovery_finalized_group_history WHERE finalized_group_id=?",
            (source.finalized_group_id,),
        ).fetchone()
        if group is None:
            raise CandidatePromotionHistoryError("finalized Group is missing")
        group_ids = tuple(json.loads(group["ordered_observation_ids_json"]))
        bindings = self._connection.execute(
            """SELECT product_snapshot_id,collected_observation_id,candidate_id,capture_command_id
            FROM product_snapshot_source_binding_history
            WHERE product_snapshot_id IN ({})""".format(
                ",".join("?" for _ in persisted_ids)
            ), persisted_ids,
        ).fetchall()
        by_snapshot = {row["product_snapshot_id"]: row for row in bindings}
        if tuple(by_snapshot) != persisted_ids:
            # SQL ordering is not authoritative; reconstruct explicitly below.
            if set(by_snapshot) != set(persisted_ids):
                raise MalformedCandidatePromotionPersistenceError(
                    "Product Snapshot source cohort is incomplete"
                )
        snapshots = self._connection.execute(
            """SELECT snapshot_id,candidate_id FROM product_observation_snapshot_history
            WHERE snapshot_id IN ({})""".format(
                ",".join("?" for _ in persisted_ids)
            ), persisted_ids,
        ).fetchall()
        snapshot_candidates = {row["snapshot_id"]: row["candidate_id"] for row in snapshots}
        if (
            set(snapshot_candidates) != set(persisted_ids)
            or any(value != binding.candidate_id for value in snapshot_candidates.values())
        ):
            raise MalformedCandidatePromotionPersistenceError(
                "Product Snapshot cohort Candidate lineage differs"
            )
        observation_ids = tuple(by_snapshot[value]["collected_observation_id"] for value in persisted_ids)
        representative = by_snapshot.get(source.representative_product_snapshot_id)
        if (
            observation_ids != group_ids
            or representative is None
            or representative["collected_observation_id"] != group["representative_observation_id"]
            or any(
                row["candidate_id"] != binding.candidate_id
                or row["capture_command_id"] != source.product_snapshot_capture_command_id
                for row in by_snapshot.values()
            )
        ):
            raise MalformedCandidatePromotionPersistenceError(
                "Product Snapshot and finalized Group lineage differ"
            )

    def _insert_v2_source(self, value):
        self._connection.execute(
            "INSERT INTO opportunity_candidate_promotion_v2_source_history VALUES(?,?,?,?,?,?,?,?)",
            (value.binding_id, value.candidate_id, value.finalized_group_id,
             value.product_snapshot_capture_command_id,
             json.dumps(value.product_snapshot_ids, separators=(",", ":")),
             value.representative_product_snapshot_id, value.schema_version,
             datetime.now(timezone.utc).isoformat()),
        )

    def _insert_v2_admission(self, value, note, command_fingerprint, subject_fingerprint):
        self._connection.execute(
            "INSERT INTO candidate_promotion_v2_admission_history VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (value.admission_id, self._opportunity_for_binding(value.candidate_opportunity_binding_id),
             value.candidate_id, value.candidate_opportunity_binding_id,
             value.discovery_command_id, value.discovery_execution_id,
             value.finalized_group_id, value.product_snapshot_capture_command_id,
             json.dumps(value.product_snapshot_ids, separators=(",", ":")),
             value.representative_product_snapshot_id, value.operator_id, value.reason,
             note, value.requested_at.isoformat(), value.promoted_at.isoformat(),
             value.committed_at.isoformat(), value.admission_kind, value.policy_name,
             value.policy_version, value.schema_version, command_fingerprint,
             subject_fingerprint, value.committed_at.astimezone(timezone.utc).isoformat()),
        )

    def _opportunity_for_binding(self, binding_id):
        row = self._connection.execute(
            "SELECT opportunity_id FROM opportunity_candidate_promotion_history WHERE binding_id=?",
            (binding_id,),
        ).fetchone()
        if row is None:
            raise CandidatePromotionHistoryError("promotion binding is missing")
        return row[0]

    def _commit_promotion(self):
        try:
            self._connection.commit()
        except sqlite3.Error as error:
            raise CandidatePromotionCommitError(
                "Candidate Promotion transaction commit failed"
            ) from error

    def _validate_source(self,b):
        row=self._connection.execute("""SELECT c.discovery_reference,c.discovery_command_id,c.discovery_execution_id,c.finalized_group_id,
        x.market_identity_payload_json,x.context_command_id,x.context_execution_id FROM opportunity_candidate_history c
        JOIN opportunity_candidate_context_history x USING(candidate_id) WHERE c.candidate_id=?""",(b.candidate_id,)).fetchone()
        if not row:raise CandidatePromotionHistoryError("authoritative Candidate/context is missing")
        if tuple(row[n] for n in ("discovery_reference","discovery_command_id","discovery_execution_id","finalized_group_id"))!=(b.discovery_reference,b.discovery_command_id,b.discovery_execution_id,b.finalized_group_id):
            raise MalformedCandidatePromotionPersistenceError("Candidate lineage differs")
        if row["context_command_id"]!=b.discovery_command_id or row["context_execution_id"]!=b.discovery_execution_id or json.loads(row["market_identity_payload_json"])!=self._composition_identity(b.market_observation_identity):
            raise MalformedCandidatePromotionPersistenceError("Candidate context differs")

    def _insert_promotion(self,v,subject):
        self._connection.execute("INSERT INTO opportunity_candidate_promotion_history VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (v.binding_id,v.candidate_id,v.opportunity_id,v.discovery_reference,json.dumps(self._composition_identity(v.market_observation_identity),sort_keys=True,separators=(",",":")),v.discovery_command_id,v.discovery_execution_id,v.finalized_group_id,v.promotion_command_id,subject,v.promoted_at.isoformat(),v.schema_version,v.promoted_at.astimezone(timezone.utc).isoformat()))

    def _insert_receipt(self,v):
        self._connection.execute("INSERT INTO opportunity_candidate_promotion_receipts VALUES(?,?,?,?,?,?,?,?)",(v.promotion_command_id,v.candidate_id,v.opportunity_id,v.command_fingerprint,v.subject_fingerprint,v.committed_at.isoformat(),v.schema_version,v.committed_at.astimezone(timezone.utc).isoformat()))

    def _binding(self,row):
        try:
            if row["schema_version"] not in (PROMOTION_BINDING_SCHEMA_VERSION, PROMOTION_BINDING_V2_SCHEMA_VERSION):raise UnsupportedCandidatePromotionVersionError("unsupported promotion binding version")
            i=json.loads(row["market_identity_payload_json"]);identity=MarketObservationIdentity(scope=MarketObservationScope(i["scope"]),market=i["market"],marketplace=i["marketplace"],canonical_product_id=i["canonical_product_id"],marketplace_item_id=i["marketplace_item_id"],normalized_query=i["normalized_query"],category=i["category"],variant_identity=i["variant_identity"],condition=i["condition"],window_started_at=datetime.fromisoformat(i["window_started_at"]),window_ended_at=datetime.fromisoformat(i["window_ended_at"]))
            source = None
            if row["schema_version"] == PROMOTION_BINDING_V2_SCHEMA_VERSION:
                source = self._connection.execute(
                    "SELECT * FROM opportunity_candidate_promotion_v2_source_history WHERE binding_id=?",
                    (row["binding_id"],),
                ).fetchone()
                if source is None or source["schema_version"] != PROMOTION_SOURCE_V2_SCHEMA_VERSION:
                    raise MalformedCandidatePromotionPersistenceError("v2 promotion source is missing")
            return CandidateOpportunityBinding(row["binding_id"],row["candidate_id"],row["opportunity_id"],row["discovery_reference"],identity,row["discovery_command_id"],row["discovery_execution_id"],row["finalized_group_id"],row["initial_promotion_command_id"],datetime.fromisoformat(row["promoted_at"]),row["schema_version"],None if source is None else source["capture_command_id"],() if source is None else tuple(json.loads(source["ordered_product_snapshot_ids_json"])),None if source is None else source["representative_product_snapshot_id"])
        except UnsupportedCandidatePromotionVersionError:raise
        except Exception as e:raise MalformedCandidatePromotionPersistenceError("malformed promotion binding") from e

    def get_promotion_by_candidate(self,value):
        row=self._connection.execute("SELECT * FROM opportunity_candidate_promotion_history WHERE candidate_id=?",(value,)).fetchone();return None if not row else self._binding(row)
    def get_promotion_by_opportunity(self,value):
        row=self._connection.execute("SELECT * FROM opportunity_candidate_promotion_history WHERE opportunity_id=?",(value,)).fetchone();return None if not row else self._binding(row)
    def get_promotion_receipt(self,value):
        row=self._connection.execute("SELECT * FROM opportunity_candidate_promotion_receipts WHERE promotion_command_id=?",(value,)).fetchone()
        if not row:return None
        try:return CandidatePromotionReceipt(row["promotion_command_id"],row["candidate_id"],row["opportunity_id"],row["command_fingerprint"],row["subject_fingerprint"],datetime.fromisoformat(row["committed_at"]),row["schema_version"])
        except Exception as e:raise MalformedCandidatePromotionPersistenceError("malformed promotion receipt") from e
    def _subject(self,value):return self._connection.execute("SELECT subject_fingerprint FROM opportunity_candidate_promotion_history WHERE candidate_id=?",(value,)).fetchone()[0]
    def _validate_promotion_replay_locked(self,command_id,fingerprint):
        receipt=self.get_promotion_receipt(command_id)
        if not receipt:return None
        if receipt.command_fingerprint!=fingerprint:raise CandidatePromotionCommandConflictError("promotion command payload conflicts")
        binding=self.get_promotion_by_candidate(receipt.candidate_id);item=self.get_queue_item(receipt.opportunity_id)
        if not binding or not item:raise MalformedCandidatePromotionPersistenceError("promotion lineage is incomplete")
        return CandidatePromotionResult(item,binding,receipt,True)
    def validate_promotion_replay(self,command_id,fingerprint):return self._validate_promotion_replay_locked(command_id,fingerprint)
