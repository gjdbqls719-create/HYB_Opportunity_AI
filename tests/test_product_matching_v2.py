from __future__ import annotations

import pytest

from engine.product_matching import (
    MatchResult,
    compare_product_titles,
    normalize_product_title,
)


def test_normalize_product_title_preserves_capacity_token() -> None:
    result = normalize_product_title(
        "Apple iPhone17 128 GB - Black!"
    )

    assert result == "apple iphone 17 128gb black"


def test_normalize_product_title_preserves_quantity_token() -> None:
    result = normalize_product_title(
        "AAA Battery 4 Pack"
    )

    assert "qty4" in result
    assert "qty 4" not in result


def test_same_product_with_formatting_difference_matches() -> None:
    result = compare_product_titles(
        "Apple iPhone 15 128GB Black",
        "Apple iPhone15 128 GB Black",
    )

    assert result.is_match is True
    assert result.has_conflict is False
    assert result.conflict_penalty == 0.0


def test_identical_titles_receive_perfect_score() -> None:
    result = compare_product_titles(
        "Apple iPhone 15 128GB Black",
        "Apple iPhone 15 128GB Black",
    )

    assert result.score == 100.0
    assert result.is_match is True


def test_capacity_conflict_is_not_match() -> None:
    result = compare_product_titles(
        "Apple iPhone 15 128GB Black",
        "Apple iPhone 15 256GB Black",
    )

    assert result.is_match is False
    assert result.has_conflict is True
    assert result.has_high_conflict is True
    assert result.conflict_penalty > 0


def test_capacity_match_is_recorded() -> None:
    result = compare_product_titles(
        "Apple iPhone 15 128GB Black",
        "Apple iPhone 15 128GB White",
    )

    assert "capacity" in result.matched_fields


def test_model_conflict_is_not_match() -> None:
    result = compare_product_titles(
        "Apple iPhone 15 128GB Black",
        "Apple iPhone 16 128GB Black",
    )

    assert result.is_match is False
    assert result.has_conflict is True
    assert result.has_high_conflict is True


def test_brand_conflict_is_not_match() -> None:
    result = compare_product_titles(
        "Apple Galaxy S24 256GB Black",
        "Samsung Galaxy S24 256GB Black",
    )

    assert result.is_match is False
    assert result.has_conflict is True
    assert result.has_high_conflict is True


def test_color_difference_is_not_high_conflict() -> None:
    result = compare_product_titles(
        "Apple iPhone 15 128GB Black",
        "Apple iPhone 15 128GB White",
    )

    assert result.has_conflict is True
    assert result.has_high_conflict is False
    assert result.conflict_penalty > 0


def test_same_color_is_recorded_as_matched_field() -> None:
    result = compare_product_titles(
        "Apple iPhone 15 128GB Black",
        "Apple iPhone15 128 GB Black",
    )

    assert "color" in result.matched_fields


def test_quantity_conflict_is_detected() -> None:
    result = compare_product_titles(
        "AAA Battery 4 Pack",
        "AAA Battery 8 Pack",
    )

    assert result.is_match is False
    assert result.has_conflict is True
    assert result.conflict_penalty > 0


def test_bundle_and_single_product_are_distinguished() -> None:
    result = compare_product_titles(
        "AAA Battery 4 Pack",
        "AAA Battery Single",
    )

    assert result.has_conflict is True
    assert result.conflict_penalty > 0


def test_accessory_and_main_product_do_not_match() -> None:
    result = compare_product_titles(
        "Apple iPhone 15 128GB Black",
        "Apple iPhone 15 Case Black",
    )

    assert result.is_match is False
    assert result.has_conflict is True
    assert result.has_high_conflict is True


def test_two_similar_accessories_can_match() -> None:
    result = compare_product_titles(
        "Apple iPhone 15 Black Case",
        "Black Case for Apple iPhone15",
        match_threshold=60.0,
    )

    assert result.is_match is True


def test_match_result_contains_v2_fields() -> None:
    result = compare_product_titles(
        "Apple iPhone 15 128GB Black",
        "Apple iPhone 15 256GB Black",
    )

    assert isinstance(result, MatchResult)
    assert isinstance(result.matched_fields, tuple)
    assert isinstance(result.conflicts, tuple)
    assert isinstance(result.conflict_penalty, float)
    assert isinstance(result.has_conflict, bool)
    assert isinstance(result.has_high_conflict, bool)


@pytest.mark.parametrize(
    "invalid_threshold",
    [
        -0.1,
        100.1,
        "invalid",
        None,
    ],
)
def test_invalid_match_threshold_raises_value_error(
    invalid_threshold: object,
) -> None:
    with pytest.raises(ValueError):
        compare_product_titles(
            "Apple iPhone 15",
            "Apple iPhone 15",
            match_threshold=invalid_threshold,
        )