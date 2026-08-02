from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.domain.market_intelligence import MarketEvidence, MarketEvidenceStatus


OBSERVED_AT = datetime(2026, 8, 5, tzinfo=timezone.utc)


def evidence(**overrides) -> MarketEvidence:
    values = dict(
        value=Decimal("12"),
        source="coupang-capture",
        reference="capture:sha256",
        observed_at=OBSERVED_AT,
        status=MarketEvidenceStatus.VERIFIED,
        confidence=Decimal("0.95"),
        market="KR",
        marketplace="Coupang",
        collection_method="human_review",
        schema_version="market-evidence-v1",
        keyword="wireless mouse",
        category="electronics",
        marketplace_item_id="item-1",
        canonical_product_id="CP-000001",
        unit="count",
    )
    values.update(overrides)
    return MarketEvidence(**values)


def test_verified_evidence_is_normalized_and_preserves_zero() -> None:
    item = evidence(value=Decimal("0"), status="verified")

    assert item.value == Decimal("0")
    assert item.status is MarketEvidenceStatus.VERIFIED
    assert item.marketplace == "coupang"
    assert item.source == "coupang-capture"
    assert item.observed_at == OBSERVED_AT


def test_unknown_evidence_has_explicit_absence_and_confidence() -> None:
    item = evidence(
        value=None,
        source=None,
        reference=None,
        observed_at=None,
        status=MarketEvidenceStatus.UNKNOWN,
        confidence=Decimal("0"),
    )

    assert item.value is None
    assert item.status is MarketEvidenceStatus.UNKNOWN
    assert item.confidence == Decimal("0")


@pytest.mark.parametrize(
    "status",
    (
        MarketEvidenceStatus.UNKNOWN,
        MarketEvidenceStatus.UNAVAILABLE,
        MarketEvidenceStatus.UNSUPPORTED,
        MarketEvidenceStatus.EXTRACTION_FAILED,
    ),
)
def test_absent_status_rejects_a_value(status: MarketEvidenceStatus) -> None:
    with pytest.raises(ValueError, match="value to be None"):
        evidence(status=status, value=0)


@pytest.mark.parametrize("confidence", (Decimal("-0.01"), Decimal("1.01")))
def test_confidence_must_be_within_inclusive_decimal_range(confidence: Decimal) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        evidence(confidence=confidence)


def test_confidence_must_be_decimal() -> None:
    with pytest.raises(TypeError, match="confidence must be Decimal"):
        evidence(confidence=0.5)


def test_observed_timestamp_must_be_timezone_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        evidence(observed_at=datetime(2026, 8, 5))


def test_schema_version_is_required() -> None:
    with pytest.raises(ValueError, match="schema_version"):
        evidence(schema_version=" ")


@pytest.mark.parametrize(
    "status",
    (
        MarketEvidenceStatus.VERIFIED,
        MarketEvidenceStatus.HUMAN_VERIFIED,
        MarketEvidenceStatus.OBSERVED,
    ),
)
def test_observed_statuses_require_source_and_observed_at(status: MarketEvidenceStatus) -> None:
    with pytest.raises(ValueError, match="requires source"):
        evidence(status=status, source=None)
    with pytest.raises(ValueError, match="requires observed_at"):
        evidence(status=status, observed_at=None)


def test_estimated_evidence_requires_a_value() -> None:
    with pytest.raises(ValueError, match="estimated evidence requires value"):
        evidence(status=MarketEvidenceStatus.ESTIMATED, value=None)


def test_market_evidence_is_immutable() -> None:
    item = evidence()
    with pytest.raises(FrozenInstanceError):
        item.confidence = Decimal("0")  # type: ignore[misc]
