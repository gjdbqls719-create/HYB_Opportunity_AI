from __future__ import annotations

from engine.orchestrator import OpportunityResult


class AIAnalyst:
    """
    OpportunityResult를 사람이 읽기 쉬운
    AI 분석 리포트로 변환한다.

    계산은 수행하지 않는다.
    """

    @staticmethod
    def build_report(
        result: OpportunityResult,
    ) -> str:
        recommendation = result.ai_recommendation

        if recommendation is None:
            return (
                "AI Recommendation이 아직 생성되지 "
                "않았습니다."
            )

        lines: list[str] = []

        lines.append("=" * 60)
        lines.append("HYB AI ANALYSIS REPORT")
        lines.append("=" * 60)
        lines.append("")

        lines.append(
            f"상품 : {result.product.title}"
        )
        lines.append(
            f"마켓 : {result.product.marketplace}"
        )
        lines.append(
            f"가격 : {result.product.price:.2f} "
            f"{result.product.currency}"
        )

        lines.append("")

        lines.append(
            f"Opportunity Score : "
            f"{result.final_opportunity_score}"
        )

        lines.append(
            f"Recommendation : "
            f"{recommendation.grade}"
        )

        lines.append(
            f"Action : "
            f"{recommendation.action}"
        )

        lines.append(
            f"Success : "
            f"{recommendation.success_probability}%"
        )

        lines.append("")

        lines.append(
            "Recommendation Reasons"
        )

        for reason in recommendation.reasons:
            lines.append(f" - {reason}")

        if recommendation.warnings:
            lines.append("")
            lines.append("Warnings")

            for warning in recommendation.warnings:
                lines.append(
                    f" - {warning}"
                )

        lines.append("")
        lines.append("Summary")
        lines.append(
            recommendation.summary
        )

        return "\n".join(lines)