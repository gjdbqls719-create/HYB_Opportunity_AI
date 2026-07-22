from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from app.models import Product
from engine.confidence import ConfidenceResult
from engine.orchestrator import OpportunityResult
from engine.price_intelligence import PriceIntelligence
from engine.recommendation import RecommendationResult
from storage.opportunity_history import OpportunityHistoryRepository


def make_result() -> OpportunityResult:
    product = Product(
        marketplace="amazon",
        item_id="A-1",
        title="Gaming Mouse",
        price=20,
        currency="USD",
        condition="New",
        url="https://example.com/a-1",
    )
    price_info = PriceIntelligence(
        currency="USD",
        lowest_price=Decimal("20.00"),
        average_price=Decimal("30.00"),
        median_price=Decimal("30.00"),
        highest_price=Decimal("40.00"),
        price_range=Decimal("20.00"),
        price_variation_rate=Decimal("66.67"),
        price_stability_level="very_low",
        recommended_selling_price=Decimal("35.00"),
        sample_size=2,
    )
    confidence = ConfidenceResult(
        confidence_score=80,
        confidence_level="high",
        confidence_multiplier=1.0,
        sample_size=2,
        used_fallback_price=False,
        reason="enough samples",
    )
    recommendation = RecommendationResult(
        score=88,
        stars=5,
        star_display="★★★★★",
        grade="A",
        action="구매 검토",
        success_probability=82,
        reasons=("good",),
        warnings=(),
        summary="good",
    )
    return OpportunityResult(
        product=product,
        analysis={
            "net_profit": 10,
            "roi": 50,
        },
        matched_product_count=2,
        price_intelligence=price_info,
        confidence=confidence,
        final_opportunity_score=80,
        ai_recommendation=recommendation,
    )


def test_save_and_read_opportunity_results(
    tmp_path: Path,
) -> None:
    repository = OpportunityHistoryRepository(
        tmp_path / "history.db"
    )
    saved = repository.save_results(
        "gaming mouse",
        [make_result()],
        created_at=datetime(
            2026,
            7,
            21,
            tzinfo=timezone.utc,
        ),
    )
    records = repository.get_recent(limit=10)

    assert saved == 1
    assert repository.count_records() == 1
    assert records[0].query == "gaming mouse"
    assert records[0].title == "Gaming Mouse"
    assert records[0].recommended_selling_price == 35
    assert records[0].recommendation_grade == "A"