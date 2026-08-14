from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import sqlite3
from types import SimpleNamespace

import pytest

import app.application.demand_v2_admission as admission_module
from app.application.demand_v2_admission import (
    DemandV2AdmissionConflictError, DemandV2Submission, FinalizeDemandV2Admission,
    FinalizeDemandV2AdmissionCommand,
)
from app.domain.market_intelligence.demand_v2 import (
    CompetitionCohortReference, DemandArtifactReference, DemandComparableCard, DemandComparableCohort,
    DemandComparableCohortManifest, DemandEvidenceOutcome, DemandResultPlacement,
    DemandV2Availability, DemandV2Conclusion, DemandV2Observation,
    ListingRatingEvidence, ListingReviewEvidence, MarketIntentEvidence,
    ProviderFieldKind, QueryMatchSemantics, analyze_demand_v2,
    market_intent_to_data,
)
from app.domain.opportunity.new_to_market_domestic_selling import NewToMarketDomesticSellingTargetIdentity
from app.infrastructure.market_observation.demand_v2_sqlite_repository import (
    DemandV2PersistenceError, SQLiteDemandV2Repository,
)
from app.web import (
    DemandV2CompetitionCohortReferenceRequest, DemandV2MarketIntentRequest,
    DemandV2ProviderSignalRequest, DemandV2RatingEvidenceRequest,
    DemandV2ReviewEvidenceRequest, _demand_v2_cohort, _demand_v2_market_intent,
    _demand_v2_payload, _demand_v2_provider_signal, _demand_v2_rating,
    _demand_v2_review, app,
)


NOW = datetime(2026, 8, 13, 6, tzinfo=timezone.utc)
EARLIER = datetime(2026, 8, 12, 6, tzinfo=timezone.utc)
SHA = "a" * 64


def _subject(): return NewToMarketDomesticSellingTargetIdentity("target-demand-v2")
def _artifact(name="evidence.json"): return DemandArtifactReference(name, SHA)


def _intent(value=120, outcome=DemandEvidenceOutcome.OBSERVED_VALUE, confidence="0.9", reason=None):
    if value is None and reason is None:
        reason = "provider fact was not available"
    return MarketIntentEvidence(
        provider="provider-a", provider_field_name="monthly_query_count",
        provider_schema_version="provider-a-v1", provider_field_kind=ProviderFieldKind.QUERY_COUNT,
        query="portable blender", market="KR", geography="KR", locale="ko-KR",
        match_semantics=QueryMatchSemantics.EXACT, period_started_at=EARLIER,
        period_ended_at=NOW, unit="queries", value=value, source="provider-export",
        reference="provider://query/portable-blender", artifact=_artifact("intent.json"),
        collection_method="founder-assisted-export", observed_at=NOW, outcome=outcome,
        confidence=Decimal(confidence), reason=reason)


def test_naver_market_intent_preserves_returned_query_and_provider_period_label():
    intent = _naver_intent()

    assert intent.query == "차량용 시트백 수납함"
    assert intent.provider_returned_query == "차량용시트백수납함"
    assert intent.provider_period_label == "최근 한 달"
    assert intent.period_started_at is intent.period_ended_at is None


def _naver_intent(*, returned_query="차량용시트백수납함", period_label="최근 한 달"):
    return MarketIntentEvidence(
        provider="NAVER Search Ads Keyword Tool", provider_field_name="월간검색수",
        provider_schema_version="unknown", provider_field_kind=ProviderFieldKind.QUERY_COUNT,
        query="차량용 시트백 수납함", market="KR", geography="KR", locale="ko-KR",
        match_semantics=QueryMatchSemantics.PROVIDER_SPECIFIC,
        period_started_at=None, period_ended_at=None, unit="searches", value=30,
        source="NAVER Search Ads Keyword Tool web UI", reference="naver-evidence.zip#result",
        artifact=_artifact("naver-evidence.zip"), collection_method="founder-assisted-capture",
        observed_at=NOW, outcome=DemandEvidenceOutcome.OBSERVED_VALUE,
        confidence=Decimal("1"), provider_returned_query=returned_query,
        provider_period_label=period_label, device_scope="모바일",
        result_surface="NAVER 통합검색",
    )


