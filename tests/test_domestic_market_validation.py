from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

import pytest

from app.application.assessment_snapshot import (
    CompetitionAssessmentSnapshot,
    DemandAssessmentSnapshot,
)
from app.application.decision_composition import (
    ASSESSMENT_SCHEMA_VERSION,
    COMPETITION_POLICY_VERSION,
    DEMAND_POLICY_VERSION,
)
from app.application.domestic_market_validation import (
    DomesticMarketValidationReplayConflictError,
    ValidateDomesticMarketCommand,
    ValidateDomesticMarketForCapital,
)
from app.application.opportunity_market_identity import OpportunityMarketIdentityBinding
from app.domain.decision_engine import (
    DecisionEvidenceAvailability,
    DecisionFreshness,
    OpportunityIdentity,
)
from app.domain.market_intelligence import (
    CompetitionObservation,
    DemandObservation,
    DomesticMarketValidationReasonCode,
    DomesticMarketValidationState,
    DomesticMarketVerification,
    MarketEvidence,
    MarketEvidenceStatus,
    MarketObservationIdentity,
    MarketObservationScope,
    analyze_competition,
    analyze_demand,
)
from app.infrastructure.domestic_market_validation import (
    ProductionDomesticMarketValidationIdentityGenerator,
)


NOW = datetime(2026, 8, 9, 9, tzinfo=timezone.utc)


def identity(*, market: str = "KR", marketplace: str = "coupang") -> MarketObservationIdentity:
    return MarketObservationIdentity(
        scope=MarketObservationScope.LISTING,
        market=market,
        marketplace=marketplace,
        canonical_product_id="product-1",
        marketplace_item_id="listing-1",
        normalized_query=None,
        category="electronics",
        variant_identity=None,
        condition="new",
        window_started_at=NOW - timedelta(minutes=5),
        window_ended_at=NOW,
    )


def evidence(
    value,
    *,
    identity_value: MarketObservationIdentity,
    metric: str,
    status: MarketEvidenceStatus = MarketEvidenceStatus.OBSERVED,
    source: str | None = "domestic-capture",
    reference: str | None = None,
    observed_at: datetime | None = NOW,
    unit: str = "count",
) -> MarketEvidence:
    return MarketEvidence(
        value=value,
        source=source,
        reference=reference if reference is not None else f"capture:{metric}",
        observed_at=observed_at,
        status=status,
        confidence=Decimal("0.9"),
        market=identity_value.market,
        marketplace=identity_value.marketplace,
        collection_method="operator_capture",
        schema_version="market-evidence-v1",
        unit=unit,
    )


def competition(
    identity_value: MarketObservationIdentity,
    *,
    omit: str | None = None,
    overrides: dict[str, MarketEvidence] | None = None,
) -> CompetitionObservation:
    values = {
        "competitor_count": evidence(20, identity_value=identity_value, metric="competitor_count"),
        "rocket_seller_count": evidence(4, identity_value=identity_value, metric="rocket_seller_count"),
        "price_spread": evidence(Decimal("2000"), identity_value=identity_value, metric="price_spread", unit="KRW"),
        "median_price": evidence(Decimal("19900"), identity_value=identity_value, metric="median_price", unit="KRW"),
    }
    if omit is not None:
        values.pop(omit)
    values.update(overrides or {})
    return CompetitionObservation("competition-observation-1", identity_value, NOW, "competition-v1", values)


def demand(
    identity_value: MarketObservationIdentity,
    *,
    omit: str | None = None,
    overrides: dict[str, MarketEvidence] | None = None,
) -> DemandObservation:
    values = {
        "search_volume": evidence(2001, identity_value=identity_value, metric="search_volume"),
        "review_count": evidence(201, identity_value=identity_value, metric="review_count"),
        "rating": evidence(Decimal("4.6"), identity_value=identity_value, metric="rating", unit="stars"),
        "coupang_popularity_rank": evidence(3, identity_value=identity_value, metric="coupang_popularity_rank", unit="rank"),
        "itemscout_popularity_rank": evidence(7, identity_value=identity_value, metric="itemscout_popularity_rank", unit="rank"),
    }
    if omit is not None:
        values.pop(omit)
    values.update(overrides or {})
    return DemandObservation("demand-observation-1", identity_value, NOW, "demand-v1", values)


def competition_snapshot(observation: CompetitionObservation) -> CompetitionAssessmentSnapshot:
    assessment = analyze_competition(observation, generated_at=NOW)
    return CompetitionAssessmentSnapshot(
        "competition-assessment-1",
        observation.identity,
        observation.observation_id,
        assessment,
        DecisionEvidenceAvailability.COMPLETE,
        assessment.confidence,
        DecisionFreshness.FRESH,
        NOW,
        ASSESSMENT_SCHEMA_VERSION,
        COMPETITION_POLICY_VERSION,
    )


