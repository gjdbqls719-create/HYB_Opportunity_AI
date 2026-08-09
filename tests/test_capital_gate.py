from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal
import re

import pytest

from app.application.capital_gate import (
    CapitalGatePublication,
    CapitalGateReplayConflictError,
    CapitalGateSourceNotFoundError,
    EvaluateCapitalGate,
    EvaluateCapitalGateCommand,
)
from app.domain.capital import (
    DEPLOYABLE_CAPITAL_SEMANTICS_VERSION,
    CapitalGateBlockingReasonCode,
    CapitalGateRejectionReasonCode,
    CapitalGateState,
    CapitalReadinessReason,
    CapitalReadinessReasonCode,
    CapitalReadinessState,
    DeployableCapitalSnapshot,
    IntendedOrderQuantity,
    PlannedAcquisitionCapitalRequirement,
    PlannedAcquisitionCapitalRequirementBlockingReason,
    PlannedAcquisitionCapitalRequirementState,
    UpfrontCostScopeStatus,
    UpfrontCostScopeVerification,
    planned_acquisition_capital_amount,
)
from app.domain.opportunity import ConservativeEconomicsStatus
from app.domain.sourcing import CommercialFactAvailability, SourcingQuantityFact
from app.infrastructure.capital_gate import ProductionCapitalGateIdentityGenerator
from test_capital_investment_facts import Calls
from test_capital_readiness import evaluate as evaluate_readiness, ready_sources
from test_sourcing_authority_contract import NOW


def unchecked(value, **changes):
    result = object.__new__(type(value))
    for name in value.__dataclass_fields__:
        object.__setattr__(result, name, changes.get(name, getattr(value, name)))
    return result


class MemoryCapitalGateRepository:
    def __init__(self, readiness, requirement, deployable, conservative, intent, admission):
        self.readiness = readiness
        self.requirement = requirement
        self.deployable = deployable
        self.conservative = conservative
        self.intent = intent
        self.admission = admission
        self.results = {}
        self.source_reads = 0

    def get_capital_readiness(self, identity):
        self.source_reads += 1
        return self.readiness if self.readiness.assessment_id == identity else None

    def get_capital_requirement(self, identity):
        return self.requirement if self.requirement.requirement_id == identity else None

    def get_deployable_capital(self, identity):
        return self.deployable if self.deployable.snapshot_id == identity else None

    def get_conservative_economics(self, identity):
        return self.conservative if self.conservative.result_id == identity else None

    def get_intended_order_quantity(self, identity):
        return self.intent if self.intent.intent_id == identity else None

    def get_sourcing_admission(self, admission_id, revision):
        return (
            self.admission
            if self.admission.admission_id == admission_id and self.admission.revision == revision
            else None
        )

    def validate_replay(self, command_id, fingerprint):
        value = self.results.get(command_id)
        if value is not None and value.receipt.command_fingerprint != fingerprint:
            raise CapitalGateReplayConflictError("payload conflict")
        return value

    def save_gate(self, command, assessment, receipt):
        replay = self.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replay
        value = CapitalGatePublication(assessment, receipt, False)
        self.results[command.command_id] = value
        return value


def requirement(intent, normalization, admission, *, complete=True):
    status = UpfrontCostScopeStatus.COMPLETE if complete else UpfrontCostScopeStatus.UNRESOLVED
    amount = (
        planned_acquisition_capital_amount(
            normalization.total_per_unit_acquisition_cost, intent.quantity
        )
        if complete
        else None
    )
    return PlannedAcquisitionCapitalRequirement(
        requirement_id="requirement-1",
        opportunity_identity=intent.opportunity_identity,
        state=(
            PlannedAcquisitionCapitalRequirementState.CALCULABLE
            if complete
            else PlannedAcquisitionCapitalRequirementState.BLOCKED
        ),
        intended_order_quantity_id=intent.intent_id,
        acquisition_normalization_id=normalization.normalization_id,
        sourcing_binding_id="binding-1",
        sourcing_admission_id=admission.admission_id,
        sourcing_admission_revision=admission.revision,
        quote_id=admission.quote_revision.quote_id,
        quote_revision=admission.quote_revision.revision,
        quantity=intent.quantity,
        quantity_unit=intent.quantity_unit,
        normalized_acquisition_cost_per_unit=normalization.total_per_unit_acquisition_cost,
        currency=normalization.target_currency,
        planned_acquisition_capital=amount,
        scope_verification=UpfrontCostScopeVerification(
            status, intent.intent_id, normalization.normalization_id,
            "founder-1", NOW + timedelta(minutes=2),
        ),
        blocking_reasons=(
            ()
            if complete
            else (
                PlannedAcquisitionCapitalRequirementBlockingReason.UPFRONT_COST_SCOPE_UNVERIFIED,
            )
        ),
        policy_name="planned-acquisition-capital-requirement",
        policy_version="1.0.0",
        policy_precision=34,
        policy_rounding="ROUND_HALF_EVEN",
        requested_at=NOW,
        calculated_at=NOW + timedelta(minutes=3),
    )


