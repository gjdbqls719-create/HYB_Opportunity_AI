"""Application owner for exact critical-cost completeness evaluation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from typing import Callable, Protocol

from app.application.verified_economics_snapshot import VerifiedEconomicsSnapshot
from app.domain.opportunity import EvidenceStatus, MoneyInput
from app.domain.sourcing import (
    ACQUISITION_COST_NORMALIZATION_POLICY_NAME,
    ACQUISITION_COST_NORMALIZATION_POLICY_VERSION,
    ACQUISITION_COST_NORMALIZATION_SCHEMA_VERSION,
    CRITICAL_COST_COMPLETENESS_SCHEMA_VERSION,
    CRITICAL_COST_COMPLETENESS_SCHEMA_VERSION_V2,
    AcquisitionCostNormalization,
    CommercialFactAvailability,
    CostAllocationBasis,
    CriticalCostCompleteness,
    CriticalCostCompletenessPolicy,
    CriticalCostCompletenessReason,
    CriticalCostCompletenessState,
    CriticalCostReasonCode,
    CriticalCostReasonSeverity,
    FounderSourcingAdmission,
    FXConversionDirection,
    FXObservation,
    LandedCostComposition,
    SourcingEconomicsBinding,
    SourcingEconomicsBindingReference,
    SourcingEconomicsSourceReference,
    ShippingAllocationAuthority,
    ShippingAllocationAuthorityStatus,
)


class CriticalCostCompletenessError(RuntimeError):
    pass


class CriticalCostSourceNotFoundError(CriticalCostCompletenessError):
    pass


class CriticalCostSourceMismatchError(CriticalCostCompletenessError):
    pass


class CriticalCostCompletenessReplayConflictError(CriticalCostCompletenessError):
    pass


CRITICAL_COST_COMPLETENESS_COMMAND_SCHEMA_VERSION = "critical-cost-completeness-command-v1"
CRITICAL_COST_COMPLETENESS_COMMAND_SCHEMA_VERSION_V2 = (
    "critical-cost-completeness-command-v2"
)
CRITICAL_COST_COMPLETENESS_RECEIPT_SCHEMA_VERSION = "critical-cost-completeness-receipt-v1"


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


@dataclass(frozen=True, slots=True)
class PersistCriticalCostCompletenessCommand:
    command_id: str
    composition_id: str
    verified_economics_opportunity_id: str
    verified_economics_snapshot_at: datetime
    verified_economics_schema_version: str
    policy_name: str
    policy_version: str
    requested_at: datetime
    schema_version: str = CRITICAL_COST_COMPLETENESS_COMMAND_SCHEMA_VERSION
    acquisition_normalization_id: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "command_id", "composition_id", "verified_economics_opportunity_id",
            "verified_economics_schema_version", "policy_name", "policy_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        _aware(self.verified_economics_snapshot_at, "verified_economics_snapshot_at")
        _aware(self.requested_at, "requested_at")
        if self.schema_version not in {
            CRITICAL_COST_COMPLETENESS_COMMAND_SCHEMA_VERSION,
            CRITICAL_COST_COMPLETENESS_COMMAND_SCHEMA_VERSION_V2,
        }:
            raise ValueError("unsupported Critical Cost Completeness command version")
        if self.schema_version == CRITICAL_COST_COMPLETENESS_COMMAND_SCHEMA_VERSION:
            if self.acquisition_normalization_id is not None:
                raise ValueError("v1 command cannot name Acquisition Normalization")
        else:
            object.__setattr__(
                self,
                "acquisition_normalization_id",
                _text(
                    self.acquisition_normalization_id,  # type: ignore[arg-type]
                    "acquisition_normalization_id",
                ),
            )

    @property
    def fingerprint(self) -> str:
        payload = {
            "command_id": self.command_id,
            "composition_id": self.composition_id,
            "verified_economics_source": {
                "opportunity_id": self.verified_economics_opportunity_id,
                "snapshot_at": self.verified_economics_snapshot_at.astimezone(timezone.utc).isoformat(),
                "schema_version": self.verified_economics_schema_version,
            },
            "policy_name": self.policy_name,
            "policy_version": self.policy_version,
            "requested_at": self.requested_at.astimezone(timezone.utc).isoformat(),
            "schema_version": self.schema_version,
        }
        if self.schema_version == CRITICAL_COST_COMPLETENESS_COMMAND_SCHEMA_VERSION_V2:
            payload["acquisition_normalization_id"] = self.acquisition_normalization_id
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass(frozen=True, slots=True)
class CriticalCostCompletenessReceipt:
    command_id: str
    assessment_id: str
    command_fingerprint: str
    committed_at: datetime
    schema_version: str = CRITICAL_COST_COMPLETENESS_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _text(self.command_id, "command_id"))
        object.__setattr__(self, "assessment_id", _text(self.assessment_id, "assessment_id"))
        if (
            not isinstance(self.command_fingerprint, str)
            or len(self.command_fingerprint) != 64
            or any(value not in "0123456789abcdef" for value in self.command_fingerprint)
        ):
            raise ValueError("command_fingerprint must be SHA-256 text")
        _aware(self.committed_at, "committed_at")
        if self.schema_version != CRITICAL_COST_COMPLETENESS_RECEIPT_SCHEMA_VERSION:
            raise ValueError("unsupported Critical Cost Completeness receipt version")


@dataclass(frozen=True, slots=True)
class CriticalCostCompletenessPersistenceResult:
    assessment: CriticalCostCompleteness
    receipt: CriticalCostCompletenessReceipt
    replayed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.assessment, CriticalCostCompleteness):
            raise TypeError("assessment must be CriticalCostCompleteness")
        if not isinstance(self.receipt, CriticalCostCompletenessReceipt):
            raise TypeError("receipt must be CriticalCostCompletenessReceipt")


class CriticalCostCompletenessRepository(Protocol):
    def get_composition(self, composition_id: str) -> LandedCostComposition | None: ...
    def get_binding(self, reference: SourcingEconomicsBindingReference) -> SourcingEconomicsBinding | None: ...
    def get_source_admission(self, reference: SourcingEconomicsSourceReference) -> FounderSourcingAdmission | None: ...
    def get_acquisition_normalization(self, normalization_id: str) -> AcquisitionCostNormalization | None: ...
    def get_allocation_authority(self, authority_id: str) -> ShippingAllocationAuthority | None: ...
    def get_fx_observation(self, observation_id: str) -> FXObservation | None: ...


class CriticalCostCompletenessPersistenceRepository(
    CriticalCostCompletenessRepository, Protocol
):
    def validate_replay(self, command_id: str, fingerprint: str) -> CriticalCostCompletenessPersistenceResult | None: ...
    def save_assessment(self, command: PersistCriticalCostCompletenessCommand,
                        assessment: CriticalCostCompleteness,
                        receipt: CriticalCostCompletenessReceipt) -> CriticalCostCompletenessPersistenceResult: ...


class CriticalCostVerifiedEconomicsRepository(Protocol):
    def get_verified_economics_snapshot(self, opportunity_id: str) -> VerifiedEconomicsSnapshot | None: ...


DOMESTIC_COMMERCE_CRITICAL_COST_POLICY = CriticalCostCompletenessPolicy(
    name="domestic-commerce-critical-cost-completeness",
    version="1.0.0",
    expected_sale_evidence_statuses=("verified", "estimated"),
    required_evidence_statuses=("verified",),
    require_evidence_reference=True,
    require_quote_valid_until=True,
)

DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2 = CriticalCostCompletenessPolicy(
    name="domestic-commerce-critical-cost-completeness",
    version="2.0.0",
    expected_sale_evidence_statuses=("verified", "estimated"),
    required_evidence_statuses=("verified",),
    require_evidence_reference=True,
    require_quote_valid_until=True,
)


class EvaluateCriticalCostCompleteness:
    def __init__(self, repository: CriticalCostCompletenessRepository,
                 verified_economics_repository: CriticalCostVerifiedEconomicsRepository, *,
                 policy: CriticalCostCompletenessPolicy,
                 evaluated_clock: Callable[[], datetime]) -> None:
        if not isinstance(policy, CriticalCostCompletenessPolicy):
            raise TypeError("policy must be CriticalCostCompletenessPolicy")
        if not callable(evaluated_clock):
            raise TypeError("evaluated_clock must be callable")
        self._repository = repository
        self._verified_repository = verified_economics_repository
        self._policy = policy
        self._clock = evaluated_clock

    def execute(
        self,
        composition_id: str,
        acquisition_normalization_id: str | None = None,
    ) -> CriticalCostCompleteness:
        if not isinstance(composition_id, str) or not composition_id.strip():
            raise ValueError("composition_id must be non-empty text")
        composition = self._repository.get_composition(composition_id.strip())
        if composition is None:
            raise CriticalCostSourceNotFoundError("exact Landed Cost Composition is missing")
        binding = self._repository.get_binding(composition.binding_reference)
        if binding is None:
            raise CriticalCostSourceNotFoundError("exact Sourcing Economics Binding is missing")
        if binding.reference != composition.binding_reference:
            raise CriticalCostSourceMismatchError("binding reference differs from composition")
        if binding.opportunity_identity != composition.opportunity_identity:
            raise CriticalCostSourceMismatchError("binding Opportunity differs from composition")
        admission = self._repository.get_source_admission(binding.source_reference)
        if admission is None:
            raise CriticalCostSourceNotFoundError("exact Sourcing Admission revision is missing")
        if admission.to_economics_source_reference() != binding.source_reference:
            raise CriticalCostSourceMismatchError("Admission source differs from binding")
        if admission.selling_product_lineage.opportunity_identity != composition.opportunity_identity:
            raise CriticalCostSourceMismatchError("Admission Opportunity differs from composition")
        if admission.quote_revision.evidence != composition.evidence_reference:
            raise CriticalCostSourceMismatchError("quote evidence differs from composition")
        self._validate_composition_source(composition, admission)
        opportunity_id = composition.opportunity_identity.opportunity_id
        verified = self._verified_repository.get_verified_economics_snapshot(opportunity_id)
        if verified is None:
            raise CriticalCostSourceNotFoundError("Verified Economics Snapshot is missing")
        if verified.opportunity_id != opportunity_id:
            raise CriticalCostSourceMismatchError("Verified Economics Opportunity differs")
        normalization = self._normalization(
            composition,
            verified,
            acquisition_normalization_id,
        )
        evaluated_at = self._aware(self._clock(), "evaluated_at")
        blockers = self._blocking_reasons(
            composition,
            admission,
            verified,
            evaluated_at,
            normalization,
        )
        warnings = (
            self._warning(CriticalCostReasonCode.ADVERTISING_ALLOWANCE_DEFERRED, "advertising"),
            self._warning(CriticalCostReasonCode.RETURNS_ALLOWANCE_DEFERRED, "returns"),
        )
        return CriticalCostCompleteness(
            opportunity_identity=composition.opportunity_identity,
            composition_id=composition.composition_id,
            binding_reference=composition.binding_reference,
            source_reference=binding.source_reference,
            verified_economics_opportunity_id=verified.opportunity_id,
            verified_economics_snapshot_at=verified.snapshot_at,
            verified_economics_schema_version=verified.schema_version,
            policy_name=self._policy.name,
            policy_version=self._policy.version,
            evaluated_at=evaluated_at,
            state=CriticalCostCompletenessState.INCOMPLETE if blockers else CriticalCostCompletenessState.COMPLETE,
            blocking_reasons=tuple(blockers),
            warning_reasons=warnings,
            acquisition_normalization_id=(
                None if normalization is None else normalization.normalization_id
            ),
            allocation_authority_ids=(
                () if normalization is None else normalization.allocation_authority_ids
            ),
            fx_observation_ids=(
                () if normalization is None else normalization.fx_observation_ids
            ),
            schema_version=(
                CRITICAL_COST_COMPLETENESS_SCHEMA_VERSION
                if normalization is None
                else CRITICAL_COST_COMPLETENESS_SCHEMA_VERSION_V2
            ),
        )

    def _normalization(self, composition, verified, normalization_id):
        is_v2 = self._policy == DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2
        if not is_v2:
            if normalization_id is not None:
                raise CriticalCostSourceMismatchError(
                    "v1 Critical Cost policy cannot consume Acquisition Normalization"
                )
            return None
        if normalization_id is None:
            raise CriticalCostSourceNotFoundError(
                "exact Acquisition Cost Normalization is missing"
            )
        normalization = self._repository.get_acquisition_normalization(
            _text(normalization_id, "acquisition_normalization_id")
        )
        if normalization is None:
            raise CriticalCostSourceNotFoundError(
                "exact Acquisition Cost Normalization is missing"
            )
        if (
            normalization.schema_version
            != ACQUISITION_COST_NORMALIZATION_SCHEMA_VERSION
            or normalization.policy_name
            != ACQUISITION_COST_NORMALIZATION_POLICY_NAME
            or normalization.policy_version
            != ACQUISITION_COST_NORMALIZATION_POLICY_VERSION
        ):
            raise CriticalCostSourceMismatchError(
                "Acquisition Normalization policy or schema is unsupported"
            )
        if (
            normalization.opportunity_identity != composition.opportunity_identity
            or normalization.composition_id != composition.composition_id
        ):
            raise CriticalCostSourceMismatchError(
                "Acquisition Normalization differs from exact Opportunity or composition"
            )
        self._validate_normalization_sources(composition, normalization)
        return normalization

    def _validate_normalization_sources(self, composition, normalization) -> None:
        for source, normalized in zip(
            composition.components,
            normalization.components,
            strict=True,
        ):
            if (
                source.kind is not normalized.kind
                or source.availability is not normalized.original_availability
                or source.amount != normalized.original_amount
                or source.currency != normalized.original_currency
                or source.allocation_basis is not normalized.original_allocation_basis
                or normalized.target_currency != normalization.target_currency
            ):
                raise CriticalCostSourceMismatchError(
                    "normalized component differs from exact Landed Cost source"
                )
            if normalized.allocation_authority_id is not None:
                authority = self._repository.get_allocation_authority(
                    normalized.allocation_authority_id
                )
                if authority is None:
                    raise CriticalCostSourceNotFoundError(
                        "exact Shipping Allocation Authority is missing"
                    )
                denominator = authority.denominator
                if (
                    authority.authority_id
                    not in normalization.allocation_authority_ids
                    or authority.composition_id != composition.composition_id
                    or authority.opportunity_identity != composition.opportunity_identity
                    or authority.component_kind is not source.kind
                    or authority.original_allocation_basis
                    is not source.allocation_basis
                    or authority.allocation_basis
                    is not normalized.effective_allocation_basis
                    or authority.status is not ShippingAllocationAuthorityStatus.RESOLVED
                    or authority.allocation_basis
                    in {CostAllocationBasis.PER_WEIGHT, CostAllocationBasis.UNSPECIFIED}
                    or (None if denominator is None else denominator.quantity)
                    != normalized.denominator_quantity
                    or (None if denominator is None else denominator.source)
                    != normalized.denominator_source
                ):
                    raise CriticalCostSourceMismatchError(
                        "Shipping Allocation Authority differs from normalization manifest"
                    )
            if normalized.fx_observation_id is not None:
                observation = self._repository.get_fx_observation(
                    normalized.fx_observation_id
                )
                if observation is None:
                    raise CriticalCostSourceNotFoundError(
                        "exact FX Observation is missing"
                    )
                pair = (
                    (observation.base_currency, observation.quote_currency)
                    if normalized.fx_direction is FXConversionDirection.DIRECT
                    else (observation.quote_currency, observation.base_currency)
                    if normalized.fx_direction is FXConversionDirection.INVERSE
                    else None
                )
                if (
                    normalized.fx_observation_id
                    not in normalization.fx_observation_ids
                    or pair
                    != (normalized.original_currency, normalization.target_currency)
                ):
                    raise CriticalCostSourceMismatchError(
                        "FX Observation differs from normalization manifest"
                    )

    @staticmethod
    def _aware(value: datetime, name: str) -> datetime:
        if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{name} must be timezone-aware")
        return value

    @staticmethod
    def _blocking(code: CriticalCostReasonCode, category: str, reference: str | None = None):
        return CriticalCostCompletenessReason(code, CriticalCostReasonSeverity.BLOCKING, category, reference)

    @staticmethod
    def _warning(code: CriticalCostReasonCode, category: str):
        return CriticalCostCompletenessReason(code, CriticalCostReasonSeverity.WARNING, category)

    @staticmethod
    def _validate_composition_source(composition, admission) -> None:
        quote = admission.quote_revision
        shipping = {term.scope.value: term.cost for term in quote.shipping_terms}
        expected = (
            (quote.unit_price.availability, quote.unit_price.amount, quote.unit_price.currency),
            *((shipping[scope].availability, shipping[scope].amount, shipping[scope].currency)
              for scope in ("supplier_side", "international_freight", "domestic_inbound")),
        )
        actual = tuple((value.availability, value.amount, value.currency) for value in composition.components)
        if actual != expected:
            raise CriticalCostSourceMismatchError("composition facts differ from exact quote")
        if composition.minimum_order_quantity != quote.minimum_order_quantity:
            raise CriticalCostSourceMismatchError("composition MOQ differs from exact quote")
        if composition.quoted_quantity != quote.quoted_quantity:
            raise CriticalCostSourceMismatchError("composition quoted quantity differs from exact quote")

    def _blocking_reasons(
        self,
        composition,
        admission,
        verified,
        evaluated_at,
        normalization=None,
    ):
        reasons: list[CriticalCostCompletenessReason] = []
        purchase = composition.components[0]
        if purchase.availability is not CommercialFactAvailability.KNOWN:
            reasons.append(self._blocking(CriticalCostReasonCode.PURCHASE_COST_UNKNOWN, purchase.kind.value))

        normalized_by_kind = (
            {}
            if normalization is None
            else {value.kind: value for value in normalization.components}
        )
        for component in composition.components[1:]:
            if component.availability is CommercialFactAvailability.UNKNOWN:
                reasons.append(self._blocking(CriticalCostReasonCode.SHIPPING_SCOPE_UNKNOWN, component.kind.value))
                continue
            if component.availability is CommercialFactAvailability.NOT_APPLICABLE:
                continue
            if component.amount == Decimal("0") or component.allocation_basis is CostAllocationBasis.PER_UNIT:
                continue
            if normalization is not None:
                normalized = normalized_by_kind[component.kind]
                if normalized.allocation_authority_id is not None:
                    continue
            if component.allocation_basis is CostAllocationBasis.PER_QUOTED_QUANTITY:
                quantity = composition.quoted_quantity
                if quantity.availability is not CommercialFactAvailability.KNOWN or quantity.quantity is None:
                    reasons.append(self._blocking(
                        CriticalCostReasonCode.SHIPPING_ALLOCATION_DENOMINATOR_MISSING,
                        component.kind.value,
                    ))
                continue
            reasons.append(self._blocking(CriticalCostReasonCode.SHIPPING_ALLOCATION_UNKNOWN, component.kind.value))

        inputs = verified.inputs
        required = (
            ("expected_sale_price", inputs.expected_sale_price,
             CriticalCostReasonCode.EXPECTED_SALE_PRICE_MISSING, self._policy.expected_sale_evidence_statuses),
            ("marketplace_fee", inputs.marketplace_fee_rate,
             CriticalCostReasonCode.MARKETPLACE_FEE_MISSING, self._policy.required_evidence_statuses),
            ("payment_fee", inputs.payment_fee_rate,
             CriticalCostReasonCode.PAYMENT_FEE_MISSING, self._policy.required_evidence_statuses),
            ("fixed_fee", inputs.fixed_fee,
             CriticalCostReasonCode.FIXED_FEE_MISSING, self._policy.required_evidence_statuses),
            ("tax", inputs.tax_rate,
             CriticalCostReasonCode.TAX_MISSING, self._policy.required_evidence_statuses),
            ("duty", inputs.duty_cost,
             CriticalCostReasonCode.DUTY_MISSING, self._policy.required_evidence_statuses),
            ("other_cost", inputs.other_cost,
             CriticalCostReasonCode.OTHER_COST_MISSING, self._policy.required_evidence_statuses),
        )
        for category, value, missing_code, allowed_statuses in required:
            numeric = value.amount if isinstance(value, MoneyInput) else value.rate
            evidence = value.evidence
            if numeric is None or evidence.status in {EvidenceStatus.MISSING, EvidenceStatus.UNSUPPORTED}:
                reasons.append(self._blocking(missing_code, category, evidence.reference))
            elif evidence.status.value not in allowed_statuses:
                reasons.append(self._blocking(CriticalCostReasonCode.EVIDENCE_NOT_VERIFIED, category, evidence.reference))
            elif self._policy.require_evidence_reference and evidence.reference is None:
                reasons.append(self._blocking(CriticalCostReasonCode.EVIDENCE_REFERENCE_MISSING, category))

        currencies = list(composition.known_currencies)
        if normalization is None and inputs.currency not in currencies:
            currencies.append(inputs.currency)
        if (
            (normalization is None and len(currencies) > 1)
            or (
                normalization is not None
                and normalization.target_currency != inputs.currency
            )
        ):
            reasons.append(self._blocking(CriticalCostReasonCode.CROSS_CURRENCY_FX_MISSING, "fx"))

        valid_until = admission.quote_revision.valid_until
        if self._policy.require_quote_valid_until and valid_until is None:
            reasons.append(self._blocking(CriticalCostReasonCode.QUOTE_VALIDITY_UNKNOWN, "quote"))
        elif valid_until is not None and valid_until <= evaluated_at:
            reasons.append(self._blocking(CriticalCostReasonCode.QUOTE_EXPIRED, "quote"))
        return reasons


class PersistCriticalCostCompleteness:
    """Replay-first authoritative publication of one evaluated assessment."""

    def __init__(
        self,
        repository: CriticalCostCompletenessPersistenceRepository,
        *,
        assessment_id_generator: Callable[[], str],
        evaluated_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
        policy: CriticalCostCompletenessPolicy,
    ) -> None:
        if not all(callable(value) for value in (
            assessment_id_generator, evaluated_clock, committed_clock,
        )):
            raise TypeError("persistence dependencies must be callable")
        if not isinstance(policy, CriticalCostCompletenessPolicy):
            raise TypeError("policy must be CriticalCostCompletenessPolicy")
        self._repository = repository
        self._identity = assessment_id_generator
        self._evaluated = evaluated_clock
        self._committed = committed_clock
        self._policy = policy

    def execute(
        self, command: PersistCriticalCostCompletenessCommand
    ) -> CriticalCostCompletenessPersistenceResult:
        if not isinstance(command, PersistCriticalCostCompletenessCommand):
            raise TypeError("command must be PersistCriticalCostCompletenessCommand")
        replay = self._repository.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replace(replay, replayed=True)
        expected_command_schema = (
            CRITICAL_COST_COMPLETENESS_COMMAND_SCHEMA_VERSION_V2
            if self._policy == DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2
            else CRITICAL_COST_COMPLETENESS_COMMAND_SCHEMA_VERSION
        )
        if command.schema_version != expected_command_schema:
            raise CriticalCostSourceMismatchError(
                "Critical Cost command version differs from policy version"
            )
        assessment = EvaluateCriticalCostCompleteness(
            self._repository,
            self._repository,
            policy=self._policy,
            evaluated_clock=self._evaluated,
        ).execute(
            command.composition_id,
            command.acquisition_normalization_id,
        )
        if (
            assessment.composition_id != command.composition_id
            or assessment.verified_economics_opportunity_id
            != command.verified_economics_opportunity_id
            or assessment.verified_economics_snapshot_at
            != command.verified_economics_snapshot_at
            or assessment.verified_economics_schema_version
            != command.verified_economics_schema_version
            or assessment.policy_name != command.policy_name
            or assessment.policy_version != command.policy_version
            or assessment.acquisition_normalization_id
            != command.acquisition_normalization_id
        ):
            raise CriticalCostSourceMismatchError(
                "evaluated assessment differs from commanded exact sources or policy"
            )
        assessment_id = _text(self._identity(), "assessment_id")
        receipt = CriticalCostCompletenessReceipt(
            command.command_id,
            assessment_id,
            command.fingerprint,
            _aware(self._committed(), "committed_at"),
        )
        return self._repository.save_assessment(command, assessment, receipt)


@dataclass(frozen=True, slots=True)
class CriticalCostCompletenessProductionRequest:
    """Caller-owned exact source facts for one fresh v2 assessment."""

    command_id: str
    opportunity_id: str
    composition_id: str
    acquisition_normalization_id: str
    verified_economics_opportunity_id: str
    verified_economics_snapshot_at: datetime
    verified_economics_schema_version: str
    requested_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "command_id",
            "opportunity_id",
            "composition_id",
            "acquisition_normalization_id",
            "verified_economics_opportunity_id",
            "verified_economics_schema_version",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        _aware(self.verified_economics_snapshot_at, "verified_economics_snapshot_at")
        _aware(self.requested_at, "requested_at")


class CriticalCostCompletenessProductionEntry:
    """Resolve the named O2 sources and delegate all evaluation to the owner."""

    def __init__(
        self,
        repository: CriticalCostCompletenessPersistenceRepository,
        owner: PersistCriticalCostCompleteness,
    ) -> None:
        self._repository = repository
        self._owner = owner

    def execute(
        self, request: CriticalCostCompletenessProductionRequest
    ) -> CriticalCostCompletenessPersistenceResult:
        if not isinstance(request, CriticalCostCompletenessProductionRequest):
            raise TypeError(
                "request must be CriticalCostCompletenessProductionRequest"
            )
        if request.verified_economics_opportunity_id != request.opportunity_id:
            raise CriticalCostSourceMismatchError(
                "Verified Economics differs from route Opportunity"
            )
        command = PersistCriticalCostCompletenessCommand(
            command_id=request.command_id,
            composition_id=request.composition_id,
            verified_economics_opportunity_id=(
                request.verified_economics_opportunity_id
            ),
            verified_economics_snapshot_at=request.verified_economics_snapshot_at,
            verified_economics_schema_version=(
                request.verified_economics_schema_version
            ),
            policy_name=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2.name,
            policy_version=DOMESTIC_COMMERCE_CRITICAL_COST_POLICY_V2.version,
            requested_at=request.requested_at,
            schema_version=CRITICAL_COST_COMPLETENESS_COMMAND_SCHEMA_VERSION_V2,
            acquisition_normalization_id=request.acquisition_normalization_id,
        )
        replay = self._repository.validate_replay(
            command.command_id, command.fingerprint
        )
        if replay is not None:
            return replace(replay, replayed=True)
        composition = self._repository.get_composition(request.composition_id)
        if composition is None:
            raise CriticalCostSourceNotFoundError(
                "exact Landed Cost Composition is missing"
            )
        normalization = self._repository.get_acquisition_normalization(
            request.acquisition_normalization_id
        )
        if normalization is None:
            raise CriticalCostSourceNotFoundError(
                "exact Acquisition Cost Normalization is missing"
            )
        if (
            composition.opportunity_identity.opportunity_id != request.opportunity_id
            or normalization.opportunity_identity.opportunity_id
            != request.opportunity_id
        ):
            raise CriticalCostSourceMismatchError(
                "Critical Cost sources differ from route Opportunity"
            )
        return self._owner.execute(command)


__all__ = [
    name for name in globals()
    if name.startswith("CriticalCost") or name.startswith("Evaluate")
    or name.startswith("Persist") or name.startswith("DOMESTIC")
    or name.startswith("CRITICAL_COST")
]
