from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.application.candidate_promotion import CandidateOpportunityBinding
from app.application.domestic_selling_opportunity import (
    AdmitDomesticSellingOpportunity,
    AdmitDomesticSellingOpportunityCommand,
    DomesticSellingOpportunityCardinalityConflictError,
    DomesticSellingOpportunityLineageError,
    DomesticSellingOpportunityPolicyError,
    DomesticSellingOpportunityReplayConflictError,
    DomesticSellingOpportunitySourceNotFoundError,
    DomesticSellingOpportunityVerificationError,
)
from app.application.opportunity_market_identity import (
    OpportunityMarketIdentityBinding,
)
from app.domain.decision_engine import OpportunityIdentity
from app.domain.discovery_identity import OpportunityCandidateIdentity
from app.domain.market_intelligence import (
    MarketObservationIdentity,
    MarketObservationScope,
)
from app.domain.opportunity import OpportunityLifecycle, OpportunityLifecycleStatus
from app.domain.product_observation import (
    CollectorProvenance,
    ObservedProductSnapshot,
    ProductObservationSnapshot,
)
from app.infrastructure.domestic_selling_opportunity import (
    ProductionDomesticSellingOpportunityAdmissionIdentityGenerator,
    ProductionDomesticSellingOpportunityIdentityGenerator,
)
from app.models import ProductDataSource


NOW = datetime(2026, 8, 9, 10, tzinfo=timezone.utc)


class Calls:
    def __init__(self, *values):
        self.values = list(values)
        self.calls = 0

    def __call__(self):
        index = self.calls
        self.calls += 1
        value = self.values[min(index, len(self.values) - 1)]
        if isinstance(value, Exception):
            raise value
        return value


def market(
    *,
    scope=MarketObservationScope.LISTING,
    market_name="KR",
    marketplace="coupang",
    item_id="kr-listing-1",
    canonical_id=None,
    normalized_query=None,
):
    return MarketObservationIdentity(
        scope=scope,
        market=market_name,
        marketplace=marketplace,
        canonical_product_id=canonical_id,
        marketplace_item_id=item_id,
        normalized_query=normalized_query,
        category="electronics",
        variant_identity="black",
        condition="new",
        window_started_at=NOW - timedelta(hours=1),
        window_ended_at=NOW,
    )


def observed_product(marketplace="ebay"):
    return ObservedProductSnapshot(
        marketplace=marketplace,
        item_id="source-listing-1",
        title="Persisted source product",
        price=25.0,
        currency="USD",
        condition="new",
        url="https://example.test/source-listing-1",
        brand="Brand",
        model_number="MODEL-1",
        category="electronics",
        shipping_cost=0.0,
        seller="seller",
        image_url="https://example.test/image.jpg",
        rating=4.5,
        review_count=10,
        in_stock=True,
        data_source=ProductDataSource.PRODUCTION,
        shipping_cost_known=True,
    )


