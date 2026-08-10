"""Thin exact-source production entries for the Capital execution path."""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import datetime
from decimal import Decimal

from app.application.capital_gate import (
    CapitalGateSourceNotFoundError,
    EvaluateCapitalGate,
    EvaluateCapitalGateCommand,
)
from app.application.capital_investment import (
    AdmitIntendedOrderQuantity,
    AdmitIntendedOrderQuantityCommand,
    CapitalInvestmentSourceNotFoundError,
)
from app.application.capital_requirement import (
    CalculatePlannedAcquisitionCapitalRequirement,
    CalculatePlannedAcquisitionCapitalRequirementCommand,
    PlannedAcquisitionCapitalRequirementSourceNotFoundError,
)
from app.application.founder_capital_approval import (
    ApproveFounderCapital,
    ApproveFounderCapitalCommand,
    FounderCapitalApprovalSourceNotFoundError,
)
from app.application.real_money_execution_intent import (
    EvaluateRealMoneyExecutionIntent,
    EvaluateRealMoneyExecutionIntentCommand,
    EvaluateRealMoneyExecutionIntentCommandV2,
    RealMoneyExecutionIntentSourceNotFoundError,
)
from app.application.purchase_execution import (
    RecordPurchaseExecution,
    RecordPurchaseExecutionCommand,
    RecordPurchaseExecutionCommandV2,
    PurchaseExecutionSourceNotFoundError,
)
from app.application.actual_acquisition_settlement import (
    AdmitActualAcquisitionSettlement,
    AdmitActualAcquisitionSettlementCommand,
)
from app.application.goods_receipt import (
    AdmitGoodsReceipt,
    AdmitGoodsReceiptCommand,
)
from app.application.actual_sale_settlement import (
    AdmitActualSaleSettlement,
    AdmitActualSaleSettlementCommand,
)
from app.application.actual_outcome import (
    CalculateActualOutcome,
    CalculateActualOutcomeCommand,
)
from app.domain.capital import (
    PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_POLICY_NAME,
    PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_POLICY_VERSION,
    UpfrontCostScopeStatus,
    PurchaseExecutionEvidenceReference,
    ActualAcquisitionCostFact,
    GoodsReceiptEvidenceReference,
    OtherMandatoryAcquisitionCosts,
    ActualSaleFinalityFact,
    ActualSaleMonetaryFact,
    ActualSalePayoutFact,
    OtherActualSaleCosts,
)


class CapitalProductionOpportunityConflictError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class IntendedOrderQuantityProductionRequest:
    command_id: str
    opportunity_id: str
    sourcing_admission_id: str
    sourcing_admission_revision: int
    quote_id: str
    quote_revision: int
    quantity: int
    quantity_unit: str
    operator_id: str
    declared_at: datetime
    requested_at: datetime


class IntendedOrderQuantityProductionEntry:
    def __init__(self, repository, owner: AdmitIntendedOrderQuantity) -> None:
        self._repository = repository
        self._owner = owner

    def execute(self, request: IntendedOrderQuantityProductionRequest):
        admission = self._repository.get_sourcing_admission(
            request.sourcing_admission_id, request.sourcing_admission_revision
        )
        if admission is None:
            raise CapitalInvestmentSourceNotFoundError(
                "exact Sourcing Admission revision is missing"
            )
        identity = admission.selling_product_lineage.opportunity_identity
        if identity.opportunity_id != request.opportunity_id:
            raise CapitalProductionOpportunityConflictError(
                "Sourcing Admission differs from route Opportunity"
            )
        return self._owner.execute(
            AdmitIntendedOrderQuantityCommand(
                command_id=request.command_id,
                opportunity_identity=identity,
                sourcing_admission_id=request.sourcing_admission_id,
                sourcing_admission_revision=request.sourcing_admission_revision,
                quote_id=request.quote_id,
                quote_revision=request.quote_revision,
                quantity=request.quantity,
                quantity_unit=request.quantity_unit,
                operator_id=request.operator_id,
                declared_at=request.declared_at,
                requested_at=request.requested_at,
            )
        )


@dataclass(frozen=True, slots=True)
class PlannedCapitalRequirementProductionRequest:
    command_id: str
    opportunity_id: str
    intended_order_quantity_id: str
    acquisition_normalization_id: str
    scope_status: UpfrontCostScopeStatus
    operator_id: str
    verified_at: datetime
    requested_at: datetime


