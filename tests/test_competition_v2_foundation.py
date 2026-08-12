from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.application.competition_v2_admission import (
    CompetitionV2AdmissionConflictError,
    FinalizeCompetitionV2Admission,
    FinalizeCompetitionV2AdmissionCommand,
)
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.domain.market_intelligence.competition_v2 import (
    CompetitionV2Availability,
    CompetitionV2Card,
    CompetitionV2Cohort,
    CoupangRocketLabelState,
    ResultPlacement,
    RocketObservationOutcome,
    analyze_competition_v2,
)
from app.domain.opportunity import NewToMarketDomesticSellingTargetIdentity
from app.infrastructure.market_observation.competition_v2_sqlite_repository import (
    CompetitionV2CorruptionError,
    SQLiteCompetitionV2Repository,
)
from app.web import app, get_competition_v2_admission_service


NOW = datetime(2026, 8, 12, 9, 0, tzinfo=timezone.utc)
HASH = "a" * 64


def target():
    return NewToMarketDomesticSellingTargetIdentity("target-v2-1")


def market_subject():
    return MarketObservationIdentity(
        MarketObservationScope.SEARCH_QUERY, "KR", "coupang", None, None,
        "seat organizer", None, None, "new", NOW, NOW,
    )


def card(ordinal, *, item_id=None, price="100", placement="organic", included=True,
         comparable=True, reason=None, labels=(), outcome="observed", seller=None,
         currency="KRW", unit="item", confidence="0.9", variants=1):
    if not included and reason is None:
        reason = "not_comparable"
    return CompetitionV2Card(
        result_ordinal=ordinal,
        placement=ResultPlacement(placement),
        included=included,
        is_comparable=comparable,
        exclusion_reason=reason,
        marketplace_item_id=item_id,
        raw_title="same title" if ordinal < 3 else "sponsored",
        displayed_price=None if price is None else Decimal(price),
        currency=currency,
        price_unit=unit,
        raw_rocket_labels=tuple(labels),
        delivery_promise_text="tomorrow arrival",
        rocket_outcome=None if outcome is None else RocketObservationOutcome(outcome),
        comparability_confidence=Decimal(confidence),
        price_confidence=Decimal(confidence),
        rocket_label_confidence=Decimal(confidence) if outcome == "observed" else None,
        visible_seller_text=seller,
        visible_variant_count=variants,
        badge_color="blue",
        badge_icon="rocket-icon",
    )


def cohort(*, cards=None, subject=None, cohort_id="cohort-1", market="KR", marketplace="coupang"):
    cards = cards or (
        card(1, item_id="item-1", price="100", labels=("판매자로켓",)),
        card(2, item_id="item-2", price="120", labels=("로켓배송", "로켓그로스")),
        card(3, item_id="ad-1", price="90", placement="sponsored", included=False,
             comparable=False, reason="sponsored", labels=("판매자로켓",)),
    )
    return CompetitionV2Cohort(
        cohort_id=cohort_id, subject=subject or target(), market=market,
        marketplace=marketplace, query="seat organizer", category="car accessories",
        product_use="seat-back storage", category_form_factor="organizer", condition="new",
        locale="ko-KR", result_surface="coupang-search", window_started_at=NOW,
        window_ended_at=NOW, artifact_reference="artifact:synthetic-capture",
        artifact_sha256=HASH, bound_start=1, bound_end=len(cards), operator_id="founder",
        cards=tuple(cards),
    )


def test_bounded_cohort_derives_core_and_preserves_sponsored_and_variants():
    value = cohort(cards=(
        card(1, item_id="item-1", price="100", seller="same", variants=4),
        card(2, item_id="item-2", price="120", seller="same"),
        card(3, item_id="ad", price="1", placement="sponsored", included=False,
             comparable=False, reason="sponsored"),
    ))
    assessment = analyze_competition_v2(value, generated_at=NOW)
    assert assessment.core_metrics.comparable_listing_count == 2
    assert assessment.core_metrics.median_price == Decimal("110")
    assert assessment.core_metrics.price_spread == Decimal("20")
    assert assessment.core_metrics.sponsored_listing_count == 1
    assert value.cards[0].visible_variant_count == 4
    assert len(value.included_cards) == 2


