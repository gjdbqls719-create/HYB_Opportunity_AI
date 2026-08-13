from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Callable
from uuid import uuid4

from app.application.operational_opportunity_eligibility import (
    OperationalOpportunityBindingConflictError,
    OperationalOpportunityBindingUnavailableError,
    get_operational_opportunity_eligibility,
)
from app.domain.market_intelligence.assessment_subject import is_new_to_market_target_subject
from app.domain.market_intelligence.competition_v2 import (
    BOUNDED_COHORT_POLICY_VERSION,
    COMPETITION_V2_LEGACY_OBSERVATION_IDENTITY_VERSION,
    COMPETITION_V2_OBSERVATION_IDENTITY_VERSION,
    COMPETITION_V2_OBSERVATION_VERSION,
    CompetitionV2ObservationIdentityKind,
    subject_to_data,
)
from app.domain.market_intelligence.demand_v2 import (
    CompetitionCohortReference,
    DemandComparableCard,
    DemandComparableCohort,
    DemandComparableCohortManifest,
    DemandEvidenceOutcome,
    DemandResultPlacement,
    DemandV2Observation,
    DemandV2Assessment,
    ListingRatingEvidence,
    ListingReviewEvidence,
    MarketIntentEvidence,
    ProviderSignalEvidence,
    analyze_demand_v2,
    cohort_manifest_to_data,
    competition_reference_to_data,
    market_intent_to_data,
    provider_signal_to_data,
    rating_to_data,
    review_to_data,
)


class DemandV2AdmissionNotFoundError(LookupError): pass
class DemandV2AdmissionConflictError(ValueError): pass
class DemandV2AdmissionUnavailableError(RuntimeError): pass


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class DemandV2Submission:
    subject: object
    market_intent: MarketIntentEvidence
    cohort_source: DemandComparableCohortManifest | CompetitionCohortReference
    reviews: tuple[ListingReviewEvidence, ...]
    ratings: tuple[ListingRatingEvidence, ...] = ()
    provider_signals: tuple[ProviderSignalEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.market_intent, MarketIntentEvidence):
            raise TypeError("market_intent must be MarketIntentEvidence")
        if not isinstance(self.cohort_source, (DemandComparableCohortManifest, CompetitionCohortReference)):
            raise TypeError("cohort_source must be a Demand cohort manifest or Competition cohort reference")
        object.__setattr__(self, "reviews", tuple(self.reviews))
        object.__setattr__(self, "ratings", tuple(self.ratings))
        object.__setattr__(self, "provider_signals", tuple(self.provider_signals))

    def authority_data(self) -> dict[str, object]:
        return {"subject": subject_to_data(self.subject), "market_intent": market_intent_to_data(self.market_intent),
            "cohort_source": ({"kind": "demand_owned", "manifest": cohort_manifest_to_data(self.cohort_source)}
                if isinstance(self.cohort_source, DemandComparableCohortManifest)
                else {"kind": "competition_reference", "reference": competition_reference_to_data(self.cohort_source)}),
            "reviews": [review_to_data(value) for value in self.reviews],
            "ratings": [rating_to_data(value) for value in self.ratings],
            "provider_signals": [provider_signal_to_data(value) for value in self.provider_signals]}


@dataclass(frozen=True, slots=True)
class FinalizeDemandV2AdmissionCommand:
    opportunity_id: str
    command_id: str
    operator_id: str
    submitted_at: datetime
    submission: DemandV2Submission

    def __post_init__(self) -> None:
        for name in ("opportunity_id", "command_id", "operator_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be non-empty text")
            object.__setattr__(self, name, value.strip())
        if not isinstance(self.submission, DemandV2Submission):
            raise TypeError("submission must be DemandV2Submission")
        if self.submitted_at.tzinfo is None or self.submitted_at.utcoffset() is None:
            raise ValueError("submitted_at must be timezone-aware")
        if isinstance(self.submission.cohort_source, DemandComparableCohortManifest) and self.submission.cohort_source.operator_id != self.operator_id:
            raise ValueError("cohort operator must match command operator")

    def authority_data(self) -> dict[str, object]:
        return {"namespace": "demand-v2-authority", "opportunity_id": self.opportunity_id,
            "submission": self.submission.authority_data()}

    def authority_fingerprint(self) -> str:
        return _hash(self.authority_data())

    def fingerprint(self) -> str:
        return _hash({"namespace": "demand-v2-admission", "opportunity_id": self.opportunity_id,
            "command_id": self.command_id, "operator_id": self.operator_id,
            "submitted_at": self.submitted_at.isoformat(), "submission": self.submission.authority_data()})


