from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json
import re
import sqlite3

from app.application.demand_v2_admission import (
    DemandV2AdmissionConflictError,
    DemandV2Publication,
)
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.domain.market_intelligence.demand_v2 import (
    CompetitionCohortReference,
    DemandArtifactReference,
    DemandComparableCard,
    DemandComparableCohort,
    DemandComparableCohortManifest,
    DemandEvidenceOutcome,
    DemandResultPlacement,
    DemandV2Observation,
    ListingRatingEvidence,
    ListingReviewEvidence,
    MarketIntentEvidence,
    ProviderFieldKind,
    ProviderSignalEvidence,
    QueryMatchSemantics,
    analyze_demand_v2,
    assessment_to_data,
    observation_to_data,
)
from app.domain.opportunity import NewToMarketDomesticSellingTargetIdentity


_HASH = re.compile(r"^[0-9a-f]{64}$")
_OBJECTS = {
    "demand_v2_publications": "table", "demand_v2_current": "table", "demand_v2_receipts": "table",
    "trg_demand_v2_publications_no_update": "trigger", "trg_demand_v2_publications_no_delete": "trigger",
    "trg_demand_v2_receipts_no_update": "trigger", "trg_demand_v2_receipts_no_delete": "trigger",
}
_SCHEMA = """
CREATE TABLE demand_v2_publications (
 observation_id TEXT PRIMARY KEY, assessment_id TEXT NOT NULL UNIQUE, cohort_id TEXT NOT NULL UNIQUE,
 opportunity_id TEXT NOT NULL, subject_key TEXT NOT NULL, authority_fingerprint TEXT NOT NULL UNIQUE,
 observation_fingerprint TEXT NOT NULL, authority_json TEXT NOT NULL, observation_json TEXT NOT NULL,
 assessment_json TEXT NOT NULL, generated_at TEXT NOT NULL, committed_at TEXT NOT NULL);
CREATE TABLE demand_v2_current (
 subject_key TEXT PRIMARY KEY, observation_id TEXT NOT NULL, assessment_id TEXT NOT NULL,
 generated_at TEXT NOT NULL, FOREIGN KEY(observation_id) REFERENCES demand_v2_publications(observation_id));
CREATE TABLE demand_v2_receipts (
 command_id TEXT PRIMARY KEY, command_fingerprint TEXT NOT NULL, authority_fingerprint TEXT NOT NULL,
 observation_id TEXT NOT NULL, opportunity_id TEXT NOT NULL, operator_id TEXT NOT NULL,
 committed_at TEXT NOT NULL, FOREIGN KEY(observation_id) REFERENCES demand_v2_publications(observation_id));
CREATE TRIGGER trg_demand_v2_publications_no_update BEFORE UPDATE ON demand_v2_publications BEGIN SELECT RAISE(ABORT, 'demand v2 publications are append-only'); END;
CREATE TRIGGER trg_demand_v2_publications_no_delete BEFORE DELETE ON demand_v2_publications BEGIN SELECT RAISE(ABORT, 'demand v2 publications are append-only'); END;
CREATE TRIGGER trg_demand_v2_receipts_no_update BEFORE UPDATE ON demand_v2_receipts BEGIN SELECT RAISE(ABORT, 'demand v2 receipts are append-only'); END;
CREATE TRIGGER trg_demand_v2_receipts_no_delete BEFORE DELETE ON demand_v2_receipts BEGIN SELECT RAISE(ABORT, 'demand v2 receipts are append-only'); END;
"""


