from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from decimal import Decimal

import pytest

from app.application.economics_source_composition import (
    ComposeEconomicsSources,
    ComposeEconomicsSourcesCommand,
    EconomicsSourceCompositionResult,
    EconomicsSourceCompositionSourceError,
)
from app.application.verified_economics_snapshot import VerifiedEconomicsSnapshot
from app.domain.opportunity import (
    EconomicEvidence,
    EconomicsSourceBlockingCode,
    EconomicsSourceCompositionState,
    EvidenceStatus,
    MoneyInput,
    RateInput,
    VerifiedEconomicsInput,
)
from app.infrastructure.economics_source_composition import (
    ProductionEconomicsSourceCompositionIdentityGenerator,
)
from test_acquisition_cost_normalization import (
    Calls,
    allocations,
    complete_composition,
    fx,
    normalize,
)
from test_sourcing_authority_contract import NOW


class MemoryEconomicsSourceRepository:
    def __init__(self, normalization=None, verified=None):
        self.normalization = normalization
        self.verified = verified
        self.saved = None

    def get_normalization(self, normalization_id):
        if self.normalization and self.normalization.normalization_id == normalization_id:
            return self.normalization
        return None

    def get_verified_economics_snapshot(self, opportunity_id):
        if self.verified and self.verified.opportunity_id == opportunity_id:
            return self.verified
        return None

    def validate_replay(self, command_id, fingerprint):
        if self.saved is None:
            return None
        if self.saved.receipt.command_id != command_id:
            return None
        from app.application.economics_source_composition import (
            EconomicsSourceCompositionReplayConflictError,
        )

        if self.saved.receipt.command_fingerprint != fingerprint:
            raise EconomicsSourceCompositionReplayConflictError("conflict")
        return replace(self.saved, replayed=True)

    def save_composition(self, command, composition, receipt):
        self.saved = EconomicsSourceCompositionResult(composition, receipt, False)
        return self.saved


def evidence(status=EvidenceStatus.VERIFIED, field="source"):
    return EconomicEvidence(status, "founder", NOW, f"economics:{field}")


def money(amount, field, status=EvidenceStatus.VERIFIED, currency="KRW"):
    return MoneyInput(
        None if amount is None else Decimal(amount),
        currency,
        evidence(status, field),
    )


def rate(amount, field, status=EvidenceStatus.VERIFIED):
    return RateInput(
        None if amount is None else Decimal(amount),
        evidence(status, field),
    )


def economics(*, currency="KRW", other="0", expected_status=EvidenceStatus.ESTIMATED):
    return VerifiedEconomicsInput(
        purchase_cost=money("999999", "legacy-purchase", currency=currency),
        shipping_cost=money("888888", "legacy-shipping", currency=currency),
        marketplace_fee_rate=rate("0.15", "marketplace-fee"),
        payment_fee_rate=rate("0.03", "payment-fee"),
        fixed_fee=money("400", "fixed-fee", currency=currency),
        tax_rate=rate("0.10", "tax"),
        duty_cost=money("1000", "duty", currency=currency),
        other_cost=money(other, "other", currency=currency),
        expected_sale_price=money(
            "20000", "expected-sale", expected_status, currency
        ),
    )


def sources(*, verified=None):
    composition = complete_composition()
    authorities = allocations(composition)
    observations = (
        fx("fx-cny-krw", "CNY", "KRW", "190"),
        fx("fx-usd-krw", "USD", "KRW", "1400"),
    )
    normalization = normalize(composition, authorities, observations)[0].normalization
    snapshot = VerifiedEconomicsSnapshot(
        normalization.opportunity_identity.opportunity_id,
        verified or economics(),
        NOW + timedelta(minutes=4),
    )
    return normalization, snapshot


def command(normalization, snapshot, **changes):
    values = {
        "command_id": "economics-source-command-1",
        "opportunity_identity": normalization.opportunity_identity,
        "acquisition_normalization_id": normalization.normalization_id,
        "verified_economics_opportunity_id": snapshot.opportunity_id,
        "verified_economics_snapshot_at": snapshot.snapshot_at,
        "verified_economics_schema_version": snapshot.schema_version,
        "requested_at": NOW,
        "policy_name": "authoritative-economics-source-composition",
        "policy_version": "1.0.0",
    }
    values.update(changes)
    return ComposeEconomicsSourcesCommand(**values)


