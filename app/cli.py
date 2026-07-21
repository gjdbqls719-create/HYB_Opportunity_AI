from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

from engine.orchestrator import OpportunityResult, find_best_opportunities
from storage.opportunity_history import (
    OpportunityHistoryRepository,
    SavedOpportunity,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="HYB Opportunity AI",
        description="마켓 상품을 검색하고 수익 기회를 분석합니다.",
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="검색할 상품명. 생략하면 실행 중에 입력받습니다.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="마켓별 검색 개수 (기본값: 10)",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=5,
        help="출력할 상위 기회 개수 (기본값: 5)",
    )
    parser.add_argument(
        "--selling-multiplier",
        type=float,
        default=1.5,
        help="표본이 하나일 때 판매가 추정 배수 (기본값: 1.5)",
    )
    parser.add_argument(
        "--shipping-cost",
        type=float,
        default=0.0,
        help="상품당 예상 배송비 (기본값: 0)",
    )
    parser.add_argument(
        "--fee-rate",
        type=float,
        default=0.15,
        help="마켓 수수료율 (기본값: 0.15)",
    )
    parser.add_argument(
        "--monthly-sales",
        type=int,
        default=100,
        help="예상 월 판매량 (기본값: 100)",
    )
    parser.add_argument(
        "--competitors",
        type=int,
        default=20,
        help="예상 경쟁자 수 (기본값: 20)",
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="저장된 최근 분석 결과를 조회합니다.",
    )
    parser.add_argument(
        "--db",
        default="data/hyb_opportunity.db",
        help="SQLite DB 경로 (기본값: data/hyb_opportunity.db)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="이번 검색 결과를 DB에 저장하지 않습니다.",
    )
    parser.add_argument(
        "--risk",
        choices=("low", "medium", "high"),
        default="medium",
        help="위험 수준 (기본값: medium)",
    )
    return parser


def _resolve_query(query: str | None, input_stream: TextIO) -> str:
    if query is not None:
        cleaned_query = query.strip()
    else:
        print("검색할 상품명을 입력하세요: ", end="", flush=True)
        cleaned_query = input_stream.readline().strip()

    if not cleaned_query:
        raise ValueError("검색어를 입력해야 합니다.")

    return cleaned_query


def _format_money(value: object, currency: str = "USD") -> str:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        amount = 0.0
    return f"{amount:,.2f} {currency}"


def render_results(
    query: str,
    results: Sequence[OpportunityResult],
    *,
    top: int = 5,
    output: TextIO = sys.stdout,
) -> None:
    print("\nHYB Opportunity AI", file=output)
    print("=" * 64, file=output)
    print(f"검색어: {query}", file=output)
    print(f"분석 결과: {len(results)}개 그룹", file=output)

    if not results:
        print("검색 결과가 없습니다.", file=output)
        return

    for rank, result in enumerate(results[:top], start=1):
        analysis = result.analysis
        recommendation = result.ai_recommendation
        currency = result.product.currency or "USD"

        print("\n" + "-" * 64, file=output)
        print(f"#{rank} {result.product.title}", file=output)
        print(
            f"마켓: {result.product.marketplace} | "
            f"매입가: {_format_money(result.product.price, currency)} | "
            f"유사 표본: {result.matched_product_count}개",
            file=output,
        )
        print(
            "추천 판매가: "
            f"{_format_money(result.price_intelligence.recommended_selling_price, currency)}",
            file=output,
        )
        print(
            f"예상 순이익: {_format_money(analysis.get('net_profit'), currency)} | "
            f"ROI: {float(analysis.get('roi', 0)):.2f}%",
            file=output,
        )
        print(
            f"최종 기회점수: {result.final_opportunity_score:.2f} | "
            f"신뢰도: {analysis.get('confidence_level', 'unknown')}",
            file=output,
        )

        if recommendation is not None:
            print(
                f"추천: {recommendation.grade} / {recommendation.action} | "
                f"성공확률: {recommendation.success_probability:.1f}%",
                file=output,
            )

        if result.product.url:
            print(f"URL: {result.product.url}", file=output)



def render_saved_results(
    records: Sequence[SavedOpportunity],
    *,
    output: TextIO = sys.stdout,
) -> None:
    print("\n저장된 최근 기회 분석", file=output)
    print("=" * 64, file=output)
    if not records:
        print("저장된 분석 결과가 없습니다.", file=output)
        return

    for rank, record in enumerate(records, start=1):
        print("\n" + "-" * 64, file=output)
        print(f"#{rank} [{record.query}] {record.title}", file=output)
        print(
            f"마켓: {record.marketplace} | "
            f"매입가: {_format_money(record.purchase_price, record.currency)} | "
            f"판매가: {_format_money(record.recommended_selling_price, record.currency)}",
            file=output,
        )
        print(
            f"순이익: {_format_money(record.net_profit, record.currency)} | "
            f"ROI: {record.roi:.2f}% | 점수: {record.opportunity_score:.2f}",
            file=output,
        )
        print(
            f"추천: {record.recommendation_grade} / {record.recommendation_action} | "
            f"성공확률: {record.success_probability:.1f}%",
            file=output,
        )
        print(f"저장시각: {record.created_at}", file=output)
        if record.url:
            print(f"URL: {record.url}", file=output)


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    input_stream: TextIO = sys.stdin,
    output: TextIO = sys.stdout,
    error_output: TextIO = sys.stderr,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        repository = OpportunityHistoryRepository(args.db)

        if args.history:
            render_saved_results(
                repository.get_recent(limit=args.top),
                output=output,
            )
            return 0

        query = _resolve_query(args.query, input_stream)

        if args.limit < 1:
            raise ValueError("limit은 1 이상이어야 합니다.")
        if args.top < 1:
            raise ValueError("top은 1 이상이어야 합니다.")
        if not 0 <= args.fee_rate < 1:
            raise ValueError("fee-rate는 0 이상 1 미만이어야 합니다.")

        print(f"'{query}' 검색 및 분석 중...", file=output)

        search_warnings: list[str] = []

        def handle_search_error(
            marketplace: str,
            error: Exception,
        ) -> None:
            search_warnings.append(
                f"{marketplace} 검색 실패: {error}"
            )

        results = find_best_opportunities(
            query=query,
            selling_price_multiplier=args.selling_multiplier,
            shipping_cost=args.shipping_cost,
            marketplace_fee_rate=args.fee_rate,
            estimated_monthly_sales=args.monthly_sales,
            competitor_count=args.competitors,
            risk_level=args.risk,
            limit=args.limit,
            search_error_handler=handle_search_error,
        )

        for warning in search_warnings:
            print(f"경고: {warning}", file=error_output)

        render_results(
            query,
            results,
            top=args.top,
            output=output,
        )

        if not args.no_save:
            saved_count = repository.save_results(query, results)
            print(
                f"\nDB 저장 완료: {saved_count}개 결과 ({args.db})",
                file=output,
            )
        return 0

    except (ValueError, RuntimeError) as error:
        print(f"오류: {error}", file=error_output)
        return 1
    except KeyboardInterrupt:
        print("\n작업을 취소했습니다.", file=error_output)
        return 130


def run_demo() -> None:
    """기존 호출 호환용 함수."""
    raise SystemExit(run_cli([]))
