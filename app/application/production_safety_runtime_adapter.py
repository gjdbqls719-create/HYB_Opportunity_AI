"""Disposable runtime projections from authoritative Production Safety sources."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from enum import Enum
from typing import Mapping

from app.application.production_safety_integration import (
    ProductionSafetyEvaluationContext,
    ProductionSafetySnapshotLineageError,
)
from app.application.verified_economics_snapshot import (
    VERIFIED_ECONOMICS_SNAPSHOT_SCHEMA_VERSION,
    VerifiedEconomicsSnapshot,
    VerifiedEconomicsSnapshotRepository,
)
from app.domain.economics_calculation_snapshot import (
    ECONOMICS_ANALYSIS_SCHEMA_VERSION,
    ECONOMICS_CALCULATION_SNAPSHOT_SCHEMA_VERSION,
    EconomicsCalculationSnapshot,
    UnsupportedEconomicsAnalysisValueError,
)
from app.domain.opportunity import EconomicsCalculation
from app.domain.price_intelligence import (
    PRICE_INTELLIGENCE_SNAPSHOT_SCHEMA_VERSION,
    PriceIntelligenceSnapshot,
)
from app.domain.product_observation import (
    PRODUCT_OBSERVATION_SNAPSHOT_SCHEMA_VERSION,
    ProductObservationSnapshot,
)
from app.models import Product
from app.application.product_runtime import (
    ProductRuntimeReconstructionError,
    reconstruct_runtime_product,
)
from engine.price_intelligence import PriceIntelligence


class ProductionSafetyRuntimeAdapterError(RuntimeError):
    pass


class MissingProductionSafetyRuntimeSourceError(ProductionSafetyRuntimeAdapterError):
    pass


class ProductionSafetyRuntimeIdentityConflictError(ProductionSafetyRuntimeAdapterError):
    pass


class MalformedProductionSafetyRuntimeSourceError(ProductionSafetyRuntimeAdapterError):
    pass


class UnsupportedProductionSafetyRuntimeVersionError(ProductionSafetyRuntimeAdapterError):
    pass


class ProductionSafetyRuntimeReconstructionError(ProductionSafetyRuntimeAdapterError):
    pass


class UnsupportedProductionSafetyRuntimeAnalysisValueError(
    ProductionSafetyRuntimeAdapterError
):
    pass


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value


@dataclass(frozen=True, slots=True)
class ProductionSafetyRuntimeInputs:
    product: Product
    price_intelligence: PriceIntelligence
    economics: EconomicsCalculation
    analysis: Mapping[str, object]

    def __post_init__(self) -> None:
        if not isinstance(self.product, Product):
            raise TypeError("product must be Product")
        if not isinstance(self.price_intelligence, PriceIntelligence):
            raise TypeError("price_intelligence must be PriceIntelligence")
        if not isinstance(self.economics, EconomicsCalculation):
            raise TypeError("economics must be EconomicsCalculation")
        if not isinstance(self.analysis, Mapping):
            raise TypeError("analysis must be a Mapping")
        object.__setattr__(self, "analysis", MappingProxyType(dict(self.analysis)))


class ProductionSafetyRuntimeAdapter:
    """Reconstructs exact runtime values but never evaluates Production Safety."""

    def __init__(
        self,
        verified_economics_repository: VerifiedEconomicsSnapshotRepository,
        *,
        supported_analyzer_version: str,
        supported_calculation_version: str,
        analysis_enum_types: tuple[type[Enum], ...] = (),
    ) -> None:
        self._verified_economics = verified_economics_repository
        self._supported_analyzer_version = _required_text(
            supported_analyzer_version, "supported_analyzer_version"
        )
        self._supported_calculation_version = _required_text(
            supported_calculation_version, "supported_calculation_version"
        )
        if not isinstance(analysis_enum_types, tuple):
            raise TypeError("analysis_enum_types must be a tuple")
        self._analysis_enum_types = analysis_enum_types

    def load_verified_economics_snapshot(
        self, context: ProductionSafetyEvaluationContext
    ) -> VerifiedEconomicsSnapshot:
        self._validate_context(context)
        reference = context.verified_economics_opportunity_id
        try:
            snapshot = self._verified_economics.get_verified_economics_snapshot(reference)
        except Exception as error:
            raise ProductionSafetyRuntimeReconstructionError(
                "Verified Economics source query failed"
            ) from error
        if snapshot is None:
            raise MissingProductionSafetyRuntimeSourceError(
                "Verified Economics snapshot not found"
            )
        if not isinstance(snapshot, VerifiedEconomicsSnapshot):
            raise MalformedProductionSafetyRuntimeSourceError(
                "Verified Economics source is malformed"
            )
        if snapshot.schema_version != VERIFIED_ECONOMICS_SNAPSHOT_SCHEMA_VERSION:
            raise UnsupportedProductionSafetyRuntimeVersionError(
                "unsupported Verified Economics snapshot schema version"
            )
        opportunity_id = context.candidate_opportunity_binding.opportunity_id
        if snapshot.opportunity_id != reference or snapshot.opportunity_id != opportunity_id:
            raise ProductionSafetyRuntimeIdentityConflictError(
                "Verified Economics snapshot identity conflicts with evaluation context"
            )
        return snapshot

    def reconstruct_product(self, snapshot: ProductObservationSnapshot) -> Product:
        try:
            return reconstruct_runtime_product(snapshot)
        except ProductRuntimeReconstructionError as error:
            if "unsupported" in str(error):
                raise UnsupportedProductionSafetyRuntimeVersionError(str(error)) from error
            if "malformed" in str(error) or "unknown shipping" in str(error):
                raise MalformedProductionSafetyRuntimeSourceError(str(error)) from error
            raise ProductionSafetyRuntimeReconstructionError(
                str(error)
            ) from error

    def reconstruct_price_intelligence(
        self, snapshot: PriceIntelligenceSnapshot
    ) -> PriceIntelligence:
        if not isinstance(snapshot, PriceIntelligenceSnapshot):
            raise MalformedProductionSafetyRuntimeSourceError(
                "PriceIntelligence source is malformed"
            )
        if snapshot.schema_version != PRICE_INTELLIGENCE_SNAPSHOT_SCHEMA_VERSION:
            raise UnsupportedProductionSafetyRuntimeVersionError(
                "unsupported PriceIntelligence snapshot schema version"
            )
        if snapshot.analyzer_version != self._supported_analyzer_version:
            raise UnsupportedProductionSafetyRuntimeVersionError(
                "unsupported PriceIntelligence analyzer version"
            )
        return PriceIntelligence(
            currency=snapshot.currency,
            lowest_price=snapshot.lowest_price,
            average_price=snapshot.average_price,
            median_price=snapshot.median_price,
            highest_price=snapshot.highest_price,
            price_range=snapshot.price_range,
            price_variation_rate=snapshot.price_variation_rate,
            price_stability_level=snapshot.price_stability_level,
            recommended_selling_price=snapshot.recommended_selling_price,
            sample_size=snapshot.sample_size,
        )

    def reconstruct_analysis(
        self, snapshot: EconomicsCalculationSnapshot
    ) -> Mapping[str, object]:
        self._validate_economics_version(snapshot)
        if snapshot.analysis.analysis_version != ECONOMICS_ANALYSIS_SCHEMA_VERSION:
            raise UnsupportedProductionSafetyRuntimeVersionError(
                "unsupported Economics analysis schema version"
            )
        try:
            return snapshot.analysis.to_runtime_mapping(self._analysis_enum_types)
        except UnsupportedEconomicsAnalysisValueError as error:
            raise UnsupportedProductionSafetyRuntimeAnalysisValueError(
                "Economics analysis runtime value cannot be reconstructed"
            ) from error

    def reconstruct_economics(
        self,
        snapshot: EconomicsCalculationSnapshot,
        verified_economics_snapshot: VerifiedEconomicsSnapshot,
    ) -> EconomicsCalculation:
        self._validate_economics_version(snapshot)
        if not isinstance(verified_economics_snapshot, VerifiedEconomicsSnapshot):
            raise MalformedProductionSafetyRuntimeSourceError(
                "Verified Economics source is malformed"
            )
        if snapshot.verified_economics_opportunity_id != verified_economics_snapshot.opportunity_id:
            raise ProductionSafetyRuntimeIdentityConflictError(
                "EconomicsCalculation source reference does not match Verified Economics"
            )
        analysis = self.reconstruct_analysis(snapshot)
        return EconomicsCalculation(
            inputs=verified_economics_snapshot.inputs,
            marketplace_fee=snapshot.marketplace_fee,
            payment_fee=snapshot.payment_fee,
            tax_cost=snapshot.tax_cost,
            landed_cost=snapshot.landed_cost,
            selling_cost=snapshot.selling_cost,
            total_cost=snapshot.total_cost,
            net_profit=snapshot.net_profit,
            roi=snapshot.roi,
            landed_cost_roi=snapshot.landed_cost_roi,
            margin_rate=snapshot.margin_rate,
            analysis=analysis,
        )

    def reconstruct_inputs(
        self,
        context: ProductionSafetyEvaluationContext,
        verified_economics_snapshot: VerifiedEconomicsSnapshot,
    ) -> ProductionSafetyRuntimeInputs:
        self._validate_context(context)
        product = self.reconstruct_product(context.product_observation_snapshot)
        price = self.reconstruct_price_intelligence(context.price_intelligence_snapshot)
        economics = self.reconstruct_economics(
            context.economics_calculation_snapshot,
            verified_economics_snapshot,
        )
        return ProductionSafetyRuntimeInputs(product, price, economics, economics.analysis)

    def _validate_context(self, context: ProductionSafetyEvaluationContext) -> None:
        if not isinstance(context, ProductionSafetyEvaluationContext):
            raise MalformedProductionSafetyRuntimeSourceError(
                "evaluation context is malformed"
            )
        try:
            ProductionSafetyEvaluationContext(
                context.product_observation_snapshot,
                context.price_intelligence_snapshot,
                context.economics_calculation_snapshot,
                context.candidate_opportunity_binding,
                context.verified_economics_opportunity_id,
            )
        except (ProductionSafetySnapshotLineageError, ValueError) as error:
            raise ProductionSafetyRuntimeIdentityConflictError(str(error)) from error
        self._validate_economics_version(context.economics_calculation_snapshot)
        self.reconstruct_price_intelligence(context.price_intelligence_snapshot)
        self.reconstruct_product(context.product_observation_snapshot)

    def _validate_economics_version(
        self, snapshot: EconomicsCalculationSnapshot
    ) -> None:
        if not isinstance(snapshot, EconomicsCalculationSnapshot):
            raise MalformedProductionSafetyRuntimeSourceError(
                "EconomicsCalculation source is malformed"
            )
        if snapshot.schema_version != ECONOMICS_CALCULATION_SNAPSHOT_SCHEMA_VERSION:
            raise UnsupportedProductionSafetyRuntimeVersionError(
                "unsupported EconomicsCalculation snapshot schema version"
            )
        if snapshot.calculation_version != self._supported_calculation_version:
            raise UnsupportedProductionSafetyRuntimeVersionError(
                "unsupported EconomicsCalculation version"
            )


__all__ = [
    "MalformedProductionSafetyRuntimeSourceError",
    "MissingProductionSafetyRuntimeSourceError",
    "ProductionSafetyRuntimeAdapter",
    "ProductionSafetyRuntimeAdapterError",
    "ProductionSafetyRuntimeIdentityConflictError",
    "ProductionSafetyRuntimeInputs",
    "ProductionSafetyRuntimeReconstructionError",
    "UnsupportedProductionSafetyRuntimeVersionError",
    "UnsupportedProductionSafetyRuntimeAnalysisValueError",
]