def test_market_intent_period_authority_variants_fail_closed():
    assert _intent().period_started_at == EARLIER
    with pytest.raises(ValueError, match="exactly one provider period"):
        replace(_intent(), period_started_at=None, period_ended_at=None)
    with pytest.raises(ValueError, match="both start and end"):
        replace(_intent(), period_ended_at=None)
    with pytest.raises(ValueError, match="exactly one provider period"):
        replace(_intent(), provider_period_label="recent month")
    with pytest.raises(ValueError, match="non-empty text"):
        replace(_intent(), period_started_at=None, period_ended_at=None,
            provider_period_label="   ")
    with pytest.raises(ValueError, match="non-empty text"):
        replace(_intent(), provider_returned_query="   ")


def test_market_intent_serialization_preserves_historical_exact_shape():
    historical = market_intent_to_data(_intent())
    assert historical["period_started_at"] == EARLIER.isoformat()
    assert historical["period_ended_at"] == NOW.isoformat()
    assert "provider_returned_query" not in historical
    assert "provider_period_label" not in historical
    naver = market_intent_to_data(_naver_intent())
    assert "period_started_at" not in naver and "period_ended_at" not in naver
    assert naver["provider_returned_query"] == "차량용시트백수납함"
    assert naver["provider_period_label"] == "최근 한 달"


def _manifest(subject=None):
    subject = subject or _subject()
    return DemandComparableCohortManifest(
        subject=subject, market="KR", marketplace="coupang", query="portable blender",
        category="kitchen", product_use="portable blending", category_form_factor="blender",
        condition="new", locale="ko-KR", result_surface="organic-search",
        window_started_at=EARLIER, window_ended_at=NOW, artifact=_artifact("cohort.json"),
        bound_start=1, bound_end=3, operator_id="founder",
        cards=(
            DemandComparableCard(1, DemandResultPlacement.ORGANIC, True, True, None, "item-1", "item-1", "one", 1),
            DemandComparableCard(2, DemandResultPlacement.ORGANIC, True, True, None, "item-2", "item-2", "two", 1),
            DemandComparableCard(3, DemandResultPlacement.SPONSORED, False, False, "sponsored", "item-3", "item-3", "three", 1)))


def _review(reference, count, outcome=DemandEvidenceOutcome.OBSERVED_VALUE, confidence="0.8"):
    reason = None if count is not None else "review region extraction failed"
    return ListingReviewEvidence(
        result_ordinal=int(reference.rsplit("-", 1)[1]), listing_reference=reference,
        value=count, outcome=outcome, confidence=Decimal(confidence), source="coupang",
        reference=f"coupang://{reference}", artifact=_artifact(f"{reference}.json"),
        collection_method="founder-assisted-capture", observed_at=NOW, reason=reason)


def _observation(intent=None, reviews=None, subject=None):
    subject = subject or _subject()
    return DemandV2Observation(
        "obs-1", subject, intent or _intent(), DemandComparableCohort("cohort-1", _manifest(subject)),
        tuple(reviews or (_review("item-1", 10), _review("item-2", 20))), (), (),
        DemandEvidenceOutcome.TARGET_LISTING_ABSENT, NOW)


@pytest.mark.parametrize("outcome", [DemandEvidenceOutcome.NOT_OBSERVED,
    DemandEvidenceOutcome.SEMANTICS_UNSUPPORTED, DemandEvidenceOutcome.EXTRACTION_FAILED,
    DemandEvidenceOutcome.PROVIDER_UNAVAILABLE])
def test_market_intent_non_observed_outcomes_do_not_accept_values(outcome):
    with pytest.raises(ValueError): _intent(1, outcome)
    assert _intent(None, outcome).value is None


def test_observed_zero_is_a_fact_not_missing_evidence():
    assessment = analyze_demand_v2(_observation(intent=_intent(0, DemandEvidenceOutcome.OBSERVED_ZERO)),
        assessment_id="assess-zero", generated_at=NOW)
    assert assessment.market_intent_status.value == "complete"
    assert assessment.availability is DemandV2Availability.COMPLETE_CORE
    assert assessment.conclusion is DemandV2Conclusion.DOES_NOT_SUPPORT_DEEPER_COMMERCIAL_VALIDATION


def test_review_aggregates_are_robust_and_keep_family_confidence_separate():
    assessment = analyze_demand_v2(_observation(reviews=(
        _review("item-1", 0, DemandEvidenceOutcome.OBSERVED_ZERO, "0.9"),
        _review("item-2", 20, confidence="0.8"))), assessment_id="assess-1", generated_at=NOW)
    aggregates = assessment.review_aggregates
    assert aggregates.review_counts_sorted == (0, 20)
    assert aggregates.median_review_count == Decimal("10")
    assert aggregates.engaged_listing_count == 1
    assert aggregates.engaged_listing_share == Decimal("0.5")
    assert not hasattr(aggregates, "total_review_count")
    assert not hasattr(aggregates, "mean_review_count")
    assert assessment.comparable_response_confidence == Decimal("0.8")
    assert not hasattr(assessment, "overall_confidence")