class PlannedCapitalRequirementProductionEntry:
    def __init__(
        self, repository, owner: CalculatePlannedAcquisitionCapitalRequirement
    ) -> None:
        self._repository = repository
        self._owner = owner

    def execute(self, request: PlannedCapitalRequirementProductionRequest):
        intent = self._repository.get_intent(request.intended_order_quantity_id)
        if intent is None:
            raise PlannedAcquisitionCapitalRequirementSourceNotFoundError(
                "exact Intended Order Quantity is missing"
            )
        identity = intent.opportunity_identity
        if identity.opportunity_id != request.opportunity_id:
            raise CapitalProductionOpportunityConflictError(
                "Intended Order Quantity differs from route Opportunity"
            )
        return self._owner.execute(
            CalculatePlannedAcquisitionCapitalRequirementCommand(
                command_id=request.command_id,
                opportunity_identity=identity,
                intended_order_quantity_id=request.intended_order_quantity_id,
                acquisition_normalization_id=request.acquisition_normalization_id,
                scope_status=request.scope_status,
                operator_id=request.operator_id,
                verified_at=request.verified_at,
                requested_at=request.requested_at,
                policy_name=PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_POLICY_NAME,
                policy_version=PLANNED_ACQUISITION_CAPITAL_REQUIREMENT_POLICY_VERSION,
            )
        )


@dataclass(frozen=True, slots=True)
class CapitalGateProductionRequest:
    command_id: str
    opportunity_id: str
    capital_readiness_assessment_id: str
    capital_requirement_id: str
    deployable_capital_snapshot_id: str
    requested_at: datetime


class CapitalGateProductionEntry:
    def __init__(self, repository, owner: EvaluateCapitalGate) -> None:
        self._repository = repository
        self._owner = owner

    def execute(self, request: CapitalGateProductionRequest):
        readiness = self._repository.get_capital_readiness(
            request.capital_readiness_assessment_id
        )
        if readiness is None:
            raise CapitalGateSourceNotFoundError(
                "exact Capital Readiness assessment is missing"
            )
        identity = readiness.source_manifest.opportunity_identity
        if identity.opportunity_id != request.opportunity_id:
            raise CapitalProductionOpportunityConflictError(
                "Capital Readiness differs from route Opportunity"
            )
        return self._owner.execute(
            EvaluateCapitalGateCommand(
                command_id=request.command_id,
                opportunity_identity=identity,
                capital_readiness_assessment_id=request.capital_readiness_assessment_id,
                capital_requirement_id=request.capital_requirement_id,
                deployable_capital_snapshot_id=request.deployable_capital_snapshot_id,
                requested_at=request.requested_at,
            )
        )


@dataclass(frozen=True, slots=True)
class FounderCapitalApprovalProductionRequest:
    command_id: str
    opportunity_id: str
    capital_gate_id: str
    founder_id: str
    approved_capital: Decimal
    currency: str
    requested_at: datetime
    approved_at: datetime


class FounderCapitalApprovalProductionEntry:
    def __init__(self, repository, owner: ApproveFounderCapital) -> None:
        self._repository = repository
        self._owner = owner

    def execute(self, request: FounderCapitalApprovalProductionRequest):
        gate = self._repository.get_capital_gate(request.capital_gate_id)
        if gate is None:
            raise FounderCapitalApprovalSourceNotFoundError(
                "exact Capital Gate assessment is missing"
            )
        if gate.source_manifest.opportunity_identity.opportunity_id != request.opportunity_id:
            raise CapitalProductionOpportunityConflictError(
                "Capital Gate differs from route Opportunity"
            )
        return self._owner.execute(
            ApproveFounderCapitalCommand(
                command_id=request.command_id,
                capital_gate_id=request.capital_gate_id,
                founder_id=request.founder_id,
                approved_capital=request.approved_capital,
                currency=request.currency,
                requested_at=request.requested_at,
                approved_at=request.approved_at,
            )
        )


@dataclass(frozen=True, slots=True)
class RealMoneyExecutionIntentProductionRequest:
    command_id: str
    opportunity_id: str
    founder_capital_approval_id: str
    quote_id: str
    quote_revision: int
    current_deployable_capital_snapshot_id: str
    execution_quantity: int
    execution_quantity_unit: str
    planned_execution_amount: Decimal | None
    currency: str | None
    founder_id: str
    current_execution_confirmed: bool
    confirmed_at: datetime
    requested_at: datetime
    contract_version: str = "1.0.0"
    proposed_supplier_order_committed_amount: Decimal | None = None
    supplier_order_currency: str | None = None
    supplier_order_checkout_evidence_reference: str | None = None


