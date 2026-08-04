from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

import pytest

from app.application.product_observation import ProductObservationRepository
from app.domain.decision_engine import OpportunityIdentity
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.domain.product_observation import (
    PRODUCT_OBSERVATION_SNAPSHOT_SCHEMA_VERSION,
    CollectorProvenance,
    ObservedProductSnapshot,
    ProductObservationSnapshot,
)
from app.models import Product, ProductDataSource


NOW = datetime(2026, 8, 4, 9, tzinfo=timezone.utc)


def market_identity() -> MarketObservationIdentity:
    return MarketObservationIdentity(
        scope=MarketObservationScope.LISTING,
        market="US",
        marketplace="ebay",
        canonical_product_id=None,
        marketplace_item_id="item-1",
        normalized_query=None,
        category="electronics",
        variant_identity=None,
        condition="new",
        window_started_at=NOW - timedelta(minutes=1),
        window_ended_at=NOW,
    )


def runtime_product() -> Product:
    return Product(
        marketplace="ebay", item_id="item-1", title="Observed Product",
        price=42.5, currency="USD", condition="new",
        url="https://example.test/item-1", brand="HYB", model_number="M-1",
        category="electronics", shipping_cost=3.25, seller="seller-1",
        image_url="https://example.test/item-1.png", rating=4.8,
        review_count=12, in_stock=True, data_source=ProductDataSource.PRODUCTION,
    )


def observed_product(product: Product | None = None) -> ObservedProductSnapshot:
    value = product or runtime_product()
    return ObservedProductSnapshot(**{
        name: getattr(value, name) for name in ObservedProductSnapshot.__dataclass_fields__
    })


def snapshot(snapshot_id="product-observation-1") -> ProductObservationSnapshot:
    return ProductObservationSnapshot(
        snapshot_id=snapshot_id,
        opportunity_identity=OpportunityIdentity("opp-1", "ebay:item-1"),
        market_observation_identity=market_identity(),
        product=observed_product(),
        collector_provenance=CollectorProvenance(
            "ebay-marketplace-adapter", "collector-contract-v1",
            "https://example.test/item-1",
        ),
        observed_at=NOW,
    )


def test_snapshot_preserves_every_runtime_product_field_exactly() -> None:
    source = runtime_product()
    value = observed_product(source)
    assert all(
        getattr(value, name) == getattr(source, name)
        for name in ObservedProductSnapshot.__dataclass_fields__
    )


def test_snapshot_is_deeply_immutable_and_detached_from_runtime_product() -> None:
    source = runtime_product()
    value = ProductObservationSnapshot(
        "product-observation-1", OpportunityIdentity("opp-1", "ebay:item-1"),
        market_identity(), observed_product(source),
        CollectorProvenance("collector", "v1", "source"), NOW,
    )
    source.price = 99.0
    source.title = "Changed runtime value"
    assert value.product.price == 42.5
    assert value.product.title == "Observed Product"
    with pytest.raises(FrozenInstanceError):
        value.product.price = 1.0
    with pytest.raises(FrozenInstanceError):
        value.collector_provenance.collector_name = "changed"
    with pytest.raises(FrozenInstanceError):
        value.snapshot_id = "changed"


def test_identity_provenance_time_version_and_equality_are_preserved() -> None:
    first = snapshot()
    assert first == snapshot()
    assert first.opportunity_identity.opportunity_id == "opp-1"
    assert first.market_observation_identity == market_identity()
    assert first.observed_at == NOW
    assert first.schema_version == PRODUCT_OBSERVATION_SNAPSHOT_SCHEMA_VERSION
    assert first.collector_provenance.source_reference == "https://example.test/item-1"


@pytest.mark.parametrize(
    "override,error",
    (({"snapshot_id": ""}, ValueError),
     ({"observed_at": NOW.replace(tzinfo=None)}, ValueError),
     ({"product": runtime_product()}, TypeError),
     ({"collector_provenance": object()}, TypeError)),
)
def test_snapshot_rejects_invalid_contract_values(override, error) -> None:
    fields = dict(
        snapshot_id="product-observation-1",
        opportunity_identity=OpportunityIdentity("opp-1", "ebay:item-1"),
        market_observation_identity=market_identity(), product=observed_product(),
        collector_provenance=CollectorProvenance("collector", "v1", "source"),
        observed_at=NOW,
    )
    fields.update(override)
    with pytest.raises(error):
        ProductObservationSnapshot(**fields)


class MemoryProductObservationRepository:
    def __init__(self): self.values = {}
    def save_snapshot(self, value): self.values[value.snapshot_id] = value; return value
    def get_snapshot(self, snapshot_id): return self.values.get(snapshot_id)
    def get_by_opportunity(self, identity):
        return tuple(v for v in self.values.values() if v.opportunity_identity == identity)
    def get_by_market_identity(self, identity):
        return tuple(v for v in self.values.values() if v.market_observation_identity == identity)


def exercise_repository(repository: ProductObservationRepository) -> None:
    value = snapshot()
    assert repository.save_snapshot(value) == value
    assert repository.get_snapshot(value.snapshot_id) == value
    assert repository.get_by_opportunity(value.opportunity_identity) == (value,)
    assert repository.get_by_market_identity(value.market_observation_identity) == (value,)


def test_repository_boundary_supports_required_lookup_contracts() -> None:
    exercise_repository(MemoryProductObservationRepository())