def test_partial_review_coverage_is_partial_core_and_inconclusive():
    assessment = analyze_demand_v2(_observation(reviews=(
        _review("item-1", 10), _review("item-2", None, DemandEvidenceOutcome.EXTRACTION_FAILED))),
        assessment_id="assess-partial", generated_at=NOW)
    assert assessment.availability is DemandV2Availability.PARTIAL_CORE
    assert assessment.conclusion is DemandV2Conclusion.INCONCLUSIVE
    assert assessment.review_aggregates.review_coverage == Decimal("0.5")
    assert assessment.comparable_response_confidence == Decimal("0.4")


def test_complete_positive_families_support_deeper_validation():
    assessment = analyze_demand_v2(_observation(), assessment_id="assess-positive", generated_at=NOW)
    assert assessment.availability is DemandV2Availability.COMPLETE_CORE
    assert assessment.conclusion is DemandV2Conclusion.SUPPORTS_DEEPER_COMMERCIAL_VALIDATION


def test_review_evidence_must_cover_exact_included_listing_set():
    with pytest.raises(ValueError):
        _observation(reviews=(_review("item-1", 1), _review("foreign-item", 2)))


def test_rating_aggregate_excludes_incompatible_scales():
    base = _observation()
    observation = DemandV2Observation(base.observation_id, base.subject, base.market_intent,
        base.comparable_cohort, base.reviews, (
            ListingRatingEvidence(1, "item-1", Decimal("4.0"), Decimal("0"), Decimal("5"),
                DemandEvidenceOutcome.OBSERVED_VALUE, Decimal("1"), "coupang", "r1", _artifact(),
                "founder-assisted-capture", NOW),
            ListingRatingEvidence(2, "item-2", Decimal("4.5"), Decimal("0"), Decimal("10"),
                DemandEvidenceOutcome.OBSERVED_VALUE, Decimal("1"), "coupang", "r2", _artifact(),
                "founder-assisted-capture", NOW)),
        (), DemandEvidenceOutcome.TARGET_LISTING_ABSENT, NOW)
    assessment = analyze_demand_v2(observation, assessment_id="assess-rating", generated_at=NOW)
    assert assessment.rating_aggregates is None
    assert "RATING_SCALE_INCOMPATIBLE" in assessment.reasons


def test_non_value_evidence_requires_explicit_reason():
    with pytest.raises(ValueError):
        _intent(None, DemandEvidenceOutcome.NOT_OBSERVED, reason="")


def test_api_translation_uses_domain_constructor_contracts():
    artifact = {"reference": "capture.json", "sha256": SHA}
    intent = _demand_v2_market_intent(DemandV2MarketIntentRequest(
        provider_name="provider-a", provider_field_name="monthly_query_count",
        provider_field_schema_version="provider-a-v1", provider_field_kind="query_count",
        query="portable blender", market="KR", geography="KR", locale="ko-KR",
        query_match_semantics="exact", period_started_at=EARLIER, period_ended_at=NOW,
        value_unit="queries", value=10, source="provider-export", reference="provider://query",
        artifact=artifact, collection_method="founder-assisted-export", observed_at=NOW,
        outcome="observed_value"))
    review = _demand_v2_review(DemandV2ReviewEvidenceRequest(
        result_ordinal=1, listing_reference="item-1", review_count=10, source="coupang",
        reference="coupang://item-1", artifact=artifact,
        collection_method="founder-assisted-capture", observed_at=NOW,
        outcome="observed_value"))
    rating = _demand_v2_rating(DemandV2RatingEvidenceRequest(
        result_ordinal=1, listing_reference="item-1", rating_value="4.5", rating_scale="5",
        source="coupang", reference="coupang://item-1/rating", artifact=artifact,
        collection_method="founder-assisted-capture", observed_at=NOW,
        outcome="observed_value"))
    signal = _demand_v2_provider_signal(DemandV2ProviderSignalRequest(
        signal_name="provider_rank", provider="provider-a", provider_field_name="rank",
        provider_schema_version="provider-a-v1", population="keyword results",
        result_surface="organic-search", query="portable blender", geography="KR",
        locale="ko-KR", period_started_at=EARLIER, period_ended_at=NOW,
        directionality="lower_is_better", tie_semantics="provider_defined", value="3", unit="rank",
        source="provider-export", reference="provider://rank", artifact=artifact,
        collection_method="founder-assisted-export", observed_at=NOW,
        outcome="observed_value"))
    reference = _demand_v2_cohort(DemandV2CompetitionCohortReferenceRequest(
        competition_observation_id="competition-observation-1", observation_identity_kind="issued",
        observation_identity_version="competition-observation-identity-v1",
        cohort_id="competition-cohort-1", authority_fingerprint=SHA,
        observation_schema_version="competition-observation-v2",
        cohort_policy_version="bounded-comparable-cohort-v1", artifact=artifact), _subject(), "founder")
    assert (intent.provider, intent.provider_schema_version, intent.match_semantics.value, intent.unit) == (
        "provider-a", "provider-a-v1", "exact", "queries")
    assert (review.result_ordinal, review.value) == (1, 10)
    assert (rating.result_ordinal, rating.scale_min, rating.scale_max) == (1, Decimal("0"), Decimal("5"))
    assert not hasattr(rating, "review_count")
    assert (signal.provider, signal.provider_field_name, signal.query) == ("provider-a", "rank", "portable blender")
    assert (reference.competition_observation_id, reference.cohort_id) == (
        "competition-observation-1", "competition-cohort-1")


