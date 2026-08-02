from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.domain.market_intelligence.artifact import _aware, _required_text


@dataclass(frozen=True, slots=True)
class HumanVerification:
    """Immutable verification fact; it does not mutate its OCR candidate."""

    verification_id: str
    candidate_id: str
    verified_value: Any
    operator_id: str
    verified_at: datetime
    comment: str | None
    schema_version: str

    def __post_init__(self) -> None:
        comment = self.comment
        if comment is not None:
            if not isinstance(comment, str):
                raise TypeError("comment must be text or None")
            comment = comment.strip() or None
        object.__setattr__(self, "verification_id", _required_text(self.verification_id, "verification_id"))
        object.__setattr__(self, "candidate_id", _required_text(self.candidate_id, "candidate_id"))
        object.__setattr__(self, "operator_id", _required_text(self.operator_id, "operator_id"))
        object.__setattr__(self, "verified_at", _aware(self.verified_at, "verified_at"))
        object.__setattr__(self, "comment", comment)
        object.__setattr__(self, "schema_version", _required_text(self.schema_version, "schema_version"))