def compose(*, verified=None, repository=None):
    normalization, snapshot = sources(verified=verified)
    repository = repository or MemoryEconomicsSourceRepository(normalization, snapshot)
    identity = Calls("economics-source-composition-1")
    composed = Calls(NOW + timedelta(minutes=5))
    committed = Calls(NOW + timedelta(minutes=6))
    boundary = ComposeEconomicsSources(
        repository,
        composition_id_generator=identity,
        composed_clock=composed,
        committed_clock=committed,
    )
    result = boundary.execute(command(normalization, snapshot))
    return result, repository, identity, composed, committed, normalization, snapshot


def codes(value):
    return tuple(reason.code for reason in value.blocking_reasons)


def test_exact_normalized_acquisition_and_sale_sources_are_composed_without_duplication():
    result, _, _, _, _, normalization, snapshot = compose()
    value = result.composition

    assert value.state is EconomicsSourceCompositionState.READY
    assert value.acquisition_normalization_id == normalization.normalization_id
    assert value.acquisition_cost_per_unit == normalization.total_per_unit_acquisition_cost
    assert value.economics_currency == normalization.target_currency == "KRW"
    assert value.verified_economics_snapshot_at == snapshot.snapshot_at
    assert value.expected_sale_price == snapshot.inputs.expected_sale_price
    assert value.marketplace_fee_rate == snapshot.inputs.marketplace_fee_rate
    assert value.payment_fee_rate == snapshot.inputs.payment_fee_rate
    assert value.fixed_fee == snapshot.inputs.fixed_fee
    assert value.tax_rate == snapshot.inputs.tax_rate
    assert value.duty_cost == snapshot.inputs.duty_cost
    assert value.other_cost == snapshot.inputs.other_cost
    assert not hasattr(value, "purchase_cost")
    assert not hasattr(value, "shipping_cost")


def test_missing_normalization_and_wrong_opportunity_are_rejected():
    normalization, snapshot = sources()
    missing = MemoryEconomicsSourceRepository(None, snapshot)
    boundary = ComposeEconomicsSources(
        missing,
        composition_id_generator=lambda: "id",
        composed_clock=lambda: NOW,
        committed_clock=lambda: NOW,
    )
    with pytest.raises(EconomicsSourceCompositionSourceError):
        boundary.execute(command(normalization, snapshot))

    from app.domain.decision_engine import OpportunityIdentity

    wrong = command(
        normalization,
        snapshot,
        opportunity_identity=OpportunityIdentity("other", "other-discovery"),
    )
    with pytest.raises(EconomicsSourceCompositionSourceError):
        ComposeEconomicsSources(
            MemoryEconomicsSourceRepository(normalization, snapshot),
            composition_id_generator=lambda: "id",
            composed_clock=lambda: NOW,
            committed_clock=lambda: NOW,
        ).execute(wrong)


def test_estimated_expected_sale_price_remains_estimated_and_exact():
    result, *_ = compose()
    assert result.composition.expected_sale_price.evidence.status is EvidenceStatus.ESTIMATED
    assert result.composition.expected_sale_price.evidence.reference == "economics:expected-sale"


