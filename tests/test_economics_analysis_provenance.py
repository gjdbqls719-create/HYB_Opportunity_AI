from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from types import MappingProxyType

import pytest

from app.application.production_safety_runtime_adapter import (
    ProductionSafetyRuntimeAdapter,
    UnsupportedProductionSafetyRuntimeAnalysisValueError,
    UnsupportedProductionSafetyRuntimeVersionError,
)
from app.application.verified_economics_snapshot import VerifiedEconomicsSnapshot
from app.domain.economics_calculation_snapshot import (
    ECONOMICS_ANALYSIS_SCHEMA_VERSION,
    CanonicalEconomicsAnalysisValue,
    EconomicsAnalysisSnapshot,
    EconomicsAnalysisValueKind,
    UnsupportedEconomicsAnalysisValueError,
)
from test_economics_calculation_snapshot import NOW, calculation, inputs, snapshot
from test_production_safety_integration_foundation import source_chain
from app.application.production_safety_integration import ProductionSafetyEvaluationContext


class AnalysisState(StrEnum):
    READY = "ready"


class VerifiedSources:
    def __init__(self, value):
        self.value = value

    def get_verified_economics_snapshot(self, opportunity_id):
        return self.value if self.value.opportunity_id == opportunity_id else None


def runtime_adapter(verified, *, enum_types=()):
    return ProductionSafetyRuntimeAdapter(
        VerifiedSources(verified),
        supported_analyzer_version="price-intelligence-analyzer-v1",
        supported_calculation_version="verified-economics-calculator-v1",
        analysis_enum_types=enum_types,
    )


def assert_same_shape(left, right):
    assert type(left) is type(right)
    if isinstance(left, MappingProxyType) or isinstance(left, dict):
        assert set(left) == set(right)
        for key in left:
            assert_same_shape(left[key], right[key])
    elif isinstance(left, (tuple, list)):
        assert len(left) == len(right)
        for left_item, right_item in zip(left, right, strict=True):
            assert_same_shape(left_item, right_item)
    else:
        assert left == right


def test_real_calculator_analysis_is_preserved_completely_without_defaults() -> None:
    runtime = calculation().analysis
    persisted = EconomicsAnalysisSnapshot.from_runtime(runtime)
    restored = persisted.to_runtime_mapping()

    assert tuple(restored) == tuple(sorted(runtime))
    assert set(restored) == set(runtime)
    for key in runtime:
        assert_same_shape(runtime[key], restored[key])
    assert {
        "marketplace",
        "marketplace_fee",
        "payment_fee",
        "total_cost",
        "net_profit",
        "roi",
        "landed_cost_roi",
        "margin_rate",
        "recommendation",
        "reasons",
        "risk_warnings",
        "passes_profitability_filter",
    } <= set(restored)


def test_supported_analysis_types_round_trip_with_exact_semantics() -> None:
    value = {
        "none": None,
        "bool": True,
        "int": 1,
        "float": 1.25,
        "decimal": Decimal("1.2500"),
        "string": "value",
        "enum": AnalysisState.READY,
        "datetime": datetime(2026, 8, 4, tzinfo=timezone.utc),
        "tuple": (1, "two"),
        "list": [False, Decimal("3.0")],
        "mapping": {"nested": [1, 2]},
    }
    persisted = EconomicsAnalysisSnapshot.from_runtime(value)
    restored = persisted.to_runtime_mapping((AnalysisState,))
    assert_same_shape(value, restored)
    assert restored["decimal"] == Decimal("1.2500")
    assert restored["enum"] is AnalysisState.READY
    enum_node = dict(persisted.entries)["enum"]
    assert enum_node.enum_type.endswith(".AnalysisState")
    assert enum_node.enum_value.to_runtime({}) == "ready"


def test_bool_and_int_have_distinct_canonical_tags() -> None:
    persisted = EconomicsAnalysisSnapshot.from_runtime({"bool": True, "int": 1})
    values = dict(persisted.entries)
    assert values["bool"].kind is EconomicsAnalysisValueKind.BOOL
    assert values["int"].kind is EconomicsAnalysisValueKind.INT


def test_snapshot_is_deeply_immutable_and_detached_from_mutable_input() -> None:
    source = {"nested": {"items": [1, 2]}}
    persisted = EconomicsAnalysisSnapshot.from_runtime(source)
    source["nested"]["items"].append(3)
    assert persisted.to_runtime_mapping() == {"nested": {"items": [1, 2]}}
    with pytest.raises(FrozenInstanceError):
        persisted.analysis_version = "changed"
    with pytest.raises(FrozenInstanceError):
        persisted.entries[0][1].kind = EconomicsAnalysisValueKind.NONE


