from __future__ import annotations

import pytest

from engine.product_synonyms import (
    PRODUCT_SYNONYMS,
    normalize_product_synonyms,
)


def test_normalizes_korean_iphone_name() -> None:
    result = normalize_product_synonyms(
        "아이폰15 프로"
    )

    assert result == "iphone15 pro"


def test_normalizes_korean_iphone_pro_max() -> None:
    result = normalize_product_synonyms(
        "아이폰 15 프로 맥스"
    )

    assert result == "iphone 15 pro max"


def test_normalizes_korean_samsung_galaxy_name() -> None:
    result = normalize_product_synonyms(
        "삼성 갤럭시 S24 울트라"
    )

    assert result == "samsung galaxy S24 ultra"


def test_normalizes_korean_apple_products() -> None:
    result = normalize_product_synonyms(
        "애플 맥북 에어"
    )

    assert result == "apple macbook air"


def test_normalizes_wireless_terms() -> None:
    result = normalize_product_synonyms(
        "무선 블루투스 이어폰"
    )

    assert result == "wireless bluetooth 이어폰"


def test_normalizes_accessory_terms() -> None:
    result = normalize_product_synonyms(
        "아이폰15 액정 보호 필름"
    )

    assert result == "iphone15 screen protector"


def test_normalizes_product_condition() -> None:
    result = normalize_product_synonyms(
        "미개봉 아이폰15"
    )

    assert result == "new iphone15"


def test_longer_synonym_is_processed_first() -> None:
    result = normalize_product_synonyms(
        "아이폰15 프로맥스"
    )

    assert result == "iphone15 pro max"


def test_existing_english_terms_remain_unchanged() -> None:
    result = normalize_product_synonyms(
        "Apple iPhone 15 Pro Max"
    )

    assert result == "Apple iPhone 15 Pro Max"


def test_synonym_mapping_is_read_only() -> None:
    with pytest.raises(TypeError):
        PRODUCT_SYNONYMS["테스트"] = "test"  # type: ignore[index]


@pytest.mark.parametrize(
    "invalid_text",
    [
        "",
        "   ",
        None,
    ],
)
def test_empty_text_raises_value_error(
    invalid_text: object,
) -> None:
    with pytest.raises(ValueError):
        normalize_product_synonyms(
            invalid_text  # type: ignore[arg-type]
        )