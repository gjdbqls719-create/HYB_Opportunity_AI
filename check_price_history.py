from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from engine.orchestrator import search_products
from storage.price_history import (
    DEFAULT_DATABASE_PATH,
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

    print_separator()
    print("HYB Opportunity AI - 가격 이력 저장 확인")
    print_separator()

    database_path = Path(DEFAULT_DATABASE_PATH).resolve()

    print(f"데이터베이스 저장 위치: {database_path}")
    print(f"실행 전 DB 존재 여부: {database_path.exists()}")
    print()

    repository = PriceHistoryRepository(
        database_path=database_path,
    )

    print(f"DB 생성 후 존재 여부: {database_path.exists()}")
    print(f"저장 전 전체 기록 수: {repository.count_records()}개")
    print()

    print(f"상품 검색 시작: {query}")

    products = search_products(
        query=query,
        limit=limit,
    )

    print(f"검색된 전체 상품 수: {len(products)}개")

    if not products:
        print("검색된 상품이 없어 저장하지 않았습니다.")
        return

    observed_at = datetime.now(timezone.utc)

    saved_count = repository.save_products(
        products,
        observed_at=observed_at,
    )

    print(f"이번 실행에서 저장된 기록: {saved_count}개")
    print(f"저장 후 전체 기록 수: {repository.count_records()}개")
    print()

    print_separator("-")
    print("최근 저장된 가격 기록")
    print_separator("-")

    records = repository.get_all_records(limit=20)

    if not records:
        print("저장된 기록이 없습니다.")
        return

    for index, record in enumerate(records, start=1):
        print(
            f"{index}. [{record.marketplace}] "
            f"{record.title}"
        )
        print(f"   상품 ID: {record.item_id}")
        print(f"   가격: {record.price} {record.currency}")
        print(f"   상태: {record.condition}")
        print(f"   수집 시각: {record.observed_at}")
        print(f"   링크: {record.url}")
        print_separator("-")


if __name__ == "__main__":
    print("check_price_history.py 실행됨")
    main()