from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import uuid4

from app.application.change import (
    DetectLatestPriceChangeUseCase,
)
from app.application.change.models import (
    ChangeDetectionResponse,
)
from app.infrastructure.change import (
    PriceHistorySnapshotProvider,
)
from app.models import Product
from app.domain.opportunity import EconomicsCalculation
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
    build_verified_economics_input,
    calculate_verified_economics,
)
from engine.price_intelligence import (
    PriceIntelligence,
    analyze_product_prices,
)
from engine.price_trend import (
    PriceTrend,
    analyze_price_trend,
)
from engine.production_safety import (
    apply_production_safety_gate,
    assess_production_safety,
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
from engine.inventory_analysis import (
    InventoryAnalysisResult,
    analyze_inventory,
)

from engine.seller_analysis import (
    SellerAnalysisResult,
    analyze_seller,
)

from engine.market_adjustment import (
    MarketAdjustmentResult,
    calculate_market_adjustment,
)

from engine.market_intelligence import (
    build_market_intelligence,
)

from market_data.inventory_snapshot import (
    InventorySnapshot,
)
from market_data.price_snapshot import (
    PriceSnapshot,
)

from market_data.seller_snapshot import (
    SellerSnapshot,
)
from marketplaces.ebay import (
    search_products as search_ebay_products,
)
from collectors.collection_fact import CollectionFact
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
    economics: EconomicsCalculation | None = None

    price_snapshot: PriceSnapshot | None = None
    price_change_detection: (
        ChangeDetectionResponse | None
    ) = None
    price_history_record_id: int | None = None
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

    inventory_analysis: InventoryAnalysisResult | None = None

    seller_analysis: SellerAnalysisResult | None = None

    market_adjustment: MarketAdjustmentResult | None = None

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
GroupingCorrelationSink = Callable[[tuple[int, ...], int], None]


def search_products(
    query: str,
    limit: int = 10,
    *,
    error_handler: SearchErrorHandler | None = None,
    collection_fact_sink: Callable[[CollectionFact], None] | None = None,
) -> list[Product]:
    """
    여러 마켓을 독립적으로 검색해 하나의 목록으로 합친다.

    한 마켓의 연결이 실패해도 다른 마켓 검색은 계속한다.
    모든 마켓이 실패했을 때만 RuntimeError를 발생시킨다.
    """
    marketplace_searches = (
        ("ebay", search_ebay_products),
    )

    products: list[Product] = []
    failures: list[tuple[str, Exception]] = []

    for marketplace, search in marketplace_searches:
        try:
            search_arguments: dict[str, Any] = {
                "query": query,
                "limit": limit,
            }
            if collection_fact_sink is not None:
                search_arguments["collection_fact_sink"] = collection_fact_sink
            products.extend(search(**search_arguments))
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
    *,
    grouping_correlation_sink: GroupingCorrelationSink | None = None,
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
    group_collection_positions: list[list[int]] = []

    for collection_position, product in enumerate(products):
        matched_group_position: int | None = None

        for group_position, group in enumerate(groups):
            match_result = compare_products(
                product,
                group.representative,
                match_threshold=match_threshold,
            )

            if match_result.is_match:
                matched_group_position = group_position
                break

        if matched_group_position is None:
            groups.append(
                ProductGroup(
                    products=[product],
                )
            )
            group_collection_positions.append([collection_position])
        else:
            groups[matched_group_position].products.append(product)
            group_collection_positions[matched_group_position].append(
                collection_position
            )

    if grouping_correlation_sink is not None:
        for group, collection_positions in zip(
            groups,
            group_collection_positions,
            strict=True,
        ):
            representative = group.representative
            representative_collection_position = next(
                collection_position
                for member, collection_position in zip(
                    group.products,
                    collection_positions,
                    strict=True,
                )
                if member is representative
            )
            grouping_correlation_sink(
                tuple(collection_positions),
                representative_collection_position,
            )

    return groups


def build_price_snapshot(
    *,
    product: Product,
    observed_at: datetime | None = None,
) -> PriceSnapshot:
    """
    Marketplace Product를 변경 탐지용 PriceSnapshot으로 변환한다.

    현재 Discovery 단계에는 별도의 Canonical Product ID가 없으므로
    기존 Inventory/Seller Snapshot과 동일하게 item_id를 임시
    canonical_product_id로 사용한다.
    """
    resolved_observed_at = observed_at or datetime.now(
        timezone.utc
    )
    resolved_condition = (
        product.condition.strip()
        if product.condition
        and product.condition.strip()
        else "unknown"
    )
    resolved_seller_id = (
        product.seller.strip()
        if product.seller
        and product.seller.strip()
        else None
    )

    return PriceSnapshot(
        snapshot_id=(
            "price_"
            f"{product.marketplace}_"
            f"{product.item_id}_"
            f"{uuid4().hex}"
        ),
        canonical_product_id=product.item_id,
        marketplace=product.marketplace,
        observed_at=resolved_observed_at,
        source_url=(
            product.url
            or "unknown://source"
        ),
        item_id=product.item_id,
        price=Decimal(str(product.price)),
        currency=product.currency,
        condition=resolved_condition,
        seller_id=resolved_seller_id,
    )


def _build_price_change_detector(
    *,
    repository: PriceHistoryRepository | None,
) -> DetectLatestPriceChangeUseCase | None:
    """
    PriceHistoryRepository가 제공된 경우에만
    최신 가격 변경 탐지 Use Case를 구성한다.
    """
    if repository is None:
        return None

    snapshot_provider = PriceHistorySnapshotProvider(
        repository=repository,
    )

    return DetectLatestPriceChangeUseCase(
        snapshot_provider=snapshot_provider,
    )


def _save_current_price_snapshot(
    *,
    repository: PriceHistoryRepository | None,
    product: Product,
    snapshot: PriceSnapshot,
) -> int | None:
    """
    변경 탐지가 끝난 현재 가격 Snapshot을
    append-only Price History에 저장한다.
    """
    if repository is None:
        return None

    return repository.save_product_price(
        product,
        observed_at=snapshot.observed_at,
        canonical_product_id=(
            snapshot.canonical_product_id
        ),
        seller_id=snapshot.seller_id,
    )


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
    shipping_cost: float | None = None,
    marketplace_fee_rate: float = 0.15,
    payment_fee_rate: float = 0,
    fixed_fee: float | None = None,
    marketplace_fee_known: bool = False,
    payment_fee_known: bool = False,
    fixed_fee_known: bool = False,
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
    collection_fact_sink: Callable[[CollectionFact], None] | None = None,
    grouping_correlation_sink: GroupingCorrelationSink | None = None,
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
        search_arguments: dict[str, Any] = {
            "query": cleaned_query,
            "limit": limit,
        }
        if collection_fact_sink is not None:
            search_arguments["collection_fact_sink"] = collection_fact_sink
        products = search_products(**search_arguments)
    else:
        search_arguments = {
            "query": cleaned_query,
            "limit": limit,
            "error_handler": search_error_handler,
        }
        if collection_fact_sink is not None:
            search_arguments["collection_fact_sink"] = collection_fact_sink
        products = search_products(**search_arguments)
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
        grouping_correlation_sink=grouping_correlation_sink,
    )

    price_change_detector = _build_price_change_detector(
        repository=price_history_repository,
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

        economics_input = build_verified_economics_input(
            product=representative,
            selling_price=selling_price,
            shipping_cost=shipping_cost,
            marketplace_fee_rate=(
                marketplace_fee_rate
            ),
            payment_fee_rate=payment_fee_rate,
            fixed_fee=fixed_fee,
            marketplace_fee_known=marketplace_fee_known,
            payment_fee_known=payment_fee_known,
            fixed_fee_known=fixed_fee_known,
            tax_rate=tax_rate,
            other_cost=other_cost,
        )
        economics = calculate_verified_economics(
            marketplace=representative.marketplace,
            economics=economics_input,
            minimum_net_profit=minimum_net_profit,
            minimum_roi=minimum_roi,
            estimated_monthly_sales=estimated_monthly_sales,
            competitor_count=competitor_count,
            risk_level=risk_level,
            context={
                "item_id": representative.item_id,
                "name": representative.title,
                "url": representative.url,
                "condition": representative.condition,
                "currency": representative.currency,
                "shipping_cost_source": (
                    economics_input.shipping_cost.evidence.source
                ),
                "shipping_cost_known": (
                    economics_input.shipping_cost.amount is not None
                ),
                "is_free_shipping": (
                    economics_input.shipping_cost.amount == Decimal("0")
                    if economics_input.shipping_cost.amount is not None
                    else False
                ),
            },
        )
        analysis = dict(economics.analysis)

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

        snapshot_observed_at = datetime.now(
            timezone.utc
        )

        price_snapshot = build_price_snapshot(
            product=representative,
            observed_at=snapshot_observed_at,
        )

        price_change_detection = (
            price_change_detector.execute(
                current_snapshot=price_snapshot,
            )
            if price_change_detector is not None
            else None
        )

        price_history_record_id = (
            _save_current_price_snapshot(
                repository=price_history_repository,
                product=representative,
                snapshot=price_snapshot,
            )
        )

        inventory_snapshot = InventorySnapshot(
            snapshot_id=(
                f"inventory_{representative.item_id}"
            ),
            canonical_product_id=(
                representative.item_id
            ),
            marketplace=(
                representative.marketplace
            ),
            observed_at=snapshot_observed_at,
            source_url=(
                representative.url
                or "unknown://source"
            ),
            item_id=(
                representative.item_id
            ),
            available=(
                representative.in_stock
            ),
            quantity=None,
        )

        inventory_analysis = analyze_inventory(
            inventory_snapshot
        )

        seller_snapshot = SellerSnapshot(
            snapshot_id=(
                f"seller_{representative.item_id}"
            ),
            canonical_product_id=(
                representative.item_id
            ),
            marketplace=(
                representative.marketplace
            ),
            observed_at=snapshot_observed_at,
            source_url=(
                representative.url
                or "unknown://source"
            ),
            item_id=(
                representative.item_id
            ),
            seller_id=(
                representative.seller.strip()
                if representative.seller
                else None
            ),
            seller_rating=(
                representative.rating
            ),
            seller_review_count=(
                representative.review_count
            ),
            seller_count=(
                competitor_count
            ),
        )

        seller_analysis = analyze_seller(
            seller_snapshot
        )

        market_intelligence = build_market_intelligence(
            price_trend=price_trend,
            inventory_analysis=inventory_analysis,
            seller_analysis=seller_analysis,
        )

        market_adjustment = calculate_market_adjustment(
            market_intelligence
        )


        final_opportunity_score = round(
            adjusted_opportunity_score
            + trend_score_adjustment
            + market_adjustment.adjustment,
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
            market_adjustment=market_adjustment,
        )

        safety_assessment = assess_production_safety(
            product=representative,
            analysis=analysis,
            price_intelligence=price_info,
            economics=economics,
        )
        ai_recommendation = apply_production_safety_gate(
            ai_recommendation,
            safety_assessment,
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

        analysis["production_safety_status"] = (
            ai_recommendation.safety_status
        )

        analysis["production_safety_reasons"] = (
            ai_recommendation.safety_reasons
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
                economics=economics,

                price_snapshot=price_snapshot,

                price_change_detection=(
                    price_change_detection
                ),

                price_history_record_id=(
                    price_history_record_id
                ),

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

                inventory_analysis=(
                    inventory_analysis
                ),

                seller_analysis=(
                    seller_analysis
                ),

                market_adjustment=(
                    market_adjustment
                ),
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