@pytest.mark.parametrize("bounds", ((0, 2), (3, 2)))
def test_finite_bounds_are_required_and_order_is_exact(bounds):
    with pytest.raises(ValueError, match="finite bounds"):
        replace(cohort(), bound_start=bounds[0], bound_end=bounds[1])
    with pytest.raises(ValueError, match="ordering"):
        replace(cohort(), cards=tuple(reversed(cohort().cards)))


def test_manifest_reconciles_bounds_and_preserves_noncomparable_and_fallback_reference():
    excluded = card(2, item_id=None, included=False, comparable=False, reason="wrong_form_factor")
    value = cohort(cards=(card(1, item_id=None), excluded))
    assert value.cards[1].exclusion_reason == "wrong_form_factor"
    assert value.listing_reference(value.cards[0]) == "artifact:synthetic-capture#result:1"
    with pytest.raises(ValueError, match="ordering"):
        replace(value, bound_end=3)


def test_duplicate_item_id_requires_later_explicit_exclusion_but_distinct_ids_and_titles_do_not_deduplicate():
    duplicate = card(2, item_id="item-1", included=False, comparable=True,
                     reason="duplicate_marketplace_item_id")
    value = cohort(cards=(card(1, item_id="item-1", seller="same"), duplicate,
                          card(3, item_id="item-2", seller="same")))
    assert len(value.included_cards) == 2
    with pytest.raises(ValueError, match="duplicate"):
        cohort(cards=(card(1, item_id="item-1"), card(2, item_id="item-1")))


@pytest.mark.parametrize("field", ("price", "currency", "unit"))
def test_missing_or_unresolved_included_price_fact_makes_core_unavailable(field):
    kwargs = {"price": "100", "currency": "KRW", "unit": "item"}
    kwargs[field] = None
    value = cohort(cards=(card(1, item_id="item-1", **kwargs),))
    assessment = analyze_competition_v2(value, generated_at=NOW)
    assert assessment.availability is CompetitionV2Availability.UNAVAILABLE
    assert assessment.core_metrics.comparable_listing_count == 1
    assert assessment.core_metrics.median_price is None


def test_zero_comparable_cards_is_unavailable_without_dropping_manifest():
    value = cohort(cards=(card(1, included=False, comparable=False, reason="not_comparable"),))
    assessment = analyze_competition_v2(value, generated_at=NOW)
    assert assessment.availability is CompetitionV2Availability.UNAVAILABLE
    assert assessment.core_metrics.comparable_listing_count == 0
    assert len(value.cards) == 1


def test_coupang_taxonomy_is_explicit_overlapping_and_ignores_context_only_signals():
    value = cohort(cards=(
        card(1, labels=("판매자로켓", "로켓배송", "로켓그로스", "새로운 로켓프로그램")),
        card(2, labels=(), outcome="observed"),
        card(3, labels=(), outcome="status_not_observed"),
        card(4, labels=(), outcome="semantics_unsupported"),
        card(5, labels=(), outcome="extraction_failed"),
    ))
    assessment = analyze_competition_v2(value, generated_at=NOW)
    signal = assessment.coupang_signal
    assert signal is not None
    assert signal.observable_listing_count == 2
    assert signal.explicit_label_counts[CoupangRocketLabelState.SELLER_ROCKET] == 1
    assert signal.explicit_label_counts[CoupangRocketLabelState.ROCKET_DELIVERY] == 1
    assert signal.explicit_label_counts[CoupangRocketLabelState.ROCKET_GROWTH] == 1
    assert signal.explicit_label_counts[CoupangRocketLabelState.OTHER_EXPLICIT_ROCKET_LABEL] == 1
    assert signal.no_explicit_rocket_label_count == 1
    assert signal.status_not_observed_count == signal.semantics_unsupported_count == signal.extraction_failed_count == 1
    assert assessment.availability is CompetitionV2Availability.COMPLETE_CORE_WITH_PARTIAL_MARKETPLACE_SIGNAL
    assert assessment.marketplace_signal_coverage == Decimal("0.4")
    assert assessment.marketplace_signal_confidence == Decimal("0.36")


