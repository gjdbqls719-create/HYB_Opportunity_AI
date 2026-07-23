from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from app.models import Product
from engine.ai_partner import (
    AIPartnerReport,
    build_ai_partner_report,
)
from engine.ai_memory import (
    AIMemoryInsight,
    HistoricalOpportunity,
    analyze_ai_memory,
)
from engine.confidence import (
    ConfidenceResult,
    calculate_price_confidence,
)
from engine.decision_report import (
    DecisionReport,
    build_decision_report,
)
from engine.opportunity import (
    calculate_product_opportunity,
)
from engine.price_intelligence import (
    PriceIntelligence,
    analyze_product_prices,
)
from engine.price_trend import (
    PriceTrend,
    analyze_price_trend,
)
from engine.product_matching import compare_products
from engine.recommendation import (
    RecommendationResult,
    generate_recommendation,
)
from engine.trend_scoring import (
    TrendScoreResult,
    calculate_trend_score,
)
from marketplaces.amazon import (
    search_products as search_amazon_products,
)
from marketplaces.ebay import (
    search_products as search_ebay_products,
)
from services.currency import (
    CurrencyConverter,
    normalize_currency_code,
    normalize_products_currency,
)
from storage.price_history import (
    PriceHistoryRepository,
)


@dataclass(slots=True)
class ProductGroup:
    """
    서로 같은 상품으로 판단된 Product 묶음.
    """

    products: list[Product]

    @property
    def representative(self) -> Product:
        return min(
            self.products,
            key=lambda product: product.price,
        )


@dataclass(slots=True)
class OpportunityResult:
    """
    최종 상품 기회 분석 결과.
    """

    product: Product
    analysis: dict[str, Any]
    matched_product_count: int
    price_intelligence: PriceIntelligence

    confidence: ConfidenceResult | None = None
    adjusted_opportunity_score: float = 0.0

    price_trend: PriceTrend | None = None
    trend_score: TrendScoreResult | None = None
    trend_score_adjustment: float = 0.0

    final_opportunity_score: float = 0.0

    ai_recommendation: (
        RecommendationResult | None
    ) = None

    decision_report: DecisionReport | None = None

    ai_partner_report: AIPartnerReport | None = None

    memory_insight: AIMemoryInsight | None = None

class OpportunityHistoryLoader(Protocol):
    """
    AI Memory용 과거 기회 기록을 제공하는 저장소 규약.
    """

    def load_ai_memory_history(
        self,
        *,
        limit: int = 500,
    ) -> list[HistoricalOpportunity]:
        ...


SearchErrorHandler = Callable[[str, Exception], None]


def search_products(
    query: str,
    limit: int = 10,
    *,
    error_handler: SearchErrorHandler | None = None,
) -> list[Product]:
    """
    여러 마켓을 독립적으로 검색해 하나의 목록으로 합친다.

    한 마켓의 연결이 실패해도 다른 마켓 검색은 계속한다.
    모든 마켓이 실패했을 때만 RuntimeError를 발생시킨다.
    """
    marketplace_searches = (
        ("ebay", search_ebay_products),
        ("amazon", search_amazon_products),
    )

    products: list[Product] = []
    failures: list[tuple[str, Exception]] = []

    for marketplace, search in marketplace_searches:
        try:
            products.extend(
                search(
                    query=query,
                    limit=limit,
                )
            )
        except (RuntimeError, ValueError) as error:
            failures.append((marketplace, error))

            if error_handler is not None:
                error_handler(marketplace, error)

    if len(failures) == len(marketplace_searches):
        details = "; ".join(
            f"{marketplace}: {error}"
            for marketplace, error in failures
        )

        raise RuntimeError(
            "모든 마켓 검색에 실패했습니다. "
            f"{details}"
        )

    return products


def group_similar_products(
    products: list[Product],
    match_threshold: float = 75.0,
) -> list[ProductGroup]:
    """
    제목이 유사한 상품을 같은 그룹으로 묶는다.
    """
    if not 0 <= match_threshold <= 100:
        raise ValueError(
            "match_threshold는 0 이상 "
            "100 이하여야 합니다."
        )

    groups: list[ProductGroup] = []

    for product in products:
        matched_group: ProductGroup | None = None

        for group in groups:
            match_result = compare_products(
                product,
                group.representative,
                match_threshold=match_threshold,
            )

            if match_result.is_match:
                matched_group = group
                break

        if matched_group is None:
            groups.append(
                ProductGroup(
                    products=[product],
                )
            )
        else:
            matched_group.products.append(product)

    return groups


