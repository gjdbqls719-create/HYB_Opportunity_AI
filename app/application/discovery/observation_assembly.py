"""Application assembly of collector facts into discovery observations."""

from __future__ import annotations

from app.application.discovery.ports import ObservationIdentityProvider
from app.domain.discovery_identity import CollectedProductObservation
from app.domain.product_observation import CollectorProvenance, ObservedProductSnapshot
from collectors.collection_fact import CollectionFact


def assemble_collected_product_observations(
    *,
    discovery_execution_id: str,
    collection_facts: tuple[CollectionFact, ...],
    identity_provider: ObservationIdentityProvider,
) -> tuple[CollectedProductObservation, ...]:
    return tuple(
        _assemble_observation(
            discovery_execution_id=discovery_execution_id,
            fact=fact,
            observation_id=identity_provider.provide_observation_id(),
        )
        for fact in collection_facts
    )


def _assemble_observation(
    *,
    discovery_execution_id: str,
    fact: CollectionFact,
    observation_id: str,
) -> CollectedProductObservation:
    product = fact.product
    return CollectedProductObservation(
        observation_id=observation_id,
        discovery_execution_id=discovery_execution_id,
        source_marketplace=product.marketplace,
        source_item_id=product.item_id,
        product=ObservedProductSnapshot(
            marketplace=product.marketplace,
            item_id=product.item_id,
            title=product.title,
            price=product.price,
            currency=product.currency,
            condition=product.condition,
            url=product.url,
            brand=product.brand,
            model_number=product.model_number,
            category=product.category,
            shipping_cost=product.shipping_cost,
            seller=product.seller,
            image_url=product.image_url,
            rating=product.rating,
            review_count=product.review_count,
            in_stock=product.in_stock,
            data_source=product.data_source,
            shipping_cost_known=product.shipping_cost_known,
        ),
        collector_provenance=CollectorProvenance(
            collector_name=fact.collector_descriptor.collector_name,
            collector_version=fact.collector_descriptor.collector_version,
            source_reference=fact.source_reference,
        ),
        observed_at=fact.observed_at,
        candidate_market_identity=None,
    )


__all__ = ["assemble_collected_product_observations"]