class RealMoneyExecutionIntentProductionEntry:
    def __init__(self, repository, owner: EvaluateRealMoneyExecutionIntent) -> None:
        self._repository = repository
        self._owner = owner

    def execute(self, request: RealMoneyExecutionIntentProductionRequest):
        approval = self._repository.get_founder_capital_approval(
            request.founder_capital_approval_id
        )
        if approval is None:
            raise RealMoneyExecutionIntentSourceNotFoundError(
                "exact Founder Capital Approval is missing"
            )
        if approval.opportunity_identity.opportunity_id != request.opportunity_id:
            raise CapitalProductionOpportunityConflictError(
                "Founder Capital Approval differs from route Opportunity"
            )
        if request.contract_version == "2.0.0":
            command = EvaluateRealMoneyExecutionIntentCommandV2(
                command_id=request.command_id,
                founder_capital_approval_id=request.founder_capital_approval_id,
                quote_id=request.quote_id,
                quote_revision=request.quote_revision,
                current_deployable_capital_snapshot_id=request.current_deployable_capital_snapshot_id,
                execution_quantity=request.execution_quantity,
                execution_quantity_unit=request.execution_quantity_unit,
                proposed_supplier_order_committed_amount=request.proposed_supplier_order_committed_amount,
                supplier_order_currency=request.supplier_order_currency,
                supplier_order_checkout_evidence_reference=request.supplier_order_checkout_evidence_reference,
                founder_id=request.founder_id,
                requested_at=request.requested_at,
                confirmed_at=request.confirmed_at,
                current_execution_confirmed=request.current_execution_confirmed,
            )
        elif request.contract_version == "1.0.0":
            command = EvaluateRealMoneyExecutionIntentCommand(
                command_id=request.command_id,
                founder_capital_approval_id=request.founder_capital_approval_id,
                quote_id=request.quote_id,
                quote_revision=request.quote_revision,
                current_deployable_capital_snapshot_id=(
                    request.current_deployable_capital_snapshot_id
                ),
                execution_quantity=request.execution_quantity,
                execution_quantity_unit=request.execution_quantity_unit,
                planned_execution_amount=request.planned_execution_amount,
                currency=request.currency,
                founder_id=request.founder_id,
                requested_at=request.requested_at,
                confirmed_at=request.confirmed_at,
                current_execution_confirmed=request.current_execution_confirmed,
            )
            if self._repository.validate_replay(command.command_id, command.fingerprint) is None:
                raise ValueError("new v1 Real-Money Execution Intent writes are disabled")
        else:
            raise ValueError("unsupported Real-Money Execution Intent contract version")
        return self._owner.execute(command)


@dataclass(frozen=True, slots=True)
class PurchaseExecutionProductionRequest:
    command_id: str
    opportunity_id: str
    real_money_execution_intent_id: str
    quote_id: str
    quote_revision: int
    actual_quantity: int
    actual_quantity_unit: str
    actual_total_committed_amount: Decimal | None
    currency: str | None
    external_order_reference: str
    founder_id: str
    executed_at: datetime
    evidence_references: tuple[PurchaseExecutionEvidenceReference, ...]
    requested_at: datetime
    contract_version: str = "1.0.0"
    supplier_order_committed_amount: Decimal | None = None
    supplier_order_currency: str | None = None


class PurchaseExecutionProductionEntry:
    def __init__(self, repository, owner: RecordPurchaseExecution) -> None:
        self._repository = repository
        self._owner = owner

    def execute(self, request: PurchaseExecutionProductionRequest):
        intent = self._repository.get_execution_intent(
            request.real_money_execution_intent_id
        )
        if intent is None:
            raise PurchaseExecutionSourceNotFoundError(
                "exact Real-Money Execution Intent is missing"
            )
        if intent.source_manifest.opportunity_identity.opportunity_id != request.opportunity_id:
            raise CapitalProductionOpportunityConflictError(
                "Real-Money Execution Intent differs from route Opportunity"
            )
        if request.contract_version == "2.0.0":
            command = RecordPurchaseExecutionCommandV2(
                command_id=request.command_id,
                real_money_execution_intent_id=request.real_money_execution_intent_id,
                quote_id=request.quote_id,
                quote_revision=request.quote_revision,
                actual_quantity=request.actual_quantity,
                actual_quantity_unit=request.actual_quantity_unit,
                supplier_order_committed_amount=request.supplier_order_committed_amount,
                supplier_order_currency=request.supplier_order_currency,
                external_order_reference=request.external_order_reference,
                founder_id=request.founder_id,
                executed_at=request.executed_at,
                evidence_references=request.evidence_references,
                requested_at=request.requested_at,
            )
        elif request.contract_version == "1.0.0":
            command = RecordPurchaseExecutionCommand(
                command_id=request.command_id,
                real_money_execution_intent_id=(
                    request.real_money_execution_intent_id
                ),
                quote_id=request.quote_id,
                quote_revision=request.quote_revision,
                actual_quantity=request.actual_quantity,
                actual_quantity_unit=request.actual_quantity_unit,
                actual_total_committed_amount=(
                    request.actual_total_committed_amount
                ),
                currency=request.currency,
                external_order_reference=request.external_order_reference,
                founder_id=request.founder_id,
                executed_at=request.executed_at,
                evidence_references=request.evidence_references,
                requested_at=request.requested_at,
            )
            if self._repository.validate_replay(command.command_id, command.fingerprint) is None:
                raise ValueError("new v1 Purchase Execution writes are disabled")
        else:
            raise ValueError("unsupported Purchase Execution contract version")
        return self._owner.execute(command)


