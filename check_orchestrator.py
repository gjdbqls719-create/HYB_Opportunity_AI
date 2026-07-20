from engine.orchestrator import find_best_opportunities
from marketplaces.ebay import search_products


def main() -> None:
    query = input("검색어: ").strip()

    if not query:
        print("검색어를 입력해야 합니다.")
        return

    print()
    print("1단계: eBay 원본 검색 확인")

    products = search_products(
        query=query,
        limit=10,
    )

    print(f"검색된 Product 수: {len(products)}개")

    if not products:
        print()
        print("eBay 검색 결과가 0개입니다.")
        print("조금 더 짧거나 일반적인 검색어로 다시 시도해 주세요.")
        print("예: iphone, gaming mouse, keyboard")
        return

    print()
    print("검색된 상품 목록")

    for index, product in enumerate(
        products,
        start=1,
    ):
        print("-" * 60)
        print(f"{index}. {product.title}")
        print(
            f"가격: {product.price} "
            f"{product.currency}"
        )
        print(f"상태: {product.condition}")
        print(f"링크: {product.url}")

    print()
    print("2단계: 상품 그룹화 및 Opportunity 분석")

    results = find_best_opportunities(
        query=query,
        limit=10,
    )

    print()
    print(f"분석된 상품 그룹: {len(results)}개")

    if not results:
        print()
        print("검색된 상품은 있지만 분석 결과가 없습니다.")
        print("이 경우 engine/orchestrator.py를 확인해야 합니다.")
        return

    for index, result in enumerate(
        results,
        start=1,
    ):
        print()
        print("=" * 60)
        print(f"{index}위")
        print(f"상품명: {result.product.title}")
        print(
            f"매입 후보 가격: "
            f"{result.product.price} "
            f"{result.product.currency}"
        )
        print(
            f"유사 상품 수: "
            f"{result.matched_product_count}개"
        )
        print(
            f"예상 판매가: "
            f"{result.analysis['selling_price']}"
        )
        print(
            f"예상 순이익: "
            f"{result.analysis['net_profit']}"
        )
        print(
            f"ROI: "
            f"{result.analysis['roi']}%"
        )
        print(
            f"기회 점수: "
            f"{result.analysis['opportunity_score']}"
        )
        print(
            f"판정: "
            f"{result.analysis['recommendation']}"
        )

        print("판단 근거:")

        for reason in result.analysis["reasons"]:
            print(f"- {reason}")

        print(f"링크: {result.product.url}")


if __name__ == "__main__":
    main()