def _load_price_trend(
    *,
    repository: PriceHistoryRepository | None,
    product: Product,
) -> PriceTrend | None:
    """
    데이터베이스에 저장된 가격 이력을 분석한다.
    """
    if repository is None:
        return None

    records = repository.get_product_history(
        marketplace=product.marketplace,
        item_id=product.item_id,
    )

    if not records:
        return None

    return analyze_price_trend(records)


def find_best_opportunities(
    query: str,
    *,
    selling_price_multiplier: float = 1.5,
    shipping_cost: float = 0,
    marketplace_fee_rate: float = 0.15,
    payment_fee_rate: float = 0,
    tax_rate: float = 0,
    other_cost: float = 0,
    minimum_net_profit: float = 0,
    minimum_roi: float = 0,
    estimated_monthly_sales: int = 100,
    competitor_count: int = 20,
    risk_level: str = "medium",
    limit: int = 10,
    match_threshold: float = 75.0,
    price_history_repository: (
        PriceHistoryRepository | None
    ) = None,
    search_error_handler: (
        SearchErrorHandler | None
    ) = None,
    opportunity_history_repository: (
        OpportunityHistoryLoader | None
    ) = None,
    ai_memory_history: list[HistoricalOpportunity] | None = None,
    currency_converter: CurrencyConverter | None = None,
    target_currency: str | None = None,
) -> list[OpportunityResult]:
    """상품 검색부터 최종 AI Partner 보고서까지 생성한다."""
    cleaned_query = query.strip()

    if not cleaned_query:
        raise ValueError(
            "검색어를 입력해야 합니다."
        )

    if selling_price_multiplier <= 0:
        raise ValueError(
            "selling_price_multiplier는 "
            "0보다 커야 합니다."
        )

    resolved_target_currency: str | None = None

    if target_currency is not None:
        resolved_target_currency = normalize_currency_code(
            target_currency,
            "대상 통화",
        )

        if currency_converter is None:
            raise ValueError(
                "target_currency를 사용하려면 "
                "currency_converter가 필요합니다."
            )

    resolved_ai_memory_history = (
        ai_memory_history
    )

    if (
        resolved_ai_memory_history is None
        and opportunity_history_repository
        is not None
    ):
        resolved_ai_memory_history = (
            opportunity_history_repository
            .load_ai_memory_history()
        )

    if search_error_handler is None:
        products = search_products(
            query=cleaned_query,
            limit=limit,
        )
    else:
        products = search_products(
            query=cleaned_query,
            limit=limit,
            error_handler=search_error_handler,
        )
    currency_normalized = False

    if resolved_target_currency is not None:
        if currency_converter is None:
            raise RuntimeError(
                "통화 변환기가 설정되지 않았습니다."
            )

        products = normalize_products_currency(
            products,
            converter=currency_converter,
            target_currency=resolved_target_currency,
        )

        currency_normalized = True

    product_groups = group_similar_products(
        products,
        match_threshold=match_threshold,
    )

    results: list[OpportunityResult] = []

    for group in product_groups:
        representative = group.representative

        price_info = analyze_product_prices(
            group.products,
            fallback_multiplier=(
                selling_price_multiplier
            ),
        )

        used_fallback_price = (
            price_info.sample_size == 1
        )

        confidence = calculate_price_confidence(
            price_info.sample_size,
            used_fallback_price=(
                used_fallback_price
            ),
        )

        selling_price = (
            price_info.recommended_selling_price
        )

        analysis = calculate_product_opportunity(
            product=representative,
            selling_price=selling_price,
            shipping_cost=shipping_cost,
            marketplace_fee_rate=(
                marketplace_fee_rate
            ),
            payment_fee_rate=payment_fee_rate,
            tax_rate=tax_rate,
            other_cost=other_cost,
            minimum_net_profit=minimum_net_profit,
            minimum_roi=minimum_roi,
            estimated_monthly_sales=(
                estimated_monthly_sales
            ),
            competitor_count=competitor_count,
            risk_level=risk_level,
        )

        raw_opportunity_score = float(
            analysis["opportunity_score"]
        )

        adjusted_opportunity_score = round(
            raw_opportunity_score
            * confidence.confidence_multiplier,
            2,
        )

        price_trend = _load_price_trend(
            repository=price_history_repository,
            product=representative,
        )

        trend_score = calculate_trend_score(
            price_trend
        )

        trend_score_adjustment = (
            trend_score.adjustment
        )

        final_opportunity_score = round(
            adjusted_opportunity_score
            + trend_score_adjustment,
            2,
        )

        ai_recommendation = generate_recommendation(
            final_opportunity_score=(
                final_opportunity_score
            ),
            roi=float(analysis["roi"]),
            net_profit=float(
                analysis["net_profit"]
            ),
            competitor_count=int(
                analysis["competitor_count"]
            ),
            risk_level=str(
                analysis["risk_level"]
            ),
            confidence=confidence,
            price_trend=price_trend,
        )

        decision_report = build_decision_report(
            recommendation=ai_recommendation,
            confidence=confidence,
            price_trend=price_trend,
        )
        memory_insight = analyze_ai_memory(
            current_opportunity_score=final_opportunity_score,
            current_roi=float(analysis["roi"]),
            current_net_profit=float(
                analysis["net_profit"]
            ),
            current_success_probability=float(
                ai_recommendation.success_probability
            ),
            history=resolved_ai_memory_history or [],
        )
        ai_partner_report = build_ai_partner_report(
            recommendation=ai_recommendation,
            decision_report=decision_report,
            memory_insight=memory_insight,
        )
        analysis["analysis_currency"] = (
            price_info.currency
        )

        analysis["currency_normalized"] = (
            currency_normalized
        )
        
        analysis["raw_opportunity_score"] = (
            raw_opportunity_score
        )

        analysis["confidence_score"] = (
            confidence.confidence_score
        )

        analysis["confidence_level"] = (
            confidence.confidence_level
        )

        analysis["used_fallback_price"] = (
            confidence.used_fallback_price
        )

        analysis["adjusted_opportunity_score"] = (
            adjusted_opportunity_score
        )

        analysis["trend_score_adjustment"] = (
            trend_score_adjustment
        )

        analysis["final_opportunity_score"] = (
            final_opportunity_score
        )

        analysis["recommendation_score"] = (
            ai_recommendation.score
        )

        analysis["recommendation_grade"] = (
            ai_recommendation.grade
        )

        analysis["recommendation_action"] = (
            ai_recommendation.action
        )

        analysis["success_probability"] = (
            ai_recommendation.success_probability
        )

        analysis["recommendation_stars"] = (
            ai_recommendation.stars
        )

        analysis["recommendation_star_display"] = (
            ai_recommendation.star_display
        )

        analysis["recommendation_reasons"] = (
            ai_recommendation.reasons
        )

        analysis["recommendation_warnings"] = (
            ai_recommendation.warnings
        )

        analysis["recommendation_summary"] = (
            ai_recommendation.summary
        )

        analysis["decision_report_strengths"] = (
            decision_report.strengths
        )

        analysis["decision_report_weaknesses"] = (
            decision_report.weaknesses
        )

        analysis["decision_report_market_summary"] = (
            decision_report.market_summary
        )

        analysis["decision_report_buy_timing"] = (
            decision_report.buy_timing
        )

        analysis["decision_report_ai_comment"] = (
            decision_report.ai_comment
        )

        analysis["ai_partner_title"] = (
            ai_partner_report.title
        )

        analysis["ai_partner_summary"] = (
            ai_partner_report.summary
        )

        analysis["ai_partner_recommendation"] = (
            ai_partner_report.recommendation
        )

        analysis["ai_partner_next_action"] = (
            ai_partner_report.next_action
        )
        analysis["ai_memory_summary"] = (
            memory_insight.summary
        )

        analysis["ai_memory_rank"] = (
            memory_insight.rank_label
        )

        analysis["ai_memory_percentile"] = (
            memory_insight.overall_percentile
        )
        results.append(
            OpportunityResult(
                product=representative,
                analysis=analysis,
                matched_product_count=len(
                    group.products
                ),
                price_intelligence=price_info,
                confidence=confidence,
                adjusted_opportunity_score=(
                    adjusted_opportunity_score
                ),
                price_trend=price_trend,
                trend_score=trend_score,
                trend_score_adjustment=(
                    trend_score_adjustment
                ),
                final_opportunity_score=(
                    final_opportunity_score
                ),
                ai_recommendation=(
                    ai_recommendation
                ),
                decision_report=decision_report,
                ai_partner_report=(
                    ai_partner_report
                ),
                memory_insight=memory_insight,
            )
        )

    results.sort(
        key=lambda result: (
            (
                result.ai_recommendation.score
                if result.ai_recommendation
                is not None
                else 0
            ),
            result.final_opportunity_score,
            result.analysis["net_profit"],
        ),
        reverse=True,
    )

    return results