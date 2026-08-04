"""HTTP-facing DTO boundary for operational Production Safety."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.application.production_safety_evaluation import (
    EvaluateAndPersistProductionSafety,
    EvaluateAndPersistProductionSafetyCommand,
    ProductionSafetyEvaluationResult,
    ProductionSafetyChainNotFoundError,
    ProductionSafetyProductNotFoundError,
)


@dataclass(frozen=True, slots=True)
class ProductionSafetyEvaluationResponseDTO:
    evaluation_id: str
    opportunity_id: str
    status: str
    missing_fields: tuple[str, ...]
    failed_checks: tuple[str, ...]
    snapshot_chain_binding_id: str
    selected_product_snapshot_id: str
    candidate_id: str
    price_intelligence_snapshot_id: str
    economics_calculation_snapshot_id: str
    verified_economics_opportunity_id: str
    rule_version: str
    evaluation_schema_version: str
    provenance_schema_version: str
    evaluated_at: datetime
    replayed: bool

    @classmethod
    def from_result(cls, result: ProductionSafetyEvaluationResult):
        evaluation, provenance = result.evaluation, result.provenance
        return cls(
            evaluation.evaluation_id, evaluation.opportunity_id,
            evaluation.assessment.status.value, evaluation.assessment.missing_fields,
            evaluation.assessment.failed_checks, provenance.snapshot_chain_binding_id,
            provenance.selected_product_snapshot_id, provenance.candidate_id,
            provenance.price_intelligence_snapshot_id,
            provenance.economics_calculation_snapshot_id,
            provenance.verified_economics_opportunity_id, evaluation.rule_version,
            evaluation.schema_version, provenance.schema_version,
            evaluation.evaluated_at, result.replayed,
        )

    def to_dict(self):
        return {
            "evaluation_id": self.evaluation_id, "opportunity_id": self.opportunity_id,
            "status": self.status, "missing_fields": list(self.missing_fields),
            "failed_checks": list(self.failed_checks),
            "snapshot_chain_binding_id": self.snapshot_chain_binding_id,
            "selected_product_snapshot_id": self.selected_product_snapshot_id,
            "candidate_id": self.candidate_id,
            "price_intelligence_snapshot_id": self.price_intelligence_snapshot_id,
            "economics_calculation_snapshot_id": self.economics_calculation_snapshot_id,
            "verified_economics_opportunity_id": self.verified_economics_opportunity_id,
            "rule_version": self.rule_version,
            "evaluation_schema_version": self.evaluation_schema_version,
            "provenance_schema_version": self.provenance_schema_version,
            "evaluated_at": self.evaluated_at.isoformat(), "replayed": self.replayed,
        }


class EvaluateProductionSafetyApi:
    def __init__(self, evaluator: EvaluateAndPersistProductionSafety, opportunities, sources) -> None:
        self._evaluator, self._opportunities, self._sources = evaluator, opportunities, sources

    def execute(self, command: EvaluateAndPersistProductionSafetyCommand):
        if self._opportunities.get_queue_item(command.opportunity_id) is None:
            raise LookupError("opportunity not found")
        if self._sources.get_binding(command.snapshot_chain_binding_id) is None:
            raise ProductionSafetyChainNotFoundError("snapshot chain binding not found")
        if self._sources.get_product_snapshot(command.selected_product_snapshot_id) is None:
            raise ProductionSafetyProductNotFoundError("selected Product Snapshot not found")
        return ProductionSafetyEvaluationResponseDTO.from_result(
            self._evaluator.execute(command)
        )


class GetProductionSafetyOperationalDetail:
    def __init__(self, repository, opportunities) -> None:
        self._repository, self._opportunities = repository, opportunities

    def execute(self, opportunity_id: str):
        if self._opportunities.get_queue_item(opportunity_id) is None:
            raise LookupError("opportunity not found")
        bindings = self._repository.get_bindings_by_opportunity(opportunity_id)
        values = []
        for binding in bindings:
            products = []
            for snapshot_id in binding.product_snapshot_ids:
                snapshot = self._repository.get_product_snapshot(snapshot_id)
                product = snapshot.product
                products.append({
                    "snapshot_id": snapshot.snapshot_id, "title": product.title,
                    "marketplace": product.marketplace, "item_id": product.item_id,
                    "price": str(product.price), "currency": product.currency,
                    "shipping_cost_known": product.shipping_cost_known,
                    "shipping_cost": None if product.shipping_cost is None else str(product.shipping_cost),
                    "data_source": product.data_source.value,
                    "observed_at": snapshot.observed_at.isoformat(),
                })
            values.append({
                "binding_id": binding.binding_id, "chain_version": binding.chain_version,
                "candidate_id": binding.candidate_id, "opportunity_id": binding.opportunity_id,
                "bound_at": binding.bound_at.isoformat(),
                "product_snapshot_ids": list(binding.product_snapshot_ids),
                "price_snapshot_id": binding.price_snapshot_id,
                "economics_snapshot_id": binding.economics_snapshot_id,
                "market_identity": str(binding.market_observation_identity),
                "products": products,
            })
        current = self._repository.get_current_decision_source(opportunity_id)
        return {
            "opportunity_id": opportunity_id, "bindings": values,
            "current": None if current is None else {
                "evaluation_id": current.evaluation_id, "status": current.assessment.status.value,
                "missing_fields": list(current.assessment.missing_fields),
                "failed_checks": list(current.assessment.failed_checks),
                "selected_product_snapshot_id": current.selected_product_snapshot_id,
                "snapshot_chain_binding_id": current.snapshot_chain_binding_id,
                "rule_version": current.rule_version,
                "evaluated_at": current.evaluated_at.isoformat(),
            },
        }
