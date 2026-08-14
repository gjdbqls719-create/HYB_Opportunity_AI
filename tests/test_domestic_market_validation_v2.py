from __future__ import annotations

from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
import hashlib
import json

import pytest

from app.application.competition_v2_admission import CompetitionV2Publication
from app.application.demand_v2_admission import DemandV2Publication
from app.application.domestic_market_validation_v2 import (
    DomesticMarketValidationV2SourceConflictError,
    ValidateDomesticMarketV2Command,
    ValidateDomesticMarketV2ForCapital,
)
from app.domain.market_intelligence.competition_v2 import (
    BOUNDED_COHORT_POLICY_VERSION,
    COMPETITION_V2_ASSESSMENT_VERSION,
    COMPETITION_V2_OBSERVATION_IDENTITY_VERSION,
    COMPETITION_V2_OBSERVATION_VERSION,
    COMPETITION_V2_POLICY_VERSION,
    CompetitionV2Availability,
    CompetitionV2ObservationIdentity,
    CompetitionV2ObservationIdentityKind,
    analyze_competition_v2,
    cohort_to_data,
)
from app.domain.market_intelligence.demand_v2 import (
    DEMAND_COMPARABLE_COHORT_VERSION,
    DEMAND_V2_ASSESSMENT_VERSION,
    DEMAND_V2_OBSERVATION_VERSION,
    DEMAND_V2_POLICY_VERSION,
    CompetitionCohortReference,
    DemandEvidenceOutcome,
    DemandFamilyStatus,
    DemandV2Availability,
    analyze_demand_v2,
)
from app.domain.market_intelligence.domestic_market_validation import (
    DomesticMarketValidationAssessment,
    DomesticMarketValidationSourceManifest,
    DomesticMarketValidationState,
    DomesticMarketVerification,
)
from app.domain.market_intelligence.domestic_market_validation_v2 import (
    DOMESTIC_MARKET_VALIDATION_V2_POLICY_NAME,
    DOMESTIC_MARKET_VALIDATION_V2_POLICY_VERSION,
    DomesticMarketValidationV2Assessment,
    DomesticMarketValidationV2ReasonCode,
    DomesticMarketValidationV2SourceManifest,
    DomesticMarketVerificationV2,
)
from app.domain.market_intelligence.identity import MarketObservationIdentity
from app.domain.opportunity import (
    NewToMarketDomesticSellingTargetIdentity,
    OpportunityDomesticSellingTargetBinding,
)
from test_competition_v2_foundation import card, cohort
from test_demand_v2_foundation import _intent, _observation, _review


SOURCE_TIME = datetime(2026, 8, 13, 12, tzinfo=timezone.utc)
VERIFIED_AT = datetime(2026, 8, 14, 3, tzinfo=timezone.utc)
EVALUATED_AT = VERIFIED_AT + timedelta(minutes=1)
TARGET = NewToMarketDomesticSellingTargetIdentity("dmv-v2-target-1")
COMPETITION_FINGERPRINT = "a" * 64
DEMAND_FINGERPRINT = "d" * 64