class DemandV2PersistenceError(RuntimeError): pass
class DemandV2CorruptionError(ValueError): pass


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class SQLiteDemandV2Repository:
    def __init__(self, database) -> None:
        self._connection = sqlite3.connect(database, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._ensure_schema()

    def close(self):
        self._connection.close()

    def _ensure_schema(self) -> None:
        rows = self._connection.execute(
            "SELECT name,type FROM sqlite_master WHERE name IN (%s)" % ",".join("?" for _ in _OBJECTS),
            tuple(_OBJECTS),
        ).fetchall()
        found = {row["name"]: row["type"] for row in rows}
        if found == _OBJECTS:
            return
        if found:
            raise DemandV2PersistenceError("partial Demand v2 schema is malformed")
        self._connection.executescript(_SCHEMA)

    def get_receipt(self, command_id):
        row = self._connection.execute("SELECT * FROM demand_v2_receipts WHERE command_id=?", (command_id,)).fetchone()
        if row is None:
            return None
        data = dict(row)
        if not _HASH.fullmatch(data["command_fingerprint"]) or not _HASH.fullmatch(data["authority_fingerprint"]):
            raise DemandV2CorruptionError("Demand v2 receipt fingerprint is malformed")
        publication = self._connection.execute(
            "SELECT opportunity_id,authority_fingerprint FROM demand_v2_publications WHERE observation_id=?",
            (data["observation_id"],),
        ).fetchone()
        if publication is None or publication["opportunity_id"] != data["opportunity_id"] or publication["authority_fingerprint"] != data["authority_fingerprint"]:
            raise DemandV2CorruptionError("Demand v2 receipt relationship is malformed")
        return data

    def get_publication_by_authority_fingerprint(self, fingerprint):
        row = self._connection.execute(
            "SELECT observation_id FROM demand_v2_publications WHERE authority_fingerprint=?", (fingerprint,),
        ).fetchone()
        return None if row is None else self.get_publication(row["observation_id"])

    def get_publication(self, observation_id):
        row = self._connection.execute("SELECT * FROM demand_v2_publications WHERE observation_id=?", (observation_id,)).fetchone()
        if row is None:
            return None
        try:
            authority = json.loads(row["authority_json"])
            if _digest(authority) != row["authority_fingerprint"]:
                raise DemandV2CorruptionError("Demand v2 authority fingerprint mismatch")
            observation_data = json.loads(row["observation_json"])
            if _digest(observation_data) != row["observation_fingerprint"]:
                raise DemandV2CorruptionError("Demand v2 observation fingerprint mismatch")
            observation = _observation_from_data(observation_data)
            if observation.observation_id != observation_id or observation.comparable_cohort.cohort_id != row["cohort_id"]:
                raise DemandV2CorruptionError("Demand v2 persisted identity mismatch")
            stored_assessment = json.loads(row["assessment_json"])
            assessment = analyze_demand_v2(
                observation, assessment_id=row["assessment_id"],
                generated_at=datetime.fromisoformat(row["generated_at"]),
            )
            if _canonical(assessment_to_data(assessment)) != _canonical(stored_assessment):
                raise DemandV2CorruptionError("Demand v2 assessment does not reconcile to raw authority")
            if row["subject_key"] != _canonical(observation_to_data(observation)["subject"]):
                raise DemandV2CorruptionError("Demand v2 subject key mismatch")
            return DemandV2Publication(
                row["opportunity_id"], observation, assessment,
                datetime.fromisoformat(row["generated_at"]), datetime.fromisoformat(row["committed_at"]),
            )
        except DemandV2CorruptionError:
            raise
        except Exception as error:
            raise DemandV2CorruptionError("Demand v2 persisted state is malformed") from error

    def get_current_publication(self, subject):
        key = _canonical(_subject_data(subject))
        row = self._connection.execute("SELECT * FROM demand_v2_current WHERE subject_key=?", (key,)).fetchone()
        if row is None:
            return None
        publication = self.get_publication(row["observation_id"])
        if publication is None or publication.assessment.assessment_id != row["assessment_id"] or publication.generated_at.isoformat() != row["generated_at"]:
            raise DemandV2CorruptionError("Demand v2 current projection is malformed")
        return publication

    def finalize(self, publication, command_id, command_fingerprint, authority_fingerprint, authority_data, operator_id):
        observation_data = observation_to_data(publication.observation)
        assessment_data = assessment_to_data(publication.assessment)
        subject_key = _canonical(observation_data["subject"])
        try:
            self._connection.execute("BEGIN IMMEDIATE")
            self._connection.execute(
                "INSERT INTO demand_v2_publications VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (publication.observation.observation_id, publication.assessment.assessment_id,
                 publication.observation.comparable_cohort.cohort_id, publication.opportunity_id, subject_key,
                 authority_fingerprint, _digest(observation_data), _canonical(authority_data),
                 _canonical(observation_data), _canonical(assessment_data), publication.generated_at.isoformat(),
                 publication.committed_at.isoformat()),
            )
            self._connection.execute(
                "INSERT INTO demand_v2_current VALUES (?,?,?,?) ON CONFLICT(subject_key) DO UPDATE SET "
                "observation_id=excluded.observation_id, assessment_id=excluded.assessment_id, generated_at=excluded.generated_at "
                "WHERE excluded.generated_at >= demand_v2_current.generated_at",
                (subject_key, publication.observation.observation_id, publication.assessment.assessment_id,
                 publication.generated_at.isoformat()),
            )
            self._connection.execute(
                "INSERT INTO demand_v2_receipts VALUES (?,?,?,?,?,?,?)",
                (command_id, command_fingerprint, authority_fingerprint, publication.observation.observation_id,
                 publication.opportunity_id, operator_id, publication.committed_at.isoformat()),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as error:
            self._connection.rollback()
            raise DemandV2AdmissionConflictError("Demand v2 immutable authority conflicts") from error
        except Exception:
            self._connection.rollback()
            raise

    def save_alias_receipt(self, command_id, command_fingerprint, authority_fingerprint, observation_id, opportunity_id, operator_id, committed_at):
        try:
            self._connection.execute(
                "INSERT INTO demand_v2_receipts VALUES (?,?,?,?,?,?,?)",
                (command_id, command_fingerprint, authority_fingerprint, observation_id,
                 opportunity_id, operator_id, committed_at.isoformat()),
            )
            self._connection.commit()
        except sqlite3.IntegrityError as error:
            self._connection.rollback()
            raise DemandV2AdmissionConflictError("Demand v2 alias receipt conflicts") from error


def _subject_data(subject):
    from app.domain.market_intelligence.competition_v2 import subject_to_data
    return subject_to_data(subject)


def _subject(data):
    if data["kind"] == "new_to_market_domestic_selling_target":
        return NewToMarketDomesticSellingTargetIdentity(data["domestic_selling_target_id"])
    if data["kind"] != "market_observation":
        raise DemandV2CorruptionError("Demand v2 subject variant is malformed")
    return MarketObservationIdentity(
        MarketObservationScope(data["scope"]), data["market"], data["marketplace"],
        data["canonical_product_id"], data["marketplace_item_id"], data["normalized_query"],
        data["category"], data["variant_identity"], data["condition"],
        datetime.fromisoformat(data["window_started_at"]), datetime.fromisoformat(data["window_ended_at"]),
    )


def _artifact(data):
    return DemandArtifactReference(data["reference"], data["sha256"], data["schema_version"])


def _competition_reference(data):
    if data is None:
        return None
    return CompetitionCohortReference(
        data["competition_observation_id"], data["observation_identity_kind"],
        data["observation_identity_version"], data["cohort_id"], data["authority_fingerprint"],
        data["observation_schema_version"], data["cohort_policy_version"],
        data["artifact_reference"], data["artifact_sha256"],
    )


def _observation_from_data(data):
    subject = _subject(data["subject"])
    intent = data["market_intent"]
    market_intent = MarketIntentEvidence(
        intent["provider"], intent["provider_field_name"], intent["provider_schema_version"],
        ProviderFieldKind(intent["provider_field_kind"]), intent["query"], intent["market"],
        intent["geography"], intent["locale"], QueryMatchSemantics(intent["match_semantics"]),
        (datetime.fromisoformat(intent["period_started_at"])
         if intent.get("period_started_at") is not None else None),
        (datetime.fromisoformat(intent["period_ended_at"])
         if intent.get("period_ended_at") is not None else None),
        intent["unit"], intent["value"], intent["source"], intent["reference"], _artifact(intent["artifact"]),
        intent["collection_method"], datetime.fromisoformat(intent["observed_at"]),
        DemandEvidenceOutcome(intent["outcome"]), Decimal(intent["confidence"]), intent["reason"],
        intent["collector_name"], intent["collector_version"], intent["category"],
        intent["device_scope"], intent["result_surface"], intent["schema_version"],
        intent.get("provider_returned_query"), intent.get("provider_period_label"),
    )
    cohort_data = data["comparable_cohort"]
    manifest_data = cohort_data["manifest"]
    cards = tuple(DemandComparableCard(
        value["result_ordinal"], DemandResultPlacement(value["placement"]), value["included"],
        value["is_comparable"], value["exclusion_reason"], value["marketplace_item_id"],
        value["observation_reference"], value["raw_title"], value["visible_variant_count"],
    ) for value in manifest_data["cards"])
    manifest = DemandComparableCohortManifest(
        subject, manifest_data["market"], manifest_data["marketplace"], manifest_data["query"],
        manifest_data["category"], manifest_data["product_use"], manifest_data["category_form_factor"],
        manifest_data["condition"], manifest_data["locale"], manifest_data["result_surface"],
        datetime.fromisoformat(manifest_data["window_started_at"]), datetime.fromisoformat(manifest_data["window_ended_at"]),
        _artifact(manifest_data["artifact"]), manifest_data["bound_start"], manifest_data["bound_end"],
        manifest_data["operator_id"], cards, _competition_reference(manifest_data["source_competition_cohort"]),
        manifest_data["schema_version"],
    )
    reviews = tuple(ListingReviewEvidence(
        value["result_ordinal"], value["listing_reference"], value["value"],
        DemandEvidenceOutcome(value["outcome"]), Decimal(value["confidence"]), value["source"],
        value["reference"], _artifact(value["artifact"]), value["collection_method"],
        datetime.fromisoformat(value["observed_at"]), value["reason"],
    ) for value in data["reviews"])
    ratings = tuple(ListingRatingEvidence(
        value["result_ordinal"], value["listing_reference"], None if value["value"] is None else Decimal(value["value"]),
        Decimal(value["scale_min"]), Decimal(value["scale_max"]), DemandEvidenceOutcome(value["outcome"]),
        Decimal(value["confidence"]), value["source"], value["reference"], _artifact(value["artifact"]),
        value["collection_method"], datetime.fromisoformat(value["observed_at"]), value["reason"],
    ) for value in data["ratings"])
    signals = tuple(ProviderSignalEvidence(
        value["signal_name"], value["provider"], value["provider_field_name"], value["provider_schema_version"],
        value["population"], value["result_surface"], value["query"], value["category"],
        value["geography"], value["locale"], datetime.fromisoformat(value["period_started_at"]),
        datetime.fromisoformat(value["period_ended_at"]), value["directionality"], value["tie_semantics"],
        value["value"], value["unit"], DemandEvidenceOutcome(value["outcome"]), Decimal(value["confidence"]),
        value["source"], value["reference"], _artifact(value["artifact"]), value["collection_method"],
        datetime.fromisoformat(value["observed_at"]), value["reason"], value["collection_method_version"],
    ) for value in data["provider_signals"])
    return DemandV2Observation(
        data["observation_id"], subject, market_intent,
        DemandComparableCohort(cohort_data["cohort_id"], manifest), reviews, ratings, signals,
        DemandEvidenceOutcome(data["target_traction_outcome"]), datetime.fromisoformat(data["observed_at"]),
        data["schema_version"],
    )
