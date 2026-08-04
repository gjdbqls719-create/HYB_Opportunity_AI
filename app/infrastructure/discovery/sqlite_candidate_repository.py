"""Atomic SQLite Candidate, context, and 1:N issuance receipt persistence."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3

from app.application.candidate_issuance import (
    CANDIDATE_ISSUANCE_RESULT_SCHEMA_VERSION,
    OPPORTUNITY_CANDIDATE_RECEIPT_SCHEMA_VERSION,
    OPPORTUNITY_CANDIDATE_SCHEMA_VERSION,
    CandidateCommitError, CandidateContextPersistenceError,
    CandidateHistoryPersistenceError, CandidateIssuanceCommandConflictError,
    CandidateIssuanceReplayConflictError, CandidateIssuanceResult,
    CandidateLineageConflictError, CandidateMarketIdentityConflictError,
    CandidateReceiptPersistenceError, DurableCandidateIssuanceResult,
    IssueOpportunityCandidateCommand, MalformedCandidatePersistenceError,
    OpportunityCandidateIssuanceReceipt,
    UnsupportedCandidatePersistenceVersionError,
    candidate_command_fingerprint, candidate_subject_fingerprint,
)
from app.domain.discovery_identity import (
    DISCOVERY_IDENTITY_SCHEMA_VERSION,
    DiscoveryOpportunityContext, OpportunityCandidateIdentity,
)
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope


def _dump_identity(value: MarketObservationIdentity) -> str:
    return json.dumps({
        "scope": value.scope.value, "market": value.market,
        "marketplace": value.marketplace,
        "canonical_product_id": value.canonical_product_id,
        "marketplace_item_id": value.marketplace_item_id,
        "normalized_query": value.normalized_query, "category": value.category,
        "variant_identity": value.variant_identity, "condition": value.condition,
        "window_started_at": value.window_started_at.isoformat(),
        "window_ended_at": value.window_ended_at.isoformat(),
    }, sort_keys=True, separators=(",", ":"))


def _dt(value: object, name: str) -> datetime:
    if not isinstance(value, str): raise ValueError(f"{name} must be text")
    result = datetime.fromisoformat(value)
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return result


def _identity(payload: str) -> MarketObservationIdentity:
    value = json.loads(payload)
    if not isinstance(value, dict): raise ValueError("identity must be object")
    return MarketObservationIdentity(
        scope=MarketObservationScope(value["scope"]), market=value["market"],
        marketplace=value["marketplace"], canonical_product_id=value["canonical_product_id"],
        marketplace_item_id=value["marketplace_item_id"], normalized_query=value["normalized_query"],
        category=value["category"], variant_identity=value["variant_identity"],
        condition=value["condition"], window_started_at=_dt(value["window_started_at"], "window_started_at"),
        window_ended_at=_dt(value["window_ended_at"], "window_ended_at"),
    )


class SQLiteCandidateIssuanceRepository:
    def __init__(self, database_path: str | Path | None = None, *, connection=None):
        if (database_path is None) == (connection is None):
            raise ValueError("provide exactly one database_path or connection")
        self._owns_connection = connection is None
        if connection is None:
            path = Path(database_path); path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(path, timeout=30, check_same_thread=False)
        self._connection = connection; connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON"); self._initialize()

    def _initialize(self):
        with self._connection:
            self._connection.execute("""CREATE TABLE IF NOT EXISTS opportunity_candidate_history(
                candidate_id TEXT PRIMARY KEY, discovery_reference TEXT NOT NULL,
                discovery_command_id TEXT NOT NULL, discovery_execution_id TEXT NOT NULL,
                finalized_group_id TEXT NOT NULL, candidate_issued_at TEXT NOT NULL,
                candidate_schema_version TEXT NOT NULL, subject_fingerprint TEXT NOT NULL,
                inserted_at TEXT NOT NULL, UNIQUE(discovery_command_id, finalized_group_id),
                FOREIGN KEY(discovery_command_id, discovery_execution_id)
                  REFERENCES discovery_command_history(command_id, execution_id),
                FOREIGN KEY(finalized_group_id) REFERENCES discovery_finalized_group_history(finalized_group_id))""")
            self._connection.execute("""CREATE TABLE IF NOT EXISTS opportunity_candidate_context_history(
                candidate_id TEXT PRIMARY KEY, market_identity_payload_json TEXT NOT NULL,
                context_command_id TEXT NOT NULL, context_execution_id TEXT NOT NULL,
                context_requested_at TEXT NOT NULL, context_schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL,
                FOREIGN KEY(candidate_id) REFERENCES opportunity_candidate_history(candidate_id))""")
            self._connection.execute("""CREATE TABLE IF NOT EXISTS opportunity_candidate_issuance_receipts(
                issuance_command_id TEXT PRIMARY KEY, discovery_command_id TEXT NOT NULL,
                discovery_execution_id TEXT NOT NULL, finalized_group_id TEXT NOT NULL,
                candidate_id TEXT NOT NULL, command_fingerprint TEXT NOT NULL,
                subject_fingerprint TEXT NOT NULL, discovery_reference TEXT NOT NULL,
                market_identity_payload_json TEXT NOT NULL, requested_at TEXT NOT NULL,
                receipt_committed_at TEXT NOT NULL, receipt_schema_version TEXT NOT NULL,
                inserted_at TEXT NOT NULL,
                FOREIGN KEY(candidate_id) REFERENCES opportunity_candidate_history(candidate_id),
                FOREIGN KEY(discovery_command_id, discovery_execution_id)
                  REFERENCES discovery_command_history(command_id, execution_id),
                FOREIGN KEY(finalized_group_id) REFERENCES discovery_finalized_group_history(finalized_group_id))""")
            self._connection.execute("CREATE INDEX IF NOT EXISTS idx_candidate_receipts_candidate ON opportunity_candidate_issuance_receipts(candidate_id, receipt_committed_at, issuance_command_id)")
            for table in ("opportunity_candidate_history", "opportunity_candidate_context_history", "opportunity_candidate_issuance_receipts"):
                for op in ("UPDATE", "DELETE"):
                    self._connection.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_{table}_no_{op.lower()}
                    BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT, '{table} is append-only'); END""")

    def _begin(self):
        try: self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as e: raise CandidateCommitError("candidate transaction could not start") from e
    def _rollback(self):
        if self._connection.in_transaction: self._connection.rollback()
    def _commit(self): self._connection.commit()

    def _validate_lineage(self, command: IssueOpportunityCandidateCommand):
        try:
            cmd = self._connection.execute("SELECT execution_id FROM discovery_command_history WHERE command_id=?", (command.discovery_command_id,)).fetchone()
            result = self._connection.execute("SELECT ordered_finalized_group_ids_json FROM discovery_execution_result_history WHERE command_id=? AND execution_id=?", (command.discovery_command_id, command.discovery_execution_id)).fetchone()
            group = self._connection.execute("SELECT discovery_execution_id, representative_observation_id FROM discovery_finalized_group_history WHERE finalized_group_id=?", (command.finalized_group_id,)).fetchone()
        except sqlite3.Error as e: raise CandidateLineageConflictError("candidate lineage query failed") from e
        if cmd is None or cmd[0] != command.discovery_execution_id or result is None or group is None:
            raise CandidateLineageConflictError("candidate Discovery lineage is missing")
        try: ids = json.loads(result[0])
        except (TypeError, ValueError) as e: raise CandidateLineageConflictError("malformed Discovery result lineage") from e
        if not ids or command.finalized_group_id not in ids or group[0] != command.discovery_execution_id:
            raise CandidateLineageConflictError("candidate Group is not in completed result")
        try: row = self._connection.execute("SELECT observation_payload_json FROM discovery_collected_observation_history WHERE observation_id=?", (group[1],)).fetchone()
        except sqlite3.Error as e: raise CandidateLineageConflictError("representative observation query failed") from e
        if row is None: raise CandidateLineageConflictError("representative observation is missing")
        try: obs = json.loads(row[0])
        except (TypeError, ValueError) as e: raise CandidateLineageConflictError("malformed representative observation") from e
        identity = command.market_observation_identity
        if obs["source_marketplace"] != identity.marketplace:
            raise CandidateMarketIdentityConflictError("marketplace mismatch")
        if identity.scope is MarketObservationScope.LISTING and obs["source_item_id"] != identity.marketplace_item_id:
            raise CandidateMarketIdentityConflictError("listing item mismatch")

    def save_initial_issuance(self, command, issuance, receipt):
        self._begin()
        try:
            replay = self._validate_command_locked(command.issuance_command_id, receipt.command_fingerprint)
            if replay: self._rollback(); return DurableCandidateIssuanceResult(replay.issuance, replay.receipt, True)
            self._validate_lineage(command)
            existing = self._get_group_locked(command.discovery_command_id, command.finalized_group_id)
            if existing:
                if self._subject_for(existing.candidate_identity.candidate_id) != receipt.subject_fingerprint:
                    raise CandidateIssuanceReplayConflictError("candidate subject conflicts")
                alias = replace(receipt, candidate_id=existing.candidate_identity.candidate_id)
                self._insert_receipt(alias); self._commit()
                return DurableCandidateIssuanceResult(existing, alias, True)
            try: self._insert_candidate(issuance, receipt.subject_fingerprint)
            except sqlite3.Error as e: raise CandidateHistoryPersistenceError("candidate insert failed") from e
            try: self._insert_context(issuance)
            except sqlite3.Error as e: raise CandidateContextPersistenceError("candidate context insert failed") from e
            try: self._insert_receipt(receipt)
            except sqlite3.Error as e: raise CandidateReceiptPersistenceError("candidate receipt insert failed") from e
            try: self._commit()
            except sqlite3.Error as e: raise CandidateCommitError("candidate commit failed") from e
            return DurableCandidateIssuanceResult(issuance, receipt, False)
        except Exception: self._rollback(); raise

    def save_alias_receipt(self, command, receipt):
        self._begin()
        try:
            replay = self._validate_command_locked(command.issuance_command_id, receipt.command_fingerprint)
            if replay: self._rollback(); return DurableCandidateIssuanceResult(replay.issuance, replay.receipt, True)
            self._validate_lineage(command)
            issuance = self._get_group_locked(command.discovery_command_id, command.finalized_group_id)
            if issuance is None: raise CandidateLineageConflictError("candidate subject does not exist")
            if self._subject_for(issuance.candidate_identity.candidate_id) != receipt.subject_fingerprint:
                raise CandidateIssuanceReplayConflictError("candidate subject conflicts")
            receipt = replace(receipt, candidate_id=issuance.candidate_identity.candidate_id)
            try: self._insert_receipt(receipt)
            except sqlite3.Error as e: raise CandidateReceiptPersistenceError("alias receipt insert failed") from e
            try: self._commit()
            except sqlite3.Error as e: raise CandidateCommitError("alias receipt commit failed") from e
            return DurableCandidateIssuanceResult(issuance, receipt, True)
        except Exception: self._rollback(); raise

    def _insert_candidate(self, issuance, subject):
        i=issuance.candidate_identity
        self._connection.execute("INSERT INTO opportunity_candidate_history VALUES(?,?,?,?,?,?,?,?,?)", (i.candidate_id,i.discovery_reference,issuance.discovery_command_id,issuance.discovery_context.discovery_execution_id,issuance.finalized_group_id,issuance.issued_at.isoformat(),OPPORTUNITY_CANDIDATE_SCHEMA_VERSION,subject,issuance.issued_at.astimezone(timezone.utc).isoformat()))
    def _insert_context(self, issuance):
        c=issuance.discovery_context
        self._connection.execute("INSERT INTO opportunity_candidate_context_history VALUES(?,?,?,?,?,?,?)", (issuance.candidate_identity.candidate_id,_dump_identity(c.market_observation_identity),c.command_id,c.discovery_execution_id,c.requested_at.isoformat(),c.schema_version,issuance.issued_at.astimezone(timezone.utc).isoformat()))
    def _insert_receipt(self, r):
        self._connection.execute("INSERT INTO opportunity_candidate_issuance_receipts VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", (r.issuance_command_id,r.discovery_command_id,r.discovery_execution_id,r.finalized_group_id,r.candidate_id,r.command_fingerprint,r.subject_fingerprint,r.discovery_reference,_dump_identity(r.market_observation_identity),r.requested_at.isoformat(),r.receipt_committed_at.isoformat(),r.schema_version,r.receipt_committed_at.astimezone(timezone.utc).isoformat()))

    def get_candidate(self, candidate_id):
        try: row=self._connection.execute("SELECT * FROM opportunity_candidate_history WHERE candidate_id=?",(candidate_id,)).fetchone()
        except sqlite3.Error as e: raise CandidateHistoryPersistenceError("candidate query failed") from e
        if not row:return None
        if row["candidate_schema_version"]!=OPPORTUNITY_CANDIDATE_SCHEMA_VERSION: raise UnsupportedCandidatePersistenceVersionError("unsupported candidate version")
        try:return OpportunityCandidateIdentity(row["candidate_id"],row["discovery_reference"])
        except Exception as e:raise MalformedCandidatePersistenceError("malformed candidate") from e
    def get_context(self,candidate_id):
        try: row=self._connection.execute("SELECT * FROM opportunity_candidate_context_history WHERE candidate_id=?",(candidate_id,)).fetchone()
        except sqlite3.Error as e: raise CandidateContextPersistenceError("candidate context query failed") from e
        if not row:return None
        try:
            if row["context_schema_version"]!=DISCOVERY_IDENTITY_SCHEMA_VERSION: raise UnsupportedCandidatePersistenceVersionError("unsupported context version")
            identity=self.get_candidate(candidate_id)
            return DiscoveryOpportunityContext(identity,_identity(row["market_identity_payload_json"]),row["context_execution_id"],row["context_command_id"],_dt(row["context_requested_at"],"requested_at"),row["context_schema_version"])
        except UnsupportedCandidatePersistenceVersionError: raise
        except Exception as e: raise MalformedCandidatePersistenceError("malformed candidate context") from e
    def get_receipt_by_command(self,command_id):
        try: row=self._connection.execute("SELECT * FROM opportunity_candidate_issuance_receipts WHERE issuance_command_id=?",(command_id,)).fetchone()
        except sqlite3.Error as e: raise CandidateReceiptPersistenceError("candidate receipt query failed") from e
        return None if not row else self._receipt(row)
    def _receipt(self,row):
        try:
            receipt=OpportunityCandidateIssuanceReceipt(row["issuance_command_id"],row["discovery_command_id"],row["discovery_execution_id"],row["finalized_group_id"],row["candidate_id"],row["command_fingerprint"],row["subject_fingerprint"],row["discovery_reference"],_identity(row["market_identity_payload_json"]),_dt(row["requested_at"],"requested_at"),_dt(row["receipt_committed_at"],"receipt_committed_at"),row["receipt_schema_version"])
            command=IssueOpportunityCandidateCommand(receipt.issuance_command_id,receipt.discovery_command_id,receipt.discovery_execution_id,receipt.finalized_group_id,receipt.discovery_reference,receipt.market_observation_identity,receipt.requested_at)
            if candidate_command_fingerprint(command)!=receipt.command_fingerprint or candidate_subject_fingerprint(command)!=receipt.subject_fingerprint:
                raise ValueError("candidate receipt fingerprint mismatch")
            issuance=self._get_group_locked(receipt.discovery_command_id,receipt.finalized_group_id)
            if issuance is None or issuance.candidate_identity.candidate_id!=receipt.candidate_id or issuance.candidate_identity.discovery_reference!=receipt.discovery_reference or issuance.discovery_context.market_observation_identity!=receipt.market_observation_identity:
                raise ValueError("candidate receipt lineage mismatch")
            return receipt
        except UnsupportedCandidatePersistenceVersionError: raise
        except Exception as e: raise MalformedCandidatePersistenceError("malformed candidate receipt") from e
    def _get_group_locked(self,command_id,group_id):
        try: row=self._connection.execute("SELECT * FROM opportunity_candidate_history WHERE discovery_command_id=? AND finalized_group_id=?",(command_id,group_id)).fetchone()
        except sqlite3.Error as e: raise CandidateHistoryPersistenceError("candidate group query failed") from e
        if not row:return None
        candidate=self.get_candidate(row["candidate_id"]); context=self.get_context(row["candidate_id"])
        try: issued=_dt(row["candidate_issued_at"],"candidate_issued_at")
        except Exception as e: raise MalformedCandidatePersistenceError("malformed candidate") from e
        return CandidateIssuanceResult(candidate,context,row["discovery_command_id"],row["finalized_group_id"],issued)
    def get_by_discovery_group(self,command_id,group_id): return self._get_group_locked(command_id,group_id)
    def _subject_for(self,candidate_id):
        try:return self._connection.execute("SELECT subject_fingerprint FROM opportunity_candidate_history WHERE candidate_id=?",(candidate_id,)).fetchone()[0]
        except sqlite3.Error as e:raise CandidateHistoryPersistenceError("candidate subject query failed") from e
    def list_receipts_for_candidate(self,candidate_id):
        try:rows=self._connection.execute("SELECT * FROM opportunity_candidate_issuance_receipts WHERE candidate_id=? ORDER BY receipt_committed_at,issuance_command_id",(candidate_id,)).fetchall()
        except sqlite3.Error as e:raise CandidateReceiptPersistenceError("candidate receipts query failed") from e
        return tuple(self._receipt(row) for row in rows)
    def _validate_command_locked(self,command_id,fingerprint):
        receipt=self.get_receipt_by_command(command_id)
        if not receipt:return None
        if receipt.command_fingerprint!=fingerprint: raise CandidateIssuanceCommandConflictError("issuance command payload conflicts")
        issuance=self._get_group_locked(receipt.discovery_command_id,receipt.finalized_group_id)
        if issuance is None: raise MalformedCandidatePersistenceError("receipt candidate missing")
        return DurableCandidateIssuanceResult(issuance,receipt,True)
    def validate_command_replay(self,command_id,fingerprint): return self._validate_command_locked(command_id,fingerprint)
    def validate_subject_replay(self,command_id,group_id,fingerprint):
        issuance=self._get_group_locked(command_id,group_id)
        if not issuance:return None
        if self._subject_for(issuance.candidate_identity.candidate_id)!=fingerprint: raise CandidateIssuanceReplayConflictError("candidate subject conflicts")
        return issuance
    def close(self):
        if self._owns_connection:self._connection.close()
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
