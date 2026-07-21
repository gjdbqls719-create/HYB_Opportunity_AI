from __future__ import annotations

from engine.price_trend import (
    analyze_price_trend,
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
    repository = PriceHistoryRepository()

    print_separator()
    print("HYB Opportunity AI - 가격 추세 분석")
    print_separator()

    all_records = repository.get_all_records()

    if not all_records:
        print("저장된 가격 기록이 없습니다.")
        print(
            "먼저 python check_price_history.py를 "
            "실행해 가격을 저장하세요."
        )
        return

    latest_record = all_records[0]

    history = repository.get_product_history(
        marketplace=latest_record.marketplace,
        item_id=latest_record.item_id,
    )

    trend = analyze_price_trend(history)

    print(f"상품명: {trend.title}")
    print(f"마켓: {trend.marketplace}")
    print(f"상품 ID: {trend.item_id}")
    print(f"통화: {trend.currency}")
    print()

    print("[데이터 범위]")
    print(f"가격 표본 수: {trend.sample_size}개")
    print(f"분석 기간: {trend.period_days}일")
    print()

    print("[가격 통계]")
    print(
        f"최초 가격: "
        f"{trend.oldest_price} "
        f"{trend.currency}"
    )
    print(
        f"현재 가격: "
        f"{trend.current_price} "
        f"{trend.currency}"
    )
    print(
        f"기간 최저가: "
        f"{trend.lowest_price} "
        f"{trend.currency}"
    )
    print(
        f"기간 최고가: "
        f"{trend.highest_price} "
        f"{trend.currency}"
    )
    print(
        f"기간 평균가: "
        f"{trend.average_price} "
        f"{trend.currency}"
    )
    print()

    print("[가격 변화]")
    print(
        f"가격 변화액: "
        f"{trend.absolute_change} "
        f"{trend.currency}"
    )

    if trend.percentage_change is None:
        print("가격 변화율: 계산 불가")
    else:
        print(
            f"가격 변화율: "
            f"{trend.percentage_change}%"
        )

    print(f"가격 추세: {trend.trend_direction}")
    print(f"현재 가격 위치: {trend.price_position}")
    print()

    print("[판단]")
    print(f"추천: {trend.recommendation}")
    print(f"근거: {trend.reason}")

    if not trend.has_sufficient_history:
        print()
        print(
            "현재는 가격 기록이 1개뿐입니다. "
            "시간을 두고 가격을 다시 저장하면 "
            "실제 상승·하락 추세를 분석할 수 있습니다."
        )


if __name__ == "__main__":
    main()