def prepared(*, expected_sale_price="100", quantity=25, deployable_amount="1000"):
    sources, opportunity = ready_sources(expected_sale_price=expected_sale_price)
    readiness = evaluate_readiness(sources, opportunity)[0].assessment
    admission = sources.admission
    intent = IntendedOrderQuantity(
        "intent-1", opportunity, admission.admission_id, admission.revision,
        admission.quote_revision.quote_id, admission.quote_revision.revision,
        quantity, "units", "founder-1", NOW, NOW + timedelta(minutes=1),
        NOW + timedelta(minutes=2),
    )
    capital_requirement = requirement(intent, sources.normalization, admission)
    deployable = DeployableCapitalSnapshot(
        "deployable-1", Decimal(deployable_amount), capital_requirement.currency,
        NOW, "founder-1", NOW, NOW + timedelta(minutes=1),
    )
    repository = MemoryCapitalGateRepository(
        readiness, capital_requirement, deployable, sources.conservative, intent, admission
    )
    repository.normalization = sources.normalization
    return repository, opportunity


def command(repository, opportunity, **changes):
    values = {
        "command_id": "capital-gate-command-1",
        "opportunity_identity": opportunity,
        "capital_readiness_assessment_id": repository.readiness.assessment_id,
        "capital_requirement_id": repository.requirement.requirement_id,
        "deployable_capital_snapshot_id": repository.deployable.snapshot_id,
        "requested_at": NOW + timedelta(minutes=10),
        "policy_name": "domestic-commerce-capital-gate",
        "policy_version": "1.0.0",
    }
    values.update(changes)
    return EvaluateCapitalGateCommand(**values)


def owner(repository, *, fail=False):
    identity = Calls(AssertionError("identity called on replay") if fail else "gate-1")
    evaluated = Calls(AssertionError("evaluated clock called on replay") if fail else NOW + timedelta(minutes=11))
    committed = Calls(AssertionError("committed clock called on replay") if fail else NOW + timedelta(minutes=12))
    return (
        EvaluateCapitalGate(
            repository,
            gate_id_generator=identity,
            evaluated_clock=evaluated,
            committed_clock=committed,
        ),
        identity,
        evaluated,
        committed,
    )


def evaluate(repository=None, opportunity=None):
    if repository is None:
        repository, opportunity = prepared()
    return owner(repository)[0].execute(command(repository, opportunity))


def test_exact_safe_sources_pass_without_authorizing_purchase():
    repository, opportunity = prepared()
    result = evaluate(repository, opportunity)
    assessment = result.assessment
    assert assessment.state is CapitalGateState.PASS
    assert assessment.blocking_reasons == assessment.rejection_reasons == ()
    assert assessment.source_manifest.capital_readiness_assessment_id == repository.readiness.assessment_id
    assert assessment.source_manifest.capital_requirement_id == repository.requirement.requirement_id
    assert assessment.source_manifest.deployable_capital_snapshot_id == repository.deployable.snapshot_id
    assert assessment.source_manifest.conservative_economics_result_id == repository.conservative.result_id
    assert assessment.evaluated_facts.planned_acquisition_capital == repository.requirement.planned_acquisition_capital
    assert assessment.evaluated_facts.deployable_capital == repository.deployable.amount
    assert not hasattr(assessment, "approved")
    assert not hasattr(assessment, "buy")
    assert not hasattr(assessment, "invest")
    with pytest.raises(FrozenInstanceError):
        assessment.state = CapitalGateState.REJECTED


