"""Application assembly of collector facts into discovery observations."""

from __future__ import annotations

from app.application.discovery.ports import (
    CandidateDiscoveryReferenceProvider,
    ObservationIdentityProvider,
)
from app.domain.discovery_identity import (
    CANDIDATE_HANDOFF_COLLECTOR_OBSERVATION_SCHEMA_VERSION,
    COLLECTOR_OBSERVATION_SCHEMA_VERSION,
    CollectedProductObservation,
)
from app.domain.product_observation import CollectorProvenance, ObservedProductSnapshot
from collectors.collection_fact import CollectionFact


def assemble_collected_product_observations(
    *,
    discovery_execution_id: str,
    collection_facts: tuple[CollectionFact, ...],
    identity_provider: ObservationIdentityProvider,
    candidate_discovery_reference_provider: (
        CandidateDiscoveryReferenceProvider | None
    ) = None,
) -> tuple[CollectedProductObservation, ...]:
    observations = []
    for fact in collection_facts:
        candidate_discovery_reference = None
        if fact.candidate_market_identity is not None:
            if candidate_discovery_reference_provider is None:
                raise TypeError(
                    "candidate_discovery_reference_provider is required for "
                    "Candidate handoff"
                )
            candidate_discovery_reference = (
                candidate_discovery_reference_provider
                .provide_candidate_discovery_reference()
            )
        observations.append(
            _assemble_observation(
                discovery_execution_id=discovery_execution_id,
                fact=fact,
                observation_id=identity_provider.provide_observation_id(),
                candidate_discovery_reference=candidate_discovery_reference,
            )
        )
    return tuple(observations)


def _assemble_observation(
    *,
    discovery_execution_id: str,
    fact: CollectionFact,
    observation_id: str,
    candidate_discovery_reference: str | None,
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
        candidate_market_identity=fact.candidate_market_identity,
        candidate_discovery_reference=candidate_discovery_reference,
        candidate_handoff_policy_name=fact.candidate_handoff_policy_name,
        candidate_handoff_policy_version=fact.candidate_handoff_policy_version,
        schema_version=(
            CANDIDATE_HANDOFF_COLLECTOR_OBSERVATION_SCHEMA_VERSION
            if fact.candidate_market_identity is not None
            else COLLECTOR_OBSERVATION_SCHEMA_VERSION
        ),
    )


__all__ = ["assemble_collected_product_observations"]