def test_api_translation_preserves_provider_query_and_period_label_exactly():
    artifact = {"reference": "naver-evidence.zip", "sha256": SHA}
    request = DemandV2MarketIntentRequest(
        provider_name="NAVER Search Ads Keyword Tool", provider_field_name="월간검색수",
        provider_field_schema_version="unknown", provider_field_kind="query_count",
        query="차량용 시트백 수납함", provider_returned_query="차량용시트백수납함",
        market="KR", geography="KR", locale="ko-KR",
        query_match_semantics="provider_specific", provider_period_label="최근 한 달",
        value_unit="searches", value=30, source="NAVER Search Ads Keyword Tool web UI",
        reference="naver-evidence.zip#result", artifact=artifact,
        collection_method="founder-assisted-capture", observed_at=NOW,
        outcome="observed_value", device_scope="모바일",
        result_surface="NAVER 통합검색",
    )

    intent = _demand_v2_market_intent(request)

    assert intent.query == "차량용 시트백 수납함"
    assert intent.provider_returned_query == "차량용시트백수납함"
    assert intent.provider_period_label == "최근 한 달"
    assert intent.device_scope == "모바일"
    assert intent.result_surface == "NAVER 통합검색"
    assert intent.period_started_at is intent.period_ended_at is None


@pytest.mark.parametrize("period", [
    {},
    {"period_started_at": EARLIER},
    {"period_ended_at": NOW},
    {"period_started_at": EARLIER, "period_ended_at": NOW,
     "provider_period_label": "recent month"},
    {"provider_period_label": "   "},
])
def test_api_period_authority_variants_fail_closed(period):
    payload = {
        "provider_name": "provider-a", "provider_field_name": "monthly_query_count",
        "provider_field_schema_version": "provider-a-v1", "provider_field_kind": "query_count",
        "query": "portable blender", "market": "KR", "geography": "KR", "locale": "ko-KR",
        "query_match_semantics": "exact", "value_unit": "queries", "value": 10,
        "source": "provider-export", "reference": "provider://query",
        "artifact": {"reference": "capture.json", "sha256": SHA},
        "collection_method": "founder-assisted-export", "observed_at": NOW,
        "outcome": "observed_value", **period,
    }
    with pytest.raises(ValueError):
        DemandV2MarketIntentRequest(**payload)