@pytest.mark.parametrize(
    ("field", "code"),
    [
        ("expected_sale_price", EconomicsSourceBlockingCode.EXPECTED_SALE_PRICE_MISSING),
        ("marketplace_fee_rate", EconomicsSourceBlockingCode.MARKETPLACE_FEE_MISSING),
        ("payment_fee_rate", EconomicsSourceBlockingCode.PAYMENT_FEE_MISSING),
        ("fixed_fee", EconomicsSourceBlockingCode.FIXED_FEE_MISSING),
        ("tax_rate", EconomicsSourceBlockingCode.TAX_MISSING),
        ("duty_cost", EconomicsSourceBlockingCode.DUTY_MISSING),
        ("other_cost", EconomicsSourceBlockingCode.OTHER_COST_MISSING),
    ],
)
def test_missing_sale_side_fact_blocks_and_never_becomes_zero(field, code):
    value = economics()
    current = getattr(value, field)
    missing_evidence = EconomicEvidence(
        EvidenceStatus.MISSING, "founder", NOW, f"economics:{field}"
    )
    replacement = (
        MoneyInput(None, current.currency, missing_evidence)
        if isinstance(current, MoneyInput)
        else RateInput(None, missing_evidence)
    )
    result, *_ = compose(verified=replace(value, **{field: replacement}))

    assert result.composition.state is EconomicsSourceCompositionState.BLOCKED
    assert code in codes(result.composition)
    persisted = getattr(result.composition, field)
    assert getattr(persisted, "amount", getattr(persisted, "rate", None)) is None


def test_explicit_verified_zero_is_preserved_but_nonzero_unscoped_other_cost_blocks():
    zero, *_ = compose()
    assert zero.composition.other_cost.amount == Decimal("0")
    assert zero.composition.other_cost.evidence.status is EvidenceStatus.VERIFIED
    assert zero.composition.state is EconomicsSourceCompositionState.READY

    nonzero, *_ = compose(verified=economics(other="5"))
    assert nonzero.composition.other_cost.amount == Decimal("5")
    assert EconomicsSourceBlockingCode.OTHER_COST_SCOPE_UNRESOLVED in codes(
        nonzero.composition
    )


def test_currency_mismatch_blocks_without_fx_lookup_or_conversion():
    result, *_ = compose(verified=economics(currency="USD"))
    value = result.composition
    assert value.economics_currency == "KRW"
    assert value.expected_sale_price.currency == "USD"
    assert EconomicsSourceBlockingCode.CURRENCY_MISMATCH in codes(value)


def test_weak_required_evidence_blocks_while_source_is_preserved():
    value = economics()
    weak = replace(
        value,
        marketplace_fee_rate=rate(
            "0.15", "marketplace-fee", EvidenceStatus.ESTIMATED
        ),
    )
    result, *_ = compose(verified=weak)
    assert result.composition.marketplace_fee_rate == weak.marketplace_fee_rate
    assert EconomicsSourceBlockingCode.EVIDENCE_NOT_VERIFIED in codes(
        result.composition
    )


def test_result_is_immutable_and_has_no_calculation_or_capital_judgment():
    result, *_ = compose()
    value = result.composition
    with pytest.raises(FrozenInstanceError):
        value.policy_version = "2.0.0"
    for forbidden in (
        "profit",
        "net_profit",
        "roi",
        "margin",
        "capital_ready",
        "conservative_economics",
    ):
        assert not hasattr(value, forbidden)


def test_exact_replay_precedes_identity_and_clocks():
    first, repository, *_ = compose()

    class Never:
        def __call__(self):
            raise AssertionError("fresh dependency called during replay")

    replay = ComposeEconomicsSources(
        repository,
        composition_id_generator=Never(),
        composed_clock=Never(),
        committed_clock=Never(),
    ).execute(
        command(
            repository.normalization,
            repository.verified,
        )
    )
    assert replay.replayed is True
    assert replay.composition == first.composition
    assert replay.receipt == first.receipt


def test_missing_evidence_reference_blocks_without_replacing_source():
    value = economics()
    source = value.fixed_fee
    missing_reference = replace(source.evidence, reference=None)
    changed = replace(value, fixed_fee=replace(source, evidence=missing_reference))
    result, *_ = compose(verified=changed)

    assert result.composition.fixed_fee.evidence.reference is None
    assert EconomicsSourceBlockingCode.EVIDENCE_REFERENCE_MISSING in codes(
        result.composition
    )


def test_production_composition_identity_is_dedicated_opaque_uuid4_hex():
    supplier = ProductionEconomicsSourceCompositionIdentityGenerator()
    values = {supplier() for _ in range(128)}

    assert len(values) == 128
    assert supplier.__slots__ == ()
    assert not hasattr(supplier, "__dict__")
    assert all(len(value) == 32 for value in values)
    assert all(set(value) <= set("0123456789abcdef") for value in values)
