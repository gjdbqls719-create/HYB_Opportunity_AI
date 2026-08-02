from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from app.application.ocr import (
    ConvertOCRResultToCandidates,
    DummyOCRAdapter,
    ExtractOCR,
    OCRService,
)
from app.domain.market_intelligence import (
    ArtifactOrigin,
    ArtifactReference,
    ArtifactType,
    ExternalSignalSourceType,
    OCRField,
    OCRFieldResult,
    OCRProvider,
    OCRResult,
)


NOW = datetime(2026, 8, 12, 9, tzinfo=timezone.utc)


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
        file_size=100,
        schema_version="artifact-v1",
    )
    values.update(overrides)
    return ArtifactReference(**values)


def field(**overrides) -> OCRFieldResult:
    values = dict(
        field_name=OCRField.PRICE,
        raw_text="19,900",
        normalized_value=Decimal("19900"),
        confidence=Decimal("0.9"),
        bounding_box=(1, 2, 30, 40),
    )
    values.update(overrides)
    return OCRFieldResult(**values)


def result(**overrides) -> OCRResult:
    values = dict(
        request_id="request-1",
        artifact_id="artifact-1",
        provider=OCRProvider.TESSERACT,
        provider_version="5.4",
        executed_at=NOW,
        fields=(field(),),
        confidence=Decimal("0.9"),
        schema_version="ocr-result-v1",
    )
    values.update(overrides)
    return OCRResult(**values)


@pytest.mark.parametrize("provider", tuple(OCRProvider))
def test_ocr_result_accepts_every_provider(provider: OCRProvider) -> None:
    assert result(provider=provider).provider is provider


def test_ocr_result_rejects_unknown_provider_value() -> None:
    with pytest.raises(ValueError, match="unsupported OCR provider"):
        result(provider="not-a-provider")


@pytest.mark.parametrize("confidence", (Decimal("0"), Decimal("1"), Decimal("0.25")))
def test_result_and_field_confidence_preserve_decimal(confidence: Decimal) -> None:
    assert result(confidence=confidence).confidence == confidence
    assert field(confidence=confidence).confidence == confidence


@pytest.mark.parametrize("confidence", (Decimal("-0.1"), Decimal("1.1")))
def test_result_and_field_confidence_range(confidence: Decimal) -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        result(confidence=confidence)
    with pytest.raises(ValueError, match="between 0 and 1"):
        field(confidence=confidence)


def test_ocr_result_validates_timezone_and_field_enum() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        result(executed_at=datetime(2026, 8, 12))
    with pytest.raises(ValueError, match="unsupported OCR field"):
        field(field_name="not-a-field")


def test_ocr_result_and_fields_are_immutable_value_objects() -> None:
    left = result()
    right = result()
    assert left == right
    assert isinstance(left.fields, tuple)
    with pytest.raises(FrozenInstanceError):
        left.provider = OCRProvider.CUSTOM  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        left.fields[0].raw_text = "changed"  # type: ignore[misc]


def test_optional_bounding_box_validation() -> None:
    assert field(bounding_box=None).bounding_box is None
    with pytest.raises(TypeError, match="four-integer tuple"):
        field(bounding_box=(1, 2, 3))
    with pytest.raises(ValueError, match="cannot be negative"):
        field(bounding_box=(-1, 2, 3, 4))


def test_dummy_adapter_returns_deterministic_fixed_result() -> None:
    adapter = DummyOCRAdapter()
    first = adapter.extract_text(artifact())
    second = adapter.extract_text(artifact())
    assert first == second
    assert first.provider is OCRProvider.CUSTOM
    assert tuple(item.field_name for item in first.fields) == (
        OCRField.PRICE,
        OCRField.SEARCH_VOLUME,
        OCRField.POPULARITY,
    )


def test_extract_use_case_invokes_provider_neutral_adapter() -> None:
    result_value = OCRService(DummyOCRAdapter()).extract(ExtractOCR(artifact()))
    assert result_value.artifact_id == "artifact-1"
    assert result_value.request_id == "dummy:artifact-1"


def test_ocr_result_converts_to_unverified_candidates_without_information_loss() -> None:
    source = result(fields=(
        field(),
        field(
            field_name=OCRField.SEARCH_VOLUME,
            raw_text="1,200",
            normalized_value=1200,
            confidence=Decimal("0.8"),
            bounding_box=None,
        ),
    ))
    candidates = OCRService(DummyOCRAdapter()).to_candidates(
        ConvertOCRResultToCandidates(artifact(), source)
    )
    assert len(candidates) == 2
    assert candidates[0].field_name is OCRField.PRICE
    assert candidates[0].raw_text == "19,900"
    assert candidates[0].normalized_value == Decimal("19900")
    assert candidates[0].confidence == Decimal("0.9")
    assert candidates[1].field_name is OCRField.SEARCH_VOLUME
    assert candidates[1].normalized_value == 1200
    assert all(not hasattr(candidate, "verified_at") for candidate in candidates)


def test_result_artifact_mismatch_is_rejected() -> None:
    mismatch = result(artifact_id="different")
    with pytest.raises(ValueError, match="artifact_id"):
        OCRService(DummyOCRAdapter()).to_candidates(
            ConvertOCRResultToCandidates(artifact(), mismatch)
        )


def test_dummy_adapter_has_no_engine_or_file_dependency() -> None:
    adapter = DummyOCRAdapter()
    assert not hasattr(adapter, "client")
    assert not hasattr(adapter, "model")
    assert not hasattr(adapter, "file_store")
