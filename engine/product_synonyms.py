from __future__ import annotations

import re
from types import MappingProxyType
from typing import Final, Mapping


# 긴 표현이 짧은 표현보다 먼저 처리되어야 한다.
#
# 예:
#   "프로 맥스"를 먼저 변환하지 않으면
#   "프로"만 먼저 변환되어 의도하지 않은 결과가 생길 수 있다.
_PRODUCT_SYNONYM_SOURCE: dict[str, str] = {
    # Apple 제품군
    "아이폰": "iphone",
    "아이패드": "ipad",
    "맥북": "macbook",
    "애플워치": "apple watch",
    "에어팟": "airpods",

    # Samsung 제품군
    "갤럭시": "galaxy",
    "갤럭시북": "galaxy book",
    "갤럭시탭": "galaxy tab",
    "갤럭시워치": "galaxy watch",
    "갤럭시버즈": "galaxy buds",

    # 브랜드
    "애플": "apple",
    "삼성전자": "samsung",
    "삼성": "samsung",
    "엘지전자": "lg",
    "엘지": "lg",
    "소니": "sony",
    "샤오미": "xiaomi",
    "레노버": "lenovo",
    "에이수스": "asus",
    "아수스": "asus",

    # 모델 등급 및 에디션
    "프로맥스": "pro max",
    "프로 맥스": "pro max",
    "플러스": "plus",
    "프로": "pro",
    "맥스": "max",
    "울트라": "ultra",
    "미니": "mini",
    "라이트": "lite",
    "에어": "air",
    "스탠다드": "standard",
    "기본형": "standard",

    # 연결 방식
    "와이파이": "wifi",
    "셀룰러": "cellular",
    "블루투스": "bluetooth",
    "유선": "wired",
    "무선": "wireless",

    # 상품 형태
    "본체": "main unit",
    "단품": "single",
    "낱개": "single",
    "세트상품": "bundle",
    "묶음상품": "bundle",

    # 액세서리
    "케이스": "case",
    "커버": "cover",
    "충전기": "charger",
    "충전 케이블": "charging cable",
    "케이블": "cable",
    "어댑터": "adapter",
    "거치대": "stand",
    "보호필름": "screen protector",
    "보호 필름": "screen protector",
    "액정보호필름": "screen protector",
    "액정 보호 필름": "screen protector",

    # 상품 상태
    "새상품": "new",
    "새 제품": "new",
    "미개봉": "new",
    "중고상품": "used",
    "중고 제품": "used",
    "중고": "used",
    "리퍼비시": "refurbished",
    "리퍼제품": "refurbished",
    "리퍼 제품": "refurbished",
    "리퍼": "refurbished",
}


PRODUCT_SYNONYMS: Final[Mapping[str, str]] = MappingProxyType(
    _PRODUCT_SYNONYM_SOURCE
)


def _replace_synonym(
    text: str,
    source: str,
    target: str,
) -> str:
    """
    상품명 안의 동의어를 독립된 표현으로 치환한다.

    한글 뒤에 숫자가 바로 붙은 모델 표현도 지원한다.

    예:
        아이폰15
        → iphone15

        갤럭시S24
        → galaxyS24
    """
    pattern = (
        rf"(?<![a-z0-9가-힣])"
        rf"{re.escape(source)}"
        rf"(?![a-z가-힣])"
    )

    return re.sub(
        pattern,
        target,
        text,
        flags=re.IGNORECASE,
    )


def normalize_product_synonyms(
    text: str,
) -> str:
    """
    한국어 상품 표현을 범용 영문 표현으로 통일한다.

    이 함수는 문장부호 제거, 문자·숫자 분리, 색상 및 용량
    정규화를 담당하지 않는다. 동의어 변환만 담당한다.

    예:
        아이폰15 프로 맥스
        → iphone15 pro max

        삼성 갤럭시 S24 울트라
        → samsung galaxy S24 ultra
    """
    if text is None:
        raise ValueError(
            "동의어를 변환할 문자열은 비어 있을 수 없습니다."
        )

    normalized = str(text).strip()

    if not normalized:
        raise ValueError(
            "동의어를 변환할 문자열은 비어 있을 수 없습니다."
        )

    sorted_synonyms = sorted(
        PRODUCT_SYNONYMS.items(),
        key=lambda item: len(item[0]),
        reverse=True,
    )

    for source, target in sorted_synonyms:
        normalized = _replace_synonym(
            normalized,
            source,
            target,
        )

    normalized = re.sub(
        r"\s+",
        " ",
        normalized,
    ).strip()

    return normalized