from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application.sourcing import (
    AdmitFounderSourcing,
    AdmitFounderSourcingCommand,
    ReviseFounderSourcingQuote,
    ReviseFounderSourcingQuoteCommand,
    SourcingAdmissionReplayConflictError,
    SourcingAdmissionResult,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.domain.sourcing import (
    CommercialFactAvailability,
    FounderSourcingAdmission,
    MatchVerificationStatus,
    ProductMatchVerification,
    SellingProductLineage,
    ShippingScope,
    ShippingTerm,
    SourcingEvidenceKind,
    SourcingEvidenceReference,
    SourcingMoneyFact,
    SourcingQuantityFact,
    SourcingProductIdentity,
    SupplierIdentity,
    SupplierQuoteRevision,
)


NOW = datetime(2026, 8, 7, 8, tzinfo=timezone.utc)


def market_identity() -> MarketObservationIdentity:
    return MarketObservationIdentity(
        scope=MarketObservationScope.LISTING,
        market="KR",
        marketplace="coupang",
        canonical_product_id=None,
        marketplace_item_id="selling-1",
        normalized_query=None,
        category=None,
        variant_identity="black",
        condition="new",
        window_started_at=NOW,
        window_ended_at=NOW,
    )


def lineage() -> SellingProductLineage:
    return SellingProductLineage(
        opportunity_identity=OpportunityIdentity("opp-1", "discovery-1"),
        candidate_id="candidate-1",
        candidate_opportunity_binding_id="binding-1",
        product_observation_snapshot_id="product-snapshot-1",
        market_observation_identity=market_identity(),
    )


def evidence() -> SourcingEvidenceReference:
    return SourcingEvidenceReference(
        kind=SourcingEvidenceKind.MANUAL_ENTRY,
        source_reference="founder:supplier-page-1",
        observed_at=NOW,
    )


def command(**changes) -> AdmitFounderSourcingCommand:
    values = dict(
        command_id="command-1",
        selling_product_lineage=lineage(),
        supplier_platform="1688",
        external_supplier_reference="supplier-ext-1",
        supplier_display_name="Factory A",
        external_product_reference="listing-ext-1",
        option_reference="black-220v",
        sku_reference="sku-1",
        source_url="https://example.test/product/1",
        product_observed_at=NOW,
        quoted_unit_price=SourcingMoneyFact(
            CommercialFactAvailability.KNOWN, Decimal("12.3400"), "CNY"
        ),
        minimum_order_quantity=SourcingQuantityFact(
            CommercialFactAvailability.KNOWN, 10
        ),
        quoted_quantity=SourcingQuantityFact(
            CommercialFactAvailability.KNOWN, 100
        ),
        shipping_terms=(
            ShippingTerm(
                ShippingScope.SUPPLIER_SIDE,
                SourcingMoneyFact(
                    CommercialFactAvailability.KNOWN, Decimal("20.50"), "CNY"
                ),
            ),
            ShippingTerm(
                ShippingScope.INTERNATIONAL_FREIGHT,
                SourcingMoneyFact(CommercialFactAvailability.UNKNOWN),
            ),
            ShippingTerm(
                ShippingScope.DOMESTIC_INBOUND,
                SourcingMoneyFact(CommercialFactAvailability.UNKNOWN),
            ),
        ),
        lead_time_availability=CommercialFactAvailability.KNOWN,
        lead_time_days=14,
        quote_observed_at=NOW,
        quote_valid_until=None,
        quote_evidence=evidence(),
        match_status=MatchVerificationStatus.VERIFIED_MATCH,
        match_evidence=evidence(),
        verified_at=NOW,
        proposal_score=Decimal("91.25"),
        proposal_version="product-matching-v2",
        operator_id="founder-1",
        requested_at=NOW,
    )
    values.update(changes)
    return AdmitFounderSourcingCommand(**values)


class MemoryRepository:
    def __init__(self):
        self.receipts = {}
        self.admissions = {}
        self.save_calls = 0
        self.fail = False

    def validate_replay(self, command_id, fingerprint):
        result = self.receipts.get(command_id)
        if result is None:
            return None
        if result.receipt.command_fingerprint != fingerprint:
            raise SourcingAdmissionReplayConflictError("payload conflicts")
        return result

    def save_admission(self, command, admission, receipt):
        self.save_calls += 1
        if self.fail:
            raise RuntimeError("persistence failed")
        result = SourcingAdmissionResult(admission, receipt, False)
        self.receipts[command.command_id] = result
        self.admissions[admission.admission_id] = admission
        return result

    def save_quote_revision(self, command, admission, receipt):
        return self.save_admission(command, admission, receipt)

    def get_admission(self, admission_id):
        return self.admissions.get(admission_id)

    def get_admission_revision(self, admission_id, revision):
        value = self.admissions.get(admission_id)
        return value if value is not None and value.revision == revision else None

    def get_receipt(self, command_id):
        value = self.receipts.get(command_id)
        return None if value is None else value.receipt


class Supplier:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.value


def service(repository=None, *, admitted_at=NOW, committed_at=NOW):
    repository = repository or MemoryRepository()
    suppliers = tuple(Supplier(value) for value in (
        "supplier-opaque-1", "sourcing-product-opaque-1", "quote-opaque-1",
        "match-opaque-1", "admission-opaque-1",
    ))
    boundary = AdmitFounderSourcing(
        repository,
        supplier_id_generator=suppliers[0],
        sourcing_product_id_generator=suppliers[1],
        quote_id_generator=suppliers[2],
        match_verification_id_generator=suppliers[3],
        admission_id_generator=suppliers[4],
        admission_clock=lambda: admitted_at,
        committed_clock=lambda: committed_at,
    )
    return boundary, repository, suppliers


def test_requested_verified_admitted_and_committed_times_have_distinct_authority():
    admitted_at = NOW.replace(hour=9)
    committed_at = NOW.replace(hour=10)
    result = service(admitted_at=admitted_at, committed_at=committed_at)[0].execute(
        command(verified_at=NOW.replace(hour=7))
    )

    assert result.admission.requested_at == NOW
    assert result.admission.match_verification.verified_at == NOW.replace(hour=7)
    assert result.admission.admitted_at == admitted_at
    assert result.receipt.committed_at == committed_at


def test_fresh_path_calls_each_server_clock_once_and_requested_at_is_fingerprinted():
    repository = MemoryRepository()
    admission_clock = Supplier(NOW.replace(hour=9))
    receipt_clock = Supplier(NOW.replace(hour=10))
    identities = tuple(Supplier(f"opaque-{index}") for index in range(5))
    boundary = AdmitFounderSourcing(
        repository,
        supplier_id_generator=identities[0],
        sourcing_product_id_generator=identities[1],
        quote_id_generator=identities[2],
        match_verification_id_generator=identities[3],
        admission_id_generator=identities[4],
        admission_clock=admission_clock,
        committed_clock=receipt_clock,
    )
    first = boundary.execute(command())
    assert admission_clock.calls == receipt_clock.calls == 1
    assert all(value.calls == 1 for value in identities)
    assert first.receipt.command_fingerprint == command().fingerprint
    with pytest.raises(SourcingAdmissionReplayConflictError):
        boundary.execute(command(requested_at=NOW.replace(hour=6)))
    assert admission_clock.calls == receipt_clock.calls == 1


def test_valid_manual_admission_preserves_identity_quote_moq_and_evidence():
    boundary, _, _ = service()
    result = boundary.execute(command())

    admission = result.admission
    assert admission.supplier_identity == SupplierIdentity(
        "supplier-opaque-1", "1688", "supplier-ext-1", "Factory A"
    )
    assert admission.sourcing_product_identity == SourcingProductIdentity(
        "sourcing-product-opaque-1", "supplier-opaque-1", "listing-ext-1",
        "black-220v", "sku-1", "https://example.test/product/1", NOW,
    )
    assert admission.quote_revision.unit_price.amount == Decimal("12.3400")
    assert admission.quote_revision.minimum_order_quantity.quantity == 10
    assert admission.quote_revision.evidence == evidence()
    assert admission.match_verification.status is MatchVerificationStatus.VERIFIED_MATCH
    assert result.replayed is False


def test_unknown_shipping_remains_unknown_without_zero_fallback():
    result = service()[0].execute(command())
    international = result.admission.quote_revision.shipping_terms[1]
    assert international.scope is ShippingScope.INTERNATIONAL_FREIGHT
    assert international.cost.availability is CommercialFactAvailability.UNKNOWN
    assert international.cost.amount is None
    assert international.cost.currency is None


def test_unknown_moq_and_quantity_remain_explicitly_unknown():
    result = service()[0].execute(command(
        minimum_order_quantity=SourcingQuantityFact(
            CommercialFactAvailability.UNKNOWN
        ),
        quoted_quantity=SourcingQuantityFact(
            CommercialFactAvailability.UNKNOWN
        ),
    ))
    quote = result.admission.quote_revision
    assert quote.minimum_order_quantity.availability is CommercialFactAvailability.UNKNOWN
    assert quote.minimum_order_quantity.quantity is None
    assert quote.quoted_quantity.availability is CommercialFactAvailability.UNKNOWN
    assert quote.quoted_quantity.quantity is None


def test_money_and_currency_contract_rejects_float_non_finite_and_false_unknown():
    with pytest.raises(TypeError, match="Decimal"):
        SourcingMoneyFact(CommercialFactAvailability.KNOWN, 1.2, "CNY")
    with pytest.raises(ValueError, match="finite"):
        SourcingMoneyFact(CommercialFactAvailability.KNOWN, Decimal("NaN"), "CNY")
    with pytest.raises(ValueError, match="must not carry"):
        SourcingMoneyFact(CommercialFactAvailability.UNKNOWN, Decimal("0"), "CNY")
    with pytest.raises(ValueError, match="currency"):
        SourcingMoneyFact(CommercialFactAvailability.KNOWN, Decimal("1"), "CN")


def test_shipping_scope_is_unique_and_tuple_only():
    term = ShippingTerm(
        ShippingScope.SUPPLIER_SIDE,
        SourcingMoneyFact(CommercialFactAvailability.UNKNOWN),
    )
    quote = service()[0].execute(command()).admission.quote_revision
    with pytest.raises(TypeError, match="tuple"):
        replace(quote, shipping_terms=[term])
    with pytest.raises(ValueError, match="unique"):
        replace(quote, shipping_terms=(term, term))


def test_match_verification_is_required_and_similarity_cannot_create_authority():
    for status in (
        MatchVerificationStatus.NEEDS_REVIEW,
        MatchVerificationStatus.VERIFIED_MISMATCH,
    ):
        with pytest.raises(Exception, match="verified match"):
            service()[0].execute(command(match_status=status))
    with pytest.raises(ValueError, match="proposal_version"):
        service()[0].execute(command(proposal_score=Decimal("99"), proposal_version=None))


def test_exact_replay_returns_committed_facts_without_generators_or_clock():
    boundary, repository, suppliers = service()
    first = boundary.execute(command())
    replay = AdmitFounderSourcing(
        repository,
        supplier_id_generator=lambda: pytest.fail("supplier generator called"),
        sourcing_product_id_generator=lambda: pytest.fail("product generator called"),
        quote_id_generator=lambda: pytest.fail("quote generator called"),
        match_verification_id_generator=lambda: pytest.fail("match generator called"),
        admission_id_generator=lambda: pytest.fail("admission generator called"),
        admission_clock=lambda: pytest.fail("admission clock called"),
        committed_clock=lambda: pytest.fail("clock called"),
    ).execute(command())
    assert replay == replace(first, replayed=True)
    assert repository.save_calls == 1
    assert tuple(value.calls for value in suppliers) == (1, 1, 1, 1, 1)


def test_same_command_changed_payload_conflicts_before_identity_generation():
    boundary, repository, _ = service()
    boundary.execute(command())
    later, _, suppliers = service(repository)
    with pytest.raises(SourcingAdmissionReplayConflictError):
        later.execute(command(quoted_quantity=SourcingQuantityFact(
            CommercialFactAvailability.KNOWN, 200
        )))
    assert tuple(value.calls for value in suppliers) == (0, 0, 0, 0, 0)


def test_canonical_fingerprint_is_stable_and_preserves_ordered_shipping_scope():
    original = command()
    recreated = command()
    assert original.fingerprint == recreated.fingerprint
    reordered = command(shipping_terms=tuple(reversed(original.shipping_terms)))
    assert original.fingerprint != reordered.fingerprint


def test_failed_persistence_does_not_make_generated_identity_authoritative():
    repository = MemoryRepository()
    repository.fail = True
    boundary, _, suppliers = service(repository)
    with pytest.raises(RuntimeError, match="persistence failed"):
        boundary.execute(command())
    assert repository.admissions == {}
    assert repository.receipts == {}
    assert tuple(value.calls for value in suppliers) == (1, 1, 1, 1, 1)


def test_contracts_are_immutable():
    admission = service()[0].execute(command()).admission
    with pytest.raises(FrozenInstanceError):
        admission.revision = 2
    with pytest.raises(FrozenInstanceError):
        admission.supplier_identity.supplier_id = "changed"


def test_quote_revision_value_semantics_keep_identity_and_increment_revision():
    first = service()[0].execute(command()).admission
    revised_quote = replace(
        first.quote_revision,
        revision=2,
        unit_price=SourcingMoneyFact(
            CommercialFactAvailability.KNOWN, Decimal("11.90"), "CNY"
        ),
    )
    revised = FounderSourcingAdmission(
        admission_id=first.admission_id,
        revision=2,
        selling_product_lineage=first.selling_product_lineage,
        supplier_identity=first.supplier_identity,
        sourcing_product_identity=first.sourcing_product_identity,
        quote_revision=revised_quote,
        match_verification=first.match_verification,
        admitted_by=first.admitted_by,
        requested_at=first.requested_at,
        admitted_at=first.admitted_at,
    )
    assert revised.quote_revision.quote_id == first.quote_revision.quote_id
    assert revised.revision == revised.quote_revision.revision == 2
    assert revised.quote_revision != first.quote_revision


def test_quote_revision_boundary_keeps_ids_and_appends_next_revision():
    boundary, repository, _ = service()
    first = boundary.execute(command()).admission
    revision_command = ReviseFounderSourcingQuoteCommand(
        command_id="command-2",
        admission_id=first.admission_id,
        expected_revision=1,
        quoted_unit_price=SourcingMoneyFact(
            CommercialFactAvailability.KNOWN, Decimal("11.90"), "CNY"
        ),
        minimum_order_quantity=SourcingQuantityFact(
            CommercialFactAvailability.KNOWN, 20
        ),
        quoted_quantity=SourcingQuantityFact(
            CommercialFactAvailability.KNOWN, 200
        ),
        shipping_terms=first.quote_revision.shipping_terms,
        lead_time_availability=CommercialFactAvailability.UNKNOWN,
        lead_time_days=None,
        quote_observed_at=NOW,
        quote_valid_until=None,
        quote_evidence=evidence(),
        operator_id="founder-1",
        requested_at=NOW,
    )
    revised = ReviseFounderSourcingQuote(
        repository, admission_clock=lambda: NOW.replace(hour=9),
        committed_clock=lambda: NOW
    ).execute(revision_command)
    assert revised.admission.admission_id == first.admission_id
    assert revised.admission.quote_revision.quote_id == first.quote_revision.quote_id
    assert revised.admission.revision == revised.admission.quote_revision.revision == 2
    assert revised.admission.quote_revision.unit_price.amount == Decimal("11.90")
    assert revised.admission.requested_at == NOW
    assert revised.admission.admitted_at == NOW.replace(hour=9)


def test_repository_contract_exposes_only_sourcing_fact_operations():
    from app.application.sourcing import SourcingAuthorityRepository

    expected = {
        "save_admission", "save_quote_revision", "validate_replay",
        "get_admission", "get_admission_revision", "get_receipt",
    }
    assert expected <= set(SourcingAuthorityRepository.__dict__)
    assert not any("sqlite" in name.lower() for name in SourcingAuthorityRepository.__dict__)