class MemoryDomesticSellingRepository:
    def __init__(self):
        self.source_market = market(
            market_name="US", marketplace="ebay", item_id="source-listing-1"
        )
        self.lifecycle = OpportunityLifecycle(
            "source-opportunity-1",
            "ebay:item:source-listing-1",
            created_at=NOW - timedelta(days=2),
            updated_at=NOW - timedelta(days=2),
        )
        self.promotion = CandidateOpportunityBinding(
            binding_id="candidate-opportunity-binding-1",
            candidate_id="candidate-1",
            opportunity_id=self.lifecycle.opportunity_id,
            discovery_reference=self.lifecycle.discovery_reference,
            market_observation_identity=self.source_market,
            discovery_command_id="discovery-command-1",
            discovery_execution_id="discovery-execution-1",
            finalized_group_id="group-1",
            promotion_command_id="promotion-command-1",
            promoted_at=NOW - timedelta(days=1),
        )
        self.snapshot = ProductObservationSnapshot(
            snapshot_id="product-snapshot-1",
            candidate_identity=OpportunityCandidateIdentity(
                self.promotion.candidate_id, self.lifecycle.discovery_reference
            ),
            market_observation_identity=self.source_market,
            product=observed_product(),
            collector_provenance=CollectorProvenance(
                "ebay-collector", "1.0.0", "ebay:item:source-listing-1"
            ),
            observed_at=NOW - timedelta(days=1, hours=1),
        )
        self.source_binding = OpportunityMarketIdentityBinding(
            self.lifecycle.opportunity_id,
            self.lifecycle.discovery_reference,
            self.source_market,
            NOW - timedelta(days=1),
        )
        self.results = {}
        self.by_source = {}
        self.read_calls = 0
        self.saved = 0

    def validate_replay(self, command_id, fingerprint):
        result = self.results.get(command_id)
        if result is None:
            return None
        if result.receipt.command_fingerprint != fingerprint:
            raise DomesticSellingOpportunityReplayConflictError(
                "domestic selling command payload conflicts"
            )
        return result

    def get_source_lifecycle(self, opportunity_id):
        self.read_calls += 1
        return (
            self.lifecycle
            if self.lifecycle is not None
            and opportunity_id == self.lifecycle.opportunity_id
            else None
        )

    def get_candidate_promotion(self, opportunity_id):
        self.read_calls += 1
        return (
            self.promotion
            if self.promotion is not None
            and opportunity_id == self.promotion.opportunity_id
            else None
        )

    def get_product_snapshot(self, snapshot_id):
        self.read_calls += 1
        return (
            self.snapshot
            if self.snapshot is not None and snapshot_id == self.snapshot.snapshot_id
            else None
        )

    def get_market_identity_binding(self, opportunity_id):
        self.read_calls += 1
        return (
            self.source_binding
            if self.source_binding is not None
            and opportunity_id == self.source_binding.opportunity_id
            else None
        )

    def get_admission_by_source(self, opportunity_id):
        self.read_calls += 1
        return self.by_source.get(opportunity_id)

    def save_admission(
        self, command, lifecycle, transition, market_binding, admission, receipt
    ):
        from app.application.domestic_selling_opportunity import (
            DomesticSellingOpportunityAdmissionPublication,
        )

        if admission.source_opportunity_identity.opportunity_id in self.by_source:
            raise DomesticSellingOpportunityCardinalityConflictError(
                "source Opportunity already has a domestic-selling admission"
            )
        result = DomesticSellingOpportunityAdmissionPublication(
            lifecycle, transition, market_binding, admission, receipt, False
        )
        self.results[command.command_id] = result
        self.by_source[admission.source_opportunity_identity.opportunity_id] = result
        self.saved += 1
        return result


def command(**changes):
    values = {
        "command_id": "domestic-command-1",
        "source_opportunity_id": "source-opportunity-1",
        "source_product_snapshot_id": "product-snapshot-1",
        "target_market_identity": market(),
        "operator_id": "founder-1",
        "product_equivalence_confirmed": True,
        "evidence_reference": "founder-review:source-to-kr-1",
        "verified_at": NOW + timedelta(minutes=1),
        "requested_at": NOW + timedelta(minutes=2),
    }
    values.update(changes)
    return AdmitDomesticSellingOpportunityCommand(**values)


def owner(repository=None, *, opportunity=None, admission=None, admitted=None, committed=None):
    repository = repository or MemoryDomesticSellingRepository()
    opportunity = opportunity or Calls("domestic-opportunity-1")
    admission = admission or Calls("domestic-admission-1")
    admitted = admitted or Calls(NOW + timedelta(minutes=3))
    committed = committed or Calls(NOW + timedelta(minutes=4))
    return (
        AdmitDomesticSellingOpportunity(
            repository,
            opportunity_id_generator=opportunity,
            admission_id_generator=admission,
            admitted_clock=admitted,
            committed_clock=committed,
        ),
        repository,
        opportunity,
        admission,
        admitted,
        committed,
    )


