from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
import re
import sqlite3

from app.application.competition_v2_admission import CompetitionV2AdmissionConflictError, CompetitionV2Publication
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.domain.opportunity import NewToMarketDomesticSellingTargetIdentity
from app.domain.market_intelligence.competition_v2 import (
    CompetitionV2Card, CompetitionV2Cohort, ResultPlacement, RocketObservationOutcome,
    analyze_competition_v2, assessment_to_data, cohort_to_data,
)


_HASH = re.compile(r"^[0-9a-f]{64}$")
_OBJECTS = {"competition_v2_cohorts": "table", "competition_v2_receipts": "table",
    "trg_competition_v2_cohorts_no_update": "trigger", "trg_competition_v2_cohorts_no_delete": "trigger",
    "trg_competition_v2_receipts_no_update": "trigger", "trg_competition_v2_receipts_no_delete": "trigger"}
_SCHEMA = """
CREATE TABLE competition_v2_cohorts (cohort_id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL,
 subject_key TEXT NOT NULL, authority_fingerprint TEXT NOT NULL UNIQUE, cohort_json TEXT NOT NULL,
 assessment_json TEXT NOT NULL, committed_at TEXT NOT NULL);
CREATE TABLE competition_v2_receipts (command_id TEXT PRIMARY KEY, command_fingerprint TEXT NOT NULL,
 cohort_id TEXT NOT NULL, opportunity_id TEXT NOT NULL, operator_id TEXT NOT NULL, committed_at TEXT NOT NULL,
 FOREIGN KEY(cohort_id) REFERENCES competition_v2_cohorts(cohort_id));
CREATE TRIGGER trg_competition_v2_cohorts_no_update BEFORE UPDATE ON competition_v2_cohorts BEGIN SELECT RAISE(ABORT, 'competition v2 cohorts are append-only'); END;
CREATE TRIGGER trg_competition_v2_cohorts_no_delete BEFORE DELETE ON competition_v2_cohorts BEGIN SELECT RAISE(ABORT, 'competition v2 cohorts are append-only'); END;
CREATE TRIGGER trg_competition_v2_receipts_no_update BEFORE UPDATE ON competition_v2_receipts BEGIN SELECT RAISE(ABORT, 'competition v2 receipts are append-only'); END;
CREATE TRIGGER trg_competition_v2_receipts_no_delete BEFORE DELETE ON competition_v2_receipts BEGIN SELECT RAISE(ABORT, 'competition v2 receipts are append-only'); END;
"""


class CompetitionV2PersistenceError(RuntimeError): pass
class CompetitionV2CorruptionError(ValueError): pass