@dataclass(frozen=True, slots=True)
class DemandV2Publication:
    opportunity_id: str
    observation: DemandV2Observation
    assessment: DemandV2Assessment
    generated_at: datetime
    committed_at: datetime


@dataclass(frozen=True, slots=True)
class DemandV2AdmissionResult:
    publication: DemandV2Publication
    replayed: bool
    aliased: bool = False


class FinalizeDemandV2Admission:
    def __init__(
        self,
        opportunities,
        repository,
        competition_repository=None,
        *,
        observation_id_generator: Callable[[], str] | None = None,
        cohort_id_generator: Callable[[], str] | None = None,
        assessment_id_generator: Callable[[], str] | None = None,
        generated_clock: Callable[[], datetime] | None = None,
        committed_clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._opportunities = opportunities
        self._repository = repository
        self._competition = competition_repository
        self._observation_id = observation_id_generator or (lambda: str(uuid4()))
        self._cohort_id = cohort_id_generator or (lambda: str(uuid4()))
        self._assessment_id = assessment_id_generator or (lambda: str(uuid4()))
        self._generated = generated_clock or (lambda: datetime.now(timezone.utc))
        self._committed = committed_clock or (lambda: datetime.now(timezone.utc))

    def execute(self, command: FinalizeDemandV2AdmissionCommand) -> DemandV2AdmissionResult:
        fingerprint = command.fingerprint()
        receipt = self._repository.get_receipt(command.command_id)
        if receipt is not None:
            if receipt["command_fingerprint"] != fingerprint:
                raise DemandV2AdmissionConflictError("Demand v2 command conflicts with committed receipt")
            publication = self._repository.get_publication(receipt["observation_id"])
            if publication is None:
                raise DemandV2AdmissionUnavailableError("committed Demand v2 publication is unavailable")
            return DemandV2AdmissionResult(publication, True)
        try:
            eligibility = get_operational_opportunity_eligibility(self._opportunities, command.opportunity_id)
        except OperationalOpportunityBindingConflictError as error:
            raise DemandV2AdmissionConflictError(str(error)) from error
        except OperationalOpportunityBindingUnavailableError as error:
            raise DemandV2AdmissionUnavailableError(str(error)) from error
        if eligibility is None:
            raise DemandV2AdmissionNotFoundError(command.opportunity_id)
        subject = eligibility.market_binding.market_observation_identity if eligibility.market_binding else (
            eligibility.target_binding.target_identity if eligibility.target_binding else None)
        if subject is None:
            raise DemandV2AdmissionConflictError("Opportunity has no operational assessment subject")
        if subject != command.submission.subject:
            raise DemandV2AdmissionConflictError("Demand v2 subject conflicts with Opportunity")
        authority_fingerprint = command.authority_fingerprint()
        existing = self._repository.get_publication_by_authority_fingerprint(authority_fingerprint)
        if existing is not None:
            self._repository.save_alias_receipt(command.command_id, fingerprint, authority_fingerprint,
                existing.observation.observation_id, command.opportunity_id, command.operator_id, self._committed())
            return DemandV2AdmissionResult(existing, False, True)
        manifest = self._resolve_manifest(command.submission.cohort_source, subject)
        if (
            manifest.market != command.submission.market_intent.market
            or manifest.query != command.submission.market_intent.query
            or manifest.locale != command.submission.market_intent.locale
        ):
            raise DemandV2AdmissionConflictError(
                "Demand evidence families must share market, exact query, and locale"
            )
        observation_id = self._required_id(self._observation_id(), "observation_id")
        cohort_id = self._required_id(self._cohort_id(), "cohort_id")
        assessment_id = self._required_id(self._assessment_id(), "assessment_id")
        observed_times = [command.submission.market_intent.observed_at, manifest.window_ended_at]
        observed_times.extend(value.observed_at for value in command.submission.reviews)
        observed_times.extend(value.observed_at for value in command.submission.ratings)
        observed_times.extend(value.observed_at for value in command.submission.provider_signals)
        observation = DemandV2Observation(
            observation_id, subject, command.submission.market_intent,
            DemandComparableCohort(cohort_id, manifest), command.submission.reviews,
            command.submission.ratings, command.submission.provider_signals,
            DemandEvidenceOutcome.TARGET_LISTING_ABSENT if is_new_to_market_target_subject(subject)
            else DemandEvidenceOutcome.NOT_APPLICABLE,
            max(observed_times),
        )
        generated_at = self._generated()
        committed_at = self._committed()
        assessment = analyze_demand_v2(observation, assessment_id=assessment_id, generated_at=generated_at)
        publication = DemandV2Publication(command.opportunity_id, observation, assessment, generated_at, committed_at)
        try:
            self._repository.finalize(publication, command.command_id, fingerprint,
                authority_fingerprint, command.authority_data(), command.operator_id)
        except DemandV2AdmissionConflictError:
            raise
        except Exception as error:
            raise DemandV2AdmissionUnavailableError("Demand v2 persistence unavailable") from error
        return DemandV2AdmissionResult(publication, False)

    @staticmethod
    def _required_id(value: str, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise DemandV2AdmissionUnavailableError(f"{name} generation failed")
        return value.strip()

    def _resolve_manifest(self, source, subject) -> DemandComparableCohortManifest:
        if isinstance(source, DemandComparableCohortManifest):
            if source.subject != subject:
                raise DemandV2AdmissionConflictError("Demand cohort subject conflicts with Opportunity")
            return source
        if self._competition is None:
            raise DemandV2AdmissionUnavailableError("Competition cohort repository is unavailable")
        publication = self._competition.get_publication_by_observation_id(
            source.competition_observation_id
        )
        cohort_publication = self._competition.get_publication(source.cohort_id)
        if publication is None:
            raise DemandV2AdmissionConflictError("referenced Competition v2 observation is missing")
        if cohort_publication is None:
            raise DemandV2AdmissionConflictError("referenced Competition v2 cohort is missing")
        cohort = publication.cohort
        identity = publication.observation_identity
        actual_fingerprint = self._competition.get_authority_fingerprint(source.cohort_id)
        accepted_identity_contracts = {
            (CompetitionV2ObservationIdentityKind.ISSUED.value, COMPETITION_V2_OBSERVATION_IDENTITY_VERSION),
            (CompetitionV2ObservationIdentityKind.LEGACY_COMPATIBILITY.value,
             COMPETITION_V2_LEGACY_OBSERVATION_IDENTITY_VERSION),
        }
        if (
            (source.observation_identity_kind, source.observation_identity_version)
                not in accepted_identity_contracts
            or identity.observation_id != source.competition_observation_id
            or identity.identity_kind.value != source.observation_identity_kind
            or identity.identity_version != source.observation_identity_version
            or cohort.cohort_id != source.cohort_id
            or cohort_publication.observation_identity != identity
            or cohort.subject != subject
            or actual_fingerprint != source.authority_fingerprint
            or source.observation_schema_version != COMPETITION_V2_OBSERVATION_VERSION
            or source.cohort_policy_version != BOUNDED_COHORT_POLICY_VERSION
            or cohort.observation_schema_version != source.observation_schema_version
            or cohort.cohort_policy_version != source.cohort_policy_version
            or cohort.artifact_reference != source.artifact_reference
            or cohort.artifact_sha256 != source.artifact_sha256
        ):
            raise DemandV2AdmissionConflictError("Competition cohort reference does not match immutable authority")
        cards = tuple(DemandComparableCard(
            card.result_ordinal, DemandResultPlacement(card.placement.value), card.included,
            card.is_comparable, card.exclusion_reason, card.marketplace_item_id,
            cohort.listing_reference(card), card.raw_title, card.visible_variant_count,
        ) for card in cohort.cards)
        return DemandComparableCohortManifest(
            subject, cohort.market, cohort.marketplace, cohort.query, cohort.category,
            cohort.product_use, cohort.category_form_factor, cohort.condition, cohort.locale,
            cohort.result_surface, cohort.window_started_at, cohort.window_ended_at,
            self._artifact(source.artifact_reference, source.artifact_sha256),
            cohort.bound_start, cohort.bound_end, cohort.operator_id, cards, source,
        )

    @staticmethod
    def _artifact(reference: str, sha256: str):
        from app.domain.market_intelligence.demand_v2 import DemandArtifactReference
        return DemandArtifactReference(reference, sha256)
