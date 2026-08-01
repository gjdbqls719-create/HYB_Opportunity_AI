from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from app.domain.opportunity.lifecycle import _aware, _optional_text, _required_text


class FounderDecisionType(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class FounderDecision:
    opportunity_id: str
    decision: FounderDecisionType
    reason: str
    decided_at: datetime
    operator_id: str
    note: str | None = None
    decision_id: str = field(default_factory=lambda: uuid4().hex)

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", _required_text(self.decision_id, "decision_id"))
        object.__setattr__(self, "opportunity_id", _required_text(self.opportunity_id, "opportunity_id"))
        object.__setattr__(self, "operator_id", _required_text(self.operator_id, "operator_id"))
        object.__setattr__(self, "reason", _required_text(self.reason, "reason"))
        object.__setattr__(self, "note", _optional_text(self.note, "note"))
        if not isinstance(self.decision, FounderDecisionType):
            object.__setattr__(self, "decision", FounderDecisionType(self.decision))
        _aware(self.decided_at, "decided_at")
