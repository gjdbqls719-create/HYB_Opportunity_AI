from dataclasses import fields, replace
import inspect

import pytest

from app.application.production_safety_integration import ProductionSafetyEvaluationContext
from app.application.production_safety_runtime_adapter import (
    MalformedProductionSafetyRuntimeSourceError,
    MissingProductionSafetyRuntimeSourceError,
    ProductionSafetyRuntimeAdapter,
    ProductionSafetyRuntimeIdentityConflictError,
    UnsupportedProductionSafetyRuntimeVersionError,
)
from app.application.verified_economics_snapshot import VerifiedEconomicsSnapshot
from app.domain.price_intelligence import PriceIntelligenceSnapshot
from app.domain.product_observation import ObservedProductSnapshot
from engine.price_intelligence import PriceIntelligence
from test_economics_calculation_snapshot import NOW, inputs
from test_production_safety_integration_foundation import source_chain, promotion_binding


class VerifiedEconomicsSources:
    def __init__(self, value):
        self.value = value
        self.reads = []
        self.writes = 0

    def get_verified_economics_snapshot(self, opportunity_id):
        self.reads.append(opportunity_id)
        return self.value


def authoritative_chain():
    product, price, economics = source_chain()
    context = ProductionSafetyEvaluationContext(product, price, economics, promotion_binding(product), "opp-1")
    verified = VerifiedEconomicsSnapshot("opp-1", inputs(), NOW)
    return context, verified


def adapter(source):
    return ProductionSafetyRuntimeAdapter(
        source,
        supported_analyzer_version="price-intelligence-analyzer-v1",
        supported_calculation_version="verified-economics-calculator-v1",
    )


def test_product_reconstruction_preserves_every_field_and_is_independent() -> None:
    context, verified = authoritative_chain()
    source = VerifiedEconomicsSources(verified)
    runtime = adapter(source).reconstruct_product(context.product_observation_snapshot)
    observed = context.product_observation_snapshot.product

    assert all(getattr(runtime, name) == getattr(observed, name) for name in observed.__dataclass_fields__)
    runtime.title = "runtime changed"
    runtime.price = 999.0
    assert context.product_observation_snapshot.product.title == "Observed Product"
    assert context.product_observation_snapshot.product.price == 42.5


def test_unknown_shipping_and_product_data_source_are_preserved_exactly() -> None:
    context, verified = authoritative_chain()
    observed = replace(
        context.product_observation_snapshot.product,
        shipping_cost=0.0,
        shipping_cost_known=False,
    )
    product_snapshot = replace(context.product_observation_snapshot, product=observed)
    runtime = adapter(VerifiedEconomicsSources(verified)).reconstruct_product(product_snapshot)

    assert runtime.shipping_cost == 0.0
    assert runtime.shipping_cost_known is False
    assert runtime.data_source is observed.data_source


def test_malformed_unknown_shipping_is_rejected_without_inference() -> None:
    context, verified = authoritative_chain()
    observed = replace(
        context.product_observation_snapshot.product,
        shipping_cost=1.0,
        shipping_cost_known=False,
    )
    with pytest.raises(MalformedProductionSafetyRuntimeSourceError):
        adapter(VerifiedEconomicsSources(verified)).reconstruct_product(
            replace(context.product_observation_snapshot, product=observed)
        )


def test_price_reconstruction_preserves_all_runtime_fields_and_decimal_identity() -> None:
    context, verified = authoritative_chain()
    runtime = adapter(VerifiedEconomicsSources(verified)).reconstruct_price_intelligence(
        context.price_intelligence_snapshot
    )
    snapshot = context.price_intelligence_snapshot

    assert isinstance(runtime, PriceIntelligence)
    assert all(getattr(runtime, field.name) == getattr(snapshot, field.name) for field in fields(PriceIntelligence))
    assert runtime.lowest_price is snapshot.lowest_price
    assert runtime.sample_size == snapshot.sample_size