def test_fresh_admission_preserves_exact_source_and_creates_distinct_kr_opportunity():
    use_case, repository, opportunity, admission, admitted, committed = owner()
    original_source = repr(repository.lifecycle)

    result = use_case.execute(command())

    assert repr(repository.lifecycle) == original_source
    assert result.admission.source_opportunity_identity == OpportunityIdentity(
        "source-opportunity-1", "ebay:item:source-listing-1"
    )
    assert result.admission.domestic_opportunity_identity == OpportunityIdentity(
        "domestic-opportunity-1", "domestic-selling:domestic-admission-1"
    )
    assert result.lifecycle.opportunity_id == "domestic-opportunity-1"
    assert result.lifecycle.status is OpportunityLifecycleStatus.DISCOVERED
    assert result.lifecycle.version == 1
    assert result.market_binding.market_observation_identity == command().target_market_identity
    assert result.market_binding.market_observation_identity.market == "KR"
    assert result.admission.source_market_identity == repository.source_market
    assert result.admission.source_market_identity.market == "US"
    assert result.admission.source_candidate_id == repository.promotion.candidate_id
    assert (
        result.admission.source_candidate_opportunity_binding_id
        == repository.promotion.binding_id
    )
    assert result.admission.source_promotion_command_id == "promotion-command-1"
    assert result.admission.source_product_snapshot_id == repository.snapshot.snapshot_id
    assert result.admission.policy_name == "domestic-selling-opportunity-admission"
    assert result.admission.policy_version == "1.0.0"
    assert result.receipt.committed_at == NOW + timedelta(minutes=4)
    assert result.replayed is False
    assert repository.saved == 1
    assert (opportunity.calls, admission.calls, admitted.calls, committed.calls) == (1, 1, 1, 1)


@pytest.mark.parametrize(
    "target",
    (
        market(),
        market(
            scope=MarketObservationScope.CANONICAL_PRODUCT,
            item_id=None,
            canonical_id="kr-canonical-1",
        ),
    ),
)
def test_listing_and_canonical_product_targets_are_accepted(target):
    use_case, *_ = owner()
    assert use_case.execute(command(target_market_identity=target)).admission.domestic_market_identity == target


@pytest.mark.parametrize(
    "target",
    (
        market(
            scope=MarketObservationScope.SEARCH_QUERY,
            item_id=None,
            normalized_query="camera",
        ),
        market(
            scope=MarketObservationScope.CATEGORY,
            item_id=None,
        ),
        market(market_name="US"),
    ),
)
def test_non_product_or_non_kr_target_is_rejected_before_identity(target):
    use_case, _, opportunity, admission, admitted, committed = owner()
    with pytest.raises(DomesticSellingOpportunityPolicyError):
        use_case.execute(command(target_market_identity=target))
    assert (opportunity.calls, admission.calls, admitted.calls, committed.calls) == (0, 0, 0, 0)


@pytest.mark.parametrize(
    "changes",
    (
        {"product_equivalence_confirmed": False},
        {"evidence_reference": ""},
        {"operator_id": ""},
    ),
)
def test_explicit_operator_product_equivalence_verification_is_required(changes):
    with pytest.raises((DomesticSellingOpportunityVerificationError, ValueError)):
        command(**changes)


def test_command_has_no_title_similarity_or_caller_owned_authoritative_ids():
    names = {item.name for item in fields(AdmitDomesticSellingOpportunityCommand)}
    assert "title" not in names
    assert "similarity_score" not in names
    assert "domestic_opportunity_id" not in names
    assert "admission_id" not in names


@pytest.mark.parametrize("missing", ("lifecycle", "promotion", "snapshot", "source_binding"))
def test_exact_source_facts_must_exist(missing):
    repository = MemoryDomesticSellingRepository()
    setattr(repository, missing, None)
    use_case, *_ = owner(repository)
    with pytest.raises(DomesticSellingOpportunitySourceNotFoundError):
        use_case.execute(command())


@pytest.mark.parametrize("mismatch", ("promotion", "snapshot", "market"))
def test_exact_source_lineage_mismatch_is_rejected(mismatch):
    repository = MemoryDomesticSellingRepository()
    if mismatch == "promotion":
        repository.promotion = replace(repository.promotion, discovery_reference="ebay:item:other")
    elif mismatch == "snapshot":
        repository.snapshot = replace(
            repository.snapshot,
            candidate_identity=OpportunityCandidateIdentity(
                "other-candidate", repository.lifecycle.discovery_reference
            ),
        )
    else:
        repository.source_binding = replace(
            repository.source_binding,
            market_observation_identity=market(
                market_name="US", marketplace="amazon", item_id="other"
            ),
        )
    use_case, _, opportunity, admission, admitted, committed = owner(repository)
    with pytest.raises(DomesticSellingOpportunityLineageError):
        use_case.execute(command())
    assert (opportunity.calls, admission.calls, admitted.calls, committed.calls) == (0, 0, 0, 0)


