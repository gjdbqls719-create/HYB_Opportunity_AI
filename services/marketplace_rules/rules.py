from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from .models import MarketplaceRule


MARKETPLACE_RULES: tuple[MarketplaceRule, ...] = (
    # ---------------------------------------------------------
    # eBay 기본 규칙
    # ---------------------------------------------------------
    MarketplaceRule(
        marketplace="ebay",
        marketplace_fee_rate=Decimal("0.13"),
        payment_fee_rate=Decimal("0.03"),
        fixed_fee=Decimal("0.30"),
        priority=0,
        description="eBay 기본 수수료 규칙",
    ),

    # eBay 국가 규칙
    MarketplaceRule(
        marketplace="ebay",
        country_code="US",
        marketplace_fee_rate=Decimal("0.13"),
        priority=10,
        description="eBay 미국 기본 규칙",
    ),
    MarketplaceRule(
        marketplace="ebay",
        country_code="GB",
        marketplace_fee_rate=Decimal("0.14"),
        priority=10,
        description="eBay 영국 기본 규칙",
    ),

    # eBay 카테고리 규칙
    MarketplaceRule(
        marketplace="ebay",
        category="electronics",
        marketplace_fee_rate=Decimal("0.12"),
        priority=20,
        description="eBay 전자제품 카테고리 규칙",
    ),
    MarketplaceRule(
        marketplace="ebay",
        category="fashion",
        marketplace_fee_rate=Decimal("0.15"),
        priority=20,
        description="eBay 패션 카테고리 규칙",
    ),
    MarketplaceRule(
        marketplace="ebay",
        category="books",
        marketplace_fee_rate=Decimal("0.12"),
        priority=20,
        description="eBay 도서 카테고리 규칙",
    ),

    # eBay 국가 + 카테고리 규칙
    MarketplaceRule(
        marketplace="ebay",
        category="electronics",
        country_code="US",
        marketplace_fee_rate=Decimal("0.125"),
        priority=30,
        description="eBay 미국 전자제품 규칙",
    ),

    # ---------------------------------------------------------
    # Amazon 기본 규칙
    # ---------------------------------------------------------
    MarketplaceRule(
        marketplace="amazon",
        marketplace_fee_rate=Decimal("0.15"),
        payment_fee_rate=Decimal("0.03"),
        fixed_fee=Decimal("0.30"),
        priority=0,
        description="Amazon 기본 수수료 규칙",
    ),

    # Amazon 국가 규칙
    MarketplaceRule(
        marketplace="amazon",
        country_code="US",
        marketplace_fee_rate=Decimal("0.15"),
        priority=10,
        description="Amazon 미국 기본 규칙",
    ),
    MarketplaceRule(
        marketplace="amazon",
        country_code="JP",
        marketplace_fee_rate=Decimal("0.15"),
        priority=10,
        description="Amazon 일본 기본 규칙",
    ),

    # Amazon 카테고리 규칙
    MarketplaceRule(
        marketplace="amazon",
        category="electronics",
        marketplace_fee_rate=Decimal("0.12"),
        priority=20,
        description="Amazon 전자제품 카테고리 규칙",
    ),
    MarketplaceRule(
        marketplace="amazon",
        category="fashion",
        marketplace_fee_rate=Decimal("0.17"),
        priority=20,
        description="Amazon 패션 카테고리 규칙",
    ),
    MarketplaceRule(
        marketplace="amazon",
        category="books",
        marketplace_fee_rate=Decimal("0.15"),
        priority=20,
        description="Amazon 도서 카테고리 규칙",
    ),

    # Amazon 국가 + 카테고리 규칙
    MarketplaceRule(
        marketplace="amazon",
        category="electronics",
        country_code="US",
        marketplace_fee_rate=Decimal("0.13"),
        priority=30,
        description="Amazon 미국 전자제품 규칙",
    ),
)


def get_marketplace_rules(
    marketplace: str | None = None,
    *,
    include_disabled: bool = False,
) -> tuple[MarketplaceRule, ...]:
    """
    등록된 마켓플레이스 규칙 목록을 반환한다.

    marketplace를 전달하면 해당 마켓플레이스의
    규칙만 필터링한다.
    """
    normalized_marketplace = (
        str(marketplace).strip().lower()
        if marketplace is not None
        else None
    )

    rules: list[MarketplaceRule] = []

    for rule in MARKETPLACE_RULES:
        if not include_disabled and not rule.enabled:
            continue

        if (
            normalized_marketplace is not None
            and rule.marketplace != normalized_marketplace
        ):
            continue

        rules.append(rule)

    return tuple(rules)


def register_marketplace_rules(
    rules: Iterable[MarketplaceRule],
) -> tuple[MarketplaceRule, ...]:
    """
    전달된 규칙을 검증해 tuple로 반환한다.

    현재 기본 규칙 상수를 직접 변경하지 않고,
    사용자 정의 Rules Engine을 생성할 때 사용할 수 있다.
    """
    registered: list[MarketplaceRule] = []

    for rule in rules:
        if not isinstance(rule, MarketplaceRule):
            raise TypeError(
                "모든 규칙은 MarketplaceRule이어야 합니다."
            )

        registered.append(rule)

    return tuple(registered)