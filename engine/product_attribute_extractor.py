from __future__ import annotations

import re
from collections.abc import Iterable

from app.models import Product
from engine.product_attributes import ProductAttributes
from engine.product_normalizer import (
    COLOR_ALIASES,
    CONDITION_ALIASES,
    normalize_title_detailed,
)


KNOWN_BRANDS: tuple[str, ...] = (
    "apple",
    "samsung",
    "sony",
    "lg",
    "nike",
    "adidas",
    "puma",
    "new balance",
    "nintendo",
    "microsoft",
    "xbox",
    "playstation",
    "lenovo",
    "dell",
    "hp",
    "asus",
    "acer",
    "logitech",
    "dyson",
    "rolex",
    "seiko",
    "casio",
    "lego",
    "xiaomi",
    "huawei",
    "google",
    "amazon",
)

CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "smartphone": (
        "iphone",
        "galaxy",
        "smartphone",
        "휴대폰",
        "스마트폰",
    ),
    "tablet": (
        "ipad",
        "tablet",
        "태블릿",
        "갤럭시탭",
    ),
    "laptop": (
        "macbook",
        "laptop",
        "notebook",
        "노트북",
    ),
    "headphones": (
        "headphone",
        "headphones",
        "earbuds",
        "airpods",
        "buds",
        "이어폰",
        "헤드폰",
    ),
    "console": (
        "playstation",
        "ps5",
        "xbox",
        "nintendo switch",
        "닌텐도",
    ),
    "shoes": (
        "shoes",
        "sneakers",
        "boots",
        "air jordan",
        "운동화",
        "신발",
    ),
    "clothing": (
        "shirt",
        "t shirt",
        "hoodie",
        "jacket",
        "pants",
        "dress",
        "셔츠",
        "후드",
        "자켓",
        "바지",
        "원피스",
    ),
    "watch": (
        "watch",
        "wristwatch",
        "시계",
    ),
    "beauty": (
        "perfume",
        "cosmetic",
        "serum",
        "cream",
        "향수",
        "화장품",
        "세럼",
        "크림",
    ),
    "toy": (
        "lego",
        "figure",
        "toy",
        "피규어",
        "장난감",
    ),
}

MODEL_STOP_TOKENS: frozenset[str] = frozenset(
    {
        "new",
        "used",
        "refurbished",
        "black",
        "white",
        "red",
        "blue",
        "green",
        "gray",
        "silver",
        "gold",
        "pink",
        "purple",
        "yellow",
        "brown",
        "beige",
        "bundle",
        "set",
        "pack",
        "case",
        "cover",
        "charger",
        "cable",
        "adapter",
    }
)

SIZE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\b(?:us|uk|eu)\s*[-:]?\s*(\d+(?:\.\d+)?)\b"
    ),
    re.compile(
        r"\bsize\s*[-:]?\s*([a-z0-9.]+)\b"
    ),
    re.compile(
        r"\b(\d+(?:\.\d+)?)\s*(?:inch|inches|in)\b"
    ),
    re.compile(
        r"\b(xs|s|m|l|xl|xxl|xxxl)\b"
    ),
)

EDITION_KEYWORDS: tuple[str, ...] = (
    "limited edition",
    "special edition",
    "collector edition",
    "collectors edition",
    "pro",
    "pro max",
    "ultra",
    "plus",
    "max",
    "mini",
)

CONDITION_PRIORITY: tuple[str, ...] = (
    "refurbished",
    "used",
    "new",
)


def _normalize_optional_text(
    value: str | None,
) -> str | None:
    if value is None:
        return None

    normalized = str(value).strip().lower()

    return normalized or None


def _extract_capacity(
    normalized_title: str,
) -> str | None:
    """
    저장 용량 또는 메모리 용량을 추출한다.

    예:
        128gb
        1tb
        512mb
    """
    match = re.search(
        r"\b(\d+(?:\.\d+)?(?:kb|mb|gb|tb))\b",
        normalized_title,
    )

    if match is None:
        return None

    return match.group(1)