@pytest.mark.parametrize("kind,version", [
    ("issued", "competition-observation-identity-v1"),
    ("legacy_compatibility", "competition-observation-legacy-compatibility-v1"),
])
def test_competition_reference_resolves_exact_observation_cohort_pair(kind, version):
    manifest = _manifest(); identity = SimpleNamespace(
        observation_id="competition-observation-1", identity_kind=SimpleNamespace(value=kind),
        identity_version=version)
    cohort = SimpleNamespace(**{
        **{name: getattr(manifest, name) for name in (
            "subject", "market", "marketplace", "query", "category", "product_use",
            "category_form_factor", "condition", "locale", "result_surface",
            "window_started_at", "window_ended_at", "bound_start", "bound_end", "operator_id", "cards")},
        "cohort_id": "competition-cohort-1", "observation_schema_version": "competition-observation-v2",
        "cohort_policy_version": "bounded-comparable-cohort-v1", "artifact_reference": "competition.json",
        "artifact_sha256": SHA, "listing_reference": lambda card: card.observation_reference,
    })
    publication = SimpleNamespace(cohort=cohort, observation_identity=identity)
    repository = SimpleNamespace(
        get_publication_by_observation_id=lambda value: publication if value == identity.observation_id else None,
        get_publication=lambda value: publication if value == cohort.cohort_id else None,
        get_authority_fingerprint=lambda value: SHA if value == cohort.cohort_id else None)
    reference = CompetitionCohortReference(
        identity.observation_id, kind, version, cohort.cohort_id, SHA,
        cohort.observation_schema_version, cohort.cohort_policy_version,
        cohort.artifact_reference, cohort.artifact_sha256)
    resolved = FinalizeDemandV2Admission(object(), _MemoryRepository(), repository)._resolve_manifest(
        reference, manifest.subject)
    assert resolved.source_competition_cohort == reference


def test_competition_reference_rejects_observation_cohort_pair_mismatch():
    reference = CompetitionCohortReference(
        "missing-observation", "issued", "competition-observation-identity-v1",
        "missing-cohort", SHA, "competition-observation-v2", "bounded-comparable-cohort-v1",
        "competition.json", SHA)
    repository = SimpleNamespace(
        get_publication_by_observation_id=lambda value: None,
        get_publication=lambda value: None,
        get_authority_fingerprint=lambda value: None)
    with pytest.raises(DemandV2AdmissionConflictError):
        FinalizeDemandV2Admission(object(), _MemoryRepository(), repository)._resolve_manifest(
            reference, _subject())


class _MemoryRepository:
    def __init__(self): self.receipts, self.publications, self.authorities = {}, {}, {}
    def get_receipt(self, command_id): return self.receipts.get(command_id)
    def get_publication(self, observation_id): return self.publications.get(observation_id)
    def get_publication_by_authority_fingerprint(self, fingerprint): return self.authorities.get(fingerprint)
    def save_alias_receipt(self, command_id, fingerprint, authority, observation_id, opportunity_id, operator_id, committed_at):
        self.receipts[command_id] = {"command_fingerprint": fingerprint, "observation_id": observation_id}
    def finalize(self, publication, command_id, fingerprint, authority, authority_data, operator_id):
        self.publications[publication.observation.observation_id] = publication
        self.authorities[authority] = publication
        self.receipts[command_id] = {"command_fingerprint": fingerprint,
            "observation_id": publication.observation.observation_id}


def _command(command_id="command-1", subject=None, intent=None):
    subject = subject or _subject()
    intent = intent or _intent()
    return FinalizeDemandV2AdmissionCommand("opp-1", command_id, "founder", NOW,
        DemandV2Submission(subject, intent, replace(_manifest(subject), query=intent.query),
            (_review("item-1", 10), _review("item-2", 20))))


def test_admission_owns_ids_timestamps_replay_and_alias(monkeypatch):
    subject = _subject()
    eligibility = SimpleNamespace(market_binding=None, target_binding=SimpleNamespace(target_identity=subject))
    monkeypatch.setattr(admission_module, "get_operational_opportunity_eligibility", lambda repo, opportunity_id: eligibility)
    repository = _MemoryRepository(); generated_calls = []
    service = FinalizeDemandV2Admission(object(), repository,
        observation_id_generator=lambda: "server-observation", cohort_id_generator=lambda: "server-cohort",
        assessment_id_generator=lambda: "server-assessment",
        generated_clock=lambda: generated_calls.append(1) or NOW, committed_clock=lambda: NOW)
    first = service.execute(_command(subject=subject)); replay = service.execute(_command(subject=subject))
    alias = service.execute(_command("command-2", subject))
    assert first.publication.observation.observation_id == "server-observation"
    assert first.publication.assessment.assessment_id == "server-assessment"
    assert replay.replayed is True and alias.aliased is True and len(generated_calls) == 1


