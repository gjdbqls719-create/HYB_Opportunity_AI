from __future__ import annotations

from marketplaces.ebay import search_products


def main() -> None:
    query = input("eBay 검색어를 입력하세요: ").strip()

    try:
        products = search_products(
            query=query,
            limit=10,
        )
    except (ValueError, RuntimeError) as error:
        print()
        print(error)
        return

    print()
    print(f"검색 결과: {len(products)}개")
    print("=" * 70)

    if not products:
        print("검색 결과가 없습니다.")
        return

    for index, product in enumerate(products, start=1):
        print(f"[{index}] {product.title}")
        print(f"마켓: {product.marketplace}")
        print(
            f"가격: {product.price:.2f} "
            f"{product.currency}"
        )
        print(f"상태: {product.condition}")
        print(f"상품 ID: {product.item_id}")
        print(f"URL: {product.url}")
        print("-" * 70)


if __name__ == "__main__":
    main()