def test_admission_is_deeply_immutable_and_preserves_policy_and_verification():
    result = owner()[0].execute(command())
    with pytest.raises(FrozenInstanceError):
        result.admission.policy_version = "2.0.0"
    with pytest.raises(FrozenInstanceError):
        result.admission.product_equivalence.operator_id = "other"
    assert result.admission.product_equivalence.confirmed is True
    assert result.admission.product_equivalence.evidence_reference == "founder-review:source-to-kr-1"


def test_unsupported_policy_is_rejected_before_source_reads_or_identity():
    use_case, repository, opportunity, admission, admitted, committed = owner()
    with pytest.raises(DomesticSellingOpportunityPolicyError):
        use_case.execute(command(policy_version="2.0.0"))
    assert repository.read_calls == 0
    assert (opportunity.calls, admission.calls, admitted.calls, committed.calls) == (0, 0, 0, 0)


def test_exact_replay_precedes_source_reads_identities_and_clocks():
    use_case, repository, opportunity, admission, admitted, committed = owner()
    first = use_case.execute(command())
    reads = repository.read_calls

    replay = use_case.execute(command())

    assert replay.admission == first.admission
    assert replay.lifecycle == first.lifecycle
    assert replay.market_binding == first.market_binding
    assert replay.receipt == first.receipt
    assert replay.replayed is True
    assert repository.read_calls == reads
    assert repository.saved == 1
    assert (opportunity.calls, admission.calls, admitted.calls, committed.calls) == (1, 1, 1, 1)


@pytest.mark.parametrize(
    "change",
    (
        {"target_market_identity": market(item_id="kr-listing-2")},
        {"operator_id": "founder-2"},
        {"evidence_reference": "founder-review:changed"},
    ),
)
def test_same_command_changed_payload_conflicts_without_authoritative_replacement(change):
    use_case, repository, opportunity, admission, admitted, committed = owner()
    original = use_case.execute(command())
    with pytest.raises(DomesticSellingOpportunityReplayConflictError):
        use_case.execute(command(**change))
    assert repository.by_source["source-opportunity-1"].admission == original.admission
    assert repository.saved == 1
    assert (opportunity.calls, admission.calls, admitted.calls, committed.calls) == (1, 1, 1, 1)


def test_one_source_has_at_most_one_domestic_selling_opportunity():
    use_case, repository, opportunity, admission, admitted, committed = owner(
        opportunity=Calls("domestic-opportunity-1", "domestic-opportunity-2"),
        admission=Calls("domestic-admission-1", "domestic-admission-2"),
        admitted=Calls(NOW + timedelta(minutes=3), NOW + timedelta(minutes=5)),
        committed=Calls(NOW + timedelta(minutes=4), NOW + timedelta(minutes=6)),
    )
    use_case.execute(command())
    with pytest.raises(DomesticSellingOpportunityCardinalityConflictError):
        use_case.execute(command(command_id="domestic-command-2"))
    assert repository.saved == 1
    assert (opportunity.calls, admission.calls, admitted.calls, committed.calls) == (1, 1, 1, 1)


def test_production_identity_suppliers_are_uuid4_stateless_and_concurrently_unique():
    suppliers = (
        ProductionDomesticSellingOpportunityIdentityGenerator(),
        ProductionDomesticSellingOpportunityAdmissionIdentityGenerator(),
    )
    assert all(type(value).__slots__ == () and not hasattr(value, "__dict__") for value in suppliers)
    with ThreadPoolExecutor(max_workers=16) as pool:
        values = tuple(pool.map(lambda index: suppliers[index % 2](), range(512)))
    assert len(set(values)) == 512
    assert all(len(value) == 32 and value == value.lower() for value in values)
    assert all(UUID(hex=value).version == 4 for value in values)
