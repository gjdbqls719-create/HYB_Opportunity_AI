from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from engine.product_synonyms import normalize_product_synonyms


CAPACITY_UNIT_ALIASES: dict[str, str] = {
    "기가바이트": "gb",
    "기가": "gb",
    "테라바이트": "tb",
    "테라": "tb",
    "메가바이트": "mb",
    "메가": "mb",
    "킬로바이트": "kb",
    "킬로": "kb",
}

COLOR_ALIASES: dict[str, str] = {
    "검은색": "black",
    "검정색": "black",
    "검정": "black",
    "블랙": "black",
    "흰색": "white",
    "하얀색": "white",
    "하양": "white",
    "화이트": "white",
    "빨간색": "red",
    "빨강": "red",
    "레드": "red",
    "파란색": "blue",
    "파랑": "blue",
    "블루": "blue",
    "초록색": "green",
    "초록": "green",
    "그린": "green",
    "회색": "gray",
    "그레이": "gray",
    "은색": "silver",
    "실버": "silver",
    "금색": "gold",
    "골드": "gold",
    "분홍색": "pink",
    "분홍": "pink",
    "핑크": "pink",
    "보라색": "purple",
    "보라": "purple",
    "퍼플": "purple",
    "노란색": "yellow",
    "노랑": "yellow",
    "옐로우": "yellow",
    "갈색": "brown",
    "브라운": "brown",
    "베이지": "beige",
}

BUNDLE_ALIASES: tuple[str, ...] = (
    "bundle",
    "set",
    "세트",
    "묶음",
    "패키지",
    "package",
    "pack",
)

ACCESSORY_ALIASES: tuple[str, ...] = (
    "case",
    "cover",
    "charger",
    "cable",
    "adapter",
    "stand",
    "holder",
    "screen protector",
    "케이스",
    "커버",
    "충전기",
    "케이블",
    "어댑터",
    "거치대",
)

CONDITION_ALIASES: dict[str, str] = {
    "brand new": "new",
    "new": "new",
    "새상품": "new",
    "새 제품": "new",
    "미개봉": "new",
    "unused": "new",
    "pre owned": "used",
    "pre-owned": "used",
    "used": "used",
    "중고": "used",
    "refurbished": "refurbished",
    "renewed": "refurbished",
    "리퍼비시": "refurbished",
    "리퍼": "refurbished",
}


@dataclass(frozen=True, slots=True)
class NormalizedProductTitle:
    """
    확장된 상품명 정규화 결과.
    """

    original: str
    normalized: str
    tokens: tuple[str, ...]
    is_bundle: bool
    is_accessory: bool


def _replace_aliases(
    text: str,
    aliases: dict[str, str],
) -> str:
    """
    긴 표현부터 치환해 부분 문자열 충돌을 줄인다.
    """
    sorted_aliases = sorted(
        aliases.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )

    for source, target in sorted_aliases:
        text = re.sub(
            rf"(?<![a-z0-9가-힣])"
            rf"{re.escape(source)}"
            rf"(?![a-z0-9가-힣])",
            target,
            text,
        )

    return text


def _normalize_capacity_units(text: str) -> str:
    """
    한글 및 영문 저장 용량 표현을 통일한다.

    예:
        256 기가
        256기가
        256 GB
        256gb
        → 256gb
    """
    for alias, unit in sorted(
        CAPACITY_UNIT_ALIASES.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    ):
        text = re.sub(
            rf"(?<!\d)"
            rf"(\d+(?:\.\d+)?)\s*"
            rf"{re.escape(alias)}"
            rf"(?![a-z0-9가-힣])",
            rf"\1{unit}",
            text,
        )

    text = re.sub(
        r"\b(\d+(?:\.\d+)?)\s*(kb|mb|gb|tb)\b",
        r"\1\2",
        text,
    )

    return text


