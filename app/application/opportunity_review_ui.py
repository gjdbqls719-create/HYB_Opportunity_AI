from __future__ import annotations

from app.application.review_api import ReviewSessionResponseDTO
from app.domain.opportunity import OpportunityLifecycleStatus


def _identity(value):
    return {"scope": value.scope.value, "market": value.market, "marketplace": value.marketplace,
        "canonical_product_id": value.canonical_product_id, "marketplace_item_id": value.marketplace_item_id,
        "normalized_query": value.normalized_query, "category": value.category,
        "variant_identity": value.variant_identity, "condition": value.condition,
        "window_started_at": value.window_started_at.isoformat(), "window_ended_at": value.window_ended_at.isoformat()}


class OpportunityReviewUIQueryService:
    def __init__(self, opportunities, reviews, candidates, observations=None):
        self._opportunities, self._reviews, self._candidates = opportunities, reviews, candidates
        self._observations = observations

    def list(self) -> dict[str, object]:
        items = self._opportunities.list_queue(statuses=tuple(OpportunityLifecycleStatus), limit=100)
        return {"items": [self._summary(item) for item in items], "total_count": len(items)}

    def detail(self, opportunity_id: str) -> dict[str, object] | None:
        item = self._opportunities.get_queue_item(opportunity_id)
        if item is None: return None
        market = self._opportunities.get_market_identity_binding(opportunity_id)
        bindings = self._reviews.list_opportunity_bindings(opportunity_id)
        review = self._reviews.get(bindings[0].session_id) if bindings else None
        economics = self._opportunities.get_verified_economics_snapshot(opportunity_id)
        competition = (self._observations.get_latest_competition_assessment_snapshot(
            market.market_observation_identity) if self._observations is not None and market else None)
        competition_observation = (self._observations.get_observation_by_id(
            competition.source_observation_id) if competition and self._observations is not None else None)
        return {**self._summary(item),
            "market_identity": _identity(market.market_observation_identity) if market else None,
            "review": ReviewSessionResponseDTO.from_session(review).to_dict() if review else None,
            "verified_economics": self._economics(economics) if economics else None,
            "competition_assessment": self._competition(competition, competition_observation) if competition else None,
            "candidates": [self._candidate(value) for value in self._candidates.list_candidates()]}

    @staticmethod
    def _competition(snapshot, observation):
        value = snapshot.assessment
        return {"snapshot_id": snapshot.snapshot_id, "source_observation_id": snapshot.source_observation_id,
            "competition_level": value.competition_level.value, "price_pressure": value.price_pressure.value,
            "rocket_competition": value.rocket_competition.value,
            "market_concentration": str(value.market_concentration), "confidence": str(snapshot.confidence),
            "summary": value.summary, "availability": snapshot.availability.value,
            "freshness": snapshot.freshness.value, "generated_at": snapshot.generated_at.isoformat(),
            "schema_version": snapshot.schema_version, "policy_version": snapshot.policy_version,
            "raw_observation": {"observation_id": observation.observation_id,
                "observed_at": observation.observed_at.isoformat(), "schema_version": observation.schema_version,
                "evidence": {name: {"value": str(item.value) if item.value is not None else None,
                    "source": item.source, "reference": item.reference,
                    "observed_at": item.observed_at.isoformat() if item.observed_at else None,
                    "status": item.status.value, "confidence": str(item.confidence), "unit": item.unit,
                    "collection_method": item.collection_method} for name, item in observation.evidence.items()}}
                if observation is not None else None}

    @staticmethod
    def _economics(snapshot):
        result = {"snapshot_at": snapshot.snapshot_at.isoformat(), "schema_version": snapshot.schema_version}
        for name in ("purchase_cost", "shipping_cost", "marketplace_fee_rate", "payment_fee_rate",
                     "fixed_fee", "tax_rate", "duty_cost", "other_cost", "expected_sale_price"):
            item = getattr(snapshot.inputs, name)
            number = getattr(item, "amount", getattr(item, "rate", None))
            result[name] = {"value": str(number) if number is not None else None,
                            "currency": getattr(item, "currency", None),
                            "evidence": {"status": item.evidence.status.value, "source": item.evidence.source,
                                         "observed_at": item.evidence.observed_at.isoformat() if item.evidence.observed_at else None,
                                         "reference": item.evidence.reference}}
        return result

    def _summary(self, item):
        bindings = self._reviews.list_opportunity_bindings(item.opportunity_id)
        review = self._reviews.get(bindings[0].session_id) if bindings else None
        return {"opportunity_id": item.opportunity_id, "discovery_reference": item.discovery_reference,
            "status": item.lifecycle_status.value, "created_at": item.created_at.isoformat(),
            "review_bound": review is not None, "review_session_id": review.session_id if review else None,
            "review_status": review.status.value if review else None}

    @staticmethod
    def _candidate(value):
        artifact=value.artifact
        return {"candidate_id":value.candidate_id, "field_name":value.field_name.value,
            "raw_text":value.raw_text, "normalized_value":value.normalized_value,
            "confidence":str(value.confidence), "captured_at":value.captured_at.isoformat(),
            "artifact":{"artifact_id":artifact.artifact_id,"origin":artifact.artifact_origin.value,
                "mime_type":artifact.mime_type,"width":artifact.width,"height":artifact.height}}