def demand_snapshot(observation: DemandObservation) -> DemandAssessmentSnapshot:
    assessment = analyze_demand(observation, generated_at=NOW)
    availability = (
        DecisionEvidenceAvailability.COMPLETE
        if not assessment.missing_metrics
        else DecisionEvidenceAvailability.PARTIAL
    )
    return DemandAssessmentSnapshot(
        "demand-assessment-1",
        observation.identity,
        observation.observation_id,
        assessment,
        availability,
        assessment.confidence,
        DecisionFreshness.FRESH,
        NOW,
        ASSESSMENT_SCHEMA_VERSION,
        DEMAND_POLICY_VERSION,
    )


class FakeRepository:
    def __init__(self, identity_value: MarketObservationIdentity | None = None) -> None:
        identity_value = identity_value or identity()
        self.binding = OpportunityMarketIdentityBinding(
            "opportunity-1", "discovery:1", identity_value, NOW
        )
        comp = competition(identity_value)
        dem = demand(identity_value)
        self.observations = {comp.observation_id: comp, dem.observation_id: dem}
        self.competition_snapshots = {
            "competition-assessment-1": competition_snapshot(comp)
        }
        self.demand_snapshots = {"demand-assessment-1": demand_snapshot(dem)}
        self.publications = {}

    def get_market_identity_binding(self, opportunity_id):
        return self.binding if self.binding.opportunity_id == opportunity_id else None

    def get_observation_by_id(self, observation_id):
        return self.observations.get(observation_id)

    def get_competition_assessment_snapshot(self, snapshot_id):
        return self.competition_snapshots.get(snapshot_id)

    def get_demand_assessment_snapshot(self, snapshot_id):
        return self.demand_snapshots.get(snapshot_id)

    def get_human_verified_external_signals_by_ids(self, identity_value, signal_ids):
        return tuple(
            SimpleNamespace(signal_id=value, identity=identity_value)
            for value in signal_ids
        )

    def validate_replay(self, command_id, fingerprint):
        value = self.publications.get(command_id)
        if value is None:
            return None
        if value.receipt.command_fingerprint != fingerprint:
            raise DomesticMarketValidationReplayConflictError("command payload conflicts")
        return replace(value, replayed=True)

    def save_assessment(self, command, assessment, receipt):
        replay = self.validate_replay(command.command_id, command.fingerprint)
        if replay is not None:
            return replay
        from app.application.domestic_market_validation import DomesticMarketValidationPublication

        result = DomesticMarketValidationPublication(assessment, receipt, False)
        self.publications[command.command_id] = result
        return result

    def get_assessment(self, assessment_id):
        return next(
            (value.assessment for value in self.publications.values() if value.assessment.assessment_id == assessment_id),
            None,
        )

    def get_receipt(self, command_id):
        value = self.publications.get(command_id)
        return None if value is None else value.receipt


class Counter:
    def __init__(self, value):
        self.value = value
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return self.value


def verification(*, current=True, reviewed_source_ids=None, verified_at=NOW + timedelta(minutes=1)):
    return DomesticMarketVerification(
        operator_id="founder-1",
        verified_at=verified_at,
        current_use_confirmed=current,
        reviewed_source_ids=reviewed_source_ids
        or (
            "competition-observation-1",
            "competition-assessment-1",
            "demand-observation-1",
            "demand-assessment-1",
        ),
    )


def command(*, identity_value=None, verification_value=None, command_id="market-validation-command-1", **overrides):
    values = dict(
        command_id=command_id,
        opportunity_identity=OpportunityIdentity("opportunity-1", "discovery:1"),
        market_identity=identity_value or identity(),
        competition_observation_id="competition-observation-1",
        competition_assessment_id="competition-assessment-1",
        demand_observation_id="demand-observation-1",
        demand_assessment_id="demand-assessment-1",
        accepted_external_signal_ids=(),
        verification=verification_value or verification(),
        requested_at=NOW,
    )
    values.update(overrides)
    return ValidateDomesticMarketCommand(**values)


def execute(repository, command_value=None, *, identity_counter=None, evaluated=None, committed=None):
    identity_counter = identity_counter or Counter("validation-assessment-1")
    evaluated = evaluated or Counter(NOW + timedelta(minutes=2))
    committed = committed or Counter(NOW + timedelta(minutes=3))
    publication = ValidateDomesticMarketForCapital(
        repository,
        assessment_id_generator=identity_counter,
        evaluated_clock=evaluated,
        committed_clock=committed,
    ).execute(command_value or command())
    return publication, identity_counter, evaluated, committed


