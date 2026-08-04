"""Lossless runtime Product reconstruction from an authoritative snapshot."""

from app.domain.product_observation import (
    PRODUCT_OBSERVATION_SNAPSHOT_SCHEMA_VERSION,
    ProductObservationSnapshot,
)
from app.models import Product


class ProductRuntimeReconstructionError(ValueError): pass


def reconstruct_runtime_product(snapshot: ProductObservationSnapshot) -> Product:
    if not isinstance(snapshot, ProductObservationSnapshot):
        raise ProductRuntimeReconstructionError("Product Observation source is malformed")
    if snapshot.schema_version != PRODUCT_OBSERVATION_SNAPSHOT_SCHEMA_VERSION:
        raise ProductRuntimeReconstructionError("unsupported Product Observation version")
    source = snapshot.product
    if not source.shipping_cost_known and source.shipping_cost != 0.0:
        raise ProductRuntimeReconstructionError(
            "unknown shipping cost cannot carry a non-zero runtime value"
        )
    try:
        product = Product(
            marketplace=source.marketplace, item_id=source.item_id,
            title=source.title, price=source.price, currency=source.currency,
            condition=source.condition, url=source.url, brand=source.brand,
            model_number=source.model_number, category=source.category,
            shipping_cost=(source.shipping_cost if source.shipping_cost_known else None),
            seller=source.seller, image_url=source.image_url, rating=source.rating,
            review_count=source.review_count, in_stock=source.in_stock,
            data_source=source.data_source,
        )
    except (TypeError, ValueError) as error:
        raise ProductRuntimeReconstructionError(
            "Product runtime reconstruction failed"
        ) from error
    for field_name in source.__dataclass_fields__:
        if getattr(product, field_name) != getattr(source, field_name):
            raise ProductRuntimeReconstructionError(
                f"Product runtime field changed during reconstruction: {field_name}"
            )
    return product


__all__ = ["ProductRuntimeReconstructionError", "reconstruct_runtime_product"]
