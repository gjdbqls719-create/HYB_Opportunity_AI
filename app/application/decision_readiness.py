from __future__ import annotations

from app.application.decision_composition import ASSESSMENT_SCHEMA_VERSION, COMPETITION_POLICY_VERSION, DEMAND_POLICY_VERSION, EXTERNAL_SIGNAL_SCHEMA_VERSION
from app.application.production_safety_snapshot import PRODUCTION_SAFETY_SNAPSHOT_SCHEMA_VERSION
from app.application.verified_economics_snapshot import VERIFIED_ECONOMICS_SNAPSHOT_SCHEMA_VERSION


class DecisionReadinessNotFoundError(LookupError): pass


class DecisionReadinessService:
    def __init__(self, sources, assessments, reviews, safety_evaluations=None):
        self._sources, self._assessments, self._reviews = sources, assessments, reviews
        self._safety_evaluations = safety_evaluations

    def execute(self, opportunity_id: str) -> dict[str, object]:
        if self._sources.get_queue_item(opportunity_id) is None:
            raise DecisionReadinessNotFoundError(opportunity_id)
        blockers=[]; states={}
        def missing(name, reason):
            states[name]={"status":"missing","description":reason}; blockers.append(reason)
        try:
            market_binding=self._sources.get_market_identity_binding(opportunity_id)
            if market_binding is None: missing("opportunity_market_identity","Opportunity Market Identity binding is missing.")
            else: states["opportunity_market_identity"]={"status":"ready","description":"Authoritative Opportunity Market Identity is available."}
        except Exception:
            market_binding=None; states["opportunity_market_identity"]={"status":"error","description":"Opportunity Market Identity could not be validated."};blockers.append(states["opportunity_market_identity"]["description"])
        try:
            bindings=self._reviews.list_opportunity_bindings(opportunity_id)
            if not bindings: missing("opportunity_review_binding","Opportunity–Review binding is missing.")
            elif market_binding is not None and any(v.market_observation_identity != market_binding.market_observation_identity for v in bindings):
                states["opportunity_review_binding"]={"status":"error","description":"Review binding identity conflicts with the Opportunity."};blockers.append(states["opportunity_review_binding"]["description"])
            else: states["opportunity_review_binding"]={"status":"ready","description":"Authoritative Opportunity–Review binding is available."}
        except Exception:
            states["opportunity_review_binding"]={"status":"error","description":"Opportunity–Review binding could not be validated."};blockers.append(states["opportunity_review_binding"]["description"])
        identity=market_binding.market_observation_identity if market_binding else None
        self._snapshot(states, blockers, "verified_economics", lambda:self._sources.get_verified_economics_snapshot(opportunity_id),
            lambda v:v.opportunity_id==opportunity_id and v.schema_version==VERIFIED_ECONOMICS_SNAPSHOT_SCHEMA_VERSION, "Verified Economics snapshot is missing.")
        if self._safety_evaluations is None:
            safety_load=lambda:self._sources.get_production_safety_snapshot(opportunity_id)
            safety_validate=lambda v:v.opportunity_id==opportunity_id and v.schema_version==PRODUCTION_SAFETY_SNAPSHOT_SCHEMA_VERSION and v.rule_version=="production-safety-v1"
        else:
            from app.application.production_safety_evaluation import PRODUCTION_SAFETY_EVALUATION_RULE_VERSION,PRODUCTION_SAFETY_EVALUATION_SCHEMA_VERSION
            safety_load=lambda:self._safety_evaluations.get_current_production_safety_evaluation(opportunity_id)
            safety_validate=lambda v:v.opportunity_id==opportunity_id and v.schema_version==PRODUCTION_SAFETY_EVALUATION_SCHEMA_VERSION and v.rule_version==PRODUCTION_SAFETY_EVALUATION_RULE_VERSION
        self._snapshot(states, blockers, "production_safety", safety_load,
            safety_validate, "Operational Production Safety evaluation is missing." if self._safety_evaluations is not None else "Production Safety snapshot is missing.")
        self._snapshot(states, blockers, "competition_assessment", lambda:self._assessments.get_latest_competition_assessment_snapshot(identity) if identity else None,
            lambda v:v.identity==identity and v.schema_version==ASSESSMENT_SCHEMA_VERSION and v.policy_version==COMPETITION_POLICY_VERSION, "Competition assessment snapshot is missing.")
        self._snapshot(states, blockers, "demand_assessment", lambda:self._assessments.get_latest_demand_assessment_snapshot(identity) if identity else None,
            lambda v:v.identity==identity and v.schema_version==ASSESSMENT_SCHEMA_VERSION and v.policy_version==DEMAND_POLICY_VERSION, "Demand assessment snapshot is missing.")
        try:
            ids=self._sources.get_bound_review_external_signal_ids(opportunity_id)
            if ids:
                signals=self._assessments.get_human_verified_external_signals_by_ids(identity,ids)
                valid=len(signals)==len(ids) and all(v.identity==identity and v.schema_version==EXTERNAL_SIGNAL_SCHEMA_VERSION for v in signals)
                states["external_signals"]={"status":"ready" if valid else "error","description":"Bound HUMAN_VERIFIED External Signals are available." if valid else "Bound External Signals could not be validated."}
                if not valid: blockers.append(states["external_signals"]["description"])
            else: states["external_signals"]={"status":"optional","description":"No bound External Signal is selected; Decision finalization permits none."}
        except Exception:
            states["external_signals"]={"status":"error","description":"External Signals could not be validated."};blockers.append(states["external_signals"]["description"])
        try:
            composition=self._sources.get_latest_decision_composition(opportunity_id)
            states["composition"]={"status":"finalized" if composition else "not_finalized","description":"A finalized Decision Composition is available." if composition else "Decision Composition has not been finalized."}
            version=composition.composition_version if composition else None
        except Exception:
            states["composition"]={"status":"error","description":"Decision Composition could not be read."};blockers.append(states["composition"]["description"]);version=None
        required=("opportunity_market_identity","opportunity_review_binding","verified_economics","production_safety","competition_assessment","demand_assessment")
        return {"opportunity_id":opportunity_id,"sources":states,"latest_composition_version":version,
            "finalize_allowed":all(states[name]["status"]=="ready" for name in required) and states["external_signals"]["status"] in {"ready","optional"},
            "blocking_reasons":blockers}

    @staticmethod
    def _snapshot(states, blockers, name, load, validate, missing_reason):
        try:
            value=load()
            if value is None: states[name]={"status":"missing","description":missing_reason};blockers.append(missing_reason)
            elif not validate(value): states[name]={"status":"error","description":f"{name.replace('_',' ').title()} has unsupported version or identity."};blockers.append(states[name]["description"])
            else: states[name]={"status":"ready","description":f"{name.replace('_',' ').title()} is available."}
        except Exception:
            states[name]={"status":"error","description":f"{name.replace('_',' ').title()} could not be validated."};blockers.append(states[name]["description"])