def _normalize_quantity(text: str) -> str:
    """
    수량 표현을 qty 토큰으로 통일한다.

    예:
        2개
        2 pcs
        2-pack
        pack of 2
        → qty2
    """
    quantity_patterns = (
        r"(?<!\d)(\d+)\s*개(?![가-힣])",
        r"\b(\d+)\s*(?:pcs?|pieces?)\b",
        r"\b(\d+)\s*[- ]?pack\b",
        r"\bpack\s+of\s+(\d+)\b",
        r"\bset\s+of\s+(\d+)\b",
    )

    for pattern in quantity_patterns:
        text = re.sub(
            pattern,
            r" qty\1 ",
            text,
        )

    return text


def _normalize_model_boundaries(text: str) -> str:
    """
    문자와 숫자 사이를 분리하되 용량과 수량 토큰은 유지한다.

    예:
        iphone17 → iphone 17
        s24ultra → s 24 ultra
        128gb → 128gb
        qty2 → qty2
    """
    protected_tokens: dict[str, str] = {}

    def protect_token(
        match: re.Match[str],
    ) -> str:
        key = f"__protected_{len(protected_tokens)}__"
        protected_tokens[key] = match.group(0)
        return key

    text = re.sub(
        r"\b(?:"
        r"\d+(?:\.\d+)?(?:kb|mb|gb|tb)"
        r"|qty\d+"
        r")\b",
        protect_token,
        text,
    )

    text = re.sub(
        r"([a-z가-힣])(\d)",
        r"\1 \2",
        text,
    )
    text = re.sub(
        r"(\d)([a-z가-힣])",
        r"\1 \2",
        text,
    )

    for key, value in protected_tokens.items():
        text = text.replace(
            key,
            value,
        )

    return text


def _contains_alias(
    normalized_text: str,
    aliases: tuple[str, ...],
) -> bool:
    """
    독립된 단어나 표현으로 포함된 별칭만 감지한다.

    예:
        case는 감지
        showcase 안의 case는 감지하지 않음
    """
    for alias in sorted(
        aliases,
        key=len,
        reverse=True,
    ):
        if re.search(
            rf"(?<![a-z0-9가-힣])"
            rf"{re.escape(alias)}"
            rf"(?![a-z0-9가-힣])",
            normalized_text,
        ):
            return True

    return False


def normalize_title_detailed(
    title: str,
) -> NormalizedProductTitle:
    """
    상품명을 범용 비교용 문자열로 정규화한다.

    처리 순서:
        1. 유니코드 및 소문자 정규화
        2. 한영 상품 동의어 통일
        3. 용량 및 수량 정규화
        4. 색상 정규화
        5. 모델 문자·숫자 경계 분리
        6. 불필요한 문장부호 제거
    """
    if title is None:
        raise ValueError(
            "상품명은 비어 있을 수 없습니다."
        )

    original = str(title)

    normalized = unicodedata.normalize(
        "NFKC",
        original,
    )
    normalized = normalized.strip().lower()

    if not normalized:
        raise ValueError(
            "상품명은 비어 있을 수 없습니다."
        )

    # 한국어와 영문 상품 표현을 동일한 기준으로 통일한다.
    normalized = normalize_product_synonyms(
        normalized
    )

    normalized = re.sub(
        r"\bgrey\b",
        "gray",
        normalized,
    )

    normalized = _normalize_capacity_units(
        normalized
    )
    normalized = _normalize_quantity(
        normalized
    )
    normalized = _replace_aliases(
        normalized,
        COLOR_ALIASES,
    )
    normalized = _normalize_model_boundaries(
        normalized
    )

    normalized = re.sub(
        r"[^a-z0-9가-힣.]+",
        " ",
        normalized,
    )
    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    ).strip()

    if not normalized:
        raise ValueError(
            "정규화된 상품명은 비어 있을 수 없습니다."
        )

    tokens = tuple(
        token
        for token in normalized.split()
        if token
    )

    return NormalizedProductTitle(
        original=original,
        normalized=normalized,
        tokens=tokens,
        is_bundle=_contains_alias(
            normalized,
            BUNDLE_ALIASES,
        ),
        is_accessory=_contains_alias(
            normalized,
            ACCESSORY_ALIASES,
        ),
    )


def normalize_title(
    title: str,
) -> str:
    """
    정규화 문자열만 반환하는 편의 함수.
    """
    return normalize_title_detailed(
        title
    ).normalized