def test_arrival_color_icon_and_delivery_promise_alone_are_observed_no_explicit_not_positive():
    assessment = analyze_competition_v2(cohort(cards=(card(1, labels=()),)), generated_at=NOW)
    signal = assessment.coupang_signal
    assert signal is not None
    assert signal.no_explicit_rocket_label_count == 1
    assert all(signal.explicit_label_counts[state] == 0 for state in signal.explicit_label_counts)
    assert assessment.availability is CompetitionV2Availability.COMPLETE_WITH_MARKETPLACE_SIGNAL


def test_optional_signal_and_separate_confidence_semantics():
    no_signal = cohort(cards=(card(1, outcome=None, confidence="0.7"), card(2, outcome=None, confidence="0.8")))
    assessment = analyze_competition_v2(no_signal, generated_at=NOW)
    assert assessment.availability is CompetitionV2Availability.COMPLETE_CORE_ONLY
    assert assessment.core_confidence == Decimal("0.7")
    assert assessment.marketplace_signal_coverage is None
    assert assessment.marketplace_signal_confidence is None
    assert not hasattr(assessment, "confidence")


def test_wrong_market_and_non_coupang_signal_fail_closed():
    with pytest.raises(ValueError, match="market"):
        cohort(market="US")
    with pytest.raises(ValueError, match="marketplace must match"):
        cohort(subject=market_subject(), marketplace="other")


class Opportunities:
    def __init__(self, subject): self.subject = subject
    def get(self, opportunity_id):
        return None if opportunity_id == "missing" else SimpleNamespace(is_archived=opportunity_id == "archived")
    def get_market_identity_binding(self, _):
        return SimpleNamespace(market_observation_identity=self.subject) if isinstance(self.subject, MarketObservationIdentity) else None
    def get_target_binding(self, _):
        return SimpleNamespace(target_identity=self.subject) if isinstance(self.subject, NewToMarketDomesticSellingTargetIdentity) else None


def command(value, command_id="command-1"):
    return FinalizeCompetitionV2AdmissionCommand("opp-1", command_id, "founder", NOW, value)


@pytest.mark.parametrize("subject", (target(), market_subject()))
def test_application_and_sqlite_support_both_subjects_replay_alias_restart_and_append_only(tmp_path, subject):
    path = tmp_path / "v2.sqlite"
    repository = SQLiteCompetitionV2Repository(path)
    service = FinalizeCompetitionV2Admission(Opportunities(subject), repository, clock=lambda: NOW)
    value = cohort(subject=subject)
    first = service.execute(command(value))
    replay = service.execute(command(value))
    alias = service.execute(command(value, "command-2"))
    assert not first.replayed and replay.replayed and alias.aliased
    with pytest.raises(CompetitionV2AdmissionConflictError):
        service.execute(command(replace(value, query="changed")))
    with pytest.raises(Exception, match="append-only"):
        repository._connection.execute("UPDATE competition_v2_cohorts SET cohort_id=cohort_id")
    repository._connection.rollback(); repository.close()
    restarted = SQLiteCompetitionV2Repository(path)
    assert restarted.get_publication(value.cohort_id) == first.publication
    restarted.close()


def test_current_v2_schema_repository_construction_is_byte_stable(tmp_path):
    path = tmp_path / "stable.sqlite"
    repository = SQLiteCompetitionV2Repository(path); repository.close()
    before = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size, path.stat().st_mtime_ns)
    repository = SQLiteCompetitionV2Repository(path); repository.close()
    after = (hashlib.sha256(path.read_bytes()).hexdigest(), path.stat().st_size, path.stat().st_mtime_ns)
    assert after == before
    assert not any((tmp_path / f"stable.sqlite{suffix}").exists() for suffix in ("-wal", "-shm", "-journal"))


def test_corrupted_derived_assessment_fails_closed(tmp_path):
    path = tmp_path / "corrupt.sqlite"
    repository = SQLiteCompetitionV2Repository(path)
    service = FinalizeCompetitionV2Admission(Opportunities(target()), repository, clock=lambda: NOW)
    service.execute(command(cohort()))
    repository._connection.execute("DROP TRIGGER trg_competition_v2_cohorts_no_update")
    row = repository._connection.execute("SELECT assessment_json FROM competition_v2_cohorts").fetchone()
    data = json.loads(row["assessment_json"]); data["core_metrics"]["comparable_listing_count"] = 999
    repository._connection.execute("UPDATE competition_v2_cohorts SET assessment_json=?", (json.dumps(data),))
    repository._connection.commit()
    with pytest.raises(CompetitionV2CorruptionError, match="reconcile"):
        repository.get_publication("cohort-1")
    repository.close()


