from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.models import Product


@dataclass(frozen=True, slots=True)
class MatchResult:
    """
    두 상품의 제목 비교 결과.
    """

    score: float
    is_match: bool
    normalized_left: str
    normalized_right: str
    common_tokens: tuple[str, ...]


def normalize_product_title(title: str) -> str:
    """
    상품 제목을 비교하기 쉬운 형태로 정규화한다.

    예:
        "Apple iPhone17 128 GB - Black!"
        → "apple iphone 17 128gb black"
    """
    normalized = title.strip().lower()

    # iPhone17 → iPhone 17처럼 문자와 숫자 사이를 분리한다.
    normalized = re.sub(r"([a-z])(\d)", r"\1 \2", normalized)
    normalized = re.sub(r"(\d)([a-z])", r"\1 \2", normalized)

    # 128 GB → 128gb 형태로 통일한다.
    normalized = re.sub(
        r"\b(\d+)\s*(gb|tb|mb)\b",
        r"\1\2",
        normalized,
    )

    # 영문, 숫자, 한글을 제외한 기호를 공백으로 바꾼다.
    normalized = re.sub(
        r"[^a-z0-9가-힣]+",
        " ",
        normalized,
    )

    # 연속 공백을 하나로 통일한다.
    normalized = re.sub(r"\s+", " ", normalized)

    return normalized.strip()


def _get_tokens(normalized_title: str) -> set[str]:
    """
    정규화된 제목을 중복 없는 단어 집합으로 변환한다.
    """
    return {
        token
        for token in normalized_title.split()
        if token
    }


def _calculate_token_score(
    left_tokens: set[str],
    right_tokens: set[str],
) -> float:
    """
    두 제목이 공유하는 단어 비율을 0~100 점수로 계산한다.
    """
    if not left_tokens or not right_tokens:
        return 0.0

    common_tokens = left_tokens & right_tokens
    all_tokens = left_tokens | right_tokens

    return len(common_tokens) / len(all_tokens) * 100


def _calculate_sequence_score(
    left_title: str,
    right_title: str,
) -> float:
    """
    문자열 배열의 유사도를 0~100 점수로 계산한다.
    """
    return SequenceMatcher(
        None,
        left_title,
        right_title,
    ).ratio() * 100


def compare_product_titles(
    left_title: str,
    right_title: str,
    match_threshold: float = 75.0,
) -> MatchResult:
    """
    두 상품 제목의 유사도를 계산한다.

    최종 점수:
        단어 일치율 70%
        문자열 유사도 30%
    """
    if not 0 <= match_threshold <= 100:
        raise ValueError(
            "match_threshold는 0 이상 100 이하여야 합니다."
        )

    normalized_left = normalize_product_title(left_title)
    normalized_right = normalize_product_title(right_title)

    left_tokens = _get_tokens(normalized_left)
    right_tokens = _get_tokens(normalized_right)

    token_score = _calculate_token_score(
        left_tokens,
        right_tokens,
    )

    sequence_score = _calculate_sequence_score(
        normalized_left,
        normalized_right,
    )

    final_score = (
        token_score * 0.7
        + sequence_score * 0.3
    )

    common_tokens = tuple(
        sorted(left_tokens & right_tokens)
    )

    rounded_score = round(final_score, 1)

    return MatchResult(
        score=rounded_score,
        is_match=rounded_score >= match_threshold,
        normalized_left=normalized_left,
        normalized_right=normalized_right,
        common_tokens=common_tokens,
    )


def compare_products(
    left_product: Product,
    right_product: Product,
    match_threshold: float = 75.0,
) -> MatchResult:
    """
    두 Product 객체의 제목을 비교한다.
    """
    return compare_product_titles(
        left_title=left_product.title,
        right_title=right_product.title,
        match_threshold=match_threshold,
    )