class SQLiteCompetitionV2Repository:
    def __init__(self, database):
        self._connection = sqlite3.connect(database, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._ensure_schema()

    def close(self): self._connection.close()

    def _ensure_schema(self):
        rows = self._connection.execute("SELECT name,type FROM sqlite_master WHERE name IN (%s)" %
            ",".join("?" for _ in _OBJECTS), tuple(_OBJECTS)).fetchall()
        found = {row["name"]: row["type"] for row in rows}
        if found == _OBJECTS: return
        if found: raise CompetitionV2PersistenceError("partial Competition v2 schema is malformed")
        self._connection.executescript(_SCHEMA)

    def get_receipt(self, command_id):
        row = self._connection.execute("SELECT * FROM competition_v2_receipts WHERE command_id=?", (command_id,)).fetchone()
        if row is None: return None
        data = dict(row)
        if not _HASH.fullmatch(data["command_fingerprint"]):
            raise CompetitionV2CorruptionError("Competition v2 receipt fingerprint is malformed")
        cohort = self._connection.execute("SELECT opportunity_id FROM competition_v2_cohorts WHERE cohort_id=?", (data["cohort_id"],)).fetchone()
        if cohort is None or cohort["opportunity_id"] != data["opportunity_id"]:
            raise CompetitionV2CorruptionError("Competition v2 receipt relationship is malformed")
        return data

    def get_authority_fingerprint(self, cohort_id):
        row = self._connection.execute("SELECT authority_fingerprint FROM competition_v2_cohorts WHERE cohort_id=?", (cohort_id,)).fetchone()
        return None if row is None else row["authority_fingerprint"]

    def get_publication(self, cohort_id):
        row = self._connection.execute("SELECT * FROM competition_v2_cohorts WHERE cohort_id=?", (cohort_id,)).fetchone()
        if row is None: return None
        try:
            cohort = _cohort_from_data(json.loads(row["cohort_json"]))
            if cohort.cohort_id != cohort_id: raise CompetitionV2CorruptionError("Competition v2 cohort identity mismatch")
            canonical = _canonical(cohort_to_data(cohort))
            if hashlib.sha256(canonical.encode("utf-8")).hexdigest() != row["authority_fingerprint"]:
                raise CompetitionV2CorruptionError("Competition v2 cohort fingerprint mismatch")
            stored_assessment = json.loads(row["assessment_json"])
            assessment = analyze_competition_v2(cohort, generated_at=datetime.fromisoformat(stored_assessment["generated_at"]))
            if _canonical(assessment_to_data(assessment)) != _canonical(stored_assessment):
                raise CompetitionV2CorruptionError("Competition v2 assessment does not reconcile to cohort")
            return CompetitionV2Publication(row["opportunity_id"], cohort, assessment, datetime.fromisoformat(row["committed_at"]))
        except CompetitionV2CorruptionError: raise
        except Exception as error: raise CompetitionV2CorruptionError("Competition v2 persisted state is malformed") from error

    def finalize(self, publication, command_id, command_fingerprint, authority_fingerprint, operator_id):
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute("INSERT INTO competition_v2_cohorts VALUES (?,?,?,?,?,?,?)",
                (publication.cohort.cohort_id, publication.opportunity_id, _canonical(cohort_to_data(publication.cohort)["subject"]),
                 authority_fingerprint, _canonical(cohort_to_data(publication.cohort)),
                 _canonical(assessment_to_data(publication.assessment)), publication.committed_at.isoformat()))
            self._connection.execute("INSERT INTO competition_v2_receipts VALUES (?,?,?,?,?,?)",
                (command_id, command_fingerprint, publication.cohort.cohort_id, publication.opportunity_id,
                 operator_id, publication.committed_at.isoformat()))
            self._connection.commit()
        except sqlite3.IntegrityError as error:
            self._connection.rollback(); raise CompetitionV2AdmissionConflictError("Competition v2 immutable authority conflicts") from error
        except Exception: self._connection.rollback(); raise

    def save_alias_receipt(self, command_id, fingerprint, cohort_id, opportunity_id, operator_id, committed_at):
        try:
            self._connection.execute("INSERT INTO competition_v2_receipts VALUES (?,?,?,?,?,?)",
                (command_id, fingerprint, cohort_id, opportunity_id, operator_id, committed_at.isoformat()))
            self._connection.commit()
        except sqlite3.IntegrityError as error:
            self._connection.rollback(); raise CompetitionV2AdmissionConflictError("Competition v2 alias receipt conflicts") from error


def _canonical(value): return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _subject(data):
    if data["kind"] == "new_to_market_domestic_selling_target":
        return NewToMarketDomesticSellingTargetIdentity(data["domestic_selling_target_id"])
    if data["kind"] != "market_observation": raise CompetitionV2CorruptionError("Competition v2 subject variant is malformed")
    return MarketObservationIdentity(MarketObservationScope(data["scope"]), data["market"], data["marketplace"],
        data["canonical_product_id"], data["marketplace_item_id"], data["normalized_query"], data["category"],
        data["variant_identity"], data["condition"], datetime.fromisoformat(data["window_started_at"]),
        datetime.fromisoformat(data["window_ended_at"]))


def _cohort_from_data(data):
    cards = tuple(CompetitionV2Card(v["result_ordinal"], ResultPlacement(v["placement"]), v["included"],
        v["is_comparable"], v["exclusion_reason"], v["marketplace_item_id"], v["raw_title"],
        None if v["displayed_price"] is None else Decimal(v["displayed_price"]), v["currency"], v["price_unit"],
        tuple(v["raw_rocket_labels"]), v["delivery_promise_text"],
        None if v["rocket_outcome"] is None else RocketObservationOutcome(v["rocket_outcome"]),
        Decimal(v["comparability_confidence"]), Decimal(v["price_confidence"]),
        None if v["rocket_label_confidence"] is None else Decimal(v["rocket_label_confidence"]),
        v["visible_seller_text"], v["visible_variant_count"], v["raw_payload_reference"], v["badge_color"], v["badge_icon"])
        for v in data["cards"])
    return CompetitionV2Cohort(data["cohort_id"], _subject(data["subject"]), data["market"], data["marketplace"],
        data["query"], data["category"], data["product_use"], data["category_form_factor"], data["condition"],
        data["locale"], data["result_surface"], datetime.fromisoformat(data["window_started_at"]),
        datetime.fromisoformat(data["window_ended_at"]), data["artifact_reference"], data["artifact_sha256"],
        data["bound_start"], data["bound_end"], data["operator_id"], cards, data["cohort_policy_version"],
        data["observation_schema_version"], data["collector_name"], data["collector_version"], data["source_schema_version"])
