from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.application.external_signal import (
    CreateExternalSignal,
    CreateOCRCandidate,
    ExternalSignalTrustError,
    ExternalSignalTrustService,
    VerifyOCRCandidate,
)
from app.domain.market_intelligence import (
    ArtifactOrigin,
    ArtifactReference,
    ArtifactType,
    ExternalSignalDirection,
    ExternalSignalSourceType,
    HumanVerification,
    MarketEvidenceStatus,
    MarketObservationIdentity,
    MarketObservationScope,
    OCRCandidate,
    OCRField,
)


NOW = datetime(2026, 8, 10, 9, tzinfo=timezone.utc)


def artifact(**overrides) -> ArtifactReference:
    values = dict(
        artifact_id="artifact-1",
        artifact_type=ArtifactType.SCREENSHOT,
        artifact_origin=ArtifactOrigin.ITEMSCOUT,
        source_type=ExternalSignalSourceType.ITEMSCOUT_SCREENSHOT,
        sha256="a" * 64,
        captured_at=NOW,
        width=1920,
        height=1080,
        mime_type="image/png",
        file_size=12345,
        schema_version="artifact-v1",
    )
    values.update(overrides)
    return ArtifactReference(**values)


def candidate(**overrides) -> OCRCandidate:
    values = dict(
        candidate_id="candidate-1",
        artifact=artifact(),
        field_name=OCRField.SEARCH_VOLUME,
        raw_text="1,234",
        normalized_value=1234,
        confidence=Decimal("0.82"),
        captured_at=NOW + timedelta(seconds=1),
        schema_version="ocr-candidate-v1",
    )
    values.update(overrides)
    return OCRCandidate(**values)


def verification(**overrides) -> HumanVerification:
    values = dict(
        verification_id="verification-1",
        candidate_id="candidate-1",
        verified_value=1234,
        operator_id="founder-1",
        verified_at=NOW + timedelta(minutes=1),
        comment="checked against screenshot",
        schema_version="human-verification-v1",
    )
    values.update(overrides)
    return HumanVerification(**values)


def identity() -> MarketObservationIdentity:
    return MarketObservationIdentity(
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


@pytest.mark.parametrize("sha256", ("a" * 63, "a" * 65, "g" * 64))
def test_artifact_requires_exact_sha256_hex(sha256: str) -> None:
    with pytest.raises(ValueError, match="64 hexadecimal"):
        artifact(sha256=sha256)


def test_artifact_normalizes_sha256_and_is_immutable() -> None:
    item = artifact(sha256="A" * 64)
    assert item.sha256 == "a" * 64
    with pytest.raises(FrozenInstanceError):
        item.width = 1  # type: ignore[misc]


@pytest.mark.parametrize(("field", "value"), (("width", 0), ("height", -1)))
def test_artifact_requires_positive_dimensions(field: str, value: int) -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        artifact(**{field: value})


def test_artifact_validates_mime_file_size_and_timezone() -> None:
    with pytest.raises(ValueError, match="mime_type"):
        artifact(mime_type=" ")
    with pytest.raises(ValueError, match="file_size"):
        artifact(file_size=-1)
    with pytest.raises(ValueError, match="timezone-aware"):
        artifact(captured_at=datetime(2026, 8, 10))


@pytest.mark.parametrize("confidence", (Decimal("-0.1"), Decimal("1.1")))
def test_ocr_candidate_confidence_range(confidence: Decimal) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        candidate(confidence=confidence)


@pytest.mark.parametrize("confidence", (Decimal("NaN"), Decimal("Infinity")))
def test_ocr_candidate_rejects_non_finite_confidence(confidence: Decimal) -> None:
    with pytest.raises(ValueError, match="finite"):
        candidate(confidence=confidence)


def test_ocr_candidate_validates_enum_timezone_and_immutability() -> None:
    with pytest.raises(ValueError, match="unsupported OCR field"):
        candidate(field_name="not-a-field")
    with pytest.raises(ValueError, match="timezone-aware"):
        candidate(captured_at=datetime(2026, 8, 10))
    item = candidate(field_name="rating")
    assert item.field_name is OCRField.RATING
    assert not hasattr(item, "status")
    assert not hasattr(item, "verified_at")
    with pytest.raises(FrozenInstanceError):
        item.normalized_value = 5  # type: ignore[misc]


def test_human_verification_requires_operator_and_aware_time() -> None:
    with pytest.raises(ValueError, match="operator_id"):
        verification(operator_id=" ")
    with pytest.raises(ValueError, match="timezone-aware"):
        verification(verified_at=datetime(2026, 8, 10))


def test_human_verification_is_new_immutable_fact_and_does_not_mutate_candidate() -> None:
    original = candidate()
    before = candidate()
    result = ExternalSignalTrustService().verify_ocr_candidate(VerifyOCRCandidate(
        verification_id="verification-1",
        candidate=original,
        verified_value=1200,
        operator_id="founder-1",
        verified_at=NOW + timedelta(minutes=1),
        comment=None,
    ))
    assert original == before
    assert result.candidate_id == original.candidate_id
    assert result.verified_value == 1200
    with pytest.raises(FrozenInstanceError):
        result.operator_id = "other"  # type: ignore[misc]


def test_application_creates_candidate_without_ocr_engine() -> None:
    result = ExternalSignalTrustService().create_ocr_candidate(CreateOCRCandidate(
        candidate_id="candidate-1",
        artifact=artifact(),
        field_name=OCRField.PRICE,
        raw_text="19,900",
        normalized_value=Decimal("19900"),
        confidence=Decimal("0.75"),
        captured_at=NOW + timedelta(seconds=1),
    ))
    assert result.field_name is OCRField.PRICE
    assert result.normalized_value == Decimal("19900")


def signal_command(*, verified=verification(), item=candidate()) -> CreateExternalSignal:
    return CreateExternalSignal(
        signal_id="signal-1",
        identity=identity(),
        candidate=item,
        verification=verified,
        signal_name="search volume",
        signal_direction=ExternalSignalDirection.POSITIVE,
    )


def test_external_signal_requires_matching_human_verification() -> None:
    service = ExternalSignalTrustService()
    with pytest.raises(ExternalSignalTrustError, match="required"):
        service.create_external_signal(signal_command(verified=None))
    with pytest.raises(ExternalSignalTrustError, match="belong"):
        service.create_external_signal(signal_command(
            verified=verification(candidate_id="different"),
        ))


def test_verified_signal_is_created_only_after_human_verification() -> None:
    signal = ExternalSignalTrustService().create_external_signal(signal_command())
    assert signal.evidence.status is MarketEvidenceStatus.HUMAN_VERIFIED
    assert signal.evidence.value == 1234
    assert signal.operator_id == "founder-1"
    assert signal.verified_at == verification().verified_at
    assert signal.artifact_reference == "artifact-1"
    for forbidden in ("recommendation", "score", "decision"):
        assert not hasattr(signal, forbidden)
