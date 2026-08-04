from dataclasses import FrozenInstanceError, replace
import inspect

import pytest

from app.application.production_safety_integration import (
    BuildProductionSafetyEvaluationContext,
    ProductionSafetyEvaluationContext,
    ProductionSafetyIntegrationService,
    ProductionSafetySnapshotLineageError,
    ProductionSafetySourceNotFoundError,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.opportunity import EconomicsCalculation
from app.models import Product
from engine.price_intelligence import PriceIntelligence
from test_economics_calculation_snapshot import snapshot as economics_snapshot
from test_price_intelligence_snapshot import snapshot as price_snapshot
from test_product_observation_snapshot import snapshot as product_snapshot


def source_chain():
    product = product_snapshot()
    price = replace(
        price_snapshot(),
        opportunity_identity=product.opportunity_identity,
        market_observation_identity=product.market_observation_identity,
        product_observation_snapshot_ids=(
            product.snapshot_id,
            "product-observation-2",
            "product-observation-3",
        ),
    )
    economics = replace(
        economics_snapshot(),
        opportunity_identity=product.opportunity_identity,
        market_observation_identity=product.market_observation_identity,
    )
    return product, price, economics


def context() -> ProductionSafetyEvaluationContext:
    product, price, economics = source_chain()
    return ProductionSafetyEvaluationContext(
        product,
        price,
        economics,
        economics.verified_economics_opportunity_id,
    )


def test_context_preserves_exact_snapshot_chain_without_runtime_engine_objects() -> None:
    value = context()
    product, price, economics = source_chain()

    assert value.product_observation_snapshot == product
    assert value.price_intelligence_snapshot == price
    assert value.economics_calculation_snapshot == economics
    assert value.verified_economics_opportunity_id == economics.verified_economics_opportunity_id
    assert not isinstance(value.product_observation_snapshot, Product)
    assert not isinstance(value.price_intelligence_snapshot, PriceIntelligence)
    assert not isinstance(value.economics_calculation_snapshot, EconomicsCalculation)


def test_context_is_immutable_and_value_equal() -> None:
    value = context()
    assert value == context()
    with pytest.raises(FrozenInstanceError):
        value.verified_economics_opportunity_id = "changed"


@pytest.mark.parametrize("conflict", ("opportunity", "market", "cohort", "verified"))
def test_context_rejects_broken_snapshot_lineage(conflict) -> None:
    product, price, economics = source_chain()
    verified_id = economics.verified_economics_opportunity_id
    if conflict == "opportunity":
        economics = replace(
            economics,
            opportunity_identity=OpportunityIdentity("other", "ebay:other"),
        )
    elif conflict == "market":
        economics = replace(
            economics,
            market_observation_identity=price_snapshot().market_observation_identity,
        )
    elif conflict == "cohort":
        price = replace(
            price,
            product_observation_snapshot_ids=("other-1", "other-2", "other-3"),
        )
    else:
        verified_id = "other-verified-economics"

    with pytest.raises(ProductionSafetySnapshotLineageError):
        ProductionSafetyEvaluationContext(product, price, economics, verified_id)


class MemoryProductionSafetySources:
    def __init__(self, product, price, economics):
        self.product = product
        self.price = price
        self.economics = economics
        self.validated = []

    def get_product_snapshot(self, snapshot_id):
        return self.product if self.product and self.product.snapshot_id == snapshot_id else None

    def get_price_snapshot(self, snapshot_id):
        return self.price if self.price and self.price.snapshot_id == snapshot_id else None

    def get_economics_snapshot(self, snapshot_id):
        return self.economics if self.economics and self.economics.snapshot_id == snapshot_id else None

    def validate_snapshot_lineage(self, value):
        self.validated.append(value)


def command(product, price, economics):
    return BuildProductionSafetyEvaluationContext(
        product.snapshot_id,
        price.snapshot_id,
        economics.snapshot_id,
        economics.verified_economics_opportunity_id,
    )


def test_service_loads_authoritative_sources_and_delegates_repository_validation() -> None:
    product, price, economics = source_chain()
    repository = MemoryProductionSafetySources(product, price, economics)
    value = ProductionSafetyIntegrationService(repository).build_context(
        command(product, price, economics)
    )

    assert value == context()
    assert repository.validated == [value]


@pytest.mark.parametrize("missing", ("product", "price", "economics"))
def test_service_rejects_each_missing_authoritative_source(missing) -> None:
    product, price, economics = source_chain()
    values = {"product": product, "price": price, "economics": economics}
    repository = MemoryProductionSafetySources(
        None if missing == "product" else product,
        None if missing == "price" else price,
        None if missing == "economics" else economics,
    )
    with pytest.raises(ProductionSafetySourceNotFoundError, match="source not found"):
        ProductionSafetyIntegrationService(repository).build_context(
            command(values["product"], values["price"], values["economics"])
        )


def test_foundation_does_not_call_or_reimplement_production_safety_engine() -> None:
    source = inspect.getsource(ProductionSafetyIntegrationService)
    assert "assess_production_safety" not in source
    assert "engine.production_safety" not in source
