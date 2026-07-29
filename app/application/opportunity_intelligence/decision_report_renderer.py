from __future__ import annotations

from app.application.opportunity_intelligence.decision_report import (
    OpportunityDecisionReport,
)


class DecisionReportRenderer:
    """DecisionReport를 사람이 읽기 쉬운 문자열로 렌더링한다."""

    @staticmethod
    def render_text(report: OpportunityDecisionReport) -> str:
        if not isinstance(report, OpportunityDecisionReport):
            raise TypeError(
                "report는 OpportunityDecisionReport여야 합니다."
            )

        lines: list[str] = [
            "==============================",
            "Opportunity Decision Report",
            "==============================",
            "",
            f"Decision   : {report.decision.value}",
            f"Grade      : {report.grade.value}",
            f"Score      : {report.score}",
            f"Confidence : {report.confidence}",
            "",
        ]

        if report.strengths:
            lines.append("Strengths")
            for reason in report.strengths:
                lines.append(f"✓ {reason.value}")
            lines.append("")

        if report.warnings:
            lines.append("Warnings")
            for reason in report.warnings:
                lines.append(f"• {reason.value}")
            lines.append("")

        lines.append("Recommendation")
        lines.append(report.recommended_action)

        return "\n".join(lines)