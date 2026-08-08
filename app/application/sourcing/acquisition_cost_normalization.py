"""Authoritative exact-source acquisition-cost normalization owner."""

from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from enum import Enum
import hashlib
import json
from typing import Callable, Protocol

from app.domain.sourcing import (
    ACQUISITION_COST_NORMALIZATION_DECIMAL_PRECISION,
    ACQUISITION_COST_NORMALIZATION_POLICY_NAME,
    ACQUISITION_COST_NORMALIZATION_POLICY_VERSION,
    ACQUISITION_COST_NORMALIZATION_ROUNDING,
    AcquisitionCostNormalization,
    CommercialFactAvailability,
    CostAllocationBasis,
    FXConversionDirection,
    FXObservation,
    LandedCostComponentKind,
    LandedCostComposition,
    NormalizedAcquisitionCostComponent,
    ShippingAllocationAuthority,
    ShippingAllocationAuthorityDenominatorSource,
    ShippingAllocationAuthorityStatus,
    normalization_decimal_context,
    normalized_total,
)
from app.domain.decision_engine import OpportunityIdentity


ACQUISITION_COST_NORMALIZATION_COMMAND_SCHEMA_VERSION = (
    "acquisition-cost-normalization-command-v1"
)
ACQUISITION_COST_NORMALIZATION_RECEIPT_SCHEMA_VERSION = (
    "acquisition-cost-normalization-receipt-v1"
)


class AcquisitionCostNormalizationError(RuntimeError):
    pass


class AcquisitionCostNormalizationSourceError(AcquisitionCostNormalizationError):
    pass


class AcquisitionCostNormalizationPolicyError(AcquisitionCostNormalizationError):
    pass


