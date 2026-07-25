from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from app.models import Product
from engine.product_attribute_comparator import (
    compare_product_attributes,
    get_conflict_penalty,
    has_identity_conflict,
)
from engine.product_attribute_extractor import (
    extract_attributes_from_product,
    extract_product_attributes,
)
from engine.product_attributes import (
    AttributeConflict,
    ProductAttributes,
)
from engine.product_normalizer import normalize_title


@dataclass(frozen=True, slots=True)
class MatchResult:
    """
    두 상품의 매칭 결과.

    기존 필드는 그대로 유지하면서 속성 비교 정보를 추가한다.

    score:
        속성 충돌 페널티가 반영된 최종 점수.

    is_match:
        최종 점수가 기준 이상이고 핵심 속성 충돌이 없을 때 True.

    normalized_left / normalized_right:
        비교에 사용된 정규화 상품명.

    common_tokens:
        두 상품명에 공통으로 포함된 토큰.

    matched_fields:
        두 상품에서 동일하게 확인된 속성 이름.

    conflicts:
        서로 다른 것으로 확인된 속성 충돌 정보.

    conflict_penalty:
        속성 충돌로 인해 차감된 점수.
    """

    score: float
    is_match: bool
    normalized_left: str
    normalized_right: str
    common_tokens: tuple[str, ...]

    matched_fields: tuple[str, ...] = ()
    conflicts: tuple[AttributeConflict, ...] = ()
    conflict_penalty: float = 0.0

    @property
    def has_conflict(self) -> bool:
        """
        하나 이상의 속성 충돌이 있는지 반환한다.
        """
        return bool(self.conflicts)

    @property
    def has_high_conflict(self) -> bool:
        """
        높은 심각도의 속성 충돌이 있는지 반환한다.
        """
        return any(
            conflict.severity == "high"
            for conflict in self.conflicts
        )


def normalize_product_title(
    title: str,
) -> str:
    """
    상품 제목을 비교하기 쉬운 형태로 정규화한다.

    기존 공개 함수 이름을 유지하면서 확장 정규화기를 사용한다.

    예:
        "Apple iPhone17 128 GB - Black!"
        → "apple iphone 17 128gb black"
    """
    return normalize_title(title)


def _get_tokens(
    normalized_title: str,
) -> set[str]:
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
    두 제목의 공통 토큰 비율을 0~100 점수로 계산한다.

    Jaccard 유사도:
        교집합 토큰 수 / 합집합 토큰 수
    """
    if not left_tokens or not right_tokens:
        return 0.0

    common_tokens = left_tokens & right_tokens
    all_tokens = left_tokens | right_tokens

    return (
        len(common_tokens)
        / len(all_tokens)
        * 100
    )


def _calculate_sequence_score(
    left_title: str,
    right_title: str,
) -> float:
    """
    문자열 배열의 유사도를 0~100 점수로 계산한다.
    """
    return (
        SequenceMatcher(
            None,
            left_title,
            right_title,
        ).ratio()
        * 100
    )


def _validate_match_threshold(
    match_threshold: float,
) -> float:
    """
    매칭 기준 점수가 올바른 범위인지 검증한다.
    """
    try:
        resolved_threshold = float(
            match_threshold
        )
    except (TypeError, ValueError) as error:
        raise ValueError(
            "match_threshold는 숫자여야 합니다."
        ) from error

    if not 0 <= resolved_threshold <= 100:
        raise ValueError(
            "match_threshold는 0 이상 "
            "100 이하여야 합니다."
        )

    return resolved_threshold


def _compare_extracted_attributes(
    left_attributes: ProductAttributes,
    right_attributes: ProductAttributes,
    *,
    match_threshold: float,
) -> MatchResult:
    """
    이미 추출된 두 상품 속성으로 최종 매칭 결과를 계산한다.

    기본 문자열 점수:
        토큰 일치도 70%
        문자열 배열 유사도 30%

    이후 속성 충돌 페널티를 차감한다.
    """
    resolved_threshold = _validate_match_threshold(
        match_threshold
    )

    normalized_left = (
        left_attributes.normalized_title
    )
    normalized_right = (
        right_attributes.normalized_title
    )

    left_tokens = _get_tokens(
        normalized_left
    )
    right_tokens = _get_tokens(
        normalized_right
    )

    token_score = _calculate_token_score(
        left_tokens,
        right_tokens,
    )

    sequence_score = _calculate_sequence_score(
        normalized_left,
        normalized_right,
    )

    base_score = (
        token_score * 0.7
        + sequence_score * 0.3
    )

    attribute_comparison = (
        compare_product_attributes(
            left_attributes,
            right_attributes,
        )
    )

    conflict_penalty = get_conflict_penalty(
        attribute_comparison
    )

    final_score = max(
        0.0,
        base_score - conflict_penalty,
    )

    rounded_score = round(
        final_score,
        1,
    )
    rounded_penalty = round(
        conflict_penalty,
        1,
    )

    identity_conflict = has_identity_conflict(
        attribute_comparison
    )

    is_match = (
        rounded_score >= resolved_threshold
        and not identity_conflict
    )

    common_tokens = tuple(
        sorted(
            left_tokens & right_tokens
        )
    )

    return MatchResult(
        score=rounded_score,
        is_match=is_match,
        normalized_left=normalized_left,
        normalized_right=normalized_right,
        common_tokens=common_tokens,
        matched_fields=(
            attribute_comparison.matched_fields
        ),
        conflicts=attribute_comparison.conflicts,
        conflict_penalty=rounded_penalty,
    )


def compare_product_titles(
    left_title: str,
    right_title: str,
    match_threshold: float = 75.0,
) -> MatchResult:
    """
    두 상품 제목의 유사도를 계산한다.

    기존 함수 사용 방식은 그대로 유지한다.

    처리 흐름:
        1. 상품명 정규화
        2. 범용 상품 속성 추출
        3. 토큰 및 문자열 유사도 계산
        4. 속성 일치 및 충돌 비교
        5. 충돌 페널티 적용
        6. 최종 매칭 여부 결정

    핵심 속성 충돌 예:
        Apple ↔ Samsung
        iPhone 15 ↔ iPhone 16
        128GB ↔ 256GB
        US 9 ↔ US 10
        본체 ↔ 액세서리

    핵심 속성이 충돌하면 점수가 기준 이상이어도
    최종 매칭 결과는 False가 된다.
    """
    left_attributes = extract_product_attributes(
        left_title
    )
    right_attributes = extract_product_attributes(
        right_title
    )

    return _compare_extracted_attributes(
        left_attributes,
        right_attributes,
        match_threshold=match_threshold,
    )


def compare_products(
    left_product: Product,
    right_product: Product,
    match_threshold: float = 75.0,
) -> MatchResult:
    """
    두 Product 객체를 비교한다.

    제목뿐 아니라 Product에 저장된 다음 정보도 활용한다.

        brand
        model_number
        category
        condition

    명시적으로 저장된 상품 정보는 제목에서 추측한 값보다
    우선적으로 사용된다.
    """
    if not isinstance(
        left_product,
        Product,
    ):
        raise TypeError(
            "left_product는 Product 객체여야 합니다."
        )

    if not isinstance(
        right_product,
        Product,
    ):
        raise TypeError(
            "right_product는 Product 객체여야 합니다."
        )

    left_attributes = (
        extract_attributes_from_product(
            left_product
        )
    )
    right_attributes = (
        extract_attributes_from_product(
            right_product
        )
    )

    return _compare_extracted_attributes(
        left_attributes,
        right_attributes,
        match_threshold=match_threshold,
    )