def test_production_assessment_identity_supplier_is_stateless_uuid4() -> None:
    supplier = ProductionDomesticMarketValidationIdentityGenerator()
    with ThreadPoolExecutor(max_workers=16) as pool:
        values = tuple(pool.map(lambda _: supplier(), range(512)))
    assert type(supplier).__slots__ == ()
    assert not hasattr(supplier, "__dict__")
    assert len(values) == len(set(values))
    assert all(len(value) == 32 and value == value.lower() for value in values)
    assert all(UUID(hex=value).version == 4 for value in values)


def test_exact_complete_sources_are_validated_for_capital() -> None:
    publication, *_ = execute(FakeRepository())
    assessment = publication.assessment
    assert assessment.state is DomesticMarketValidationState.VALIDATED_FOR_CAPITAL
    assert assessment.blocking_reasons == ()
    assert assessment.source_manifest.opportunity_id == "opportunity-1"
    assert assessment.source_manifest.market_identity.market == "KR"
    assert assessment.source_manifest.competition.assessment_id == "competition-assessment-1"
    assert assessment.source_manifest.demand.assessment_id == "demand-assessment-1"


def test_non_domestic_market_is_blocked() -> None:
    foreign = identity(market="US", marketplace="ebay")
    publication, *_ = execute(FakeRepository(foreign), command(identity_value=foreign))
    assert publication.assessment.state is DomesticMarketValidationState.BLOCKED
    assert DomesticMarketValidationReasonCode.NON_DOMESTIC_MARKET in publication.assessment.reason_codes


def test_opportunity_market_lineage_mismatch_is_blocked() -> None:
    repository = FakeRepository()
    publication, *_ = execute(
        repository,
        command(identity_value=replace(identity(), marketplace_item_id="other")),
    )
    assert DomesticMarketValidationReasonCode.OPPORTUNITY_MARKET_LINEAGE_MISMATCH in publication.assessment.reason_codes


@pytest.mark.parametrize("source", ("competition", "demand"))
def test_missing_exact_source_is_blocked(source: str) -> None:
    repository = FakeRepository()
    if source == "competition":
        repository.competition_snapshots.clear()
        expected = DomesticMarketValidationReasonCode.COMPETITION_SOURCE_MISSING
    else:
        repository.demand_snapshots.clear()
        expected = DomesticMarketValidationReasonCode.DEMAND_SOURCE_MISSING
    publication, *_ = execute(repository)
    assert expected in publication.assessment.reason_codes


def test_missing_competition_metric_is_blocked() -> None:
    repository = FakeRepository()
    item = competition(identity(), omit="median_price")
    repository.observations[item.observation_id] = item
    publication, *_ = execute(repository)
    assert DomesticMarketValidationReasonCode.COMPETITION_REQUIRED_METRIC_MISSING in publication.assessment.reason_codes


def test_partial_demand_is_blocked() -> None:
    repository = FakeRepository()
    item = demand(identity(), omit="itemscout_popularity_rank")
    repository.observations[item.observation_id] = item
    repository.demand_snapshots["demand-assessment-1"] = demand_snapshot(item)
    publication, *_ = execute(repository)
    assert DomesticMarketValidationReasonCode.DEMAND_ASSESSMENT_PARTIAL in publication.assessment.reason_codes
    assert DomesticMarketValidationReasonCode.DEMAND_REQUIRED_METRIC_MISSING in publication.assessment.reason_codes


@pytest.mark.parametrize("source", ("competition", "demand"))
def test_required_metric_provenance_is_required(source: str) -> None:
    repository = FakeRepository()
    if source == "competition":
        item = competition(identity(), overrides={
            "median_price": evidence(Decimal("19900"), identity_value=identity(), metric="median_price", reference="", unit="KRW")
        })
        repository.observations[item.observation_id] = item
        expected = DomesticMarketValidationReasonCode.COMPETITION_PROVENANCE_INSUFFICIENT
    else:
        item = demand(identity(), overrides={
            "rating": evidence(Decimal("4.6"), identity_value=identity(), metric="rating", reference="", unit="stars")
        })
        repository.observations[item.observation_id] = item
        expected = DomesticMarketValidationReasonCode.DEMAND_PROVENANCE_INSUFFICIENT
    publication, *_ = execute(repository)
    assert expected in publication.assessment.reason_codes


def test_unsupported_required_evidence_status_is_blocked() -> None:
    repository = FakeRepository()
    estimated = evidence(
        Decimal("19900"), identity_value=identity(), metric="median_price",
        status=MarketEvidenceStatus.ESTIMATED, unit="KRW",
    )
    item = competition(identity(), overrides={"median_price": estimated})
    repository.observations[item.observation_id] = item
    publication, *_ = execute(repository)
    assert DomesticMarketValidationReasonCode.REQUIRED_EVIDENCE_STATUS_UNSUPPORTED in publication.assessment.reason_codes


