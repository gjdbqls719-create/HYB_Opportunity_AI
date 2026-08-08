from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal, localcontext

import pytest

from app.application.conservative_economics import (
    ConservativeEconomicsPublication,
    ConservativeEconomicsReplayConflictError,
    ConservativeEconomicsScenario,
    EvaluateConservativeEconomics,
    EvaluateConservativeEconomicsCommand,
)
from app.domain.opportunity import (
    CONSERVATIVE_ECONOMICS_POLICY_NAME,
    CONSERVATIVE_ECONOMICS_POLICY_VERSION,
    ConservativeEconomicsAssumptionKind,
    ConservativeEconomicsBlockingCode,
    ConservativeEconomicsStatus,
    EvidenceStatus,
    conservative_decimal_context,
)
from app.infrastructure.conservative_economics import (
    ProductionConservativeEconomicsIdentityGenerator,
)
from test_economics_source_composition import Calls, compose, economics, money, rate
from test_sourcing_authority_contract import NOW


class MemoryConservativeEconomicsRepository:
    def __init__(self, source):
        self.source = source
        self.saved = None

    def get_source_composition(self, composition_id):
        if self.source.composition_id == composition_id:
            return self.source
        return None

    def validate_replay(self, command_id, fingerprint):
        if self.saved is None or self.saved.receipt.command_id != command_id:
            return None
        if self.saved.receipt.command_fingerprint != fingerprint:
            raise ConservativeEconomicsReplayConflictError("conflict")
        return replace(self.saved, replayed=True)

    def save_result(self, command, result, receipt):
        self.saved = ConservativeEconomicsPublication(result, receipt, False)
        return self.saved


def verified_input(**changes):
    values = economics()
    values = replace(
        values,
        tax_rate=rate("0", "tax"),
        duty_cost=money("0", "duty"),
        other_cost=money("0", "other"),
    )
    return replace(values, **changes)


def source(**changes):
    publication = compose(verified=verified_input(**changes))[0]
    return publication.composition


def scenario(factor="1", **changes):
    values = {
        "scenario_name": "founder-explicit-unit-scenario",
        "scenario_version": "1.0.0",
        "sale_price_factor": Decimal(factor),
        "assumption_owner": "founder",
    }
    values.update(changes)
    return ConservativeEconomicsScenario(**values)


def command(value, *, factor="1", **changes):
    values = {
        "command_id": "conservative-economics-command-1",
        "opportunity_identity": value.opportunity_identity,
        "source_composition_id": value.composition_id,
        "scenario": scenario(factor),
        "requested_at": NOW,
        "policy_name": CONSERVATIVE_ECONOMICS_POLICY_NAME,
        "policy_version": CONSERVATIVE_ECONOMICS_POLICY_VERSION,
    }
    values.update(changes)
    return EvaluateConservativeEconomicsCommand(**values)


def evaluate(value=None, *, factor="1", repository=None):
    value = value or source()
    repository = repository or MemoryConservativeEconomicsRepository(value)
    identity = Calls("conservative-result-1")
    calculated = Calls(NOW + timedelta(minutes=30))
    committed = Calls(NOW + timedelta(minutes=31))
    owner = EvaluateConservativeEconomics(
        repository,
        result_id_generator=identity,
        calculated_clock=calculated,
        committed_clock=committed,
    )
    result = owner.execute(command(value, factor=factor))
    return result, repository, identity, calculated, committed


def codes(value):
    return tuple(reason.code for reason in value.blocking_reasons)