def test_admission_rejects_wrong_operational_subject(monkeypatch):
    eligibility = SimpleNamespace(market_binding=None,
        target_binding=SimpleNamespace(target_identity=NewToMarketDomesticSellingTargetIdentity("other")))
    monkeypatch.setattr(admission_module, "get_operational_opportunity_eligibility", lambda repo, opportunity_id: eligibility)
    with pytest.raises(DemandV2AdmissionConflictError): FinalizeDemandV2Admission(object(), _MemoryRepository()).execute(_command())


def test_sqlite_round_trip_restart_current_and_corruption_detection(tmp_path, monkeypatch):
    subject = _subject()
    eligibility = SimpleNamespace(market_binding=None, target_binding=SimpleNamespace(target_identity=subject))
    monkeypatch.setattr(admission_module, "get_operational_opportunity_eligibility", lambda repo, opportunity_id: eligibility)
    path = tmp_path / "demand.sqlite3"; repository = SQLiteDemandV2Repository(path)
    result = FinalizeDemandV2Admission(object(), repository,
        observation_id_generator=lambda: "persisted-observation", cohort_id_generator=lambda: "persisted-cohort",
        assessment_id_generator=lambda: "persisted-assessment", generated_clock=lambda: NOW,
        committed_clock=lambda: NOW).execute(_command())
    assert repository.get_current_publication(subject) == result.publication
    repository.close(); reopened = SQLiteDemandV2Repository(path)
    assert reopened.get_publication("persisted-observation") == result.publication
    reopened.close(); connection = sqlite3.connect(path)
    connection.execute("DROP TRIGGER trg_demand_v2_publications_no_update")
    connection.execute("UPDATE demand_v2_publications SET assessment_json='{}'")
    connection.commit(); connection.close()
    with pytest.raises(DemandV2PersistenceError):
        SQLiteDemandV2Repository(path)


def test_provider_handoff_round_trip_replay_conflict_and_read_purity(tmp_path, monkeypatch):
    subject = _subject()
    eligibility = SimpleNamespace(market_binding=None, target_binding=SimpleNamespace(target_identity=subject))
    monkeypatch.setattr(admission_module, "get_operational_opportunity_eligibility", lambda repo, opportunity_id: eligibility)
    path = tmp_path / "provider-semantics.sqlite3"
    repository = SQLiteDemandV2Repository(path)
    service = FinalizeDemandV2Admission(
        object(), repository, observation_id_generator=lambda: "provider-observation",
        cohort_id_generator=lambda: "provider-cohort", assessment_id_generator=lambda: "provider-assessment",
        generated_clock=lambda: NOW, committed_clock=lambda: NOW,
    )
    command = _command(intent=_naver_intent())
    result = service.execute(command)
    assert result.publication.observation.market_intent.provider_returned_query == "차량용시트백수납함"
    assert result.publication.observation.market_intent.provider_period_label == "최근 한 달"
    response = _demand_v2_payload(result)["market_intent"]
    assert response["query"] == "차량용 시트백 수납함"
    assert response["provider_returned_query"] == "차량용시트백수납함"
    assert response["provider_period_label"] == "최근 한 달"
    repository.close()

    persisted_bytes = path.read_bytes()
    reopened = SQLiteDemandV2Repository(path)
    reconstructed = reopened.get_publication("provider-observation")
    assert reconstructed.observation.market_intent == _naver_intent()
    replay_service = FinalizeDemandV2Admission(object(), reopened)
    assert replay_service.execute(command).replayed is True
    with pytest.raises(DemandV2AdmissionConflictError):
        replay_service.execute(_command(intent=_naver_intent(returned_query="changed")))
    with pytest.raises(DemandV2AdmissionConflictError):
        replay_service.execute(_command(intent=_naver_intent(period_label="previous month")))
    reopened.close()
    assert path.read_bytes() == persisted_bytes


def test_sqlite_rejects_partial_schema(tmp_path):
    path = tmp_path / "partial.sqlite3"; connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE demand_v2_receipts (wrong TEXT)")
    connection.commit(); connection.close()
    with pytest.raises(DemandV2PersistenceError): SQLiteDemandV2Repository(path)


def test_openapi_exposes_exact_demand_v2_route():
    schema = app.openapi(); path = "/api/v2/opportunities/{opportunity_id}/demand-observations"
    assert path in schema["paths"] and "post" in schema["paths"][path]
    intent_schema = schema["components"]["schemas"]["DemandV2MarketIntentRequest"]
    assert "provider_returned_query" in intent_schema["properties"]
    assert "provider_period_label" in intent_schema["properties"]
    assert len(intent_schema["oneOf"]) == 2
