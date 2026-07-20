from __future__ import annotations

from typing import Any

from marketplaces.ebay import search_items


def get_price_text(item: dict[str, Any]) -> str:
    price = item.get("price")

    if not isinstance(price, dict):
        return "가격 정보 없음"

    value = price.get("value", "가격 정보 없음")
    currency = price.get("currency", "")

    return f"{value} {currency}".strip()


def main() -> None:
    query = input("eBay 검색어를 입력하세요: ").strip()

    try:
        items = search_items(
            query=query,
            limit=10,
        )
    except (ValueError, RuntimeError) as error:
        print()
        print(error)
        return

    print()
    print(f"검색 결과: {len(items)}개")
    print("=" * 70)

    if not items:
        print("검색 결과가 없습니다.")
        return

    for index, item in enumerate(items, start=1):
        title = item.get("title", "제목 없음")
        price_text = get_price_text(item)
        condition = item.get("condition", "상태 정보 없음")
        item_url = item.get("itemWebUrl", "URL 없음")

        print(f"[{index}] {title}")
        print(f"가격: {price_text}")
        print(f"상태: {condition}")
        print(f"URL: {item_url}")
        print("-" * 70)


if __name__ == "__main__":
    main()