def _extract_color(
    tokens: tuple[str, ...],
) -> str | None:
    """
    정규화된 색상 토큰을 추출한다.
    """
    known_colors = set(COLOR_ALIASES.values())
    known_colors.add("gray")

    matched_colors = [
        token
        for token in tokens
        if token in known_colors
    ]

    if not matched_colors:
        return None

    unique_colors = list(
        dict.fromkeys(matched_colors)
    )

    return " ".join(unique_colors)


def _extract_quantity(
    normalized_title: str,
) -> int | None:
    """
    qty2와 같은 정규화된 수량 표현을 추출한다.
    """
    match = re.search(
        r"\bqty(\d+)\b",
        normalized_title,
    )

    if match is None:
        return None

    quantity = int(match.group(1))

    if quantity <= 0:
        return None

    return quantity


def _extract_size(
    normalized_title: str,
) -> str | None:
    """
    의류, 신발, 화면 크기 등의 규격을 추출한다.
    """
    for pattern in SIZE_PATTERNS:
        match = pattern.search(
            normalized_title
        )

        if match is None:
            continue

        value = match.group(0).strip().lower()

        return re.sub(
            r"\s+",
            " ",
            value,
        )

    return None


def _extract_edition(
    normalized_title: str,
) -> str | None:
    """
    Pro, Ultra, Limited Edition 등의 에디션 정보를 추출한다.
    """
    for keyword in sorted(
        EDITION_KEYWORDS,
        key=len,
        reverse=True,
    ):
        if re.search(
            rf"\b{re.escape(keyword)}\b",
            normalized_title,
        ):
            return keyword

    return None


def _extract_condition(
    normalized_title: str,
    explicit_condition: str | None = None,
) -> str | None:
    """
    명시적으로 제공된 상태를 우선 사용하고,
    없으면 제목에서 상태 정보를 추출한다.
    """
    explicit = _normalize_optional_text(
        explicit_condition
    )

    if explicit:
        normalized_explicit = (
            CONDITION_ALIASES.get(
                explicit,
                explicit,
            )
        )

        return normalized_explicit

    found: set[str] = set()

    for alias, normalized in CONDITION_ALIASES.items():
        if re.search(
            rf"(?<![a-z0-9가-힣])"
            rf"{re.escape(alias)}"
            rf"(?![a-z0-9가-힣])",
            normalized_title,
        ):
            found.add(normalized)

    for condition in CONDITION_PRIORITY:
        if condition in found:
            return condition

    return None


def _extract_brand(
    normalized_title: str,
    explicit_brand: str | None = None,
    known_brands: Iterable[str] = KNOWN_BRANDS,
) -> str | None:
    """
    Product에 입력된 브랜드를 우선 사용하고,
    없으면 제목에서 알려진 브랜드를 찾는다.
    """
    explicit = _normalize_optional_text(
        explicit_brand
    )

    if explicit:
        return explicit

    for brand in sorted(
        {
            str(value).strip().lower()
            for value in known_brands
            if str(value).strip()
        },
        key=len,
        reverse=True,
    ):
        if re.search(
            rf"(?<![a-z0-9가-힣])"
            rf"{re.escape(brand)}"
            rf"(?![a-z0-9가-힣])",
            normalized_title,
        ):
            return brand

    return None


def _extract_category(
    normalized_title: str,
    explicit_category: str | None = None,
) -> str | None:
    """
    Product에 입력된 카테고리를 우선 사용하고,
    없으면 상품명 키워드로 추정한다.
    """
    explicit = _normalize_optional_text(
        explicit_category
    )

    if explicit:
        return explicit

    for category, keywords in CATEGORY_KEYWORDS.items():
        for keyword in sorted(
            keywords,
            key=len,
            reverse=True,
        ):
            if re.search(
                rf"(?<![a-z0-9가-힣])"
                rf"{re.escape(keyword)}"
                rf"(?![a-z0-9가-힣])",
                normalized_title,
            ):
                return category

    return None