def test_readiness_requirement_and_conservative_blockers_remain_blocked_not_rejected():
    repository, opportunity = prepared()
    repository.readiness = replace(
        repository.readiness,
        state=CapitalReadinessState.BLOCKED,
        blocking_reasons=(CapitalReadinessReason(CapitalReadinessReasonCode.CRITICAL_COST_INCOMPLETE),),
    )
    result = evaluate(repository, opportunity).assessment
    assert result.state is CapitalGateState.BLOCKED
    assert result.blocking_reason_codes == (CapitalGateBlockingReasonCode.CAPITAL_READINESS_BLOCKED,)
    assert result.rejection_reasons == ()

    repository, opportunity = prepared()
    repository.requirement = requirement(
        repository.intent, repository.normalization, repository.admission, complete=False
    )
    result = evaluate(repository, opportunity).assessment
    assert CapitalGateBlockingReasonCode.CAPITAL_REQUIREMENT_BLOCKED in result.blocking_reason_codes
    assert result.rejection_reasons == ()


def test_missing_named_deployable_capital_is_explicit_source_error_before_identity():
    repository, opportunity = prepared()
    repository.deployable = replace(repository.deployable, snapshot_id="other")
    use_case, identity, evaluated, committed = owner(repository)
    with pytest.raises(CapitalGateSourceNotFoundError):
        use_case.execute(command(repository, opportunity, deployable_capital_snapshot_id="missing"))
    assert identity.calls == evaluated.calls == committed.calls == 0


def test_opportunity_lineage_and_currency_mismatch_are_blocked():
    repository, opportunity = prepared()
    repository.requirement = unchecked(
        repository.requirement,
        opportunity_identity=replace(opportunity, opportunity_id="other"),
    )
    result = evaluate(repository, opportunity).assessment
    assert CapitalGateBlockingReasonCode.SOURCE_OPPORTUNITY_MISMATCH in result.blocking_reason_codes

    repository, opportunity = prepared()
    repository.requirement = unchecked(repository.requirement, sourcing_binding_id="other")
    result = evaluate(repository, opportunity).assessment
    assert CapitalGateBlockingReasonCode.SOURCE_LINEAGE_MISMATCH in result.blocking_reason_codes

    repository, opportunity = prepared()
    repository.deployable = replace(repository.deployable, currency="USD")
    result = evaluate(repository, opportunity).assessment
    assert result.blocking_reason_codes == (CapitalGateBlockingReasonCode.CURRENCY_MISMATCH,)
    assert result.rejection_reasons == ()


@pytest.mark.parametrize(("available", "expected"), [("1000", CapitalGateState.PASS), ("308.500", CapitalGateState.PASS), ("1", CapitalGateState.REJECTED)])
def test_capital_sufficiency_uses_less_than_or_equal_without_reserve_subtraction(available, expected):
    repository, opportunity = prepared(deployable_amount=available)
    result = evaluate(repository, opportunity).assessment
    assert result.state is expected
    if expected is CapitalGateState.REJECTED:
        assert CapitalGateRejectionReasonCode.INSUFFICIENT_DEPLOYABLE_CAPITAL in result.rejection_reason_codes
    assert result.evaluated_facts.deployable_capital == Decimal(available)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("conservative_profit_per_unit", Decimal("0"), CapitalGateRejectionReasonCode.CONSERVATIVE_PROFIT_NON_POSITIVE),
        ("conservative_profit_per_unit", Decimal("-1"), CapitalGateRejectionReasonCode.CONSERVATIVE_PROFIT_NON_POSITIVE),
        ("conservative_margin", Decimal("0"), CapitalGateRejectionReasonCode.CONSERVATIVE_MARGIN_NON_POSITIVE),
        ("conservative_margin", Decimal("-1"), CapitalGateRejectionReasonCode.CONSERVATIVE_MARGIN_NON_POSITIVE),
        ("conservative_acquisition_roi", Decimal("0"), CapitalGateRejectionReasonCode.CONSERVATIVE_ACQUISITION_ROI_NON_POSITIVE),
        ("conservative_acquisition_roi", Decimal("-1"), CapitalGateRejectionReasonCode.CONSERVATIVE_ACQUISITION_ROI_NON_POSITIVE),
    ],
)
def test_only_strictly_positive_conservative_metrics_pass(field, value, reason):
    repository, opportunity = prepared()
    repository.conservative = unchecked(repository.conservative, **{field: value})
    result = evaluate(repository, opportunity).assessment
    assert result.state is CapitalGateState.REJECTED
    assert reason in result.rejection_reason_codes
    assert result.blocking_reasons == ()