class AcquisitionCostNormalizationReplayConflictError(
    AcquisitionCostNormalizationError
):
    pass


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _currency(value: str, name: str) -> str:
    result = _text(value, name).upper()
    if len(result) != 3 or not result.isascii() or not result.isalpha():
        raise ValueError(f"{name} must be a three-letter currency code")
    return result


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _canonical(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _canonical(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    return value


def _fingerprint(value: object) -> str:
    encoded = json.dumps(
        _canonical(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class NormalizeAcquisitionCostsCommand:
    command_id: str
    opportunity_identity: OpportunityIdentity
    composition_id: str
    allocation_authority_ids: tuple[str, ...]
    fx_observation_ids: tuple[str, ...]
    target_currency: str
    requested_at: datetime
    policy_name: str
    policy_version: str
    schema_version: str = ACQUISITION_COST_NORMALIZATION_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        if not isinstance(self.opportunity_identity, OpportunityIdentity):
            raise TypeError("opportunity_identity must be OpportunityIdentity")
        object.__setattr__(self, "composition_id", _text(self.composition_id, "composition_id"))
        for name in ("allocation_authority_ids", "fx_observation_ids"):
            values = getattr(self, name)
            if not isinstance(values, tuple):
                raise TypeError(f"{name} must be tuple")
            normalized = tuple(_text(value, name) for value in values)
            if len(set(normalized)) != len(normalized):
                raise ValueError(f"{name} cannot contain duplicates")
            object.__setattr__(self, name, normalized)
        object.__setattr__(self, "target_currency", _currency(self.target_currency, "target_currency"))
        object.__setattr__(self, "requested_at", _aware(self.requested_at, "requested_at"))
        object.__setattr__(self, "policy_name", _text(self.policy_name, "policy_name"))
        object.__setattr__(self, "policy_version", _text(self.policy_version, "policy_version"))
        if self.schema_version != ACQUISITION_COST_NORMALIZATION_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported normalization command schema")

    @property
    def fingerprint(self) -> str:
        return _fingerprint(self)


@dataclass(frozen=True, slots=True)
class AcquisitionCostNormalizationReceipt:
    command_id: str
    normalization_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = ACQUISITION_COST_NORMALIZATION_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "normalization_id", _text(self.normalization_id, "normalization_id"))
        fingerprint = _text(self.command_fingerprint, "command_fingerprint").lower()
        if len(fingerprint) != 64 or any(
            character not in "0123456789abcdef" for character in fingerprint
        ):
            raise ValueError("command_fingerprint must be SHA-256 text")
        object.__setattr__(self, "command_fingerprint", fingerprint)
        object.__setattr__(self, "committed_at", _aware(self.committed_at, "committed_at"))
        if self.schema_version != ACQUISITION_COST_NORMALIZATION_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported normalization receipt schema")


@dataclass(frozen=True, slots=True)
class AcquisitionCostNormalizationResult:
    normalization: AcquisitionCostNormalization
    receipt: AcquisitionCostNormalizationReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.normalization, AcquisitionCostNormalization):
            raise TypeError("normalization must be AcquisitionCostNormalization")
        if not isinstance(self.receipt, AcquisitionCostNormalizationReceipt):
            raise TypeError("receipt must be AcquisitionCostNormalizationReceipt")
        if self.normalization.normalization_id != self.receipt.normalization_id:
            raise ValueError("receipt must reference normalization")
        if not isinstance(self.replayed, bool):
            raise TypeError("replayed must be bool")


class AcquisitionCostNormalizationRepository(Protocol):
    def get_composition(self, composition_id: str) -> LandedCostComposition | None: ...
    def get_allocation_authority(self, authority_id: str) -> ShippingAllocationAuthority | None: ...
    def get_fx_observation(self, observation_id: str) -> FXObservation | None: ...
    def validate_replay(self, command_id: str, fingerprint: str) -> AcquisitionCostNormalizationResult | None: ...
    def save_normalization(self, command: NormalizeAcquisitionCostsCommand,
                           normalization: AcquisitionCostNormalization,
                           receipt: AcquisitionCostNormalizationReceipt) -> AcquisitionCostNormalizationResult: ...


class NormalizeAcquisitionCosts:
    def __init__(
        self,
        repository: AcquisitionCostNormalizationRepository,
        *,
        normalization_id_generator: Callable[[], str],
        normalized_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        if not all(
            callable(value)
            for value in (
                normalization_id_generator,
                normalized_clock,
                committed_clock,
            )
        ):
            raise TypeError("normalization dependencies must be callable")
        self._repository = repository
        self._identity = normalization_id_generator
        self._normalized_clock = normalized_clock
        self._committed_clock = committed_clock

    def execute(
        self,
        command: NormalizeAcquisitionCostsCommand,
    ) -> AcquisitionCostNormalizationResult:
        if not isinstance(command, NormalizeAcquisitionCostsCommand):
            raise TypeError("command must be NormalizeAcquisitionCostsCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        self._validate_policy(command)
        composition = self._repository.get_composition(command.composition_id)
        if composition is None:
            raise AcquisitionCostNormalizationSourceError("exact composition is missing")
        if composition.opportunity_identity != command.opportunity_identity:
            raise AcquisitionCostNormalizationSourceError("composition Opportunity differs")

        allocations = self._allocation_sources(command, composition)
        observations = self._fx_sources(command, composition)
        components = self._normalize_components(
            composition,
            allocations,
            observations,
            command.target_currency,
        )
        normalization = AcquisitionCostNormalization(
            normalization_id=_text(self._identity(), "normalization_id"),
            opportunity_identity=composition.opportunity_identity,
            composition_id=composition.composition_id,
            allocation_authority_ids=command.allocation_authority_ids,
            fx_observation_ids=command.fx_observation_ids,
            target_currency=command.target_currency,
            components=components,
            total_per_unit_acquisition_cost=normalized_total(
                tuple(value.normalized_per_unit_amount for value in components)
            ),
            policy_name=command.policy_name,
            policy_version=command.policy_version,
            policy_precision=ACQUISITION_COST_NORMALIZATION_DECIMAL_PRECISION,
            policy_rounding=ACQUISITION_COST_NORMALIZATION_ROUNDING,
            requested_at=command.requested_at,
            normalized_at=_aware(self._normalized_clock(), "normalized_at"),
        )
        receipt = AcquisitionCostNormalizationReceipt(
            command_id=command.command_id,
            normalization_id=normalization.normalization_id,
            command_fingerprint=command.fingerprint,
            committed_at=_aware(self._committed_clock(), "committed_at"),
        )
        return self._repository.save_normalization(command, normalization, receipt)

    @staticmethod
    def _validate_policy(command) -> None:
        if (
            command.policy_name != ACQUISITION_COST_NORMALIZATION_POLICY_NAME
            or command.policy_version != ACQUISITION_COST_NORMALIZATION_POLICY_VERSION
        ):
            raise AcquisitionCostNormalizationPolicyError(
                "unsupported acquisition normalization policy"
            )

    def _allocation_sources(self, command, composition):
        if any(
            component.availability is CommercialFactAvailability.UNKNOWN
            for component in composition.components
        ):
            raise AcquisitionCostNormalizationSourceError(
                "UNKNOWN acquisition component cannot be normalized"
            )
        expected = tuple(
            component.kind
            for component in composition.components[1:]
            if component.availability is CommercialFactAvailability.KNOWN
        )
        authorities = []
        for authority_id in command.allocation_authority_ids:
            value = self._repository.get_allocation_authority(authority_id)
            if value is None:
                raise AcquisitionCostNormalizationSourceError(
                    "exact allocation authority is missing"
                )
            authorities.append(value)
        if tuple(value.component_kind for value in authorities) != expected:
            raise AcquisitionCostNormalizationSourceError(
                "allocation authority manifest differs from applicable components"
            )
        for authority in authorities:
            component = next(
                value
                for value in composition.components
                if value.kind is authority.component_kind
            )
            if (
                authority.authority_id
                not in command.allocation_authority_ids
                or authority.composition_id != composition.composition_id
                or authority.opportunity_identity != composition.opportunity_identity
                or authority.original_allocation_basis is not component.allocation_basis
                or authority.status is not ShippingAllocationAuthorityStatus.RESOLVED
                or authority.allocation_basis
                in {CostAllocationBasis.PER_WEIGHT, CostAllocationBasis.UNSPECIFIED}
            ):
                raise AcquisitionCostNormalizationSourceError(
                    "allocation authority does not match exact component source"
                )
            if authority.allocation_basis in {
                CostAllocationBasis.PER_ORDER,
                CostAllocationBasis.PER_QUOTED_QUANTITY,
            } and (
                authority.denominator is None
                or authority.denominator.quantity <= 0
            ):
                raise AcquisitionCostNormalizationSourceError(
                    "resolved allocation denominator is missing"
                )
        return {value.component_kind: value for value in authorities}

    def _fx_sources(self, command, composition):
        observations = []
        for observation_id in command.fx_observation_ids:
            value = self._repository.get_fx_observation(observation_id)
            if value is None:
                raise AcquisitionCostNormalizationSourceError(
                    "exact FX observation is missing"
                )
            observations.append(value)
        needed = tuple(
            dict.fromkeys(
                component.currency
                for component in composition.components
                if component.availability is CommercialFactAvailability.KNOWN
                and component.currency != command.target_currency
            )
        )
        resolved = {}
        used_ids = []
        for source_currency in needed:
            matches = [
                value
                for value in observations
                if (
                    value.base_currency == source_currency
                    and value.quote_currency == command.target_currency
                )
                or (
                    value.quote_currency == source_currency
                    and value.base_currency == command.target_currency
                )
            ]
            if len(matches) != 1:
                raise AcquisitionCostNormalizationSourceError(
                    "cross-currency component requires one exact FX observation"
                )
            observation = matches[0]
            direction = (
                FXConversionDirection.DIRECT
                if observation.base_currency == source_currency
                else FXConversionDirection.INVERSE
            )
            resolved[source_currency] = (observation, direction)
            used_ids.append(observation.observation_id)
        if tuple(dict.fromkeys(used_ids)) != command.fx_observation_ids:
            raise AcquisitionCostNormalizationSourceError(
                "FX source manifest contains unused or misordered observations"
            )
        return resolved

    @staticmethod
    def _normalize_components(composition, allocations, observations, target_currency):
        normalized = []
        with localcontext(normalization_decimal_context()):
            for component in composition.components:
                if component.availability is CommercialFactAvailability.NOT_APPLICABLE:
                    normalized.append(
                        NormalizedAcquisitionCostComponent(
                            kind=component.kind,
                            original_availability=component.availability,
                            original_amount=None,
                            original_currency=None,
                            original_allocation_basis=component.allocation_basis,
                            effective_allocation_basis=component.allocation_basis,
                            allocation_authority_id=None,
                            denominator_quantity=None,
                            denominator_source=None,
                            fx_observation_id=None,
                            fx_direction=FXConversionDirection.NONE,
                            target_currency=target_currency,
                            normalized_per_unit_amount=Decimal("0"),
                        )
                    )
                    continue
                if component.availability is not CommercialFactAvailability.KNOWN:
                    raise AcquisitionCostNormalizationSourceError(
                        "UNKNOWN acquisition component cannot be normalized"
                    )
                amount = component.amount
                assert amount is not None and component.currency is not None
                authority = allocations.get(component.kind)
                basis = component.allocation_basis
                denominator = None
                if component.kind is not LandedCostComponentKind.UNIT_PURCHASE:
                    if authority is None:
                        raise AcquisitionCostNormalizationSourceError(
                            "shipping component lacks exact allocation authority"
                        )
                    basis = authority.allocation_basis
                    denominator = authority.denominator
                if basis is CostAllocationBasis.PER_UNIT:
                    per_unit = amount
                elif basis in {
                    CostAllocationBasis.PER_ORDER,
                    CostAllocationBasis.PER_QUOTED_QUANTITY,
                } and denominator is not None:
                    per_unit = amount / Decimal(denominator.quantity)
                else:
                    raise AcquisitionCostNormalizationSourceError(
                        "component allocation basis cannot be normalized"
                    )
                fx_source = observations.get(component.currency)
                if fx_source is None:
                    converted = per_unit
                    direction = FXConversionDirection.NONE
                    observation = None
                else:
                    observation, direction = fx_source
                    converted = (
                        per_unit * observation.rate
                        if direction is FXConversionDirection.DIRECT
                        else per_unit / observation.rate
                    )
                normalized.append(
                    NormalizedAcquisitionCostComponent(
                        kind=component.kind,
                        original_availability=component.availability,
                        original_amount=component.amount,
                        original_currency=component.currency,
                        original_allocation_basis=component.allocation_basis,
                        effective_allocation_basis=basis,
                        allocation_authority_id=(
                            None if authority is None else authority.authority_id
                        ),
                        denominator_quantity=(
                            None if denominator is None else denominator.quantity
                        ),
                        denominator_source=(
                            None if denominator is None else denominator.source
                        ),
                        fx_observation_id=(
                            None if observation is None else observation.observation_id
                        ),
                        fx_direction=direction,
                        target_currency=target_currency,
                        normalized_per_unit_amount=converted,
                    )
                )
        return tuple(normalized)


__all__ = [
    name
    for name in globals()
    if name.startswith("Acquisition")
    or name.startswith("Normalize")
    or name.startswith("ACQUISITION")
]
