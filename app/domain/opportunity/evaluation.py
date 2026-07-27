from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.domain.opportunity.decision import OpportunityDecision
from app.domain.opportunity.models import OpportunityScore
from app.domain.opportunity.reasons import OpportunityReason


@dataclass(frozen=True, slots=True)
class OpportunityEvaluation:
    """
    Opportunity Score를 바탕으로 만들어진 최종 판단 결과.

    점수 계산 결과와 의사결정 책임을 분리하기 위해 ``OpportunityScore``를
    변경하지 않고 참조한다. ``reasons``는 표시 문구가 아니라 안정적인
    도메인 코드이며, 사용자용 설명은 상위 계층에서 현지화할 수 있다.
    """

    score: OpportunityScore
    decision: OpportunityDecision
    reasons: tuple[OpportunityReason, ...]
    evaluated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.score, OpportunityScore):
            raise TypeError("score는 OpportunityScore여야 합니다.")

        if not isinstance(self.decision, OpportunityDecision):
            raise TypeError("decision은 OpportunityDecision이어야 합니다.")

        if not isinstance(self.reasons, tuple):
            raise TypeError("reasons는 OpportunityReason의 tuple이어야 합니다.")

        if not self.reasons:
            raise ValueError("reasons에는 최소 하나의 근거가 필요합니다.")

        for reason in self.reasons:
            if not isinstance(reason, OpportunityReason):
                raise TypeError(
                    "reasons의 모든 값은 OpportunityReason이어야 합니다."
                )

        if len(set(self.reasons)) != len(self.reasons):
            raise ValueError("reasons에는 중복된 근거를 넣을 수 없습니다.")

        if not isinstance(self.evaluated_at, datetime):
            raise TypeError("evaluated_at은 datetime이어야 합니다.")

        if (
            self.evaluated_at.tzinfo is None
            or self.evaluated_at.utcoffset() is None
        ):
            raise ValueError(
                "evaluated_at은 timezone-aware datetime이어야 합니다."
            )
