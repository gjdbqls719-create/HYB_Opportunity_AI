from __future__ import annotations

from engine.product_matching import (
    compare_product_titles,
    normalize_product_title,
)
from engine.product_normalizer import (
    normalize_title_detailed,
)


def test_korean_and_english_iphone_titles_normalize_equally() -> None:
    korean = normalize_product_title(
        "아이폰15 프로 256기가 블랙"
    )
    english = normalize_product_title(
        "iPhone 15 Pro 256GB Black"
    )

    assert korean == english
    assert korean == "iphone 15 pro 256gb black"


def test_korean_and_english_iphone_titles_match() -> None:
    result = compare_product_titles(
        "아이폰15 프로 256기가 블랙",
        "iPhone 15 Pro 256GB Black",
    )

    assert result.is_match is True
    assert result.score == 100.0
    assert result.has_conflict is False


def test_korean_and_english_galaxy_titles_match() -> None:
    result = compare_product_titles(
        "삼성 갤럭시 S24 울트라 256기가 블랙",
        "Samsung Galaxy S24 Ultra 256GB Black",
    )

    assert result.is_match is True
    assert result.score == 100.0
    assert result.has_conflict is False


def test_korean_capacity_conflict_is_detected() -> None:
    result = compare_product_titles(
        "아이폰15 프로 128기가 블랙",
        "iPhone 15 Pro 256GB Black",
    )

    assert result.is_match is False
    assert result.has_conflict is True
    assert result.has_high_conflict is True
    assert result.conflict_penalty > 0


def test_korean_accessory_is_detected() -> None:
    normalized = normalize_title_detailed(
        "아이폰15 액정 보호 필름"
    )

    assert normalized.normalized == (
        "iphone 15 screen protector"
    )
    assert normalized.is_accessory is True


def test_korean_accessory_and_main_product_do_not_match() -> None:
    result = compare_product_titles(
        "아이폰15 프로 256기가 블랙",
        "아이폰15 프로 케이스 블랙",
    )

    assert result.is_match is False
    assert result.has_conflict is True
    assert result.has_high_conflict is True