def test_ready_source_neutral_scenario_calculates_exact_unit_economics():
    source_value = source()
    publication, *_ = evaluate(source_value)
    value = publication.result
    sale = source_value.expected_sale_price.amount
    marketplace = sale * source_value.marketplace_fee_rate.rate
    payment = sale * source_value.payment_fee_rate.rate
    total = (
        source_value.acquisition_cost_per_unit
        + marketplace
        + payment
        + source_value.fixed_fee.amount
    )
    profit = sale - total

    assert value.status is ConservativeEconomicsStatus.CALCULABLE
    assert value.authoritative_expected_sale_price == sale
    assert value.conservative_sale_price == sale
    assert value.acquisition_cost_per_unit == source_value.acquisition_cost_per_unit
    assert value.marketplace_fee == marketplace
    assert value.payment_fee == payment
    assert value.fixed_fee == source_value.fixed_fee.amount
    assert value.accepted_tax_cost == Decimal("0")
    assert value.accepted_duty_cost == Decimal("0")
    assert value.accepted_other_cost == Decimal("0")
    assert value.total_unit_cost == total
    assert value.conservative_profit_per_unit == profit
    assert value.conservative_margin == profit / sale * Decimal("100")
    with localcontext(conservative_decimal_context()):
        expected_roi = profit / source_value.acquisition_cost_per_unit * Decimal("100")
    assert value.conservative_acquisition_roi == expected_roi
    assert not hasattr(value, "roi")
    assert not hasattr(value, "landed_cost_roi")
    assert not hasattr(value, "purchase_cost")
    assert not hasattr(value, "shipping_cost")
    assert not hasattr(value, "monthly_profit")
    assert not hasattr(value, "sales_volume")
    assert not hasattr(value, "capital_ready")
    assert not hasattr(value, "recommendation")


def test_explicit_factor_adjusts_sale_and_fees_without_hidden_haircut():
    source_value = source()
    neutral = evaluate(source_value)[0].result
    adjusted = evaluate(source_value, factor="0.90")[0].result

    assert neutral.conservative_sale_price == source_value.expected_sale_price.amount
    assert adjusted.conservative_sale_price == Decimal("18000.0")
    assert adjusted.marketplace_fee == Decimal("2700.000")
    assert adjusted.payment_fee == Decimal("540.000")
    assert adjusted.assumptions[0].kind is ConservativeEconomicsAssumptionKind.SALE_PRICE_FACTOR
    assert adjusted.assumptions[0].value == Decimal("0.90")
    assert adjusted.assumptions[0].owner == "founder"


@pytest.mark.parametrize("factor", ["0", "-0.1", "1.0001"])
def test_scenario_factor_must_be_explicit_positive_and_not_increase_price(factor):
    with pytest.raises(ValueError):
        scenario(factor)


def test_estimated_sale_price_status_and_reference_are_preserved():
    value = evaluate()[0].result
    assert value.expected_sale_price_evidence_status is EvidenceStatus.ESTIMATED
    assert value.expected_sale_price_evidence_reference == "economics:expected-sale"


@pytest.mark.parametrize(
    ("field", "replacement", "expected"),
    [
        ("tax_rate", rate("0.01", "tax"), ConservativeEconomicsBlockingCode.TAX_NOT_CAPITAL_AUTHORITATIVE),
        ("tax_rate", rate(None, "tax", EvidenceStatus.MISSING), ConservativeEconomicsBlockingCode.TAX_NOT_CAPITAL_AUTHORITATIVE),
        ("duty_cost", money("1", "duty"), ConservativeEconomicsBlockingCode.DUTY_NOT_CAPITAL_AUTHORITATIVE),
        ("duty_cost", money(None, "duty", EvidenceStatus.MISSING), ConservativeEconomicsBlockingCode.DUTY_NOT_CAPITAL_AUTHORITATIVE),
        ("other_cost", money("1", "other"), ConservativeEconomicsBlockingCode.OTHER_COST_SCOPE_UNRESOLVED),
        ("marketplace_fee_rate", rate(None, "marketplace", EvidenceStatus.MISSING), ConservativeEconomicsBlockingCode.MARKETPLACE_FEE_NOT_READY),
        ("payment_fee_rate", rate(None, "payment", EvidenceStatus.MISSING), ConservativeEconomicsBlockingCode.PAYMENT_FEE_NOT_READY),
        ("fixed_fee", money(None, "fixed", EvidenceStatus.MISSING), ConservativeEconomicsBlockingCode.FIXED_FEE_NOT_READY),
    ],
)
def test_unsafe_or_missing_financial_source_blocks_without_numeric_profitability(
    field, replacement, expected
):
    value = source(**{field: replacement})
    result = evaluate(value)[0].result

    assert result.status is ConservativeEconomicsStatus.BLOCKED
    assert expected in codes(result)
    for name in (
        "conservative_sale_price",
        "marketplace_fee",
        "payment_fee",
        "total_unit_cost",
        "conservative_profit_per_unit",
        "conservative_margin",
        "conservative_acquisition_roi",
    ):
        assert getattr(result, name) is None


