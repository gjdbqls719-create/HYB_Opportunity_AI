"""Authoritative source-chain boundary for future Production Safety evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.economics_calculation_snapshot import EconomicsCalculationSnapshot
from app.domain.price_intelligence import PriceIntelligenceSnapshot
from app.domain.product_observation import ProductObservationSnapshot


class ProductionSafetySourceNotFoundError(LookupError):
    pass


class ProductionSafetySnapshotLineageError(ValueError):
    pass


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


@dataclass(frozen=True, slots=True)
class ProductionSafetyEvaluationContext:
    product_observation_snapshot: ProductObservationSnapshot
    price_intelligence_snapshot: PriceIntelligenceSnapshot
    economics_calculation_snapshot: EconomicsCalculationSnapshot
    verified_economics_opportunity_id: str

    def __post_init__(self) -> None:
        product = self.product_observation_snapshot
        price = self.price_intelligence_snapshot
        economics = self.economics_calculation_snapshot
        if not isinstance(product, ProductObservationSnapshot):
            raise TypeError(
                "product_observation_snapshot must be ProductObservationSnapshot"
            )
        if not isinstance(price, PriceIntelligenceSnapshot):
            raise TypeError(
                "price_intelligence_snapshot must be PriceIntelligenceSnapshot"
            )
        if not isinstance(economics, EconomicsCalculationSnapshot):
            raise TypeError(
                "economics_calculation_snapshot must be EconomicsCalculationSnapshot"
            )
        _required_text(
            self.verified_economics_opportunity_id,
            "verified_economics_opportunity_id",
        )
        opportunity = product.opportunity_identity
        if price.opportunity_identity != opportunity or economics.opportunity_identity != opportunity:
            raise ProductionSafetySnapshotLineageError(
                "snapshot Opportunity identities must match"
            )
        market = product.market_observation_identity
        if (
            price.market_observation_identity != market
            or economics.market_observation_identity != market
        ):
            raise ProductionSafetySnapshotLineageError(
                "snapshot Market Observation identities must match"
            )
        if product.snapshot_id not in price.product_observation_snapshot_ids:
            raise ProductionSafetySnapshotLineageError(
                "Product Observation snapshot must belong to the PriceIntelligence cohort"
            )
        if economics.verified_economics_opportunity_id != self.verified_economics_opportunity_id:
            raise ProductionSafetySnapshotLineageError(
                "Verified Economics snapshot reference must match EconomicsCalculation"
            )


class ProductionSafetySourceRepository(Protocol):
    def get_product_snapshot(
        self, snapshot_id: str
    ) -> ProductObservationSnapshot | None: ...

    def get_price_snapshot(
        self, snapshot_id: str
    ) -> PriceIntelligenceSnapshot | None: ...

    def get_economics_snapshot(
        self, snapshot_id: str
    ) -> EconomicsCalculationSnapshot | None: ...

    def validate_snapshot_lineage(
        self, context: ProductionSafetyEvaluationContext
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class BuildProductionSafetyEvaluationContext:
    product_snapshot_id: str
    price_snapshot_id: str
    economics_snapshot_id: str
    verified_economics_opportunity_id: str

    def __post_init__(self) -> None:
        for name in (
            "product_snapshot_id",
            "price_snapshot_id",
            "economics_snapshot_id",
            "verified_economics_opportunity_id",
        ):
            _required_text(getattr(self, name), name)


class ProductionSafetyIntegrationService:
    """Loads and validates sources without materializing runtime engine objects."""

    def __init__(self, repository: ProductionSafetySourceRepository) -> None:
        self._repository = repository

    def build_context(
        self, command: BuildProductionSafetyEvaluationContext
    ) -> ProductionSafetyEvaluationContext:
        if not isinstance(command, BuildProductionSafetyEvaluationContext):
            raise TypeError("command must be BuildProductionSafetyEvaluationContext")
        product = self._repository.get_product_snapshot(command.product_snapshot_id)
        price = self._repository.get_price_snapshot(command.price_snapshot_id)
        economics = self._repository.get_economics_snapshot(command.economics_snapshot_id)
        missing = tuple(
            name
            for name, value in (
                ("Product Observation", product),
                ("PriceIntelligence", price),
                ("EconomicsCalculation", economics),
            )
            if value is None
        )
        if missing:
            raise ProductionSafetySourceNotFoundError(
                f"Production Safety source not found: {', '.join(missing)}"
            )
        context = ProductionSafetyEvaluationContext(
            product_observation_snapshot=product,
            price_intelligence_snapshot=price,
            economics_calculation_snapshot=economics,
            verified_economics_opportunity_id=command.verified_economics_opportunity_id,
        )
        self._repository.validate_snapshot_lineage(context)
        return context


__all__ = [
    "BuildProductionSafetyEvaluationContext",
    "ProductionSafetyEvaluationContext",
    "ProductionSafetyIntegrationService",
    "ProductionSafetySnapshotLineageError",
    "ProductionSafetySourceNotFoundError",
    "ProductionSafetySourceRepository",
]