def test_order_equality_and_fingerprint_are_deterministic() -> None:
    first = EconomicsAnalysisSnapshot.from_runtime({"b": 2, "a": {"y": 2, "x": 1}})
    second = EconomicsAnalysisSnapshot.from_runtime({"a": {"x": 1, "y": 2}, "b": 2})
    assert first == second
    assert first.fingerprint == second.fingerprint
    assert first.analysis_version == ECONOMICS_ANALYSIS_SCHEMA_VERSION


@pytest.mark.parametrize(
    "value",
    (
        object(),
        {1, 2},
        datetime(2026, 8, 4),
        Decimal("NaN"),
        float("inf"),
    ),
)
def test_unsupported_or_ambiguous_values_are_rejected(value) -> None:
    with pytest.raises(UnsupportedEconomicsAnalysisValueError):
        EconomicsAnalysisSnapshot.from_runtime({"value": value})


def test_cycles_and_non_text_mapping_keys_are_rejected() -> None:
    cyclic = []
    cyclic.append(cyclic)
    with pytest.raises(UnsupportedEconomicsAnalysisValueError):
        EconomicsAnalysisSnapshot.from_runtime({"cyclic": cyclic})
    with pytest.raises(UnsupportedEconomicsAnalysisValueError):
        EconomicsAnalysisSnapshot.from_runtime({"mapping": {1: "value"}})


def test_direct_canonical_construction_rejects_malformed_content() -> None:
    with pytest.raises(TypeError):
        CanonicalEconomicsAnalysisValue(EconomicsAnalysisValueKind.BOOL, scalar=1)
    with pytest.raises(ValueError):
        CanonicalEconomicsAnalysisValue(
            EconomicsAnalysisValueKind.MAPPING,
            entries=(("b", CanonicalEconomicsAnalysisValue(EconomicsAnalysisValueKind.NONE)),
                     ("a", CanonicalEconomicsAnalysisValue(EconomicsAnalysisValueKind.NONE))),
        )


def test_unknown_enum_and_analysis_versions_have_explicit_errors() -> None:
    canonical = EconomicsAnalysisSnapshot.from_runtime({"state": AnalysisState.READY})
    with pytest.raises(UnsupportedEconomicsAnalysisValueError):
        canonical.to_runtime_mapping()

    current = snapshot().analysis
    future = EconomicsAnalysisSnapshot(current.entries, "future")
    economics = replace(snapshot(), analysis=future)
    verified = VerifiedEconomicsSnapshot("opp-1", inputs(), NOW)
    with pytest.raises(UnsupportedProductionSafetyRuntimeVersionError):
        runtime_adapter(verified).reconstruct_analysis(economics)


def test_unknown_enum_runtime_value_maps_to_analysis_error_taxonomy() -> None:
    economics = replace(
        snapshot(), analysis=EconomicsAnalysisSnapshot.from_runtime({"state": AnalysisState.READY})
    )
    verified = VerifiedEconomicsSnapshot("opp-1", inputs(), NOW)
    with pytest.raises(UnsupportedProductionSafetyRuntimeAnalysisValueError):
        runtime_adapter(verified).reconstruct_analysis(economics)


def test_runtime_economics_and_complete_bundle_round_trip_exactly() -> None:
    product, price, economics_snapshot = source_chain()
    verified = VerifiedEconomicsSnapshot("opp-1", inputs(), NOW)
    from test_production_safety_integration_foundation import promotion_binding
    context = ProductionSafetyEvaluationContext(product, price, economics_snapshot, promotion_binding(product), "opp-1")
    adapter = runtime_adapter(verified)
    runtime = adapter.reconstruct_economics(economics_snapshot, verified)
    bundle = adapter.reconstruct_inputs(context, verified)

    expected = calculation()
    for field in expected.__dataclass_fields__:
        if field == "analysis":
            assert set(runtime.analysis) == set(expected.analysis)
            for key in expected.analysis:
                assert_same_shape(expected.analysis[key], runtime.analysis[key])
        else:
            assert getattr(runtime, field) == getattr(expected, field)
    assert bundle.economics == runtime
    assert bundle.product.item_id == product.product.item_id
    assert bundle.price_intelligence.sample_size == price.sample_size


def test_repeated_runtime_reconstruction_is_deterministic_and_disposable() -> None:
    product, price, economics = source_chain()
    verified = VerifiedEconomicsSnapshot("opp-1", inputs(), NOW)
    from test_production_safety_integration_foundation import promotion_binding
    context = ProductionSafetyEvaluationContext(product, price, economics, promotion_binding(product), "opp-1")
    adapter = runtime_adapter(verified)
    first = adapter.reconstruct_inputs(context, verified)
    second = adapter.reconstruct_inputs(context, verified)
    assert first == second
    assert first is not second
    first.analysis["reasons"].append("runtime-only")
    assert "runtime-only" not in second.analysis["reasons"]
    assert "runtime-only" not in economics.analysis.to_runtime_mapping()["reasons"]
