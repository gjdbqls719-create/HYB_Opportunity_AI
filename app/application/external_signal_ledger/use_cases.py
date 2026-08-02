from __future__ import annotations

from dataclasses import dataclass

from app.domain.market_intelligence import HumanVerification, OCRCandidate


def _required_text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    return value.strip()


@dataclass(frozen=True, slots=True)
class SaveOCRCandidate:
    candidate: OCRCandidate

    def __post_init__(self) -> None:
        if not isinstance(self.candidate, OCRCandidate):
            raise TypeError("candidate must be OCRCandidate")


@dataclass(frozen=True, slots=True)
class SaveHumanVerification:
    verification: HumanVerification

    def __post_init__(self) -> None:
        if not isinstance(self.verification, HumanVerification):
            raise TypeError("verification must be HumanVerification")


@dataclass(frozen=True, slots=True)
class GetLatestVerification:
    candidate_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _required_text(self.candidate_id, "candidate_id"))


@dataclass(frozen=True, slots=True)
class GetVerificationHistory:
    candidate_id: str
    limit: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "candidate_id", _required_text(self.candidate_id, "candidate_id"))
        if self.limit is not None and (
            isinstance(self.limit, bool) or not isinstance(self.limit, int) or self.limit < 1
        ):
            raise ValueError("limit must be a positive integer or None")
