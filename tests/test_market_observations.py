from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.domain.market_intelligence import (
    CompetitionObservation,
    DemandObservation,
    ExternalMarketSignal,
    ExternalSignalDirection,
    ExternalSignalSourceType,
    MarketEvidence,
    MarketEvidenceStatus,
    MarketObservationIdentity,
    MarketObservationScope,
)


NOW = datetime(2026, 8, 6, 9, tzinfo=timezone.utc)


def identity(**overrides) -> MarketObservationIdentity:
    values = dict(
        scope=MarketObservationScope.SEARCH_QUERY,
        market="KR",
        marketplace="coupang",
        canonical_product_id=None,
        marketplace_item_id=None,
        normalized_query="wireless mouse",
        category="electronics",
        variant_identity=None,
        condition="new",
        window_started_at=NOW,
        window_ended_at=NOW + timedelta(minutes=5),
    )
    values.update(overrides)
    return MarketObservationIdentity(**values)


def evidence(value, *, status=MarketEvidenceStatus.OBSERVED, unit="count", **overrides):
    values = dict(
        value=value,
        source="coupang-capture",
        reference="capture:1",
        observed_at=NOW,
        status=status,
        confidence=Decimal("0.9"),
        market="KR",
        marketplace="coupang",
        collection_method="capture",
        schema_version="market-evidence-v1",
        keyword="wireless mouse",
        category="electronics",
        unit=unit,
    )
    values.update(overrides)
    return MarketEvidence(**values)


def competition(values) -> CompetitionObservation:
    return CompetitionObservation(
        observation_id="competition-1",
        identity=identity(),
        observed_at=NOW,
        schema_version="competition-v1",
        evidence=values,
    )


def demand(values) -> DemandObservation:
    return DemandObservation(
        observation_id="demand-1",
        identity=identity(),
        observed_at=NOW,
        schema_version="demand-v1",
        evidence=values,
    )


def signal(**overrides) -> ExternalMarketSignal:
    values = dict(
        signal_id="signal-1",
        identity=identity(),
        source_type=ExternalSignalSourceType.MANUAL_INPUT,
        signal_name="category momentum",
        signal_direction=ExternalSignalDirection.POSITIVE,
        evidence=evidence(Decimal("0.8"), status=MarketEvidenceStatus.ESTIMATED, unit="index"),
        captured_at=NOW,
        schema_version="external-signal-v1",
    )
    values.update(overrides)
    return ExternalMarketSignal(**values)


def test_competition_accepts_non_negative_counts_and_verified_zero() -> None:
    item = competition({
        "competitor_count": evidence(12),
        "rocket_seller_count": evidence(0),
        "sponsored_result_count": evidence(0),
        "organic_result_count": evidence(20),
    })
    assert item.evidence["competitor_count"].value == 12
    assert item.evidence["rocket_seller_count"].value == 0


def test_competition_rejects_negative_and_boolean_counts() -> None:
    with pytest.raises(ValueError, match="cannot be negative"):
        competition({"competitor_count": evidence(-1)})
    with pytest.raises(TypeError, match="must be int"):
        competition({"competitor_count": evidence(True)})


def test_competition_accepts_decimal_price_with_currency_unit() -> None:
    item = competition({"median_price": evidence(Decimal("19900.50"), unit="KRW")})
    assert item.evidence["median_price"].value == Decimal("19900.50")


def test_competition_rejects_float_price_and_missing_currency_unit() -> None:
    with pytest.raises(TypeError, match="must be Decimal"):
        competition({"lowest_price": evidence(10.5, unit="KRW")})
    with pytest.raises(ValueError, match="currency unit"):
        competition({"lowest_price": evidence(Decimal("10"), unit=None)})


def test_competition_rejects_unknown_metric_and_context_mismatch() -> None:
    with pytest.raises(ValueError, match="unsupported competition metric"):
        competition({"search_result_count": evidence(10)})
    with pytest.raises(ValueError, match="marketplace"):
        competition({"competitor_count": evidence(10, marketplace="ebay")})


def test_competition_preserves_unknown_and_is_immutable() -> None:
    unknown = evidence(
        None, status=MarketEvidenceStatus.UNKNOWN, source=None,
        reference=None, observed_at=None,
    )
    item = competition({"competitor_count": unknown})
    assert item.evidence["competitor_count"].value is None
    with pytest.raises(TypeError):
        item.evidence["competitor_count"] = evidence(1)  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        item.observation_id = "changed"  # type: ignore[misc]


