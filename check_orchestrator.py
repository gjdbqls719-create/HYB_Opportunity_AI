from __future__ import annotations

from engine.orchestrator import (
    find_best_opportunities,
)
from storage.price_history import (
    PriceHistoryRepository,
)


def print_separator(
    character: str = "=",
    length: int = 70,
) -> None:
    print(character * length)


def main() -> None:
    query = "iphone"
    limit = 10

    repository = PriceHistoryRepository()

    print_separator()
    print("HYB Opportunity AI - 최종 상품 추천")
    print_separator()

    print(f"검색어: {query}")
    print()

    results = find_best_opportunities(
        query=query,
        limit=limit,
        price_history_repository=repository,
    )

    print(
        f"분석된 상품 그룹: "
        f"{len(results)}개"
    )
    print()

    for rank, result in enumerate(
        results,
        start=1,
    ):
        product = result.product
        analysis = result.analysis
        price_info = result.price_intelligence
        confidence = result.confidence
        price_trend = result.price_trend
        recommendation = (
            result.ai_recommendation
        )

        print_separator()
        print(f"{rank}위")

        if recommendation is not None:
            print(recommendation.star_display)
            print(
                f"최종 판정: "
                f"{recommendation.action}"
            )
            print(
                f"등급: "
                f"{recommendation.grade}"
            )
            print(
                f"추천 점수: "
                f"{recommendation.score}/100"
            )
            print(
                f"예상 성공 가능성: "
                f"{recommendation.success_probability}%"
            )

        print()
        print("[상품 정보]")
        print(f"상품명: {product.title}")
        print(f"마켓: {product.marketplace}")
        print(f"상품 ID: {product.item_id}")
        print(
            f"매입 후보 가격: "
            f"{product.price} "
            f"{product.currency}"
        )
        print(
            f"유사 상품 수: "
            f"{result.matched_product_count}개"
        )

        print()
        print("[시장 가격]")
        print(
            f"시장 최저가: "
            f"{price_info.lowest_price} "
            f"{price_info.currency}"
        )
        print(
            f"시장 평균가: "
            f"{price_info.average_price} "
            f"{price_info.currency}"
        )
        print(
            f"시장 중앙값: "
            f"{price_info.median_price} "
            f"{price_info.currency}"
        )
        print(
            f"시장 최고가: "
            f"{price_info.highest_price} "
            f"{price_info.currency}"
        )
        print(
            f"권장 판매가: "
            f"{price_info.recommended_selling_price} "
            f"{price_info.currency}"
        )
        print(
            f"가격 표본 수: "
            f"{price_info.sample_size}개"
        )

        print()
        print("[가격 신뢰도]")

        if confidence is None:
            print("가격 신뢰도 정보 없음")
        else:
            print(
                f"신뢰도 등급: "
                f"{confidence.confidence_level}"
            )
            print(
                f"신뢰도 점수: "
                f"{confidence.confidence_score}/100"
            )
            print(
                f"fallback 사용: "
                f"{confidence.used_fallback_price}"
            )

        print()
        print("[가격 추세]")

        if price_trend is None:
            print("저장된 가격 이력 없음")
        else:
            print(
                f"가격 이력 수: "
                f"{price_trend.sample_size}개"
            )
            print(
                f"분석 기간: "
                f"{price_trend.period_days}일"
            )
            print(
                f"가격 추세: "
                f"{price_trend.trend_direction}"
            )
            print(
                f"현재 가격 위치: "
                f"{price_trend.price_position}"
            )

            if (
                price_trend.percentage_change
                is None
            ):
                print("가격 변화율: 계산 불가")
            else:
                print(
                    f"가격 변화율: "
                    f"{price_trend.percentage_change}%"
                )

        print()
        print("[수익 분석]")
        print(
            f"예상 판매가: "
            f"{analysis.get('selling_price')} "
            f"{product.currency}"
        )
        print(
            f"예상 순이익: "
            f"{analysis.get('net_profit')} "
            f"{product.currency}"
        )
        print(
            f"ROI: "
            f"{analysis.get('roi')}%"
        )
        print(
            f"경쟁 상품 수: "
            f"{analysis.get('competitor_count')}개"
        )
        print(
            f"위험도: "
            f"{analysis.get('risk_level')}"
        )

        print()
        print("[점수 계산]")
        print(
            f"기존 기회 점수: "
            f"{analysis.get('opportunity_score')}"
        )
        print(
            f"신뢰도 보정 점수: "
            f"{result.adjusted_opportunity_score}"
        )
        print(
            f"가격 추세 보정: "
            f"{result.trend_score_adjustment}"
        )
        print(
            f"최종 기회 점수: "
            f"{result.final_opportunity_score}"
        )

        if recommendation is not None:
            print()
            print("[최종 추천 근거]")

            for reason in recommendation.reasons:
                print(f"+ {reason}")

            if recommendation.warnings:
                print()
                print("[주의 사항]")

                for warning in (
                    recommendation.warnings
                ):
                    print(f"- {warning}")

            print()
            print("[AI 요약]")
            print(recommendation.summary)

        print()
        print(f"링크: {product.url}")
        print()


if __name__ == "__main__":
    main()