from decimal import Decimal

import pytest

from engine.opportunity import calculate_opportunity
from services.marketplace_rules import (
    MarketplaceRule,
    MarketplaceRuleResolver,
    get_marketplace_rules,
    resolve_marketplace_rule,
)


def test_get_ebay_marketplace_rules() -> None:
    rules = get_marketplace_rules("ebay")

    assert rules
    assert all(
        rule.marketplace == "ebay"
        for rule in rules
    )


def test_resolve_default_ebay_rule() -> None:
    resolved = resolve_marketplace_rule(
        marketplace="ebay",
    )

    assert resolved.has_rule is True
    assert resolved.source == "default"
    assert resolved.rule is not None
    assert (
        resolved.rule.marketplace_fee_rate
        == Decimal("0.13")
    )


def test_resolve_category_rule() -> None:
    resolved = resolve_marketplace_rule(
        marketplace="ebay",
        category="electronics",
    )

    assert resolved.has_rule is True
    assert resolved.source == "matched"
    assert resolved.rule is not None
    assert resolved.rule.category == "electronics"
    assert (
        resolved.rule.marketplace_fee_rate
        == Decimal("0.12")
    )


def test_resolve_country_and_category_rule() -> None:
    resolved = resolve_marketplace_rule(
        marketplace="ebay",
        category="electronics",
        country_code="US",
    )

    assert resolved.has_rule is True
    assert resolved.rule is not None
    assert resolved.rule.country_code == "US"
    assert resolved.rule.category == "electronics"
    assert (
        resolved.rule.marketplace_fee_rate
        == Decimal("0.125")
    )


def test_more_specific_rule_wins_over_priority() -> None:
    rules = (
        MarketplaceRule(
            marketplace="ebay",
            marketplace_fee_rate=Decimal("0.10"),
            priority=100,
        ),
        MarketplaceRule(
            marketplace="ebay",
            category="electronics",
            marketplace_fee_rate=Decimal("0.20"),
            priority=1,
        ),
    )

    resolver = MarketplaceRuleResolver(
        rules=rules,
    )

    resolved = resolver.resolve(
        marketplace="ebay",
        category="electronics",
    )

    assert resolved.rule is not None
    assert resolved.rule.category == "electronics"
    assert (
        resolved.rule.marketplace_fee_rate
        == Decimal("0.20")
    )


def test_disabled_rule_is_not_selected() -> None:
    rules = (
        MarketplaceRule(
            marketplace="ebay",
            category="electronics",
            marketplace_fee_rate=Decimal("0.20"),
            priority=100,
            enabled=False,
        ),
        MarketplaceRule(
            marketplace="ebay",
            marketplace_fee_rate=Decimal("0.13"),
        ),
    )

    resolver = MarketplaceRuleResolver(
        rules=rules,
    )

    resolved = resolver.resolve(
        marketplace="ebay",
        category="electronics",
    )

    assert resolved.rule is not None
    assert resolved.rule.category is None
    assert resolved.source == "default"


def test_unknown_marketplace_returns_no_rule() -> None:
    resolved = resolve_marketplace_rule(
        marketplace="unknown",
    )

    assert resolved.has_rule is False
    assert resolved.rule is None
    assert resolved.source == "none"


def test_invalid_country_code_is_rejected() -> None:
    with pytest.raises(
        ValueError,
        match="국가 코드는 2자리여야 합니다",
    ):
        MarketplaceRule(
            marketplace="ebay",
            country_code="USA",
        )


def test_opportunity_uses_marketplace_category_rule() -> None:
    result = calculate_opportunity(
        {
            "marketplace": "ebay",
            "category": "electronics",
            "purchase_price": 50,
            "selling_price": 100,
            "use_fee_profile": True,
            "use_marketplace_rules": True,
        }
    )

    assert result["marketplace_fee_rate"] == 0.12
    assert result["marketplace_fee"] == 12.0
    assert result["payment_fee"] == 3.0
    assert result["fixed_fee"] == 0.3
    assert result["total_marketplace_fees"] == 15.3
    assert result["marketplace_rule_source"] == "matched"
    assert (
        result["marketplace_rule_description"]
        == "eBay 전자제품 카테고리 규칙"
    )


def test_explicit_fee_override_wins_over_rule() -> None:
    result = calculate_opportunity(
        {
            "marketplace": "ebay",
            "category": "electronics",
            "purchase_price": 50,
            "selling_price": 100,
            "use_fee_profile": True,
            "use_marketplace_rules": True,
            "marketplace_fee_rate": 0.08,
        }
    )

    assert result["marketplace_fee_rate"] == 0.08
    assert result["marketplace_fee"] == 8.0
    assert result["marketplace_rule_source"] == "matched"


def test_rules_are_disabled_by_default() -> None:
    result = calculate_opportunity(
        {
            "marketplace": "ebay",
            "category": "electronics",
            "purchase_price": 50,
            "selling_price": 100,
            "use_fee_profile": True,
        }
    )

    assert result["marketplace_fee_rate"] == 0.13
    assert result["use_marketplace_rules"] is False
    assert result["marketplace_rule_source"] == "disabled"