def test_exact_verified_economics_snapshot_is_loaded_read_only() -> None:
    context, verified = authoritative_chain()
    source = VerifiedEconomicsSources(verified)
    loaded = adapter(source).load_verified_economics_snapshot(context)

    assert loaded is verified
    assert loaded.inputs is verified.inputs
    assert source.reads == ["opp-1"]
    assert source.writes == 0


def test_missing_malformed_and_identity_conflicting_verified_sources_are_explicit() -> None:
    context, verified = authoritative_chain()
    with pytest.raises(MissingProductionSafetyRuntimeSourceError):
        adapter(VerifiedEconomicsSources(None)).load_verified_economics_snapshot(context)
    with pytest.raises(MalformedProductionSafetyRuntimeSourceError):
        adapter(VerifiedEconomicsSources(object())).load_verified_economics_snapshot(context)
    with pytest.raises(ProductionSafetyRuntimeIdentityConflictError):
        adapter(
            VerifiedEconomicsSources(replace(verified, opportunity_id="other"))
        ).load_verified_economics_snapshot(context)


@pytest.mark.parametrize("kind", ("product", "price_schema", "analyzer", "economics", "calculator", "verified"))
def test_unsupported_versions_are_rejected(kind) -> None:
    context, verified = authoritative_chain()
    if kind == "product":
        context = replace(
            context,
            product_observation_snapshot=replace(
                context.product_observation_snapshot, schema_version="future"
            ),
        )
    elif kind == "price_schema":
        context = replace(
            context,
            price_intelligence_snapshot=replace(
                context.price_intelligence_snapshot, schema_version="future"
            ),
        )
    elif kind == "analyzer":
        context = replace(
            context,
            price_intelligence_snapshot=replace(
                context.price_intelligence_snapshot, analyzer_version="future"
            ),
        )
    elif kind == "economics":
        context = replace(
            context,
            economics_calculation_snapshot=replace(
                context.economics_calculation_snapshot, schema_version="future"
            ),
        )
    elif kind == "calculator":
        context = replace(
            context,
            economics_calculation_snapshot=replace(
                context.economics_calculation_snapshot, calculation_version="future"
            ),
        )
    else:
        verified = replace(verified, schema_version="future")

    with pytest.raises(UnsupportedProductionSafetyRuntimeVersionError):
        adapter(VerifiedEconomicsSources(verified)).load_verified_economics_snapshot(context)


def test_economics_and_complete_bundle_reconstruct_from_authoritative_analysis() -> None:
    context, verified = authoritative_chain()
    runtime_adapter = adapter(VerifiedEconomicsSources(verified))
    economics = runtime_adapter.reconstruct_economics(
        context.economics_calculation_snapshot, verified
    )
    bundle = runtime_adapter.reconstruct_inputs(context, verified)
    assert economics.analysis == context.economics_calculation_snapshot.analysis.to_runtime_mapping()
    assert bundle.economics == economics
    assert bundle.analysis == economics.analysis


def test_reconstruction_is_deterministic_and_does_not_mutate_sources() -> None:
    context, verified = authoritative_chain()
    runtime_adapter = adapter(VerifiedEconomicsSources(verified))
    before = context
    first_product = runtime_adapter.reconstruct_product(context.product_observation_snapshot)
    second_product = runtime_adapter.reconstruct_product(context.product_observation_snapshot)
    first_price = runtime_adapter.reconstruct_price_intelligence(context.price_intelligence_snapshot)
    second_price = runtime_adapter.reconstruct_price_intelligence(context.price_intelligence_snapshot)

    assert first_product == second_product
    assert first_product is not second_product
    assert first_price == second_price
    assert first_price is not second_price
    assert context == before


def test_adapter_never_calls_production_safety_or_analyzers_or_calculators() -> None:
    source = inspect.getsource(ProductionSafetyRuntimeAdapter)
    assert "assess_production_safety" not in source
    assert "analyze_product_prices" not in source
    assert "calculate_verified_economics" not in source
