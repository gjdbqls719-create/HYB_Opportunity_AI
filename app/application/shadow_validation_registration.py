"""Authoritative manual registration for one exact Shadow O2 baseline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
from typing import Callable, Protocol

from app.application.candidate_issuance import CandidateIssuanceRepository
from app.application.candidate_promotion import CandidatePromotionRepository
from app.application.discovery.screening_persistence import (
    DiscoveryScreeningCompletionRepository,
)
from app.application.new_to_market_domestic_selling import (
    NewToMarketDomesticSellingAdmissionPublication,
)
from app.application.shadow_validation_persistence import (
    PersistShadowRegistrationCommand,
    ShadowRegistrationBaselineRepository,
    ShadowRegistrationPersistenceResult,
)
from app.domain.discovery import (
    DiscoveryScreeningRecordingState,
    screening_input_manifest_to_canonical_data,
)
from app.domain.opportunity import (
    ShadowBaselineAvailability,
    ShadowBaselineCompleteness,
    ShadowBaselineSnapshot,
    ShadowBaselineSourceManifest,
    ShadowBaselineSourceOwner,
    ShadowBaselineSourceReference,
    ShadowBaselineSourceRole,
    ShadowBaselineTruthScope,
    ShadowCalibrationEligibility,
    ShadowEvidenceClass,
    ShadowO2SubjectLineage,
    ShadowRegistrationAuthorityKind,
    ShadowScreeningLineage,
    ShadowValidationRegistration,
    ShadowVersionedPolicyReference,
    shadow_authority_fingerprint,
)


REGISTER_SHADOW_VALIDATION_COMMAND_SCHEMA_VERSION = (
    "register-shadow-validation-command-v1"
)
DEFAULT_SHADOW_CADENCE_POLICY_NAME = "shadow-validation-cadence"
DEFAULT_SHADOW_CADENCE_POLICY_VERSION = "1.0.0"


class ShadowValidationAuthorityScope(StrEnum):
    ELAPSED_TIME_MARKET_THESIS_VALIDATION = (
        "ELAPSED_TIME_MARKET_THESIS_VALIDATION"
    )


class ShadowValidationExcludedAuthority(StrEnum):
    ACTUAL_OUTCOME = "ACTUAL_OUTCOME"
    BUY_AUTHORIZATION = "BUY_AUTHORIZATION"
    CAPITAL_READINESS = "CAPITAL_READINESS"
    INVESTMENT_APPROVAL = "INVESTMENT_APPROVAL"
    PRODUCT_LAUNCH = "PRODUCT_LAUNCH"
    PROFIT = "PROFIT"
    REVENUE = "REVENUE"


SHADOW_VALIDATION_AUTHORITY_SCOPE = (
    ShadowValidationAuthorityScope.ELAPSED_TIME_MARKET_THESIS_VALIDATION
)
SHADOW_VALIDATION_EXCLUDED_AUTHORITIES = tuple(ShadowValidationExcludedAuthority)


class ShadowValidationRegistrationError(RuntimeError):
    pass


class ShadowValidationSourceNotFoundError(ShadowValidationRegistrationError):
    pass


class ShadowValidationLineageError(ShadowValidationRegistrationError):
    pass


class ShadowValidationLegacyScreeningError(ShadowValidationRegistrationError):
    pass


class ShadowValidationHindsightError(ShadowValidationRegistrationError):
    pass


class ShadowValidationIdentityGenerationError(ShadowValidationRegistrationError):
    pass


class ShadowValidationClockError(ShadowValidationRegistrationError):
    pass


def _text(value: str, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be non-empty text")
    if value != value.strip():
        raise ValueError(f"{name} must not contain surrounding whitespace")
    return value


def _aware(value: datetime, name: str) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
    return value


def _canonical_time(value: datetime) -> str:
    return (
        _aware(value, "canonical datetime")
        .astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _canonical_json(value: object) -> str:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


@dataclass(frozen=True, slots=True)
class RegisterShadowValidationCommand:
    """Founder intent and exact references; all authority facts are server-owned."""

    command_id: str
    o2_admission_id: str
    domestic_selling_target_id: str
    screening_ranking_publication_id: str
    screening_evaluation_id: str
    operator_id: str
    registration_reason: str
    requested_at: datetime
    cadence_policy_name: str = DEFAULT_SHADOW_CADENCE_POLICY_NAME
    cadence_policy_version: str = DEFAULT_SHADOW_CADENCE_POLICY_VERSION
    schema_version: str = REGISTER_SHADOW_VALIDATION_COMMAND_SCHEMA_VERSION

    def __post_init__(self) -> None:
        for name in (
            "command_id",
            "o2_admission_id",
            "domestic_selling_target_id",
            "screening_ranking_publication_id",
            "screening_evaluation_id",
            "operator_id",
            "registration_reason",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        object.__setattr__(
            self, "requested_at", _aware(self.requested_at, "requested_at")
        )
        cadence = ShadowVersionedPolicyReference(
            self.cadence_policy_name, self.cadence_policy_version
        )
        object.__setattr__(self, "cadence_policy_name", cadence.policy_name)
        object.__setattr__(self, "cadence_policy_version", cadence.policy_version)
        if self.schema_version != REGISTER_SHADOW_VALIDATION_COMMAND_SCHEMA_VERSION:
            raise ValueError("unsupported Shadow registration command schema")

    @property
    def fingerprint(self) -> str:
        payload = {
            "o2_admission_id": self.o2_admission_id,
            "domestic_selling_target_id": self.domestic_selling_target_id,
            "screening_ranking_publication_id": (
                self.screening_ranking_publication_id
            ),
            "screening_evaluation_id": self.screening_evaluation_id,
            "operator_id": self.operator_id,
            "registration_reason": self.registration_reason,
            "requested_at": _canonical_time(self.requested_at),
            "cadence_policy_name": self.cadence_policy_name,
            "cadence_policy_version": self.cadence_policy_version,
            "schema_version": self.schema_version,
        }
        return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class ShadowO2AuthorityRepository(Protocol):
    def get_admission(
        self, admission_id: str
    ) -> NewToMarketDomesticSellingAdmissionPublication | None: ...

    def get_target_binding(self, opportunity_id: str): ...

    def get_promotion_v2_admission(self, opportunity_id: str): ...


class RegisterShadowValidation:
    """Resolve exact authorities and atomically freeze one historical baseline."""

    def __init__(
        self,
        *,
        o2_repository: ShadowO2AuthorityRepository,
        candidate_repository: CandidateIssuanceRepository,
        promotion_repository: CandidatePromotionRepository,
        screening_repository: DiscoveryScreeningCompletionRepository,
        shadow_repository: ShadowRegistrationBaselineRepository,
        shadow_validation_id_generator: Callable[[], str],
        baseline_snapshot_id_generator: Callable[[], str],
        registered_clock: Callable[[], datetime],
        committed_clock: Callable[[], datetime],
    ) -> None:
        dependencies = (
            shadow_validation_id_generator,
            baseline_snapshot_id_generator,
            registered_clock,
            committed_clock,
        )
        if any(not callable(value) for value in dependencies):
            raise TypeError("Shadow registration identity and clock dependencies must call")
        self._o2 = o2_repository
        self._candidates = candidate_repository
        self._promotions = promotion_repository
        self._screening = screening_repository
        self._shadow = shadow_repository
        self._shadow_validation_id = shadow_validation_id_generator
        self._baseline_snapshot_id = baseline_snapshot_id_generator
        self._registered_clock = registered_clock
        self._committed_clock = committed_clock

    def get(
        self, shadow_validation_id: str
    ) -> ShadowRegistrationPersistenceResult | None:
        return self._shadow.get_bundle(_text(shadow_validation_id, "shadow_validation_id"))

    def _resolve_subject(self, command: RegisterShadowValidationCommand):
        publication = self._o2.get_admission(command.o2_admission_id)
        if publication is None:
            raise ShadowValidationSourceNotFoundError(
                "exact O2 admission was not found"
            )
        admission = publication.admission
        lifecycle = publication.lifecycle
        source = admission.source_manifest
        if (
            admission.admission_id != command.o2_admission_id
            or admission.target_identity.domestic_selling_target_id
            != command.domestic_selling_target_id
        ):
            raise ShadowValidationLineageError(
                "O2 admission and requested target identity differ"
            )
        target_binding = self._o2.get_target_binding(lifecycle.opportunity_id)
        if target_binding is None:
            raise ShadowValidationSourceNotFoundError(
                "exact O2 target binding was not found"
            )
        if target_binding != publication.target_binding:
            raise ShadowValidationLineageError(
                "O2 admission publication and target authority differ"
            )

        binding = self._promotions.get_promotion_by_opportunity(
            source.source_opportunity_identity.opportunity_id
        )
        if binding is None:
            raise ShadowValidationSourceNotFoundError(
                "exact Candidate-to-O1 binding was not found"
            )
        if any(
            (
                binding.opportunity_id
                != source.source_opportunity_identity.opportunity_id,
                binding.discovery_reference
                != source.source_opportunity_identity.discovery_reference,
                binding.candidate_id != source.candidate_id,
                binding.binding_id != source.candidate_opportunity_binding_id,
                binding.promotion_command_id != source.promotion_command_id,
                binding.finalized_group_id != source.finalized_group_id,
                binding.market_observation_identity != source.source_market_identity,
                binding.product_snapshot_capture_command_id
                != source.product_snapshot_capture_command_id,
                binding.product_snapshot_ids != source.product_snapshot_ids,
                binding.representative_product_snapshot_id
                != source.representative_product_snapshot_id,
            )
        ):
            raise ShadowValidationLineageError(
                "O2 source manifest and Candidate-to-O1 binding differ"
            )
        promotion_receipt = self._promotions.get_promotion_receipt(
            source.promotion_command_id
        )
        if promotion_receipt is None:
            raise ShadowValidationSourceNotFoundError(
                "exact Candidate Promotion receipt was not found"
            )
        if any(
            (
                promotion_receipt.candidate_id != binding.candidate_id,
                promotion_receipt.opportunity_id != binding.opportunity_id,
            )
        ):
            raise ShadowValidationLineageError(
                "Candidate Promotion receipt and binding differ"
            )

        promotion_admission = self._o2.get_promotion_v2_admission(
            binding.opportunity_id
        )
        if promotion_admission is None:
            raise ShadowValidationSourceNotFoundError(
                "exact Candidate Promotion v2 admission was not found"
            )
        if any(
            (
                promotion_admission.admission_id != source.promotion_admission_id,
                promotion_admission.candidate_id != binding.candidate_id,
                promotion_admission.candidate_opportunity_binding_id
                != binding.binding_id,
                promotion_admission.discovery_command_id
                != binding.discovery_command_id,
                promotion_admission.discovery_execution_id
                != binding.discovery_execution_id,
                promotion_admission.finalized_group_id
                != binding.finalized_group_id,
                promotion_admission.product_snapshot_capture_command_id
                != binding.product_snapshot_capture_command_id,
                promotion_admission.product_snapshot_ids
                != binding.product_snapshot_ids,
                promotion_admission.representative_product_snapshot_id
                != binding.representative_product_snapshot_id,
            )
        ):
            raise ShadowValidationLineageError(
                "Candidate Promotion v2 admission and O1 binding differ"
            )

        candidate = self._candidates.get_candidate(binding.candidate_id)
        context = self._candidates.get_context(binding.candidate_id)
        issuance = self._candidates.get_by_discovery_group(
            binding.discovery_command_id, binding.finalized_group_id
        )
        if candidate is None or context is None or issuance is None:
            raise ShadowValidationSourceNotFoundError(
                "exact Candidate issuance lineage was not found"
            )
        if any(
            (
                candidate != context.candidate_identity,
                candidate != issuance.candidate_identity,
                context != issuance.discovery_context,
                candidate.discovery_reference != binding.discovery_reference,
                context.command_id != binding.discovery_command_id,
                context.discovery_execution_id != binding.discovery_execution_id,
                context.market_observation_identity
                != binding.market_observation_identity,
                issuance.discovery_command_id != binding.discovery_command_id,
                issuance.finalized_group_id != binding.finalized_group_id,
            )
        ):
            raise ShadowValidationLineageError(
                "Candidate issuance and Candidate-to-O1 binding differ"
            )

        if not (
            issuance.issued_at
            <= binding.promoted_at
            == promotion_admission.promoted_at
            <= promotion_admission.committed_at
            <= target_binding.bound_at
            <= admission.admitted_at
            <= publication.receipt.committed_at
        ):
            raise ShadowValidationLineageError(
                "Candidate-to-O1-to-O2 authority time lineage is invalid"
            )

        try:
            subject = ShadowO2SubjectLineage.from_authorities(
                admission=admission,
                target_binding=target_binding,
                o2_lifecycle_status=lifecycle.status,
                o2_lifecycle_version=lifecycle.version,
                discovery_command_id=binding.discovery_command_id,
                discovery_execution_id=binding.discovery_execution_id,
                candidate_opportunity_binding_fingerprint=(
                    shadow_authority_fingerprint(binding)
                ),
            )
        except (TypeError, ValueError) as error:
            raise ShadowValidationLineageError(
                "O2 admission and subject lineage are invalid"
            ) from error
        return publication, subject, issuance.issued_at

    def _resolve_screening(
        self,
        command: RegisterShadowValidationCommand,
        subject: ShadowO2SubjectLineage,
        candidate_issued_at: datetime,
    ):
        state = self._screening.get_recording_state(
            subject.discovery_execution_id
        )
        if state is DiscoveryScreeningRecordingState.SCREENING_NOT_RECORDED_LEGACY:
            raise ShadowValidationLegacyScreeningError(
                "legacy discovery completion has no persisted screening authority"
            )
        if state is None:
            raise ShadowValidationSourceNotFoundError(
                "persisted screening completion was not found"
            )
        if state is not DiscoveryScreeningRecordingState.RECORDED:
            raise ShadowValidationLineageError(
                "screening recording state is unsupported"
            )

        bundle = self._screening.get_by_publication(
            command.screening_ranking_publication_id
        )
        publication = self._screening.get_ranking_publication(
            command.screening_ranking_publication_id
        )
        evaluation = self._screening.get_evaluation(
            command.screening_evaluation_id
        )
        if bundle is None or publication is None or evaluation is None:
            raise ShadowValidationSourceNotFoundError(
                "exact persisted screening evaluation/publication was not found"
            )
        if publication != bundle.ranking_publication:
            raise ShadowValidationLineageError(
                "screening publication readers resolve different authority"
            )
        matches = tuple(
            value
            for value in bundle.evaluations
            if value.screening_evaluation_id == evaluation.screening_evaluation_id
        )
        if len(matches) != 1 or matches[0] != evaluation:
            raise ShadowValidationLineageError(
                "screening evaluation does not belong to selected publication"
            )
        group_matches = tuple(
            group
            for group in bundle.finalized_groups
            if group.finalized_group_id == evaluation.finalized_group_id
        )
        if (
            bundle.screening_recording_state
            is not DiscoveryScreeningRecordingState.RECORDED
            or len(group_matches) != 1
            or group_matches[0].membership_fingerprint
            != evaluation.group_membership_fingerprint
        ):
            raise ShadowValidationLineageError(
                "screening completion and finalized Group authority differ"
            )
        if any(
            (
                bundle.execution_result.command_id != subject.discovery_command_id,
                bundle.execution_result.discovery_execution_id
                != subject.discovery_execution_id,
                evaluation.command_id != subject.discovery_command_id,
                evaluation.discovery_execution_id
                != subject.discovery_execution_id,
                evaluation.finalized_group_id != subject.finalized_group_id,
                publication.command_id != subject.discovery_command_id,
                publication.discovery_execution_id
                != subject.discovery_execution_id,
            )
        ):
            raise ShadowValidationLineageError(
                "O2 Candidate lineage and screening authority differ"
            )
        if publication.ranking_created_at > candidate_issued_at:
            raise ShadowValidationLineageError(
                "screening ranking must precede Candidate issuance"
            )
        evidence_values = (
            evaluation.final_opportunity_score,
            evaluation.ranking_economics_key,
            *evaluation.expected_economics,
            *(item.evidence for item in evaluation.input_manifest.used_inputs),
        )
        for evidence in evidence_values:
            for reference in evidence.source_references:
                if any(
                    value is not None and value > evaluation.evaluated_at
                    for value in (reference.observed_at, reference.effective_at)
                ):
                    raise ShadowValidationHindsightError(
                        "screening used-input source follows its evaluation time"
                    )
        try:
            lineage = ShadowScreeningLineage.from_authorities(
                evaluation, publication
            )
        except (TypeError, ValueError) as error:
            raise ShadowValidationLineageError(
                "screening evaluation/publication lineage is invalid"
            ) from error
        return evaluation, publication, lineage

    @staticmethod
    def _source_manifest(
        *, o2_publication, ranking_publication, subject, evaluation, screening_lineage
    ) -> ShadowBaselineSourceManifest:
        projection = _canonical_json(
            screening_input_manifest_to_canonical_data(evaluation.input_manifest)
        )
        return ShadowBaselineSourceManifest(
            sources=(
                ShadowBaselineSourceReference(
                    reference_id="o2.subject",
                    source_owner=ShadowBaselineSourceOwner.OPPORTUNITY,
                    source_kind="o2-subject-lineage",
                    source_id=subject.o2_opportunity_identity.opportunity_id,
                    baseline_role=ShadowBaselineSourceRole.O2_SUBJECT_LINEAGE,
                    availability=ShadowBaselineAvailability.AVAILABLE,
                    truth_scope=ShadowBaselineTruthScope.KOREA_ONLY,
                    source_revision=str(o2_publication.lifecycle.version),
                    source_schema_version=subject.schema_version,
                    source_policy_name=o2_publication.admission.policy_name,
                    source_policy_version=o2_publication.admission.policy_version,
                    source_fingerprint=subject.integrity_fingerprint,
                    generated_at=o2_publication.admission.admitted_at,
                    committed_at=o2_publication.receipt.committed_at,
                ),
                ShadowBaselineSourceReference(
                    reference_id="screening.evaluation",
                    source_owner=ShadowBaselineSourceOwner.DISCOVERY,
                    source_kind="screening-evaluation",
                    source_id=evaluation.screening_evaluation_id,
                    baseline_role=ShadowBaselineSourceRole.SCREENING_EVALUATION,
                    availability=ShadowBaselineAvailability.AVAILABLE,
                    truth_scope=ShadowBaselineTruthScope.SOURCE_DEFINED,
                    source_schema_version=evaluation.schema_version,
                    source_fingerprint=evaluation.integrity_fingerprint,
                    generated_at=evaluation.evaluated_at,
                ),
                ShadowBaselineSourceReference(
                    reference_id="screening.ranking",
                    source_owner=ShadowBaselineSourceOwner.DISCOVERY,
                    source_kind="screening-ranking-publication",
                    source_id=ranking_publication.screening_ranking_publication_id,
                    baseline_role=(
                        ShadowBaselineSourceRole.SCREENING_RANKING_PUBLICATION
                    ),
                    availability=ShadowBaselineAvailability.AVAILABLE,
                    truth_scope=ShadowBaselineTruthScope.POLICY_DEFINED,
                    source_schema_version=ranking_publication.schema_version,
                    source_policy_name=(
                        ranking_publication.ranking_policy.policy_name
                    ),
                    source_policy_version=(
                        ranking_publication.ranking_policy.policy_version
                    ),
                    source_fingerprint=(
                        ranking_publication.integrity_fingerprint
                    ),
                    generated_at=ranking_publication.ranking_created_at,
                ),
                ShadowBaselineSourceReference(
                    reference_id="screening.used-inputs",
                    source_owner=ShadowBaselineSourceOwner.DISCOVERY,
                    source_kind="screening-used-input-manifest",
                    source_id=evaluation.screening_evaluation_id,
                    baseline_role=(
                        ShadowBaselineSourceRole.SCREENING_USED_INPUT_MANIFEST
                    ),
                    availability=ShadowBaselineAvailability.AVAILABLE,
                    truth_scope=ShadowBaselineTruthScope.SOURCE_DEFINED,
                    source_schema_version=evaluation.input_manifest.schema_version,
                    semantic_projection=projection,
                    semantic_projection_fingerprint=(
                        screening_lineage.screening_input_manifest_fingerprint
                    ),
                    generated_at=evaluation.evaluated_at,
                ),
            )
        )

    def execute(
        self, command: RegisterShadowValidationCommand
    ) -> ShadowRegistrationPersistenceResult:
        if not isinstance(command, RegisterShadowValidationCommand):
            raise TypeError("command must be RegisterShadowValidationCommand")
        replay = self._shadow.validate_request_replay(
            command.command_id, command.fingerprint
        )
        if replay is not None:
            return replay

        publication, subject, candidate_issued_at = self._resolve_subject(command)
        evaluation, ranking, screening_lineage = self._resolve_screening(
            command, subject, candidate_issued_at
        )
        knowledge_cutoff_at = max(
            evaluation.evaluated_at,
            ranking.ranking_created_at,
            subject.target_bound_at,
            subject.o2_admitted_at,
            publication.receipt.committed_at,
        )
        try:
            registered_at = _aware(self._registered_clock(), "registered_at")
        except Exception as error:
            raise ShadowValidationClockError(
                "authoritative Shadow registration clock failed"
            ) from error
        if registered_at < command.requested_at:
            raise ShadowValidationClockError(
                "registered_at cannot precede requested_at"
            )
        if registered_at < knowledge_cutoff_at:
            raise ShadowValidationHindsightError(
                "registered_at cannot precede the exact knowledge cutoff"
            )
        try:
            shadow_validation_id = _text(
                self._shadow_validation_id(), "shadow_validation_id"
            )
            baseline_snapshot_id = _text(
                self._baseline_snapshot_id(), "baseline_snapshot_id"
            )
        except Exception as error:
            raise ShadowValidationIdentityGenerationError(
                "authoritative Shadow identity generation failed"
            ) from error

        registration = ShadowValidationRegistration(
            shadow_validation_id=shadow_validation_id,
            baseline_snapshot_id=baseline_snapshot_id,
            authority_kind=ShadowRegistrationAuthorityKind.MACHINE_SCREENING_BASED,
            subject=subject,
            screening_lineage=screening_lineage,
            operator_id=command.operator_id,
            registration_reason=command.registration_reason,
            registered_at=registered_at,
            knowledge_cutoff_at=knowledge_cutoff_at,
            cadence_policy=ShadowVersionedPolicyReference(
                command.cadence_policy_name, command.cadence_policy_version
            ),
            evidence_class=ShadowEvidenceClass.SHADOW_MARKET_THESIS,
        )
        baseline = ShadowBaselineSnapshot(
            registration=registration.reference(),
            source_manifest=self._source_manifest(
                o2_publication=publication,
                ranking_publication=ranking,
                subject=subject,
                evaluation=evaluation,
                screening_lineage=screening_lineage,
            ),
            baseline_created_at=registered_at,
            completeness=ShadowBaselineCompleteness.COMPLETE,
            missing_evidence_dimensions=(),
            calibration_eligibility=ShadowCalibrationEligibility.ELIGIBLE,
            calibration_reason_codes=(),
        )
        try:
            committed_at = _aware(self._committed_clock(), "committed_at")
        except Exception as error:
            raise ShadowValidationClockError(
                "authoritative Shadow commit clock failed"
            ) from error
        if committed_at < registered_at:
            raise ShadowValidationClockError(
                "committed_at cannot precede registered_at"
            )
        return self._shadow.save(
            PersistShadowRegistrationCommand(
                command_id=command.command_id,
                registration=registration,
                baseline=baseline,
                committed_at=committed_at,
                request_fingerprint=command.fingerprint,
            )
        )


__all__ = [
    name
    for name in globals()
    if name.startswith("Shadow")
    or name.startswith("RegisterShadow")
    or name.startswith("REGISTER_SHADOW")
    or name.startswith("DEFAULT_SHADOW")
    or name.startswith("SHADOW_VALIDATION_")
]
