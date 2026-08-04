"""Atomic Candidate-to-Opportunity admission persistence."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import sqlite3

from app.application.candidate_promotion import (
    PROMOTION_BINDING_SCHEMA_VERSION, CandidateAlreadyPromotedError,
    CandidateOpportunityBinding, CandidatePromotionCommandConflictError,
    CandidatePromotionCommitError, CandidatePromotionHistoryError,
    CandidatePromotionReceipt, CandidatePromotionReceiptError,
    CandidatePromotionResult, MalformedCandidatePromotionPersistenceError,
    OpportunityAlreadyBoundToCandidateError, UnsupportedCandidatePromotionVersionError,
    CandidatePromotionPersistenceError,
)
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
            if row["schema_version"]!=PROMOTION_BINDING_SCHEMA_VERSION:raise UnsupportedCandidatePromotionVersionError("unsupported promotion binding version")
            i=json.loads(row["market_identity_payload_json"]);identity=MarketObservationIdentity(scope=MarketObservationScope(i["scope"]),market=i["market"],marketplace=i["marketplace"],canonical_product_id=i["canonical_product_id"],marketplace_item_id=i["marketplace_item_id"],normalized_query=i["normalized_query"],category=i["category"],variant_identity=i["variant_identity"],condition=i["condition"],window_started_at=datetime.fromisoformat(i["window_started_at"]),window_ended_at=datetime.fromisoformat(i["window_ended_at"]))
            return CandidateOpportunityBinding(row["binding_id"],row["candidate_id"],row["opportunity_id"],row["discovery_reference"],identity,row["discovery_command_id"],row["discovery_execution_id"],row["finalized_group_id"],row["initial_promotion_command_id"],datetime.fromisoformat(row["promoted_at"]),row["schema_version"])
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
