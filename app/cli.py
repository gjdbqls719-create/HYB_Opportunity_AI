from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import TextIO

from engine.orchestrator import (
    OpportunityResult,
    find_best_opportunities,
)
from presentation.cli import print_dashboard_results
from storage.opportunity_history import (
    OpportunityHistoryRepository,
    SavedOpportunity,
)


DEFAULT_DATABASE_PATH = "data/hyb_opportunity.db"


def build_parser() -> argparse.ArgumentParser:
    """
    HYB Opportunity AI CLI 인수 파서를 생성한다.
    """
    parser = argparse.ArgumentParser(
        prog="HYB Opportunity AI",
        description=(
            "마켓플레이스 상품을 검색하고 "
            "수익 기회를 분석합니다."
        ),
    )

    parser.add_argument(
        "query",
        nargs="?",
        help=(
            "검색할 상품명. "
            "생략하면 실행 중에 입력받습니다."
        ),
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
        help=(
            "상품 가격을 기준으로 한 "
            "예상 판매가 배수 (기본값: 1.5)"
        ),
    )

    parser.add_argument(
        "--shipping-cost",
        type=float,
        default=0.0,
        help="예상 배송비 (기본값: 0)",
    )

    parser.add_argument(
        "--fee-rate",
        type=float,
        default=0.15,
        help="마켓플레이스 수수료율 (기본값: 0.15)",
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
        help="예상 경쟁 상품 수 (기본값: 20)",
    )

    parser.add_argument(
        "--history",
        action="store_true",
        help="저장된 최근 분석 결과를 조회합니다.",
    )

    parser.add_argument(
        "--db",
        default=DEFAULT_DATABASE_PATH,
        help=(
            "SQLite DB 경로 "
            f"(기본값: {DEFAULT_DATABASE_PATH})"
        ),
    )

    parser.add_argument(
        "--no-save",
        action="store_true",
        help="이번 검색 결과를 DB에 저장하지 않습니다.",
    )

    parser.add_argument(
        "--risk",
        choices=(
            "low",
            "medium",
            "high",
        ),
        default="medium",
        help="위험 성향 (기본값: medium)",
    )

    return parser


def _resolve_query(
    query: str | None,
    input_stream: TextIO,
) -> str:
    """
    명령줄 인수 또는 입력 스트림에서 검색어를 가져온다.
    """
    if query is not None:
        cleaned_query = query.strip()
    else:
        print(
            "검색할 상품명을 입력하세요: ",
            end="",
            flush=True,
        )
        cleaned_query = input_stream.readline().strip()

    if not cleaned_query:
        raise ValueError(
            "검색어를 입력해야 합니다."
        )

    return cleaned_query


def _validate_arguments(
    *,
    limit: int,
    top: int,
    fee_rate: float,
    selling_multiplier: float,
    shipping_cost: float,
    monthly_sales: int,
    competitors: int,
) -> None:
    """
    분석 실행 전에 CLI 인수를 검증한다.
    """
    if limit < 1:
        raise ValueError(
            "limit은 1 이상이어야 합니다."
        )

    if top < 1:
        raise ValueError(
            "top은 1 이상이어야 합니다."
        )

    if not 0 <= fee_rate < 1:
        raise ValueError(
            "fee-rate는 0 이상 1 미만이어야 합니다."
        )

    if selling_multiplier <= 0:
        raise ValueError(
            "selling-multiplier는 0보다 커야 합니다."
        )

    if shipping_cost < 0:
        raise ValueError(
            "shipping-cost는 0 이상이어야 합니다."
        )

    if monthly_sales < 0:
        raise ValueError(
            "monthly-sales는 0 이상이어야 합니다."
        )

    if competitors < 0:
        raise ValueError(
            "competitors는 0 이상이어야 합니다."
        )


def _format_money(
    value: object,
    currency: str = "USD",
) -> str:
    """
    저장된 분석 결과 출력에 사용하는 금액 포맷터.

    기존 테스트 및 외부 호출과의 호환성을 위해 유지한다.
    """
    try:
        amount = float(value)
    except (TypeError, ValueError):
        amount = 0.0

    cleaned_currency = currency.strip()

    if cleaned_currency:
        return (
            f"{amount:,.2f} "
            f"{cleaned_currency}"
        )

    return f"{amount:,.2f}"


def _render_ai_partner_report(
    result: OpportunityResult,
    *,
    output: TextIO,
) -> None:
    """
    AI Partner 보고서만 별도로 출력한다.

    기존 호출과의 호환성을 위해 유지하지만,
    일반 검색 결과는 Presentation Layer를 통해 출력한다.
    """
    report = result.ai_partner_report

    if report is None:
        return

    print("", file=output)
    print(
        "  [HYB AI Partner]",
        file=output,
    )
    print(
        f"  요약: {report.summary}",
        file=output,
    )
    print(
        f"  AI 판단: {report.recommendation}",
        file=output,
    )
    print(
        f"  다음 행동: {report.next_action}",
        file=output,
    )

    if report.memory_summary:
        print(
            f"  AI Memory: {report.memory_summary}",
            file=output,
        )