def test_demand_accepts_ranks_and_zero_review_count() -> None:
    item = demand({
        "coupang_popularity_rank": evidence(1),
        "itemscout_popularity_rank": evidence(25),
        "observed_result_position": evidence(3),
        "review_count": evidence(0),
    })
    assert item.evidence["coupang_popularity_rank"].value == 1
    assert item.evidence["review_count"].value == 0


def test_demand_rejects_zero_rank() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        demand({"coupang_popularity_rank": evidence(0)})


@pytest.mark.parametrize("rating", (Decimal("0"), Decimal("5"), Decimal("4.5")))
def test_demand_accepts_decimal_rating_boundaries(rating: Decimal) -> None:
    assert demand({"rating": evidence(rating, unit="stars")}).evidence["rating"].value == rating


def test_demand_rejects_float_or_out_of_range_rating() -> None:
    with pytest.raises(TypeError, match="rating must be Decimal"):
        demand({"rating": evidence(4.5, unit="stars")})
    with pytest.raises(ValueError, match="between 0 and 5"):
        demand({"rating": evidence(Decimal("5.1"), unit="stars")})


def test_demand_sales_proxy_is_non_negative_decimal_only() -> None:
    assert demand({"sales_proxy": evidence(Decimal("12.5"), unit="index")}).evidence["sales_proxy"].value == Decimal("12.5")
    with pytest.raises(ValueError, match="non-negative"):
        demand({"sales_proxy": evidence(Decimal("-0.1"), unit="index")})
    with pytest.raises(TypeError, match="sales_proxy must be Decimal"):
        demand({"sales_proxy": evidence(12, unit="index")})


def test_demand_preserves_unknown_rank_and_is_immutable() -> None:
    unknown = evidence(
        None, status=MarketEvidenceStatus.UNKNOWN, source=None,
        reference=None, observed_at=None,
    )
    item = demand({"itemscout_popularity_rank": unknown})
    assert item.evidence["itemscout_popularity_rank"].value is None
    with pytest.raises(FrozenInstanceError):
        item.observed_at = NOW + timedelta(days=1)  # type: ignore[misc]


def test_demand_rejects_identity_context_mismatch() -> None:
    with pytest.raises(ValueError, match="market must match"):
        demand({"review_count": evidence(1, market="US")})


def test_itemscout_screenshot_signal_requires_and_preserves_artifact() -> None:
    item = signal(
        source_type=ExternalSignalSourceType.ITEMSCOUT_SCREENSHOT,
        artifact_reference="artifact:sha256",
    )
    assert item.artifact_reference == "artifact:sha256"


def test_manual_signal_does_not_require_artifact() -> None:
    assert signal(source_type="manual_input").artifact_reference is None


def test_human_verified_signal_requires_verification_metadata() -> None:
    verified = evidence(10, status=MarketEvidenceStatus.HUMAN_VERIFIED)
    with pytest.raises(ValueError, match="verified_at"):
        signal(evidence=verified, operator_id="founder")
    with pytest.raises(ValueError, match="operator_id"):
        signal(evidence=verified, verified_at=NOW)
    item = signal(evidence=verified, verified_at=NOW, operator_id="founder")
    assert item.operator_id == "founder"


def test_ocr_candidate_cannot_be_human_verified_and_requires_artifact() -> None:
    verified = evidence(10, status=MarketEvidenceStatus.HUMAN_VERIFIED)
    with pytest.raises(ValueError, match="cannot be human verified"):
        signal(
            source_type=ExternalSignalSourceType.OCR_CANDIDATE,
            evidence=verified, verified_at=NOW, operator_id="founder",
            artifact_reference="artifact:ocr",
        )
    with pytest.raises(ValueError, match="artifact_reference"):
        signal(source_type=ExternalSignalSourceType.OCR_CANDIDATE)


def test_external_signal_validates_timezone_and_verification_order() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        signal(captured_at=datetime(2026, 8, 6))
    with pytest.raises(ValueError, match="cannot precede"):
        signal(verified_at=NOW - timedelta(seconds=1))


def test_external_signal_validates_direction_and_is_immutable() -> None:
    with pytest.raises(ValueError, match="unsupported external signal direction"):
        signal(signal_direction="BUY")
    item = signal(signal_direction="neutral")
    assert item.signal_direction is ExternalSignalDirection.NEUTRAL
    with pytest.raises(FrozenInstanceError):
        item.signal_direction = ExternalSignalDirection.NEGATIVE  # type: ignore[misc]


def test_external_signal_has_no_decision_or_economics_fields() -> None:
    item = signal()
    for forbidden in ("roi", "economics", "recommendation", "recommendation_grade", "score"):
        assert not hasattr(item, forbidden)