def _digest(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


def _competition_publication(
    availability: CompetitionV2Availability = (
        CompetitionV2Availability.COMPLETE_WITH_MARKETPLACE_SIGNAL
    ),
    *,
    subject=TARGET,
    observation_id="competition-observation-1",
    committed_at=SOURCE_TIME,
) -> tuple[CompetitionV2Publication, str]:
    if availability is CompetitionV2Availability.COMPLETE_WITH_MARKETPLACE_SIGNAL:
        cards = (card(1, item_id="item-1", labels=("판매자로켓",)),)
    elif availability is CompetitionV2Availability.COMPLETE_CORE_WITH_PARTIAL_MARKETPLACE_SIGNAL:
        cards = (
            card(1, item_id="item-1", labels=("판매자로켓",)),
            card(2, item_id="item-2", outcome="status_not_observed"),
        )
    elif availability is CompetitionV2Availability.COMPLETE_CORE_ONLY:
        cards = (card(1, item_id="item-1", outcome=None),)
    else:
        cards = (card(1, item_id="item-1", price=None, outcome=None),)
    source = cohort(cards=cards, subject=subject)
    fingerprint = _digest(cohort_to_data(source))
    assessment = analyze_competition_v2(source, generated_at=committed_at)
    assert assessment.availability is availability
    identity = CompetitionV2ObservationIdentity(
        observation_id,
        CompetitionV2ObservationIdentityKind.ISSUED,
        COMPETITION_V2_OBSERVATION_IDENTITY_VERSION,
    )
    return CompetitionV2Publication(
        "opportunity-1", source, assessment, committed_at, identity,
    ), fingerprint


def _demand_publication(
    *,
    market_intent_status: DemandFamilyStatus = DemandFamilyStatus.COMPLETE,
    comparable_status: DemandFamilyStatus = DemandFamilyStatus.COMPLETE,
    availability: DemandV2Availability | None = None,
    subject=TARGET,
    competition_reference: CompetitionCohortReference | None = None,
    committed_at=SOURCE_TIME,
) -> DemandV2Publication:
    intent = _intent()
    reviews = None
    if market_intent_status is DemandFamilyStatus.UNAVAILABLE:
        intent = _intent(None, DemandEvidenceOutcome.PROVIDER_UNAVAILABLE)
    if comparable_status is DemandFamilyStatus.PARTIAL:
        reviews = (
            _review("item-1", 10),
            _review("item-2", None, DemandEvidenceOutcome.EXTRACTION_FAILED),
        )
    elif comparable_status is DemandFamilyStatus.UNAVAILABLE:
        reviews = (
            _review("item-1", None, DemandEvidenceOutcome.EXTRACTION_FAILED),
            _review("item-2", None, DemandEvidenceOutcome.EXTRACTION_FAILED),
        )
    observation = _observation(intent=intent, reviews=reviews, subject=subject)
    if competition_reference is not None:
        manifest = replace(
            observation.comparable_cohort.manifest,
            source_competition_cohort=competition_reference,
        )
        observation = replace(
            observation,
            comparable_cohort=replace(observation.comparable_cohort, manifest=manifest),
        )
    assessment = analyze_demand_v2(
        observation, assessment_id="demand-assessment-1", generated_at=committed_at,
    )
    if market_intent_status is DemandFamilyStatus.PARTIAL:
        assessment = replace(
            assessment,
            market_intent_status=DemandFamilyStatus.PARTIAL,
            availability=DemandV2Availability.PARTIAL_CORE,
        )
    if availability is not None:
        assessment = replace(assessment, availability=availability)
    return DemandV2Publication(
        "opportunity-1", observation, assessment, committed_at, committed_at,
    )


def _competition_reference(
    publication: CompetitionV2Publication,
    fingerprint: str,
    **changes,
) -> CompetitionCohortReference:
    values = {
        "competition_observation_id": publication.observation_id,
        "observation_identity_kind": publication.observation_identity.identity_kind.value,
        "observation_identity_version": publication.observation_identity.identity_version,
        "cohort_id": publication.cohort.cohort_id,
        "authority_fingerprint": fingerprint,
        "observation_schema_version": publication.cohort.observation_schema_version,
        "cohort_policy_version": publication.cohort.cohort_policy_version,
        "artifact_reference": publication.cohort.artifact_reference,
        "artifact_sha256": publication.cohort.artifact_sha256,
    }
    values.update(changes)
    return CompetitionCohortReference(**values)


class Repository:
    def __init__(self, competition, demand, *, target_binding=None, competition_fingerprint=None):
        self.target_binding = target_binding or OpportunityDomesticSellingTargetBinding(
            "opportunity-1", "discovery-reference-1", TARGET, SOURCE_TIME,
        )
        self.competition = competition
        self.demand = demand
        self.competition_fingerprint = competition_fingerprint or _digest(
            cohort_to_data(competition.cohort)
        )

    def get_target_binding(self, opportunity_id):
        return self.target_binding if opportunity_id == "opportunity-1" else None

    def get_competition_publication(self, observation_id):
        return self.competition if observation_id == self.competition.observation_id else None

    def get_competition_authority_fingerprint(self, cohort_id):
        return self.competition_fingerprint if cohort_id == self.competition.cohort.cohort_id else None

    def get_demand_publication(self, observation_id):
        return self.demand if observation_id == self.demand.observation.observation_id else None

    def get_demand_authority_fingerprint(self, observation_id):
        return DEMAND_FINGERPRINT if observation_id == self.demand.observation.observation_id else None


def _service(repository, *, ids=None):
    ids = ids if ids is not None else []

    def issue_id():
        ids.append("called")
        return "dmv-v2-assessment-1"

    return ValidateDomesticMarketV2ForCapital(
        repository,
        assessment_id_generator=issue_id,
        evaluated_clock=lambda: EVALUATED_AT,
    )


def _command(service, *, current=True, reviewed_fingerprint=None):
    manifest = service.resolve_source_manifest(
        "opportunity-1", "competition-observation-1", "obs-1",
    )
    verification = DomesticMarketVerificationV2(
        operator_id="founder",
        verified_at=VERIFIED_AT,
        current_use_confirmed=current,
        reviewed_source_manifest_fingerprint=(
            reviewed_fingerprint or manifest.fingerprint
        ),
    )
    return ValidateDomesticMarketV2Command(
        command_id="dmv-v2-command-1",
        opportunity_id="opportunity-1",
        competition_observation_id="competition-observation-1",
        demand_observation_id="obs-1",
        verification=verification,
        requested_at=VERIFIED_AT,
    )


def _complete_service(competition_availability=CompetitionV2Availability.COMPLETE_WITH_MARKETPLACE_SIGNAL):
    competition, fingerprint = _competition_publication(competition_availability)
    demand = _demand_publication()
    return _service(Repository(competition, demand, competition_fingerprint=fingerprint))


def test_exact_complete_v2_authorities_validate_target_for_capital():
    service = _complete_service()
    assessment = service.execute(_command(service))

    assert assessment.state is DomesticMarketValidationState.VALIDATED_FOR_CAPITAL
    assert assessment.reason_codes == ()
    assert assessment.source_manifest.target_binding.target_identity is TARGET
    assert not isinstance(assessment.source_manifest.target_binding.target_identity, MarketObservationIdentity)
    assert not hasattr(assessment.source_manifest, "market_identity")


def test_command_cannot_declare_state_capital_buy_invest_or_subject():
    names = {field.name for field in fields(ValidateDomesticMarketV2Command)}
    forbidden = {
        "state", "capital_ready", "buy", "invest", "profit", "roi",
        "assessment_id", "target_identity", "market_identity",
    }
    assert names.isdisjoint(forbidden)
    assessment_names = {field.name for field in fields(DomesticMarketValidationV2Assessment)}
    assert assessment_names.isdisjoint({"profit", "roi", "margin", "buy", "invest"})
    with pytest.raises(TypeError):
        ValidateDomesticMarketV2Command(state="validated_for_capital")


def test_source_manifest_and_command_fingerprints_are_deterministic_and_separate():
    service = _complete_service()
    first = service.resolve_source_manifest(
        "opportunity-1", "competition-observation-1", "obs-1",
    )
    second = service.resolve_source_manifest(
        "opportunity-1", "competition-observation-1", "obs-1",
    )
    command = _command(service)

    assert first == second
    assert first.fingerprint == second.fingerprint
    assert command.fingerprint == command.fingerprint
    assert command.fingerprint != first.fingerprint


def test_verification_exact_match_succeeds_and_noncurrent_or_mismatch_blocks():
    service = _complete_service()
    assert service.execute(_command(service)).state is DomesticMarketValidationState.VALIDATED_FOR_CAPITAL

    noncurrent = service.execute(_command(service, current=False))
    mismatch = service.execute(_command(service, reviewed_fingerprint="f" * 64))

    assert noncurrent.state is DomesticMarketValidationState.BLOCKED
    assert DomesticMarketValidationV2ReasonCode.CURRENT_USE_VERIFICATION_MISSING in noncurrent.reason_codes
    assert mismatch.state is DomesticMarketValidationState.BLOCKED
    assert (
        DomesticMarketValidationV2ReasonCode.REVIEWED_SOURCE_MANIFEST_FINGERPRINT_MISMATCH
        in mismatch.reason_codes
    )


@pytest.mark.parametrize("availability", tuple(CompetitionV2Availability))
def test_competition_v2_uses_existing_availability_policy(availability):
    service = _complete_service(availability)
    assessment = service.execute(_command(service))

    if availability is CompetitionV2Availability.UNAVAILABLE:
        assert assessment.state is DomesticMarketValidationState.BLOCKED
        assert assessment.reason_codes == (
            DomesticMarketValidationV2ReasonCode.COMPETITION_V2_CORE_UNAVAILABLE,
        )
    else:
        assert assessment.state is DomesticMarketValidationState.VALIDATED_FOR_CAPITAL


@pytest.mark.parametrize(
    "market_status,comparable_status,expected_reason",
    (
        (DemandFamilyStatus.PARTIAL, DemandFamilyStatus.COMPLETE,
         DomesticMarketValidationV2ReasonCode.DEMAND_V2_MARKET_INTENT_INCOMPLETE),
        (DemandFamilyStatus.UNAVAILABLE, DemandFamilyStatus.COMPLETE,
         DomesticMarketValidationV2ReasonCode.DEMAND_V2_MARKET_INTENT_INCOMPLETE),
        (DemandFamilyStatus.COMPLETE, DemandFamilyStatus.PARTIAL,
         DomesticMarketValidationV2ReasonCode.DEMAND_V2_COMPARABLE_RESPONSE_INCOMPLETE),
        (DemandFamilyStatus.COMPLETE, DemandFamilyStatus.UNAVAILABLE,
         DomesticMarketValidationV2ReasonCode.DEMAND_V2_COMPARABLE_RESPONSE_INCOMPLETE),
    ),
)
def test_demand_v2_requires_both_existing_complete_families(
    market_status, comparable_status, expected_reason,
):
    competition, fingerprint = _competition_publication()
    demand = _demand_publication(
        market_intent_status=market_status,
        comparable_status=comparable_status,
    )
    service = _service(Repository(competition, demand, competition_fingerprint=fingerprint))
    assessment = service.execute(_command(service))

    assert assessment.state is DomesticMarketValidationState.BLOCKED
    assert expected_reason in assessment.reason_codes


@pytest.mark.parametrize(
    "availability",
    (DemandV2Availability.PARTIAL_CORE, DemandV2Availability.UNAVAILABLE),
)
def test_demand_v2_requires_existing_complete_core_availability(availability):
    competition, fingerprint = _competition_publication()
    demand = _demand_publication(availability=availability)
    service = _service(Repository(competition, demand, competition_fingerprint=fingerprint))

    assessment = service.execute(_command(service))

    assert assessment.state is DomesticMarketValidationState.BLOCKED
    assert DomesticMarketValidationV2ReasonCode.DEMAND_V2_CORE_INCOMPLETE in assessment.reason_codes


def test_exact_source_target_mismatch_is_conflict_before_assessment_identity():
    ids = []
    competition, fingerprint = _competition_publication(
        subject=NewToMarketDomesticSellingTargetIdentity("other-target")
    )
    demand = _demand_publication()
    service = _service(
        Repository(competition, demand, competition_fingerprint=fingerprint), ids=ids,
    )

    with pytest.raises(DomesticMarketValidationV2SourceConflictError):
        service.resolve_source_manifest(
            "opportunity-1", "competition-observation-1", "obs-1",
        )
    assert ids == []


def test_demand_competition_reference_must_match_selected_immutable_authority():
    ids = []
    competition, fingerprint = _competition_publication()
    reference = _competition_reference(
        competition, fingerprint, authority_fingerprint="b" * 64,
    )
    demand = _demand_publication(competition_reference=reference)
    service = _service(
        Repository(competition, demand, competition_fingerprint=fingerprint), ids=ids,
    )

    with pytest.raises(DomesticMarketValidationV2SourceConflictError):
        service.resolve_source_manifest(
            "opportunity-1", "competition-observation-1", "obs-1",
        )
    assert ids == []


def test_exact_demand_competition_reference_admits_the_selected_authority():
    competition, fingerprint = _competition_publication()
    demand = _demand_publication(
        competition_reference=_competition_reference(competition, fingerprint),
    )
    service = _service(
        Repository(competition, demand, competition_fingerprint=fingerprint),
    )

    assessment = service.execute(_command(service))

    assert assessment.state is DomesticMarketValidationState.VALIDATED_FOR_CAPITAL
    assert (
        assessment.source_manifest.demand.source_competition_cohort
        == _competition_reference(competition, fingerprint)
    )


def test_demand_owned_comparable_cohort_has_no_artificial_competition_equality():
    competition, fingerprint = _competition_publication()
    demand = _demand_publication()
    assert demand.observation.comparable_cohort.manifest.source_competition_cohort is None
    service = _service(Repository(competition, demand, competition_fingerprint=fingerprint))

    assert service.execute(_command(service)).state is DomesticMarketValidationState.VALIDATED_FOR_CAPITAL


def test_future_publication_time_is_durable_blocked_without_ttl():
    competition, fingerprint = _competition_publication(
        committed_at=VERIFIED_AT + timedelta(seconds=1)
    )
    demand = _demand_publication()
    service = _service(Repository(competition, demand, competition_fingerprint=fingerprint))

    assessment = service.execute(_command(service))

    assert assessment.state is DomesticMarketValidationState.BLOCKED
    assert DomesticMarketValidationV2ReasonCode.SOURCE_TIME_IN_FUTURE in assessment.reason_codes
    assert not hasattr(assessment, "fresh_until")
    assert not hasattr(assessment, "ttl")


def test_v2_emits_no_v1_compatibility_objects():
    service = _complete_service()
    command = _command(service)
    assessment = service.execute(command)

    assert isinstance(assessment, DomesticMarketValidationV2Assessment)
    assert isinstance(assessment.source_manifest, DomesticMarketValidationV2SourceManifest)
    assert isinstance(assessment.verification, DomesticMarketVerificationV2)
    assert not isinstance(assessment, DomesticMarketValidationAssessment)
    assert not isinstance(assessment.source_manifest, DomesticMarketValidationSourceManifest)
    assert not isinstance(assessment.verification, DomesticMarketVerification)
    assert command.policy_name == DOMESTIC_MARKET_VALIDATION_V2_POLICY_NAME
    assert command.policy_version == DOMESTIC_MARKET_VALIDATION_V2_POLICY_VERSION
    assert not hasattr(command, "opportunity_lifecycle_version")
    assert not hasattr(assessment.source_manifest, "target_digest")