@dataclass(frozen=True, slots=True)
class ActualAcquisitionSettlementProductionRequest:
    command_id: str
    opportunity_id: str
    purchase_execution_record_id: str
    predecessor_settlement_id: str | None
    target_currency: str
    fixed_cost_facts: tuple[ActualAcquisitionCostFact, ...]
    other_mandatory_costs: OtherMandatoryAcquisitionCosts
    operator_id: str
    requested_at: datetime


class ActualAcquisitionSettlementProductionEntry:
    def __init__(self, owner: AdmitActualAcquisitionSettlement) -> None:
        self._owner = owner

    def execute(self, request: ActualAcquisitionSettlementProductionRequest):
        return self._owner.execute(
            AdmitActualAcquisitionSettlementCommand(
                command_id=request.command_id,
                opportunity_id=request.opportunity_id,
                purchase_execution_record_id=request.purchase_execution_record_id,
                predecessor_settlement_id=request.predecessor_settlement_id,
                target_currency=request.target_currency,
                fixed_cost_facts=request.fixed_cost_facts,
                other_mandatory_costs=request.other_mandatory_costs,
                operator_id=request.operator_id,
                requested_at=request.requested_at,
            )
        )


@dataclass(frozen=True, slots=True)
class GoodsReceiptProductionRequest:
    command_id: str
    opportunity_id: str
    purchase_execution_record_id: str
    received_quantity: int
    quantity_unit: str
    sellable_quantity: int
    damaged_quantity: int
    evidence_references: tuple[GoodsReceiptEvidenceReference, ...]
    delivery_reference: str | None
    operator_id: str
    received_at: datetime
    inspected_at: datetime
    requested_at: datetime


class GoodsReceiptProductionEntry:
    def __init__(self, owner: AdmitGoodsReceipt) -> None:
        self._owner = owner

    def execute(self, request: GoodsReceiptProductionRequest):
        return self._owner.execute(
            AdmitGoodsReceiptCommand(
                command_id=request.command_id,
                opportunity_id=request.opportunity_id,
                purchase_execution_record_id=request.purchase_execution_record_id,
                received_quantity=request.received_quantity,
                quantity_unit=request.quantity_unit,
                sellable_quantity=request.sellable_quantity,
                damaged_quantity=request.damaged_quantity,
                evidence_references=request.evidence_references,
                delivery_reference=request.delivery_reference,
                operator_id=request.operator_id,
                received_at=request.received_at,
                inspected_at=request.inspected_at,
                requested_at=request.requested_at,
            )
        )


@dataclass(frozen=True, slots=True)
class ActualSaleSettlementProductionRequest:
    command_id: str
    opportunity_id: str
    anchor_goods_receipt_id: str
    predecessor_settlement_id: str | None
    marketplace: str
    seller_account_reference: str
    marketplace_product_reference: str
    marketplace_option_reference: str | None
    marketplace_sku_reference: str | None
    external_report_reference: str
    transaction_references: tuple[str, ...]
    period_start: datetime
    period_end: datetime
    fulfilled_outbound_quantity: int
    cancelled_quantity: int
    refunded_quantity: int
    returned_quantity: int
    quantity_unit: str
    settlement_currency: str
    fixed_monetary_facts: tuple[ActualSaleMonetaryFact, ...]
    other_sale_side_costs: OtherActualSaleCosts
    payout: ActualSalePayoutFact
    finality: ActualSaleFinalityFact
    operator_id: str
    requested_at: datetime


class ActualSaleSettlementProductionEntry:
    def __init__(self, owner: AdmitActualSaleSettlement) -> None:
        self._owner = owner

    def execute(self, request: ActualSaleSettlementProductionRequest):
        return self._owner.execute(
            AdmitActualSaleSettlementCommand(
                **{field.name: getattr(request, field.name) for field in fields(request)}
            )
        )


@dataclass(frozen=True, slots=True)
class ActualOutcomeProductionRequest:
    command_id: str
    opportunity_id: str
    actual_acquisition_settlement_id: str
    actual_sale_settlement_ids: tuple[str, ...]
    requested_at: datetime


class ActualOutcomeProductionEntry:
    def __init__(self, owner: CalculateActualOutcome) -> None:
        self._owner = owner

    def execute(self, request: ActualOutcomeProductionRequest):
        return self._owner.execute(
            CalculateActualOutcomeCommand(
                **{field.name: getattr(request, field.name) for field in fields(request)}
            )
        )


__all__ = [
    name
    for name in globals()
    if name.endswith(("ProductionEntry", "ProductionRequest"))
    or name == "CapitalProductionOpportunityConflictError"
]
