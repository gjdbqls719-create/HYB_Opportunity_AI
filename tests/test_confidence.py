import pytest

from engine.confidence import (
    calculate_price_confidence,
)


def test_one_sample_has_low_confidence() -> None:
    result = calculate_price_confidence(
        1,
        used_fallback_price=True,
    )

    assert result.sample_size == 1
    assert result.confidence_score == 35
    assert result.confidence_multiplier == 0.35
    assert result.confidence_level == "낮음"
    assert result.used_fallback_price is True


def test_two_samples_have_medium_confidence() -> None:
    result = calculate_price_confidence(2)

    assert result.confidence_score == 60
    assert result.confidence_multiplier == 0.60
    assert result.confidence_level == "보통"


def test_three_to_five_samples_have_high_confidence() -> None:
    result_three = calculate_price_confidence(3)
    result_five = calculate_price_confidence(5)

    assert result_three.confidence_score == 80
    assert result_five.confidence_score == 80
    assert result_three.confidence_level == "높음"


def test_six_or_more_samples_have_maximum_confidence() -> None:
    result = calculate_price_confidence(6)

    assert result.confidence_score == 100
    assert result.confidence_multiplier == 1.0
    assert result.confidence_level == "매우 높음"


def test_rejects_invalid_sample_size() -> None:
    with pytest.raises(ValueError):
        calculate_price_confidence(0)