from __future__ import annotations

from dataclasses import dataclass

from engine.explainable_score import (
    ExplainableScoreResult,
)


@dataclass(slots=True, frozen=True)
class FormattedScoreResult:
    """
    Explainable Score를 사람이 읽기 쉬운 형태로 변환한 결과.
    """

    title: str
    final_score: int
    raw_total: float

    lines: tuple[str, ...]
    strengths: tuple[str, ...]
    warnings: tuple[str, ...]

    text: str


def format_explainable_score(
    score_result: ExplainableScoreResult,
) -> FormattedScoreResult:
    """
    Explainable Score 결과를 콘솔, API, 대시보드에서
    재사용할 수 있는 표시용 데이터로 변환한다.
    """

    title = "HYB Explainable Score"

    lines = tuple(
        _format_contribution_line(
            label=contribution.label,
            adjustment=contribution.adjustment,
        )
        for contribution in score_result.contributions
    )

    strengths = tuple(
        score_result.reasons
    )

    warnings = tuple(
        score_result.warnings
    )

    text = _build_plain_text(
        title=title,
        final_score=score_result.final_score,
        raw_total=score_result.raw_total,
        lines=lines,
        strengths=strengths,
        warnings=warnings,
    )

    return FormattedScoreResult(
        title=title,
        final_score=score_result.final_score,
        raw_total=score_result.raw_total,
        lines=lines,
        strengths=strengths,
        warnings=warnings,
        text=text,
    )


def _format_contribution_line(
    *,
    label: str,
    adjustment: float,
) -> str:
    formatted_adjustment = _format_number(
        adjustment
    )

    if adjustment > 0:
        return (
            f"{label}: +{formatted_adjustment}"
        )

    return (
        f"{label}: {formatted_adjustment}"
    )


def _format_number(
    value: float,
) -> str:
    if value.is_integer():
        return str(
            int(value)
        )

    return str(
        round(value, 2)
    )


def _build_plain_text(
    *,
    title: str,
    final_score: int,
    raw_total: float,
    lines: tuple[str, ...],
    strengths: tuple[str, ...],
    warnings: tuple[str, ...],
) -> str:
    output_lines: list[str] = [
        title,
        "",
        *lines,
        "",
        f"원점수 합계: {_format_number(raw_total)}",
        f"최종 점수: {final_score}",
        "",
        "강점",
    ]

    if strengths:
        output_lines.extend(
            f"- {strength}"
            for strength in strengths
        )
    else:
        output_lines.append(
            "- 확인된 강점이 없습니다."
        )

    output_lines.extend(
        [
            "",
            "주의사항",
        ]
    )

    if warnings:
        output_lines.extend(
            f"- {warning}"
            for warning in warnings
        )
    else:
        output_lines.append(
            "- 확인된 주의사항이 없습니다."
        )

    return "\n".join(
        output_lines
    )