def render_results(
    query: str,
    results: Sequence[OpportunityResult],
    *,
    top: int = 5,
    output: TextIO = sys.stdout,
) -> None:
    """
    검색 결과를 HYB Dashboard 형식으로 출력한다.

    결과 표현은 presentation 패키지에 위임하며,
    app 계층은 검색어와 결과 개수 등 실행 정보만 담당한다.
    """
    selected_results = list(
        results[:top]
    )

    print(
        "\nHYB Opportunity AI",
        file=output,
    )
    print(
        "=" * 64,
        file=output,
    )
    print(
        f"검색어: {query}",
        file=output,
    )
    print(
        f"분석 결과: {len(results)}개 그룹",
        file=output,
    )
    print(
        f"표시 결과: {len(selected_results)}개",
        file=output,
    )
    print("", file=output)

    print_dashboard_results(
        selected_results,
        output=output,
    )


def render_saved_results(
    records: Sequence[SavedOpportunity],
    *,
    output: TextIO = sys.stdout,
) -> None:
    """
    SQLite에 저장된 최근 기회 분석 기록을 출력한다.
    """
    print(
        "\n저장된 최근 기회 분석",
        file=output,
    )
    print(
        "=" * 64,
        file=output,
    )

    if not records:
        print(
            "저장된 분석 결과가 없습니다.",
            file=output,
        )
        return

    for rank, record in enumerate(
        records,
        start=1,
    ):
        print(
            "\n" + "-" * 64,
            file=output,
        )
        print(
            f"#{rank} "
            f"[{record.query}] "
            f"{record.title}",
            file=output,
        )
        print(
            f"마켓: {record.marketplace} | "
            f"매입가: "
            f"{_format_money(
                record.purchase_price,
                record.currency,
            )} | "
            f"판매가: "
            f"{_format_money(
                record.recommended_selling_price,
                record.currency,
            )}",
            file=output,
        )
        print(
            f"순이익: "
            f"{_format_money(
                record.net_profit,
                record.currency,
            )} | "
            f"ROI: {record.roi:.2f}% | "
            f"점수: "
            f"{record.opportunity_score:.2f}",
            file=output,
        )
        print(
            f"추천: "
            f"{record.recommendation_grade} / "
            f"{record.recommendation_action} | "
            f"성공 확률: "
            f"{record.success_probability:.1f}%",
            file=output,
        )
        print(
            f"저장 시간: {record.created_at}",
            file=output,
        )

        if record.url:
            print(
                f"URL: {record.url}",
                file=output,
            )


def run_cli(
    argv: Sequence[str] | None = None,
    *,
    input_stream: TextIO = sys.stdin,
    output: TextIO = sys.stdout,
    error_output: TextIO = sys.stderr,
) -> int:
    """
    HYB Opportunity AI의 CLI 진입점.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        repository = OpportunityHistoryRepository(
            args.db
        )

        if args.history:
            records = repository.get_recent(
                limit=args.top
            )

            render_saved_results(
                records,
                output=output,
            )
            return 0

        query = _resolve_query(
            args.query,
            input_stream,
        )

        _validate_arguments(
            limit=args.limit,
            top=args.top,
            fee_rate=args.fee_rate,
            selling_multiplier=(
                args.selling_multiplier
            ),
            shipping_cost=args.shipping_cost,
            monthly_sales=args.monthly_sales,
            competitors=args.competitors,
        )

        print(
            f"'{query}' 검색 및 분석 중...",
            file=output,
        )

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
            selling_price_multiplier=(
                args.selling_multiplier
            ),
            shipping_cost=args.shipping_cost,
            marketplace_fee_rate=(
                args.fee_rate
            ),
            estimated_monthly_sales=(
                args.monthly_sales
            ),
            competitor_count=(
                args.competitors
            ),
            risk_level=args.risk,
            limit=args.limit,
            search_error_handler=(
                handle_search_error
            ),
        )

        for warning in search_warnings:
            print(
                f"경고: {warning}",
                file=error_output,
            )

        render_results(
            query,
            results,
            top=args.top,
            output=output,
        )

        if not args.no_save:
            saved_count = repository.save_results(
                query,
                results,
            )

            print(
                "\nDB 저장 완료: "
                f"{saved_count}개 결과 "
                f"({args.db})",
                file=output,
            )

        return 0

    except (ValueError, RuntimeError) as error:
        print(
            f"오류: {error}",
            file=error_output,
        )
        return 1

    except KeyboardInterrupt:
        print(
            "\n작업이 취소되었습니다.",
            file=error_output,
        )
        return 130


def run_demo() -> None:
    """
    기존 호출 호환용 실행 함수.
    """
    raise SystemExit(
        run_cli([])
    )