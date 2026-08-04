from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.price_intelligence_snapshot import (
    PriceIntelligenceSnapshotRepository,
)
from app.domain.discovery_identity import OpportunityCandidateIdentity
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.domain.price_intelligence import (
    PRICE_INTELLIGENCE_SNAPSHOT_SCHEMA_VERSION,
    PriceIntelligenceSnapshot,
)
from app.models import Product, ProductDataSource
from engine.price_intelligence import PriceIntelligence, analyze_product_prices


NOW = datetime(2026, 8, 4, 10, tzinfo=timezone.utc)


def market_identity() -> MarketObservationIdentity:
    return MarketObservationIdentity(
        scope=MarketObservationScope.CANONICAL_PRODUCT,
        market="US", marketplace="ebay", canonical_product_id="canonical-1",
        marketplace_item_id=None, normalized_query=None, category="electronics",
        variant_identity=None, condition="new",
        window_started_at=NOW - timedelta(minutes=5), window_ended_at=NOW,
    )


def products() -> list[Product]:
    return [
        Product(
            marketplace="ebay", item_id=f"item-{index}", title="Same Product",
            price=price, currency="USD", data_source=ProductDataSource.PRODUCTION,
        )
        for index, price in enumerate((10, 20, 30), start=1)
    ]


def snapshot(
    result: PriceIntelligence | None = None,
    source_ids=("product-observation-1", "product-observation-2", "product-observation-3"),
) -> PriceIntelligenceSnapshot:
    value = result or analyze_product_prices(products())
    return PriceIntelligenceSnapshot(
        snapshot_id="price-intelligence-1",
        candidate_identity=OpportunityCandidateIdentity("candidate-1", "ebay:item-1"),
        market_observation_identity=market_identity(),
        product_observation_snapshot_ids=source_ids,
        currency=value.currency,
        lowest_price=value.lowest_price,
        average_price=value.average_price,
        median_price=value.median_price,
        highest_price=value.highest_price,
        price_range=value.price_range,
        price_variation_rate=value.price_variation_rate,
        price_stability_level=value.price_stability_level,
        recommended_selling_price=value.recommended_selling_price,
        sample_size=value.sample_size,
        analyzer_version="price-intelligence-analyzer-v1",
        generated_at=NOW,
    )


def test_snapshot_preserves_existing_analyzer_result_without_runtime_object() -> None:
    result = analyze_product_prices(products())
    value = snapshot(result)
    result_fields = tuple(field.name for field in fields(PriceIntelligence))

    assert all(getattr(value, name) == getattr(result, name) for name in result_fields)
    assert not any(getattr(value, field.name) is result for field in fields(value))
    assert "price_intelligence" not in PriceIntelligenceSnapshot.__dataclass_fields__


def test_ordered_source_provenance_and_sample_size_are_preserved() -> None:
    value = snapshot()
    assert value.product_observation_snapshot_ids == (
        "product-observation-1", "product-observation-2", "product-observation-3"
    )
    assert value.sample_size == len(value.product_observation_snapshot_ids) == 3


def test_snapshot_is_immutable_equal_and_versioned() -> None:
    value = snapshot()
    assert value == snapshot()
    assert value.schema_version == PRICE_INTELLIGENCE_SNAPSHOT_SCHEMA_VERSION
    assert value.analyzer_version == "price-intelligence-analyzer-v1"
    assert value.generated_at == NOW
    with pytest.raises(FrozenInstanceError):
        value.sample_size = 4
    with pytest.raises(FrozenInstanceError):
        value.product_observation_snapshot_ids += ("another",)


@pytest.mark.parametrize(
    "override,error",
    (
        ({"product_observation_snapshot_ids": ["one", "two", "three"]}, TypeError),
        ({"product_observation_snapshot_ids": ("one", "one", "three")}, ValueError),
        ({"product_observation_snapshot_ids": ("one", "two")}, ValueError),
        ({"lowest_price": 10}, TypeError),
        ({"average_price": Decimal("NaN")}, ValueError),
        ({"generated_at": NOW.replace(tzinfo=None)}, ValueError),
        ({"analyzer_version": ""}, ValueError),
    ),
)
def test_snapshot_rejects_invalid_contract_values(override, error) -> None:
    value = snapshot()
    payload = {field.name: getattr(value, field.name) for field in fields(value)}
    payload.update(override)
    with pytest.raises(error):
        PriceIntelligenceSnapshot(**payload)


class MemoryPriceIntelligenceSnapshotRepository:
    def __init__(self): self.values = {}
    def save_snapshot(self, value): self.values[value.snapshot_id] = value; return value
    def get_snapshot(self, snapshot_id): return self.values.get(snapshot_id)
    def get_by_candidate(self, identity):
        return tuple(v for v in self.values.values() if v.candidate_identity == identity)
    def get_by_market_identity(self, identity):
        return tuple(v for v in self.values.values() if v.market_observation_identity == identity)


def exercise_repository(repository: PriceIntelligenceSnapshotRepository) -> None:
    value = snapshot()
    assert repository.save_snapshot(value) == value
    assert repository.get_snapshot(value.snapshot_id) == value
    assert repository.get_by_candidate(value.candidate_identity) == (value,)
    assert repository.get_by_market_identity(value.market_observation_identity) == (value,)


def test_repository_boundary_supports_required_operations() -> None:
    exercise_repository(MemoryPriceIntelligenceSnapshotRepository())
