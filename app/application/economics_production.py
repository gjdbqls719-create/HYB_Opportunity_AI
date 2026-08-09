"""Thin exact-source production entries for the acquisition/economics chain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.application.economics_source_composition import (
    ComposeEconomicsSources,
    ComposeEconomicsSourcesCommand,
    EconomicsSourceCompositionSourceError,
)
from app.application.sourcing.acquisition_cost_normalization import (
    AcquisitionCostNormalizationSourceError,
    NormalizeAcquisitionCosts,
    NormalizeAcquisitionCostsCommand,
)
from app.application.sourcing.economics_binding import (
    BindSourcingEconomicsSource,
    BindSourcingEconomicsSourceCommand,
    SourcingEconomicsSourceNotFoundError,
)
from app.application.sourcing.landed_cost import (
    ComposeLandedCost,
    ComposeLandedCostCommand,
    SourcingEconomicsBindingNotFoundError,
)
from app.application.sourcing.shipping_allocation_authority import (
    AdmitShippingAllocationAuthority,
    ShippingAllocationSourceNotFoundError,
)
from app.domain.opportunity import (
    ECONOMICS_SOURCE_COMPOSITION_POLICY_NAME,
    ECONOMICS_SOURCE_COMPOSITION_POLICY_VERSION,
)
from app.domain.sourcing import (
    ACQUISITION_COST_NORMALIZATION_POLICY_NAME,
    ACQUISITION_COST_NORMALIZATION_POLICY_VERSION,
    CostAllocationBasis,
    LandedCostComponentKind,
    ShippingAllocationAuthorityCommand,
    SourcingEconomicsBindingReference,
    SourcingEconomicsSourceReference,
    SourcingEvidenceReference,
)


class EconomicsProductionOpportunityConflictError(RuntimeError):
    pass


class EconomicsProductionSourceNotFoundError(RuntimeError):
    pass


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class SourcingEconomicsBindingProductionRequest:
    command_id: str
    opportunity_id: str
    source_reference: SourcingEconomicsSourceReference
    requested_at: datetime

    def __post_init__(self) -> None:
        for name in ("command_id", "opportunity_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if not isinstance(self.source_reference, SourcingEconomicsSourceReference):
            raise TypeError("source_reference must be SourcingEconomicsSourceReference")
        _aware(self.requested_at, "requested_at")


class SourcingEconomicsBindingProductionEntry:
    def __init__(self, repository, owner: BindSourcingEconomicsSource) -> None:
        self._repository = repository
        self._owner = owner

    def execute(self, request: SourcingEconomicsBindingProductionRequest):
        source = self._repository.get_source_admission(request.source_reference)
        if source is None:
            raise SourcingEconomicsSourceNotFoundError(
                "exact Sourcing Admission revision is missing"
            )
        identity = source.selling_product_lineage.opportunity_identity
        if identity.opportunity_id != request.opportunity_id:
            raise EconomicsProductionOpportunityConflictError(
                "Sourcing Admission Opportunity differs from request"
            )
        return self._owner.execute(
            BindSourcingEconomicsSourceCommand(
                request.command_id,
                identity,
                request.source_reference,
                request.requested_at,
            )
        )


@dataclass(frozen=True, slots=True)
class LandedCostProductionRequest:
    command_id: str
    opportunity_id: str
    binding_id: str
    requested_at: datetime

    def __post_init__(self) -> None:
        for name in ("command_id", "opportunity_id", "binding_id"):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        _aware(self.requested_at, "requested_at")


class LandedCostProductionEntry:
    def __init__(self, repository, owner: ComposeLandedCost) -> None:
        self._repository = repository
        self._owner = owner

    def execute(self, request: LandedCostProductionRequest):
        reference = SourcingEconomicsBindingReference(request.binding_id)
        binding = self._repository.get_binding(reference)
        if binding is None:
            raise SourcingEconomicsBindingNotFoundError("exact binding is missing")
        if binding.opportunity_identity.opportunity_id != request.opportunity_id:
            raise EconomicsProductionOpportunityConflictError(
                "binding Opportunity differs from request"
            )
        return self._owner.execute(
            ComposeLandedCostCommand(
                request.command_id,
                binding.opportunity_identity,
                reference,
                request.requested_at,
            )
        )


@dataclass(frozen=True, slots=True)
class ShippingAllocationProductionRequest:
    command_id: str
    opportunity_id: str
    composition_id: str
    component_kind: LandedCostComponentKind
    requested_at: datetime
    effective_allocation_basis: CostAllocationBasis | None = None
    per_order_denominator: int | None = None
    per_order_denominator_unit: str | None = None
    operator_id: str | None = None
    verified_at: datetime | None = None
    evidence_reference: SourcingEvidenceReference | None = None


class ShippingAllocationProductionEntry:
    def __init__(self, repository, owner: AdmitShippingAllocationAuthority) -> None:
        self._repository = repository
        self._owner = owner

    def execute(self, request: ShippingAllocationProductionRequest):
        composition = self._repository.get_composition(request.composition_id)
        if composition is None:
            raise ShippingAllocationSourceNotFoundError("composition is missing")
        if composition.opportunity_identity.opportunity_id != request.opportunity_id:
            raise EconomicsProductionOpportunityConflictError(
                "composition Opportunity differs from request"
            )
        return self._owner.execute(
            ShippingAllocationAuthorityCommand(
                command_id=request.command_id,
                composition_id=request.composition_id,
                opportunity_identity=composition.opportunity_identity,
                component_kind=request.component_kind,
                requested_at=request.requested_at,
                effective_allocation_basis=request.effective_allocation_basis,
                per_order_denominator=request.per_order_denominator,
                per_order_denominator_unit=request.per_order_denominator_unit,
                operator_id=request.operator_id,
                verified_at=request.verified_at,
                evidence_reference=request.evidence_reference,
            )
        )


@dataclass(frozen=True, slots=True)
class AcquisitionNormalizationProductionRequest:
    command_id: str
    opportunity_id: str
    composition_id: str
    allocation_authority_ids: tuple[str, ...]
    fx_observation_ids: tuple[str, ...]
    target_currency: str
    requested_at: datetime


class AcquisitionNormalizationProductionEntry:
    def __init__(self, repository, owner: NormalizeAcquisitionCosts) -> None:
        self._repository = repository
        self._owner = owner

    def execute(self, request: AcquisitionNormalizationProductionRequest):
        composition = self._repository.get_composition(request.composition_id)
        if composition is None:
            raise EconomicsProductionSourceNotFoundError(
                "exact composition is missing"
            )
        if composition.opportunity_identity.opportunity_id != request.opportunity_id:
            raise EconomicsProductionOpportunityConflictError(
                "composition Opportunity differs from request"
            )
        if any(
            self._repository.get_allocation_authority(value) is None
            for value in request.allocation_authority_ids
        ):
            raise EconomicsProductionSourceNotFoundError(
                "exact allocation authority is missing"
            )
        if any(
            self._repository.get_fx_observation(value) is None
            for value in request.fx_observation_ids
        ):
            raise EconomicsProductionSourceNotFoundError(
                "exact FX observation is missing"
            )
        return self._owner.execute(
            NormalizeAcquisitionCostsCommand(
                command_id=request.command_id,
                opportunity_identity=composition.opportunity_identity,
                composition_id=request.composition_id,
                allocation_authority_ids=request.allocation_authority_ids,
                fx_observation_ids=request.fx_observation_ids,
                target_currency=request.target_currency,
                requested_at=request.requested_at,
                policy_name=ACQUISITION_COST_NORMALIZATION_POLICY_NAME,
                policy_version=ACQUISITION_COST_NORMALIZATION_POLICY_VERSION,
            )
        )


@dataclass(frozen=True, slots=True)
class EconomicsSourceCompositionProductionRequest:
    command_id: str
    opportunity_id: str
    acquisition_normalization_id: str
    verified_economics_snapshot_at: datetime
    verified_economics_schema_version: str
    requested_at: datetime


class EconomicsSourceCompositionProductionEntry:
    def __init__(self, repository, owner: ComposeEconomicsSources) -> None:
        self._repository = repository
        self._owner = owner

    def execute(self, request: EconomicsSourceCompositionProductionRequest):
        normalization = self._repository.get_normalization(
            request.acquisition_normalization_id
        )
        if normalization is None:
            raise EconomicsProductionSourceNotFoundError(
                "exact Acquisition Cost Normalization is missing"
            )
        if normalization.opportunity_identity.opportunity_id != request.opportunity_id:
            raise EconomicsProductionOpportunityConflictError(
                "normalization Opportunity differs from request"
            )
        if self._repository.get_verified_economics_snapshot(request.opportunity_id) is None:
            raise EconomicsProductionSourceNotFoundError(
                "exact Verified Economics Snapshot is missing"
            )
        return self._owner.execute(
            ComposeEconomicsSourcesCommand(
                command_id=request.command_id,
                opportunity_identity=normalization.opportunity_identity,
                acquisition_normalization_id=request.acquisition_normalization_id,
                verified_economics_opportunity_id=request.opportunity_id,
                verified_economics_snapshot_at=request.verified_economics_snapshot_at,
                verified_economics_schema_version=(
                    request.verified_economics_schema_version
                ),
                requested_at=request.requested_at,
                policy_name=ECONOMICS_SOURCE_COMPOSITION_POLICY_NAME,
                policy_version=ECONOMICS_SOURCE_COMPOSITION_POLICY_VERSION,
            )
        )


__all__ = [
    name
    for name in globals()
    if name.endswith("ProductionEntry")
    or name.endswith("ProductionRequest")
    or name in {
        "EconomicsProductionOpportunityConflictError",
        "EconomicsProductionSourceNotFoundError",
    }
]
