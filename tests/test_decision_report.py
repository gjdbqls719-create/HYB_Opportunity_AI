from types import SimpleNamespace

from engine.decision_report import (
    DecisionReport,
    build_decision_report,
)


def _make_recommendation(
    *,
    grade: str = "BUY",
) -> SimpleNamespace:
    return SimpleNamespace(
        grade=grade,
        decision_label=grade,
        reasons=(
            "예상 수익성이 양호합니다.",
        ),
        warnings=(
            "배송비를 확인해야 합니다.",
        ),
    )


def test_build_decision_report_without_market_adjustment() -> None:
    report = build_decision_report(
        recommendation=_make_recommendation(),
        confidence=None,
        price_trend=None,
    )

    assert isinstance(
        report,
        DecisionReport,
    )
    assert report.strengths == (
        "예상 수익성이 양호합니다.",
    )
    assert report.weaknesses == (
        "배송비를 확인해야 합니다.",
    )
    assert report.market_explanations == ()


def test_build_decision_report_preserves_market_explanations() -> None:
    market_adjustment = SimpleNamespace(
        explanations=(
            "현재 시장 상태가 양호하여 "
            "Opportunity Score를 3점 높였습니다.",
            "경쟁 판매자가 적어 "
            "시장 진입 부담이 낮습니다.",
        )
    )

    report = build_decision_report(
        recommendation=_make_recommendation(),
        confidence=None,
        price_trend=None,
        market_adjustment=market_adjustment,
    )

    assert report.market_explanations == (
        "현재 시장 상태가 양호하여 "
        "Opportunity Score를 3점 높였습니다.",
        "경쟁 판매자가 적어 "
        "시장 진입 부담이 낮습니다.",
    )


def test_build_decision_report_removes_empty_and_duplicate_explanations() -> None:
    market_adjustment = SimpleNamespace(
        explanations=(
            "",
            "  재고가 확인되었습니다.  ",
            "재고가 확인되었습니다.",
            "판매자 경쟁이 낮습니다.",
        )
    )

    report = build_decision_report(
        recommendation=_make_recommendation(),
        confidence=None,
        price_trend=None,
        market_adjustment=market_adjustment,
    )

    assert report.market_explanations == (
        "재고가 확인되었습니다.",
        "판매자 경쟁이 낮습니다.",
    )


def test_build_decision_report_accepts_single_string_explanation() -> None:
    market_adjustment = SimpleNamespace(
        explanations=(
            "시장 데이터가 부족하여 "
            "점수를 조정하지 않았습니다."
        )
    )

    report = build_decision_report(
        recommendation=_make_recommendation(),
        confidence=None,
        price_trend=None,
        market_adjustment=market_adjustment,
    )

    assert report.market_explanations == (
        "시장 데이터가 부족하여 "
        "점수를 조정하지 않았습니다.",
    )


def test_decision_report_keeps_backward_compatible_default() -> None:
    report = DecisionReport(
        strengths=("강점",),
        weaknesses=("약점",),
        market_summary="시장 요약",
        buy_timing="매입 시점",
        ai_comment="AI 의견",
    )

    assert report.market_explanations == ()