def test_no_hidden_profit_margin_or_thirty_percent_roi_threshold():
    repository, opportunity = prepared()
    repository.conservative = unchecked(
        repository.conservative,
        conservative_profit_per_unit=Decimal("0.0001"),
        conservative_margin=Decimal("0.0001"),
        conservative_acquisition_roi=Decimal("0.0001"),
    )
    assert evaluate(repository, opportunity).assessment.state is CapitalGateState.PASS


def test_moq_is_policy_constraint_not_quantity_substitution_and_quoted_quantity_is_ignored():
    repository, opportunity = prepared(quantity=10)
    assert repository.admission.quote_revision.minimum_order_quantity.quantity == 10
    assert evaluate(repository, opportunity).assessment.state is CapitalGateState.PASS

    repository, opportunity = prepared(quantity=9)
    result = evaluate(repository, opportunity).assessment
    assert result.state is CapitalGateState.REJECTED
    assert CapitalGateRejectionReasonCode.INTENDED_QUANTITY_BELOW_MOQ in result.rejection_reason_codes
    assert result.evaluated_facts.intended_order_quantity == 9
    assert result.evaluated_facts.minimum_order_quantity.quantity == 10
    assert repository.admission.quote_revision.quoted_quantity.quantity != 9


def test_unknown_moq_blocks_and_not_applicable_moq_does_not_create_constraint():
    repository, opportunity = prepared()
    repository.admission = replace(
        repository.admission,
        quote_revision=replace(
            repository.admission.quote_revision,
            minimum_order_quantity=SourcingQuantityFact(CommercialFactAvailability.UNKNOWN),
        ),
    )
    result = evaluate(repository, opportunity).assessment
    assert CapitalGateBlockingReasonCode.MOQ_UNRESOLVED in result.blocking_reason_codes

    repository, opportunity = prepared(quantity=1)
    repository.admission = replace(
        repository.admission,
        quote_revision=replace(
            repository.admission.quote_revision,
            minimum_order_quantity=SourcingQuantityFact(CommercialFactAvailability.NOT_APPLICABLE),
        ),
    )
    assert evaluate(repository, opportunity).assessment.state is CapitalGateState.PASS


def test_multiple_rejection_reasons_are_deterministic_and_separate_from_blockers():
    repository, opportunity = prepared(quantity=9, deployable_amount="1")
    repository.conservative = unchecked(
        repository.conservative,
        conservative_profit_per_unit=Decimal("-1"),
        conservative_margin=Decimal("-2"),
        conservative_acquisition_roi=Decimal("-3"),
    )
    result = evaluate(repository, opportunity).assessment
    assert result.state is CapitalGateState.REJECTED
    assert result.rejection_reason_codes == tuple(CapitalGateRejectionReasonCode)
    assert result.blocking_reasons == ()


def test_exact_replay_skips_sources_identity_clocks_and_changed_source_conflicts():
    repository, opportunity = prepared()
    request = command(repository, opportunity)
    first = owner(repository)[0].execute(request)
    reads = repository.source_reads
    replay = owner(repository, fail=True)[0].execute(request)
    assert replay.replayed is True
    assert replay.assessment == first.assessment
    assert replay.receipt == first.receipt
    assert repository.source_reads == reads
    for changed in (
        replace(request, capital_readiness_assessment_id="other"),
        replace(request, capital_requirement_id="other"),
        replace(request, deployable_capital_snapshot_id="other"),
    ):
        with pytest.raises(CapitalGateReplayConflictError):
            owner(repository, fail=True)[0].execute(changed)


def test_production_identity_supplier_is_stateless_uuid4_hex():
    supplier = ProductionCapitalGateIdentityGenerator()
    values = {supplier() for _ in range(32)}
    assert len(values) == 32
    assert all(re.fullmatch(r"[0-9a-f]{32}", value) for value in values)
    assert supplier.__slots__ == ()
    assert not hasattr(supplier, "__dict__")
