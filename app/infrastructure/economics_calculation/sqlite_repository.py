"""Opportunity-scoped immutable EconomicsCalculation Snapshot persistence."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import sqlite3

from app.application.economics_calculation_snapshot import (
    EconomicsCalculationSnapshotBindingMismatchError,
    EconomicsCalculationSnapshotBindingNotFoundError,
    EconomicsCalculationSnapshotCommitError, EconomicsCalculationSnapshotConflictError,
    EconomicsCalculationSnapshotHistoryError, EconomicsCalculationSnapshotMarketIdentityConflictError,
    EconomicsCalculationSnapshotOpportunityNotFoundError,
    EconomicsCalculationSnapshotPriceSourceConflictError,
    EconomicsCalculationSnapshotPriceSourceNotFoundError,
    EconomicsCalculationSnapshotVerifiedSourceConflictError,
    EconomicsCalculationSnapshotVerifiedSourceNotFoundError,
    MalformedEconomicsCalculationSnapshotPersistenceError,
    UnsupportedEconomicsCalculationSnapshotVersionError,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.economics_calculation_snapshot import (
    ECONOMICS_ANALYSIS_SCHEMA_VERSION, ECONOMICS_CALCULATION_SNAPSHOT_SCHEMA_VERSION,
    CanonicalEconomicsAnalysisValue, EconomicsAnalysisSnapshot,
    EconomicsAnalysisValueKind, EconomicsCalculationParameters,
    EconomicsCalculationSnapshot, ProfitabilityResultSnapshot,
)
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.domain.opportunity import EconomicEvidence, EvidenceStatus, MoneyInput
from app.infrastructure.opportunity_validation import SQLiteCandidatePromotionRepository
from app.infrastructure.price_intelligence import SQLitePriceIntelligenceSnapshotRepository


_TABLE="""CREATE TABLE IF NOT EXISTS economics_calculation_snapshot_history(
 snapshot_id TEXT PRIMARY KEY, opportunity_id TEXT NOT NULL, discovery_reference TEXT NOT NULL,
 market_identity_payload_json TEXT NOT NULL, candidate_opportunity_binding_id TEXT NOT NULL,
 candidate_id TEXT NOT NULL, price_intelligence_snapshot_id TEXT NOT NULL,
 verified_economics_opportunity_id TEXT NOT NULL,
 calculation_results_payload_json TEXT NOT NULL, profitability_payload_json TEXT NOT NULL,
 calculation_parameters_payload_json TEXT NOT NULL, canonical_analysis_payload_json TEXT NOT NULL,
 analysis_fingerprint TEXT NOT NULL, analysis_schema_version TEXT NOT NULL,
 calculation_version TEXT NOT NULL, generated_at TEXT NOT NULL,
 snapshot_schema_version TEXT NOT NULL, payload_fingerprint TEXT NOT NULL, inserted_at TEXT NOT NULL,
 FOREIGN KEY(opportunity_id) REFERENCES opportunity_lifecycles(opportunity_id),
 FOREIGN KEY(candidate_opportunity_binding_id) REFERENCES opportunity_candidate_promotion_history(binding_id),
 FOREIGN KEY(candidate_id) REFERENCES opportunity_candidate_history(candidate_id),
 FOREIGN KEY(price_intelligence_snapshot_id) REFERENCES price_intelligence_snapshot_history(snapshot_id),
 FOREIGN KEY(verified_economics_opportunity_id) REFERENCES verified_economics_snapshots(opportunity_id))"""


def _dump(value):return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=True)
def _identity(value):return {"scope":value.scope.value,"market":value.market,"marketplace":value.marketplace,"canonical_product_id":value.canonical_product_id,"marketplace_item_id":value.marketplace_item_id,"normalized_query":value.normalized_query,"category":value.category,"variant_identity":value.variant_identity,"condition":value.condition,"window_started_at":value.window_started_at.isoformat(),"window_ended_at":value.window_ended_at.isoformat()}
def _evidence(value):return {"status":value.status.value,"source":value.source,"observed_at":value.observed_at.isoformat() if value.observed_at else None,"reference":value.reference}
def _money(value):return {"amount":str(value.amount) if value.amount is not None else None,"currency":value.currency,"evidence":_evidence(value.evidence)}
def _context(value):
    if value is None:return {"kind":"none"}
    if type(value) is bool:return {"kind":"bool","value":value}
    if type(value) is int:return {"kind":"int","value":value}
    if type(value) is float:return {"kind":"float","value":value}
    if isinstance(value,Decimal):return {"kind":"decimal","value":str(value)}
    if isinstance(value,str):return {"kind":"string","value":value}
    if isinstance(value,tuple):return {"kind":"tuple","items":[_context(item) for item in value]}
    raise TypeError("unsupported calculation context value")


def _parts(s):
    results={name:_money(getattr(s,name)) for name in ("revenue","marketplace_fee","payment_fee","tax_cost","landed_cost","selling_cost","total_cost","net_profit","break_even")}
    results.update(roi=str(s.roi),landed_cost_roi=str(s.landed_cost_roi),margin_rate=str(s.margin_rate))
    profitability={name:(str(getattr(s.profitability_result,name)) if name.startswith("minimum_") else getattr(s.profitability_result,name)) for name in s.profitability_result.__dataclass_fields__}
    parameters={"marketplace":s.calculation_parameters.marketplace,"minimum_net_profit":str(s.calculation_parameters.minimum_net_profit),"minimum_roi":str(s.calculation_parameters.minimum_roi),"estimated_monthly_sales":s.calculation_parameters.estimated_monthly_sales,"competitor_count":s.calculation_parameters.competitor_count,"risk_level":s.calculation_parameters.risk_level,"context_items":[[key,_context(value)] for key,value in s.calculation_parameters.context_items]}
    analysis={"analysis_version":s.analysis.analysis_version,"entries":[[key,value.fingerprint_value()] for key,value in s.analysis.entries]}
    return results,profitability,parameters,analysis


def _payload(s):
    results,profitability,parameters,analysis=_parts(s)
    return {"snapshot_id":s.snapshot_id,"opportunity":{"opportunity_id":s.opportunity_identity.opportunity_id,"discovery_reference":s.opportunity_identity.discovery_reference},"market_identity":_identity(s.market_observation_identity),"binding_id":s.candidate_opportunity_binding_id,"candidate_id":s.candidate_id,"price_source":s.price_intelligence_snapshot_id,"verified_source":s.verified_economics_opportunity_id,"results":results,"profitability":profitability,"parameters":parameters,"analysis":analysis,"analysis_fingerprint":s.analysis.fingerprint,"calculation_version":s.calculation_version,"generated_at":s.generated_at.isoformat(),"schema_version":s.schema_version}


def economics_snapshot_fingerprint(value):return hashlib.sha256(_dump(_payload(value)).encode("utf-8")).hexdigest()


class SQLiteEconomicsCalculationSnapshotRepository:
    def __init__(self,database_path=None,*,connection=None):
        if (database_path is None)==(connection is None):raise ValueError("provide exactly one database_path or connection")
        self._owns_connection=connection is None
        if connection is None:
            path=Path(database_path);path.parent.mkdir(parents=True,exist_ok=True);connection=sqlite3.connect(path,timeout=30,check_same_thread=False)
        self._connection=connection;connection.row_factory=sqlite3.Row;connection.execute("PRAGMA foreign_keys = ON")
        self._sources=SQLiteCandidatePromotionRepository(connection=connection)
        self._prices=SQLitePriceIntelligenceSnapshotRepository(connection=connection)
        with connection:
            connection.execute(_TABLE)
            for operation in ("UPDATE","DELETE"):
                connection.execute(f"""CREATE TRIGGER IF NOT EXISTS trg_economics_calculation_snapshot_no_{operation.lower()}
                BEFORE {operation} ON economics_calculation_snapshot_history
                BEGIN SELECT RAISE(ABORT,'economics calculation snapshot history is append-only'); END""")
            connection.execute("CREATE INDEX IF NOT EXISTS idx_economics_snapshot_opportunity ON economics_calculation_snapshot_history(opportunity_id,generated_at,snapshot_id)")
    def _begin(self):
        try:self._connection.execute("BEGIN IMMEDIATE")
        except sqlite3.Error as error:raise EconomicsCalculationSnapshotCommitError("Economics Snapshot transaction could not start") from error
    def _commit(self):self._connection.commit()
    def _rollback(self):
        if self._connection.in_transaction:self._connection.rollback()

    def save_snapshot(self,snapshot):
        if not isinstance(snapshot,EconomicsCalculationSnapshot):raise TypeError("snapshot must be EconomicsCalculationSnapshot")
        if snapshot.schema_version!=ECONOMICS_CALCULATION_SNAPSHOT_SCHEMA_VERSION or snapshot.analysis.analysis_version!=ECONOMICS_ANALYSIS_SCHEMA_VERSION:
            raise UnsupportedEconomicsCalculationSnapshotVersionError("unsupported Economics Snapshot version")
        fingerprint=economics_snapshot_fingerprint(snapshot);self._begin()
        try:
            row=self._connection.execute("SELECT payload_fingerprint FROM economics_calculation_snapshot_history WHERE snapshot_id=?",(snapshot.snapshot_id,)).fetchone()
            if row:
                if row[0]!=fingerprint:raise EconomicsCalculationSnapshotConflictError("Economics Snapshot ID payload conflicts")
                result=self.get_snapshot(snapshot.snapshot_id);self._rollback();return result
            binding=self._validate_lineage(snapshot)
            try:self._insert(snapshot,binding.candidate_id,fingerprint)
            except sqlite3.Error as error:raise EconomicsCalculationSnapshotHistoryError("Economics Snapshot history insert failed") from error
            try:self._commit()
            except sqlite3.Error as error:raise EconomicsCalculationSnapshotCommitError("Economics Snapshot commit failed") from error
            return snapshot
        except Exception:self._rollback();raise

    def _validate_lineage(self,s):
        lifecycle=self._sources.get(s.opportunity_identity.opportunity_id)
        if lifecycle is None:raise EconomicsCalculationSnapshotOpportunityNotFoundError("Opportunity lifecycle is missing")
        if lifecycle.discovery_reference!=s.opportunity_identity.discovery_reference:raise EconomicsCalculationSnapshotBindingMismatchError("Opportunity discovery reference differs")
        binding=self._sources.get_promotion_by_opportunity(s.opportunity_identity.opportunity_id)
        if binding is None:raise EconomicsCalculationSnapshotBindingNotFoundError("Candidate Opportunity binding is missing")
        if binding.binding_id!=s.candidate_opportunity_binding_id or binding.candidate_id!=s.candidate_id or binding.discovery_reference!=s.opportunity_identity.discovery_reference:
            raise EconomicsCalculationSnapshotBindingMismatchError("Candidate Opportunity binding differs")
        if binding.market_observation_identity!=s.market_observation_identity:
            raise EconomicsCalculationSnapshotMarketIdentityConflictError("Economics Market identity differs from binding")
        price=self._prices.get_snapshot(s.price_intelligence_snapshot_id)
        if price is None:raise EconomicsCalculationSnapshotPriceSourceNotFoundError("Price Snapshot source is missing")
        if price.candidate_identity.candidate_id!=s.candidate_id or price.market_observation_identity!=s.market_observation_identity:
            raise EconomicsCalculationSnapshotPriceSourceConflictError("Price Snapshot source lineage differs")
        verified=self._sources.get_verified_economics_snapshot(s.verified_economics_opportunity_id)
        if verified is None:raise EconomicsCalculationSnapshotVerifiedSourceNotFoundError("Verified Economics source is missing")
        if verified.opportunity_id!=s.opportunity_identity.opportunity_id or s.verified_economics_opportunity_id!=s.opportunity_identity.opportunity_id:
            raise EconomicsCalculationSnapshotVerifiedSourceConflictError("Verified Economics Opportunity differs")
        if s.analysis.fingerprint!=EconomicsAnalysisSnapshot(s.analysis.entries,s.analysis.analysis_version).fingerprint:
            raise MalformedEconomicsCalculationSnapshotPersistenceError("canonical analysis fingerprint differs")
        return binding

    def _insert(self,s,candidate_id,fingerprint):
        results,profitability,parameters,analysis=_parts(s)
        self._connection.execute("INSERT INTO economics_calculation_snapshot_history VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (s.snapshot_id,s.opportunity_identity.opportunity_id,s.opportunity_identity.discovery_reference,_dump(_identity(s.market_observation_identity)),s.candidate_opportunity_binding_id,candidate_id,s.price_intelligence_snapshot_id,s.verified_economics_opportunity_id,_dump(results),_dump(profitability),_dump(parameters),_dump(analysis),s.analysis.fingerprint,s.analysis.analysis_version,s.calculation_version,s.generated_at.isoformat(),s.schema_version,fingerprint,datetime.now(timezone.utc).isoformat()))

    def get_snapshot(self,snapshot_id):
        try:row=self._connection.execute("SELECT * FROM economics_calculation_snapshot_history WHERE snapshot_id=?",(snapshot_id,)).fetchone()
        except sqlite3.Error as error:raise EconomicsCalculationSnapshotHistoryError("Economics Snapshot query failed") from error
        return None if row is None else self._from_row(row)
    def get_by_opportunity(self,identity):
        if not isinstance(identity,OpportunityIdentity):raise TypeError("opportunity_identity must be OpportunityIdentity")
        try:rows=self._connection.execute("SELECT * FROM economics_calculation_snapshot_history WHERE opportunity_id=? ORDER BY generated_at,snapshot_id",(identity.opportunity_id,)).fetchall()
        except sqlite3.Error as error:raise EconomicsCalculationSnapshotHistoryError("Economics Opportunity query failed") from error
        values=tuple(self._from_row(row) for row in rows)
        if any(value.opportunity_identity!=identity for value in values):raise EconomicsCalculationSnapshotBindingMismatchError("persisted Opportunity differs")
        return values
    def get_by_market_identity(self,identity):
        if not isinstance(identity,MarketObservationIdentity):raise TypeError("market_observation_identity must be MarketObservationIdentity")
        try:rows=self._connection.execute("SELECT * FROM economics_calculation_snapshot_history WHERE market_identity_payload_json=? ORDER BY generated_at,snapshot_id",(_dump(_identity(identity)),)).fetchall()
        except sqlite3.Error as error:raise EconomicsCalculationSnapshotHistoryError("Economics Market query failed") from error
        return tuple(self._from_row(row) for row in rows)
    def get_by_verified_economics_source(self,opportunity_id):
        try:rows=self._connection.execute("SELECT * FROM economics_calculation_snapshot_history WHERE verified_economics_opportunity_id=? ORDER BY generated_at,snapshot_id",(opportunity_id,)).fetchall()
        except sqlite3.Error as error:raise EconomicsCalculationSnapshotHistoryError("Verified source query failed") from error
        return tuple(self._from_row(row) for row in rows)

    def _from_row(self,row):
        try:
            if row["snapshot_schema_version"]!=ECONOMICS_CALCULATION_SNAPSHOT_SCHEMA_VERSION or row["analysis_schema_version"]!=ECONOMICS_ANALYSIS_SCHEMA_VERSION:raise UnsupportedEconomicsCalculationSnapshotVersionError("unsupported persisted Economics Snapshot version")
            i=json.loads(row["market_identity_payload_json"]);results=json.loads(row["calculation_results_payload_json"]);profit=json.loads(row["profitability_payload_json"]);params=json.loads(row["calculation_parameters_payload_json"]);analysis_data=json.loads(row["canonical_analysis_payload_json"])
            identity=MarketObservationIdentity(scope=MarketObservationScope(i["scope"]),market=i["market"],marketplace=i["marketplace"],canonical_product_id=i["canonical_product_id"],marketplace_item_id=i["marketplace_item_id"],normalized_query=i["normalized_query"],category=i["category"],variant_identity=i["variant_identity"],condition=i["condition"],window_started_at=datetime.fromisoformat(i["window_started_at"]),window_ended_at=datetime.fromisoformat(i["window_ended_at"]))
            money={name:_money_from(results[name]) for name in ("revenue","marketplace_fee","payment_fee","tax_cost","landed_cost","selling_cost","total_cost","net_profit","break_even")}
            profitability=ProfitabilityResultSnapshot(Decimal(profit["minimum_net_profit"]),Decimal(profit["minimum_roi"]),profit["passes_net_profit_filter"],profit["passes_roi_filter"],profit["passes_profitability_filter"])
            parameters=EconomicsCalculationParameters(params["marketplace"],Decimal(params["minimum_net_profit"]),Decimal(params["minimum_roi"]),params["estimated_monthly_sales"],params["competitor_count"],params["risk_level"],tuple((key,_context_from(value)) for key,value in params["context_items"]))
            analysis=EconomicsAnalysisSnapshot(tuple((key,_analysis_from(value)) for key,value in analysis_data["entries"]),analysis_data["analysis_version"],row["analysis_fingerprint"])
            value=EconomicsCalculationSnapshot(row["snapshot_id"],OpportunityIdentity(row["opportunity_id"],row["discovery_reference"]),identity,row["candidate_opportunity_binding_id"],row["candidate_id"],row["price_intelligence_snapshot_id"],row["verified_economics_opportunity_id"],money["revenue"],money["marketplace_fee"],money["payment_fee"],money["tax_cost"],money["landed_cost"],money["selling_cost"],money["total_cost"],money["net_profit"],Decimal(results["roi"]),Decimal(results["landed_cost_roi"]),Decimal(results["margin_rate"]),money["break_even"],profitability,parameters,analysis,row["calculation_version"],datetime.fromisoformat(row["generated_at"]),row["snapshot_schema_version"])
            if economics_snapshot_fingerprint(value)!=row["payload_fingerprint"]:raise ValueError("Economics Snapshot fingerprint mismatch")
            return value
        except UnsupportedEconomicsCalculationSnapshotVersionError:raise
        except (json.JSONDecodeError,KeyError,TypeError,ValueError,InvalidOperation) as error:raise MalformedEconomicsCalculationSnapshotPersistenceError("persisted Economics Snapshot is malformed") from error
    def close(self):
        if self._owns_connection:self._connection.close()
    def __enter__(self):return self
    def __exit__(self,*_):self.close()


def _money_from(value):
    e=value["evidence"];observed=datetime.fromisoformat(e["observed_at"]) if e["observed_at"] else None
    return MoneyInput(Decimal(value["amount"]) if value["amount"] is not None else None,value["currency"],EconomicEvidence(EvidenceStatus(e["status"]),e["source"],observed,e["reference"]))
def _context_from(value):
    kind=value["kind"]
    if kind=="none":return None
    if kind=="decimal":return Decimal(value["value"])
    if kind=="tuple":return tuple(_context_from(item) for item in value["items"])
    expected={"bool":bool,"int":int,"float":float,"string":str}[kind]
    if type(value["value"]) is not expected:raise TypeError("malformed context scalar")
    return value["value"]
def _analysis_from(value):
    kind=EconomicsAnalysisValueKind(value["kind"]);scalar=value["scalar"]
    if kind is EconomicsAnalysisValueKind.DECIMAL and scalar is not None:scalar=Decimal(scalar)
    if kind is EconomicsAnalysisValueKind.DATETIME and scalar is not None:scalar=datetime.fromisoformat(scalar)
    return CanonicalEconomicsAnalysisValue(kind,scalar,tuple(_analysis_from(item) for item in value["items"]),tuple((key,_analysis_from(item)) for key,item in value["entries"]),value["enum_type"],_analysis_from(value["enum_value"]) if value["enum_value"] is not None else None)
