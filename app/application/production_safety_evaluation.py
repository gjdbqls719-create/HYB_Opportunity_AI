"""Operational Production Safety evaluation over an exact persisted chain."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from typing import Callable, Protocol

from app.application.production_safety_runtime_adapter import (
    ProductionSafetyRuntimeAdapter,
    ProductionSafetyRuntimeAdapterError,
)
from app.domain.market_intelligence import MarketObservationIdentity
from app.domain.opportunity import ProductionSafetyAssessment
from engine.production_safety import assess_production_safety


PRODUCTION_SAFETY_EVALUATION_RULE_VERSION = "production-safety-v1"
PRODUCTION_SAFETY_EVALUATION_SCHEMA_VERSION = "production-safety-evaluation-v1"
PRODUCTION_SAFETY_PROVENANCE_SCHEMA_VERSION = "production-safety-provenance-v1"
PRODUCTION_SAFETY_COMMAND_SCHEMA_VERSION = "production-safety-command-v1"
PRODUCTION_SAFETY_RECEIPT_SCHEMA_VERSION = "production-safety-receipt-v1"


class ProductionSafetyEvaluationPersistenceError(RuntimeError):
    pass


class ProductionSafetyEvaluationNotFoundError(ProductionSafetyEvaluationPersistenceError):
    pass


class ProductionSafetyEvaluationCommandConflictError(ProductionSafetyEvaluationPersistenceError):
    pass


class ProductionSafetyEvaluationSubjectConflictError(ProductionSafetyEvaluationPersistenceError):
    pass


class ProductionSafetyChainNotFoundError(ProductionSafetyEvaluationPersistenceError):
    pass


class ProductionSafetySelectedProductConflictError(ProductionSafetyEvaluationPersistenceError):
    pass


class ProductionSafetySourceLineageError(ProductionSafetyEvaluationPersistenceError):
    pass


class ProductionSafetyRuntimeReconstructionError(ProductionSafetyEvaluationPersistenceError):
    pass


class ProductionSafetyExecutionError(ProductionSafetyEvaluationPersistenceError):
    pass


class MalformedProductionSafetyEvaluationPersistenceError(ProductionSafetyEvaluationPersistenceError):
    pass


class UnsupportedProductionSafetyEvaluationVersionError(MalformedProductionSafetyEvaluationPersistenceError):
    pass


class ProductionSafetyEvaluationHistoryError(ProductionSafetyEvaluationPersistenceError):
    pass


class ProductionSafetyProvenancePersistenceError(ProductionSafetyEvaluationPersistenceError):
    pass


class ProductionSafetyCurrentProjectionError(ProductionSafetyEvaluationPersistenceError):
    pass


class ProductionSafetyReceiptPersistenceError(ProductionSafetyEvaluationPersistenceError):
    pass


class ProductionSafetyEvaluationCommitError(ProductionSafetyEvaluationPersistenceError):
    pass


def _required(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


def _aware(value: datetime, name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


@dataclass(frozen=True, slots=True)
class EvaluateAndPersistProductionSafetyCommand:
    command_id: str
    opportunity_id: str
    snapshot_chain_binding_id: str
    selected_product_snapshot_id: str
    requested_at: datetime
    schema_version: str = PRODUCTION_SAFETY_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "command_id",
            "opportunity_id",
            "snapshot_chain_binding_id",
            "selected_product_snapshot_id",
        ):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        _aware(self.requested_at, "requested_at")
        if self.schema_version != PRODUCTION_SAFETY_COMMAND_SCHEMA_VERSION:
            raise UnsupportedProductionSafetyEvaluationVersionError(
                "unsupported Production Safety command version"
            )

    @property
    def fingerprint(self) -> str:
        payload = {
            "opportunity_id": self.opportunity_id,
            "snapshot_chain_binding_id": self.snapshot_chain_binding_id,
            "selected_product_snapshot_id": self.selected_product_snapshot_id,
            "requested_at": self.requested_at.isoformat(),
            "schema_version": self.schema_version,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class ProductionSafetyEvaluationProvenance:
    evaluation_id: str
    opportunity_id: str
    snapshot_chain_binding_id: str
    candidate_opportunity_binding_id: str
    candidate_id: str
    selected_product_snapshot_id: str
    price_intelligence_snapshot_id: str
    economics_calculation_snapshot_id: str
    verified_economics_opportunity_id: str
    market_observation_identity: MarketObservationIdentity
    rule_version: str
    evaluated_at: datetime
    schema_version: str = PRODUCTION_SAFETY_PROVENANCE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "evaluation_id", "opportunity_id", "snapshot_chain_binding_id",
            "candidate_opportunity_binding_id", "candidate_id",
            "selected_product_snapshot_id", "price_intelligence_snapshot_id",
            "economics_calculation_snapshot_id", "verified_economics_opportunity_id",
            "rule_version",
        ):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        if not isinstance(self.market_observation_identity, MarketObservationIdentity):
            raise TypeError("market_observation_identity must be MarketObservationIdentity")
        _aware(self.evaluated_at, "evaluated_at")
        if self.schema_version != PRODUCTION_SAFETY_PROVENANCE_SCHEMA_VERSION:
            raise UnsupportedProductionSafetyEvaluationVersionError(
                "unsupported Production Safety provenance version"
            )


@dataclass(frozen=True, slots=True)
class ProductionSafetyEvaluation:
    evaluation_id: str
    opportunity_id: str
    evaluation_version: int
    assessment: ProductionSafetyAssessment
    rule_version: str
    evaluated_at: datetime
    schema_version: str = PRODUCTION_SAFETY_EVALUATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(self, "evaluation_id", _required(self.evaluation_id, "evaluation_id"))
        object.__setattr__(self, "opportunity_id", _required(self.opportunity_id, "opportunity_id"))
        if isinstance(self.evaluation_version, bool) or not isinstance(self.evaluation_version, int) or self.evaluation_version < 1:
            raise ValueError("evaluation_version must be a positive integer")
        if not isinstance(self.assessment, ProductionSafetyAssessment):
            raise TypeError("assessment must be ProductionSafetyAssessment")
        object.__setattr__(self, "rule_version", _required(self.rule_version, "rule_version"))
        _aware(self.evaluated_at, "evaluated_at")
        if self.schema_version != PRODUCTION_SAFETY_EVALUATION_SCHEMA_VERSION:
            raise UnsupportedProductionSafetyEvaluationVersionError(
                "unsupported Production Safety evaluation version"
            )


@dataclass(frozen=True, slots=True)
class ProductionSafetyEvaluationReceipt:
    command_id: str
    evaluation_id: str
    opportunity_id: str
    snapshot_chain_binding_id: str
    selected_product_snapshot_id: str
    command_fingerprint: str
    requested_at: datetime
    evaluated_at: datetime
    committed_at: datetime
    schema_version: str = PRODUCTION_SAFETY_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "command_id", "evaluation_id", "opportunity_id",
            "snapshot_chain_binding_id", "selected_product_snapshot_id",
            "command_fingerprint",
        ):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        if len(self.command_fingerprint) != 64:
            raise ValueError("command_fingerprint must be SHA-256 text")
        for name in ("requested_at", "evaluated_at", "committed_at"):
            _aware(getattr(self, name), name)
        if self.schema_version != PRODUCTION_SAFETY_RECEIPT_SCHEMA_VERSION:
            raise UnsupportedProductionSafetyEvaluationVersionError(
                "unsupported Production Safety receipt version"
            )


@dataclass(frozen=True, slots=True)
class ProductionSafetyEvaluationResult:
    evaluation: ProductionSafetyEvaluation
    provenance: ProductionSafetyEvaluationProvenance
    receipt: ProductionSafetyEvaluationReceipt
    replayed: bool


@dataclass(frozen=True, slots=True)
class OperationalProductionSafetyDecisionSource:
    evaluation_id: str
    opportunity_id: str
    assessment: ProductionSafetyAssessment
    snapshot_chain_binding_id: str
    selected_product_snapshot_id: str
    rule_version: str
    evaluation_schema_version: str
    provenance_schema_version: str
    evaluated_at: datetime

    def __post_init__(self) -> None:
        for name in (
            "evaluation_id", "opportunity_id", "snapshot_chain_binding_id",
            "selected_product_snapshot_id", "rule_version",
            "evaluation_schema_version", "provenance_schema_version",
        ):
            object.__setattr__(self, name, _required(getattr(self, name), name))
        if not isinstance(self.assessment, ProductionSafetyAssessment):
            raise TypeError("assessment must be ProductionSafetyAssessment")
        _aware(self.evaluated_at, "evaluated_at")


class ProductionSafetyEvaluationRepository(Protocol):
    def get_receipt(self, command_id: str) -> ProductionSafetyEvaluationReceipt | None: ...
    def get_evaluation(self, evaluation_id: str) -> ProductionSafetyEvaluation | None: ...
    def get_provenance(self, evaluation_id: str) -> ProductionSafetyEvaluationProvenance | None: ...
    def get_context(self, binding_id: str, product_snapshot_id: str): ...
    def persist(self, command, evaluation_id, assessment, rule_version, evaluated_at, committed_at): ...


class EvaluateAndPersistProductionSafety:
    def __init__(
        self,
        repository: ProductionSafetyEvaluationRepository,
        runtime_adapter: ProductionSafetyRuntimeAdapter,
        *,
        evaluation_id_generator: Callable[[], str],
        evaluated_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
        rule_version: str = PRODUCTION_SAFETY_EVALUATION_RULE_VERSION,
        evaluator: Callable[..., ProductionSafetyAssessment] = assess_production_safety,
    ) -> None:
        self._repository = repository
        self._runtime_adapter = runtime_adapter
        self._id = evaluation_id_generator
        self._evaluated_clock = evaluated_clock
        self._committed_clock = committed_clock
        self._rule_version = _required(rule_version, "rule_version")
        self._evaluator = evaluator

    def execute(self, command: EvaluateAndPersistProductionSafetyCommand) -> ProductionSafetyEvaluationResult:
        if not isinstance(command, EvaluateAndPersistProductionSafetyCommand):
            raise TypeError("command must be EvaluateAndPersistProductionSafetyCommand")
        receipt = self._repository.get_receipt(command.command_id)
        if receipt is not None:
            if receipt.command_fingerprint != command.fingerprint:
                raise ProductionSafetyEvaluationCommandConflictError(
                    "Production Safety command payload conflicts"
                )
            evaluation = self._repository.get_evaluation(receipt.evaluation_id)
            provenance = self._repository.get_provenance(receipt.evaluation_id)
            if evaluation is None or provenance is None:
                raise MalformedProductionSafetyEvaluationPersistenceError(
                    "receipt references incomplete evaluation"
                )
            return ProductionSafetyEvaluationResult(evaluation, provenance, receipt, True)
        try:
            context = self._repository.get_context(
                command.snapshot_chain_binding_id,
                command.selected_product_snapshot_id,
            )
        except ProductionSafetyEvaluationPersistenceError:
            raise
        except Exception as error:
            raise ProductionSafetySourceLineageError(
                "Production Safety source chain could not be loaded"
            ) from error
        if context.candidate_opportunity_binding.opportunity_id != command.opportunity_id:
            raise ProductionSafetySourceLineageError(
                "command Opportunity does not match Snapshot Chain"
            )
        try:
            verified = self._runtime_adapter.load_verified_economics_snapshot(context)
            runtime = self._runtime_adapter.reconstruct_inputs(context, verified)
        except ProductionSafetyRuntimeAdapterError as error:
            raise ProductionSafetyRuntimeReconstructionError(str(error)) from error
        try:
            assessment = self._evaluator(
                product=runtime.product,
                analysis=runtime.analysis,
                price_intelligence=runtime.price_intelligence,
                economics=runtime.economics,
            )
        except Exception as error:
            raise ProductionSafetyExecutionError("Production Safety evaluation failed") from error
        if not isinstance(assessment, ProductionSafetyAssessment):
            raise ProductionSafetyExecutionError("Production Safety engine returned an invalid assessment")
        evaluation_id = _required(self._id(), "evaluation_id")
        evaluated_at = self._evaluated_clock()
        committed_at = self._committed_clock()
        _aware(evaluated_at, "evaluated_at")
        _aware(committed_at, "committed_at")
        return self._repository.persist(
            command, evaluation_id, assessment, self._rule_version,
            evaluated_at, committed_at,
        )


__all__ = [
    name for name in globals()
    if name.startswith(("ProductionSafety", "OperationalProductionSafety", "EvaluateAndPersist", "MalformedProductionSafety", "UnsupportedProductionSafety"))
]