def test_missing_and_future_source_time_are_blocked() -> None:
    repository = FakeRepository()
    missing = evidence(
        Decimal("19900"), identity_value=identity(), metric="median_price",
        status=MarketEvidenceStatus.ESTIMATED, observed_at=None, unit="KRW",
    )
    item = competition(identity(), overrides={"median_price": missing})
    repository.observations[item.observation_id] = item
    publication, *_ = execute(repository)
    assert DomesticMarketValidationReasonCode.SOURCE_TIME_UNKNOWN in publication.assessment.reason_codes

    repository = FakeRepository()
    future = evidence(
        Decimal("19900"), identity_value=identity(), metric="median_price",
        observed_at=NOW + timedelta(hours=1), unit="KRW",
    )
    item = competition(identity(), overrides={"median_price": future})
    repository.observations[item.observation_id] = item
    publication, *_ = execute(repository)
    assert DomesticMarketValidationReasonCode.SOURCE_TIME_IN_FUTURE in publication.assessment.reason_codes


def test_current_use_verification_is_explicit_and_exact() -> None:
    publication, *_ = execute(FakeRepository(), command(verification_value=verification(current=False)))
    assert DomesticMarketValidationReasonCode.CURRENT_USE_VERIFICATION_MISSING in publication.assessment.reason_codes

    publication, *_ = execute(FakeRepository(), command(verification_value=verification(reviewed_source_ids=("wrong",))))
    assert DomesticMarketValidationReasonCode.OPPORTUNITY_MARKET_LINEAGE_MISMATCH in publication.assessment.reason_codes


def test_caller_cannot_declare_final_state_and_no_capital_or_profitability_is_created() -> None:
    item = command()
    for forbidden in ("state", "blocking_reasons", "assessment_id", "capital_ready", "buy", "invest"):
        assert not hasattr(item, forbidden)
    assessment = execute(FakeRepository())[0].assessment
    for forbidden in ("profit", "roi", "margin", "expected_sale_price", "capital_ready", "buy", "invest"):
        assert not hasattr(assessment, forbidden)


def test_exact_operator_sources_and_market_price_evidence_are_preserved() -> None:
    assessment = execute(FakeRepository())[0].assessment
    assert assessment.verification.operator_id == "founder-1"
    assert tuple(value.metric for value in assessment.source_manifest.competition.evidence) == (
        "competitor_count", "rocket_seller_count", "price_spread", "median_price"
    )
    median = assessment.source_manifest.competition.evidence[-1]
    assert median.value == Decimal("19900")
    assert median.unit == "KRW"


def test_reason_order_is_deterministic_and_assessment_is_immutable() -> None:
    foreign = identity(market="US", marketplace="ebay")
    publication, *_ = execute(
        FakeRepository(foreign),
        command(identity_value=foreign, verification_value=verification(current=False)),
    )
    assert publication.assessment.reason_codes == tuple(
        sorted(publication.assessment.reason_codes, key=lambda value: value.order)
    )
    with pytest.raises(FrozenInstanceError):
        publication.assessment.state = DomesticMarketValidationState.VALIDATED_FOR_CAPITAL  # type: ignore[misc]


def test_exact_replay_precedes_identity_and_server_clocks() -> None:
    repository = FakeRepository()
    first, identity_counter, evaluated, committed = execute(repository)
    calls = (identity_counter.calls, evaluated.calls, committed.calls)
    replay, *_ = execute(
        repository,
        identity_counter=identity_counter,
        evaluated=evaluated,
        committed=committed,
    )
    assert replay.replayed is True
    assert replay.assessment == first.assessment
    assert (identity_counter.calls, evaluated.calls, committed.calls) == calls


def test_changed_source_or_verification_conflicts() -> None:
    repository = FakeRepository()
    execute(repository)
    with pytest.raises(DomesticMarketValidationReplayConflictError):
        execute(repository, command(competition_assessment_id="changed"))
    with pytest.raises(DomesticMarketValidationReplayConflictError):
        execute(repository, command(verification_value=replace(verification(), operator_id="other")))


def test_optional_external_signal_cannot_replace_required_sources() -> None:
    repository = FakeRepository()
    repository.competition_snapshots.clear()
    reviewed = verification(reviewed_source_ids=(
        "competition-observation-1", "competition-assessment-1",
        "demand-observation-1", "demand-assessment-1", "signal-1",
    ))
    publication, *_ = execute(
        repository,
        command(accepted_external_signal_ids=("signal-1",), verification_value=reviewed),
    )
    assert DomesticMarketValidationReasonCode.COMPETITION_SOURCE_MISSING in publication.assessment.reason_codes