def _extract_model_number(
    normalized_title: str,
    *,
    explicit_model_number: str | None = None,
    brand: str | None = None,
) -> str | None:
    """
    Product에 입력된 모델 번호를 우선 사용한다.

    명시값이 없으면 숫자가 포함된 모델 후보를 제목에서 찾는다.
    """
    explicit = _normalize_optional_text(
        explicit_model_number
    )

    if explicit:
        return explicit

    tokens = normalized_title.split()

    filtered_tokens = [
        token
        for token in tokens
        if token not in MODEL_STOP_TOKENS
        and not re.fullmatch(
            r"\d+(?:\.\d+)?(?:kb|mb|gb|tb)",
            token,
        )
        and not re.fullmatch(
            r"qty\d+",
            token,
        )
    ]

    if brand:
        brand_tokens = set(
            brand.split()
        )
        filtered_tokens = [
            token
            for token in filtered_tokens
            if token not in brand_tokens
        ]

    model_candidates: list[str] = []

    for index, token in enumerate(filtered_tokens):
        if not any(
            character.isdigit()
            for character in token
        ):
            continue

        start = max(
            0,
            index - 1,
        )
        end = min(
            len(filtered_tokens),
            index + 3,
        )

        candidate_tokens = (
            filtered_tokens[start:end]
        )

        candidate = " ".join(
            candidate_tokens
        ).strip()

        if candidate:
            model_candidates.append(
                candidate
            )

    if not model_candidates:
        return None

    return max(
        model_candidates,
        key=lambda value: (
            len(value.split()),
            len(value),
        ),
    )


def extract_product_attributes(
    title: str,
    *,
    brand: str | None = None,
    model_number: str | None = None,
    category: str | None = None,
    condition: str | None = None,
) -> ProductAttributes:
    """
    문자열 상품명과 선택적 메타데이터에서
    범용 상품 속성을 추출한다.
    """
    detailed = normalize_title_detailed(
        title
    )

    resolved_brand = _extract_brand(
        detailed.normalized,
        explicit_brand=brand,
    )

    resolved_category = _extract_category(
        detailed.normalized,
        explicit_category=category,
    )

    resolved_model_number = (
        _extract_model_number(
            detailed.normalized,
            explicit_model_number=model_number,
            brand=resolved_brand,
        )
    )

    resolved_quantity = _extract_quantity(
        detailed.normalized
    )

    is_bundle = detailed.is_bundle or (
        resolved_quantity is not None
        and resolved_quantity > 1
    )

    return ProductAttributes(
        normalized_title=detailed.normalized,
        brand=resolved_brand,
        model_number=resolved_model_number,
        category=resolved_category,
        capacity=_extract_capacity(
            detailed.normalized
        ),
        color=_extract_color(
            detailed.tokens
        ),
        size=_extract_size(
            detailed.normalized
        ),
        edition=_extract_edition(
            detailed.normalized
        ),
        condition=_extract_condition(
            detailed.normalized,
            explicit_condition=condition,
        ),
        quantity=resolved_quantity,
        is_bundle=is_bundle,
        is_accessory=detailed.is_accessory,
        tokens=detailed.tokens,
    )


def extract_attributes_from_product(
    product: Product,
) -> ProductAttributes:
    """
    공통 Product 모델에서 상품 속성을 추출한다.

    Product에 저장된 브랜드, 모델 번호,
    카테고리, 상태를 제목보다 우선 활용한다.
    """
    if not isinstance(product, Product):
        raise TypeError(
            "product는 Product 객체여야 합니다."
        )

    return extract_product_attributes(
        title=product.title,
        brand=product.brand,
        model_number=product.model_number,
        category=product.category,
        condition=product.condition,
    )