def api_body(command_id="api-command-1"):
    return {"contract_version": "2.0.0", "command_id": command_id, "operator_id": "founder",
        "submitted_at": NOW.isoformat(), "subject": {"kind": "new_to_market_domestic_selling_target",
        "domestic_selling_target_id": "target-v2-1"}, "cohort": {"cohort_id": "api-cohort-1", "market": "KR",
        "marketplace": "coupang", "query": "seat organizer", "category": "car accessories",
        "product_use": "seat-back storage", "category_form_factor": "organizer", "condition": "new",
        "locale": "ko-KR", "result_surface": "coupang-search", "window_started_at": NOW.isoformat(),
        "window_ended_at": NOW.isoformat(), "artifact_reference": "artifact:synthetic", "artifact_sha256": HASH,
        "bound_start": 1, "bound_end": 2, "cards": [
            {"result_ordinal": 1, "placement": "organic", "included": True, "is_comparable": True,
             "raw_title": "one", "marketplace_item_id": "item-1", "displayed_price": "100",
             "currency": "KRW", "price_unit": "item", "raw_rocket_labels": ["판매자로켓"],
             "rocket_outcome": "observed", "rocket_label_confidence": "0.9"},
            {"result_ordinal": 2, "placement": "organic", "included": True, "is_comparable": True,
             "raw_title": "two", "displayed_price": "120", "currency": "KRW", "price_unit": "item",
             "raw_rocket_labels": [], "rocket_outcome": "observed", "rocket_label_confidence": "0.8"}]}}


def test_api_v2_target_admission_replay_conflict_and_server_derived_response(tmp_path):
    repository = SQLiteCompetitionV2Repository(tmp_path / "api.sqlite")
    service = FinalizeCompetitionV2Admission(Opportunities(target()), repository, clock=lambda: NOW)
    app.dependency_overrides[get_competition_v2_admission_service] = lambda: service
    client = TestClient(app)
    route = "/api/v2/opportunities/opp-1/competition-observations"
    try:
        first = client.post(route, json=api_body())
        replay = client.post(route, json=api_body())
        changed = api_body(); changed["cohort"]["cards"][0]["displayed_price"] = "101"
        conflict = client.post(route, json=changed)
        forbidden = api_body("forbidden"); forbidden["cohort"]["comparable_listing_count"] = 2
        invalid = client.post(route, json=forbidden)
        assert first.status_code == 201, first.text
        assert replay.status_code == 200
        assert replay.json()["cohort"] == first.json()["cohort"]
        assert replay.json()["assessment"] == first.json()["assessment"]
        assert replay.json()["receipt"]["state"] == "replayed"
        assert conflict.status_code == 409
        assert invalid.status_code == 422
        data = first.json()
        assert data["core_metrics"]["comparable_listing_count"] == 2
        assert data["core_metrics"]["median_price"] == "110"
        assert data["core_metrics"]["price_spread"] == "20"
        assert data["artifact"]["sha256"] == HASH
        assert "rocket_competition" not in data["assessment"]
        assert "market_concentration" not in data["assessment"]
    finally:
        app.dependency_overrides.clear(); repository.close()


def test_openapi_has_distinct_v2_contract_without_caller_derived_or_seller_fields():
    document = app.openapi()
    assert "/api/v1/opportunities/{opportunity_id}/competition-observations" in document["paths"]
    assert "/api/v2/opportunities/{opportunity_id}/competition-observations" in document["paths"]
    schemas = document["components"]["schemas"]
    assert "CompetitionV2AdmissionResponse" in schemas
    for name in ("CompetitionV2CohortRequest", "CompetitionV2CardRequest"):
        properties = schemas[name]["properties"]
        for forbidden in ("rocket_seller_count", "competitor_count", "comparable_listing_count",
                          "median_price", "price_spread", "seller_id", "seller_identity"):
            assert forbidden not in properties