def test_blocked_source_is_never_calculated_and_retains_source_lineage():
    value = source(other_cost=money("10", "other"))
    result = evaluate(value)[0].result
    assert result.status is ConservativeEconomicsStatus.BLOCKED
    assert result.source_composition_id == value.composition_id
    assert ConservativeEconomicsBlockingCode.SOURCE_COMPOSITION_BLOCKED in codes(result)
    assert ConservativeEconomicsBlockingCode.OTHER_COST_SCOPE_UNRESOLVED in codes(result)


def test_zero_acquisition_and_currency_mismatch_block_without_fallback():
    zero = replace(source(), acquisition_cost_per_unit=Decimal("0"))
    zero_result = evaluate(zero)[0].result
    assert ConservativeEconomicsBlockingCode.ACQUISITION_COST_NON_POSITIVE in codes(zero_result)
    assert zero_result.conservative_acquisition_roi is None

    wrong_currency = replace(source(), economics_currency="USD")
    wrong_result = evaluate(wrong_currency)[0].result
    assert ConservativeEconomicsBlockingCode.CURRENCY_MISMATCH in codes(wrong_result)


def test_negative_profit_remains_calculable():
    value = source(expected_sale_price=money("100", "expected-sale", EvidenceStatus.VERIFIED))
    result = evaluate(value)[0].result
    assert result.status is ConservativeEconomicsStatus.CALCULABLE
    assert result.conservative_profit_per_unit < 0
    assert result.conservative_margin < 0
    assert result.conservative_acquisition_roi < 0


def test_result_and_scenario_are_immutable_and_decimal_only():
    publication = evaluate()[0]
    with pytest.raises(FrozenInstanceError):
        publication.result.status = ConservativeEconomicsStatus.BLOCKED
    with pytest.raises(FrozenInstanceError):
        publication.result.assumptions[0].value = Decimal("0.5")
    with pytest.raises(TypeError):
        ConservativeEconomicsScenario(
            "scenario", "1.0.0", 0.9, "founder"  # type: ignore[arg-type]
        )
    for name in (
        "conservative_sale_price",
        "marketplace_fee",
        "payment_fee",
        "total_unit_cost",
        "conservative_profit_per_unit",
        "conservative_margin",
        "conservative_acquisition_roi",
    ):
        assert isinstance(getattr(publication.result, name), Decimal)


def test_exact_replay_precedes_source_identity_and_clocks():
    value = source()
    publication, repository, identity, calculated, committed = evaluate(value)

    class Never:
        def __call__(self):
            raise AssertionError("fresh dependency called during replay")

    replay = EvaluateConservativeEconomics(
        repository,
        result_id_generator=Never(),
        calculated_clock=Never(),
        committed_clock=Never(),
    ).execute(command(value))
    assert replay.replayed is True
    assert replay.result == publication.result
    assert replay.receipt == publication.receipt
    assert identity.count == calculated.count == committed.count == 1


def test_changed_scenario_conflicts_and_production_identity_is_uuid4():
    value = source()
    _, repository, *_ = evaluate(value)
    with pytest.raises(ConservativeEconomicsReplayConflictError):
        EvaluateConservativeEconomics(
            repository,
            result_id_generator=lambda: "unused",
            calculated_clock=lambda: NOW,
            committed_clock=lambda: NOW,
        ).execute(command(value, factor="0.9"))

    generated = ProductionConservativeEconomicsIdentityGenerator()()
    assert len(generated) == 32
    assert generated == generated.lower()
    assert int(generated, 16) >= 0
