from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, TypeAlias, Union

from app.domain.market_intelligence.identity import MarketObservationIdentity

if TYPE_CHECKING:
    from app.domain.opportunity.new_to_market_domestic_selling import (
        NewToMarketDomesticSellingTargetIdentity,
    )


class AssessmentSubjectKind(StrEnum):
    MARKET_OBSERVATION = "market_observation"
    NEW_TO_MARKET_DOMESTIC_SELLING_TARGET = (
        "new_to_market_domestic_selling_target"
    )


AssessmentSubject: TypeAlias = Union[
    MarketObservationIdentity,
    "NewToMarketDomesticSellingTargetIdentity",
]


def is_new_to_market_target_subject(value: object) -> bool:
    from app.domain.opportunity.new_to_market_domestic_selling import (
        NewToMarketDomesticSellingTargetIdentity,
    )

    return isinstance(value, NewToMarketDomesticSellingTargetIdentity)


def assessment_subject_kind(subject: AssessmentSubject) -> AssessmentSubjectKind:
    if isinstance(subject, MarketObservationIdentity):
        return AssessmentSubjectKind.MARKET_OBSERVATION
    if is_new_to_market_target_subject(subject):
        return AssessmentSubjectKind.NEW_TO_MARKET_DOMESTIC_SELLING_TARGET
    raise TypeError("unsupported assessment subject")


def validate_evidence_context(subject: AssessmentSubject, evidence) -> None:
    kind = assessment_subject_kind(subject)
    if evidence.market != subject.market:
        raise ValueError("evidence market must match assessment subject")
    if (
        kind is AssessmentSubjectKind.MARKET_OBSERVATION
        and evidence.marketplace != subject.marketplace
    ):
        raise ValueError("evidence marketplace must match observation identity")


__all__ = [
    "AssessmentSubject",
    "AssessmentSubjectKind",
    "assessment_subject_kind",
    "is_new_to_market_target_subject",
    "validate_evidence_context",
]
