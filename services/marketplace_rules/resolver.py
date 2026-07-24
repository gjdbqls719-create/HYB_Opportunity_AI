from __future__ import annotations

from collections.abc import Iterable

from .models import (
    MarketplaceRule,
    ResolvedMarketplaceRule,
)
from .rules import get_marketplace_rules


class MarketplaceRuleResolver:
    """
    마켓플레이스, 카테고리, 국가 조건을 기준으로
    가장 적합한 규칙을 선택한다.
    """

    def __init__(
        self,
        rules: Iterable[MarketplaceRule] | None = None,
    ) -> None:
        if rules is None:
            self._rules = get_marketplace_rules()
        else:
            resolved_rules: list[MarketplaceRule] = []

            for rule in rules:
                if not isinstance(rule, MarketplaceRule):
                    raise TypeError(
                        "모든 규칙은 MarketplaceRule이어야 합니다."
                    )

                resolved_rules.append(rule)

            self._rules = tuple(resolved_rules)

    @property
    def rules(self) -> tuple[MarketplaceRule, ...]:
        """
        Resolver에 등록된 규칙 목록을 반환한다.
        """
        return self._rules

    def resolve(
        self,
        *,
        marketplace: str,
        category: str | None = None,
        country_code: str | None = None,
    ) -> ResolvedMarketplaceRule:
        """
        조건에 맞는 가장 구체적이고 우선순위가 높은
        규칙을 선택한다.

        선택 기준:
        1. 조건 일치 여부
        2. specificity가 높은 규칙
        3. priority가 높은 규칙
        4. 등록 순서가 앞선 규칙
        """
        matching_rules: list[
            tuple[int, MarketplaceRule]
        ] = []

        for index, rule in enumerate(self._rules):
            if not rule.matches(
                marketplace=marketplace,
                category=category,
                country_code=country_code,
            ):
                continue

            matching_rules.append(
                (
                    index,
                    rule,
                )
            )

        if not matching_rules:
            return ResolvedMarketplaceRule(
                marketplace=marketplace,
                category=category,
                country_code=country_code,
                rule=None,
                source="none",
            )

        selected_index, selected_rule = max(
            matching_rules,
            key=lambda item: (
                item[1].specificity,
                item[1].priority,
                -item[0],
            ),
        )

        del selected_index

        source = (
            "default"
            if selected_rule.specificity == 0
            else "matched"
        )

        return ResolvedMarketplaceRule(
            marketplace=marketplace,
            category=category,
            country_code=country_code,
            rule=selected_rule,
            source=source,
        )


def resolve_marketplace_rule(
    *,
    marketplace: str,
    category: str | None = None,
    country_code: str | None = None,
    rules: Iterable[MarketplaceRule] | None = None,
) -> ResolvedMarketplaceRule:
    """
    클래스 생성 없이 사용할 수 있는 편의 함수.
    """
    resolver = MarketplaceRuleResolver(
        rules=rules,
    )

    return resolver.resolve(
        marketplace=marketplace,
        category=category,
        country_code=country_code,
    )