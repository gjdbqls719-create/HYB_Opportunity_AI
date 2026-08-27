from __future__ import annotations

from dataclasses import FrozenInstanceError, fields, replace
from datetime import datetime, timedelta, timezone
import json

import pytest

from app.domain.decision_engine import OpportunityIdentity
from app.domain.market_intelligence import MarketObservationIdentity, MarketObservationScope
from app.domain.opportunity import (
    BoundedKRSearchConclusion,
    BoundedKRSearchManifest,
    BoundedKRSearchScopeKind,
    NewToMarketDomesticSellingOpportunityAdmission,
    NewToMarketDomesticSellingSourceManifest,
    NewToMarketDomesticSellingTargetIdentity,
    OpportunityDomesticSellingTargetBinding,
    OpportunityLifecycleStatus,
    ShadowBaselineAvailability,
    ShadowBaselineCompleteness,
    ShadowBaselineEvidenceDimension,
    ShadowBaselineSnapshot,
    ShadowBaselineSourceManifest,
    ShadowBaselineSourceOwner,
    ShadowBaselineSourceReference,
    ShadowBaselineSourceRole,
    ShadowBaselineTruthScope,
    ShadowCalibrationEligibility,
    ShadowCalibrationEligibilityReason,
    ShadowEvidenceClass,
    ShadowO2SubjectLineage,
    ShadowRegistrationAuthorityKind,
    ShadowScreeningLineage,
    ShadowValidationRegistration,
    ShadowVersionedPolicyReference,
    serialize_shadow_baseline_snapshot,
    serialize_shadow_validation_registration,
)
from test_discovery_screening_domain_contracts import (
    NOW,
    evaluation,
    publication,
    ranked_entry,
)


O2_BOUND_AT = NOW - timedelta(hours=2)
REGISTERED_AT = NOW + timedelta(hours=2)
CUTOFF_AT = NOW + timedelta(hours=1)
BASELINE_CREATED_AT = REGISTERED_AT + timedelta(minutes=1)


def _market_identity() -> MarketObservationIdentity:
    return MarketObservationIdentity(
        scope=MarketObservationScope.LISTING,
        market="US",
        marketplace="ebay",
        canonical_product_id=None,
        marketplace_item_id="item-1",
        normalized_query=None,
        category=None,
        variant_identity=None,
        condition="new",
        window_started_at=NOW - timedelta(days=2),
        window_ended_at=NOW - timedelta(days=1),
    )


def _o2_authorities():
    o1 = OpportunityIdentity("o1-1", "candidate:candidate-1")
    o2 = OpportunityIdentity("o2-1", "new-to-market-domestic-selling:o2-admission-1")
    target = NewToMarketDomesticSellingTargetIdentity("target-1")
    source = NewToMarketDomesticSellingSourceManifest(
        source_opportunity_identity=o1,
        source_lifecycle_status=OpportunityLifecycleStatus.DISCOVERED,
        source_lifecycle_version=1,
        source_market_identity=_market_identity(),
        candidate_id="candidate-1",
        candidate_opportunity_binding_id="candidate-binding-1",
        promotion_command_id="promotion-command-1",
        promotion_admission_id="promotion-admission-1",
        finalized_group_id="group-1",
        product_snapshot_capture_command_id="capture-1",
        product_snapshot_ids=("snapshot-1", "snapshot-2"),
        representative_product_snapshot_id="snapshot-1",
        selected_product_snapshot_id="snapshot-1",
        selected_source_observation_id="observation-1",
    )
    search = BoundedKRSearchManifest(
        searched_channels=("coupang",),
        scope_kind=BoundedKRSearchScopeKind.QUERY,
        scope_value="car organizer",
        performed_at=O2_BOUND_AT - timedelta(minutes=3),
        operator_id="founder",
        evidence_references=("evidence/kr-search.png",),
        conclusion=BoundedKRSearchConclusion.EXACT_KR_IDENTITY_NOT_ESTABLISHED,
    )
    admission = NewToMarketDomesticSellingOpportunityAdmission(
        admission_id="o2-admission-1",
        source_manifest=source,
        domestic_opportunity_identity=o2,
        target_identity=target,
        search_manifest=search,
        operator_id="founder",
        decision_reason="evaluate exact product in Korea",
        verified_at=O2_BOUND_AT - timedelta(minutes=2),
        requested_at=O2_BOUND_AT - timedelta(minutes=1),
        admitted_at=O2_BOUND_AT,
        policy_name="new-to-market-domestic-selling-admission",
        policy_version="1.0.0",
    )
    binding = OpportunityDomesticSellingTargetBinding(
        opportunity_id=o2.opportunity_id,
        discovery_reference=o2.discovery_reference,
        target_identity=target,
        bound_at=O2_BOUND_AT,
    )
    return admission, binding


def _subject(**changes) -> ShadowO2SubjectLineage:
    admission, binding = _o2_authorities()
    value = ShadowO2SubjectLineage.from_authorities(
        admission=admission,
        target_binding=binding,
        o2_lifecycle_status=OpportunityLifecycleStatus.DISCOVERED,
        o2_lifecycle_version=1,
        discovery_command_id="command-1",
        discovery_execution_id="execution-1",
        candidate_opportunity_binding_fingerprint="a" * 64,
    )
    return replace(value, integrity_fingerprint="", **changes) if changes else value


def _screening(**changes) -> ShadowScreeningLineage:
    item = evaluation()
    ranking = publication((ranked_entry(item),))
    value = ShadowScreeningLineage.from_authorities(item, ranking)
    return replace(value, integrity_fingerprint="", **changes) if changes else value


def _registration(**changes) -> ShadowValidationRegistration:
    values = {
        "shadow_validation_id": "shadow-1",
        "baseline_snapshot_id": "baseline-1",
        "authority_kind": ShadowRegistrationAuthorityKind.MACHINE_SCREENING_BASED,
        "subject": _subject(),
        "screening_lineage": _screening(),
        "operator_id": "founder",
        "registration_reason": "preserve exact historical machine thesis",
        "registered_at": REGISTERED_AT,
        "knowledge_cutoff_at": CUTOFF_AT,
        "cadence_policy": ShadowVersionedPolicyReference(
            "shadow-validation-cadence", "1.0.0"
        ),
    }
    values.update(changes)
    return ShadowValidationRegistration(**values)


def _source(
    reference_id: str,
    role: ShadowBaselineSourceRole,
    *,
    owner: ShadowBaselineSourceOwner,
    source_kind: str,
    source_id: str,
    source_fingerprint: str | None = None,
    projection_fingerprint: str | None = None,
    generated_at: datetime | None = None,
) -> ShadowBaselineSourceReference:
    return ShadowBaselineSourceReference(
        reference_id=reference_id,
        source_owner=owner,
        source_kind=source_kind,
        source_id=source_id,
        baseline_role=role,
        availability=ShadowBaselineAvailability.AVAILABLE,
        truth_scope=ShadowBaselineTruthScope.SOURCE_DEFINED,
        source_fingerprint=source_fingerprint,
        semantic_projection_fingerprint=projection_fingerprint,
        generated_at=generated_at,
    )


def _manifest(
    registration: ShadowValidationRegistration,
    *additional: ShadowBaselineSourceReference,
) -> ShadowBaselineSourceManifest:
    reference = registration.reference()
    sources = (
        _source(
            "authority.o2-subject",
            ShadowBaselineSourceRole.O2_SUBJECT_LINEAGE,
            owner=ShadowBaselineSourceOwner.OPPORTUNITY,
            source_kind="o2-subject-lineage",
            source_id=reference.o2_opportunity_id,
            source_fingerprint=reference.subject_lineage_fingerprint,
            generated_at=registration.subject.o2_admitted_at,
        ),
        _source(
            "authority.screening-evaluation",
            ShadowBaselineSourceRole.SCREENING_EVALUATION,
            owner=ShadowBaselineSourceOwner.DISCOVERY,
            source_kind="screening-evaluation",
            source_id=reference.screening_evaluation_id,
            source_fingerprint=reference.screening_evaluation_fingerprint,
            generated_at=reference.screening_evaluated_at,
        ),
        _source(
            "authority.screening-input-manifest",
            ShadowBaselineSourceRole.SCREENING_USED_INPUT_MANIFEST,
            owner=ShadowBaselineSourceOwner.DISCOVERY,
            source_kind="screening-used-input-manifest",
            source_id=reference.screening_evaluation_id,
            projection_fingerprint=reference.screening_input_manifest_fingerprint,
            generated_at=reference.screening_evaluated_at,
        ),
        _source(
            "authority.screening-ranking",
            ShadowBaselineSourceRole.SCREENING_RANKING_PUBLICATION,
            owner=ShadowBaselineSourceOwner.DISCOVERY,
            source_kind="screening-ranking-publication",
            source_id=reference.screening_ranking_publication_id,
            source_fingerprint=reference.screening_ranking_publication_fingerprint,
            generated_at=reference.ranking_created_at,
        ),
        *additional,
    )
    return ShadowBaselineSourceManifest(tuple(sorted(sources, key=lambda item: item.reference_id)))


def _baseline(**changes) -> ShadowBaselineSnapshot:
    registration = changes.pop("registration_value", _registration())
    values = {
        "registration": registration.reference(),
        "source_manifest": _manifest(registration),
        "baseline_created_at": BASELINE_CREATED_AT,
        "completeness": ShadowBaselineCompleteness.COMPLETE,
        "missing_evidence_dimensions": (),
        "calibration_eligibility": ShadowCalibrationEligibility.ELIGIBLE,
        "calibration_reason_codes": (),
    }
    values.update(changes)
    return ShadowBaselineSnapshot(**values)


def test_registration_and_baseline_are_immutable_and_exactly_related() -> None:
    registration = _registration()
    baseline = _baseline(registration_value=registration)

    assert registration.authority_kind is ShadowRegistrationAuthorityKind.MACHINE_SCREENING_BASED
    assert registration.evidence_class is ShadowEvidenceClass.SHADOW_MARKET_THESIS
    assert baseline.shadow_validation_id == registration.shadow_validation_id
    assert baseline.baseline_snapshot_id == registration.baseline_snapshot_id
    assert baseline.registration.registration_fingerprint == registration.integrity_fingerprint
    assert baseline.registration.subject_lineage_fingerprint == registration.subject.integrity_fingerprint
    assert baseline.registration.screening_lineage_fingerprint == registration.screening_lineage.integrity_fingerprint
    with pytest.raises(FrozenInstanceError):
        registration.operator_id = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        baseline.baseline_created_at = NOW  # type: ignore[misc]


def test_o2_factory_reuses_authoritative_identity_types_and_rejects_mismatch() -> None:
    subject = _subject()
    assert isinstance(subject.o1_opportunity_identity, OpportunityIdentity)
    assert isinstance(subject.o2_opportunity_identity, OpportunityIdentity)
    assert isinstance(subject.target_identity, NewToMarketDomesticSellingTargetIdentity)
    admission, binding = _o2_authorities()

    with pytest.raises(ValueError, match="lineage differ"):
        ShadowO2SubjectLineage.from_authorities(
            admission=admission,
            target_binding=replace(binding, opportunity_id="different-o2"),
            o2_lifecycle_status=OpportunityLifecycleStatus.DISCOVERED,
            o2_lifecycle_version=1,
            discovery_command_id="command-1",
            discovery_execution_id="execution-1",
            candidate_opportunity_binding_fingerprint="a" * 64,
        )


def test_screening_factory_requires_exact_persisted_publication_entry() -> None:
    item = evaluation()
    good = publication((ranked_entry(item),))
    lineage = ShadowScreeningLineage.from_authorities(item, good)
    assert lineage.screening_evaluation_fingerprint == item.integrity_fingerprint
    assert lineage.screening_ranking_publication_fingerprint == good.integrity_fingerprint

    other = evaluation("evaluation-2", "group-2")
    with pytest.raises(ValueError, match="exact evaluation"):
        ShadowScreeningLineage.from_authorities(item, publication((ranked_entry(other),)))


@pytest.mark.parametrize(
    "changes,match",
    (
        ({"subject": _subject(finalized_group_id="different")}, "lineage differ"),
        ({"subject": _subject(discovery_execution_id="different")}, "lineage differ"),
        ({"knowledge_cutoff_at": REGISTERED_AT + timedelta(seconds=1)}, "cannot follow"),
        ({"knowledge_cutoff_at": NOW - timedelta(seconds=1)}, "screening authority"),
        ({"registered_at": datetime(2026, 8, 26)}, "timezone-aware"),
    ),
)
def test_registration_fails_closed_for_lineage_and_time_errors(changes, match) -> None:
    with pytest.raises(ValueError, match=match):
        _registration(**changes)


def test_registration_rejects_wrong_authority_evidence_and_corrupt_fingerprint() -> None:
    with pytest.raises(ValueError, match="authority"):
        _registration(authority_kind="FOUNDER_DECLARED")
    with pytest.raises(ValueError, match="evidence"):
        _registration(evidence_class="REAL_COMMERCE")
    with pytest.raises(ValueError, match="canonical content"):
        _registration(integrity_fingerprint="f" * 64)


def test_baseline_manifest_is_canonical_and_rejects_duplicate_authority() -> None:
    registration = _registration()
    manifest = _manifest(registration)
    with pytest.raises(ValueError, match="canonical"):
        ShadowBaselineSourceManifest(tuple(reversed(manifest.sources)))
    with pytest.raises(ValueError, match="unique"):
        ShadowBaselineSourceManifest((*manifest.sources, manifest.sources[-1]))


def test_baseline_rejects_wrong_required_reference_and_future_leakage() -> None:
    registration = _registration()
    manifest = _manifest(registration)
    evaluation_source = next(
        item
        for item in manifest.sources
        if item.baseline_role is ShadowBaselineSourceRole.SCREENING_EVALUATION
    )
    wrong = replace(evaluation_source, source_fingerprint="f" * 64)
    wrong_manifest = ShadowBaselineSourceManifest(
        tuple(sorted(
            (wrong if item is evaluation_source else item for item in manifest.sources),
            key=lambda item: item.reference_id,
        ))
    )
    with pytest.raises(ValueError, match="fingerprint differs"):
        _baseline(registration_value=registration, source_manifest=wrong_manifest)

    future = ShadowBaselineSourceReference(
        reference_id="evidence.future-competition",
        source_owner=ShadowBaselineSourceOwner.COMPETITION,
        source_kind="competition-publication",
        source_id="competition-1",
        baseline_role=ShadowBaselineSourceRole.ADDITIONAL_BASELINE_EVIDENCE,
        availability=ShadowBaselineAvailability.AVAILABLE,
        truth_scope=ShadowBaselineTruthScope.KOREA_ONLY,
        source_fingerprint="b" * 64,
        committed_at=CUTOFF_AT + timedelta(seconds=1),
    )
    with pytest.raises(ValueError, match="future evidence"):
        _baseline(
            registration_value=registration,
            source_manifest=_manifest(registration, future),
        )


def test_allowed_missing_evidence_is_explicit_not_numeric_zero() -> None:
    registration = _registration()
    missing_demand = ShadowBaselineSourceReference(
        reference_id="missing.demand",
        source_owner=ShadowBaselineSourceOwner.DEMAND,
        source_kind="korea-only-demand",
        source_id="demand-unavailable",
        baseline_role=ShadowBaselineSourceRole.MISSING_EVIDENCE_MARKER,
        availability=ShadowBaselineAvailability.UNAVAILABLE,
        truth_scope=ShadowBaselineTruthScope.KOREA_ONLY,
        availability_reason="no authoritative Korea-only demand source was available",
    )
    baseline = _baseline(
        registration_value=registration,
        source_manifest=_manifest(registration, missing_demand),
        completeness=ShadowBaselineCompleteness.PARTIAL,
        missing_evidence_dimensions=(ShadowBaselineEvidenceDimension.DEMAND,),
        calibration_eligibility=ShadowCalibrationEligibility.PROVISIONAL,
        calibration_reason_codes=(
            ShadowCalibrationEligibilityReason.INCOMPLETE_BASELINE,
        ),
    )

    marker = next(item for item in baseline.source_manifest.sources if item.reference_id == "missing.demand")
    assert marker.availability is ShadowBaselineAvailability.UNAVAILABLE
    assert marker.semantic_projection is None
    assert marker.source_fingerprint is None


def test_mixed_geography_is_preserved_and_never_upgraded_to_korea_only() -> None:
    registration = _registration()
    mixed = ShadowBaselineSourceReference(
        reference_id="evidence.naver-total-search",
        source_owner=ShadowBaselineSourceOwner.DEMAND,
        source_kind="naver-total-search-volume",
        source_id="naver-observation-1",
        baseline_role=ShadowBaselineSourceRole.ADDITIONAL_BASELINE_EVIDENCE,
        availability=ShadowBaselineAvailability.AVAILABLE,
        truth_scope=ShadowBaselineTruthScope.MIXED_GEOGRAPHY,
        semantic_projection='{"query":"car organizer","scope":"mixed_geography"}',
        observed_at=NOW - timedelta(days=1),
    )
    baseline = _baseline(
        registration_value=registration,
        source_manifest=_manifest(registration, mixed),
        completeness=ShadowBaselineCompleteness.PARTIAL,
        missing_evidence_dimensions=(ShadowBaselineEvidenceDimension.DEMAND,),
        calibration_eligibility=ShadowCalibrationEligibility.PROVISIONAL,
        calibration_reason_codes=(
            ShadowCalibrationEligibilityReason.INCOMPLETE_BASELINE,
            ShadowCalibrationEligibilityReason.MIXED_GEOGRAPHY_EVIDENCE,
        ),
    )
    assert next(item for item in baseline.source_manifest.sources if item.reference_id == mixed.reference_id).truth_scope is ShadowBaselineTruthScope.MIXED_GEOGRAPHY


def test_eligibility_contract_distinguishes_eligible_provisional_and_ineligible() -> None:
    assert _baseline().calibration_eligibility is ShadowCalibrationEligibility.ELIGIBLE
    with pytest.raises(ValueError, match="complete with no reason"):
        _baseline(
            calibration_reason_codes=(
                ShadowCalibrationEligibilityReason.SOURCE_PROVENANCE_LIMITED,
            )
        )
    ineligible = _baseline(
        calibration_eligibility=ShadowCalibrationEligibility.INELIGIBLE,
        calibration_reason_codes=(
            ShadowCalibrationEligibilityReason.KNOWN_HINDSIGHT_AT_REGISTRATION,
        ),
    )
    assert ineligible.calibration_eligibility is ShadowCalibrationEligibility.INELIGIBLE


def test_source_without_availability_time_can_only_be_provisional() -> None:
    registration = _registration()
    unknown_time = ShadowBaselineSourceReference(
        reference_id="evidence.source-without-availability-time",
        source_owner=ShadowBaselineSourceOwner.SOURCING,
        source_kind="supplier-source",
        source_id="supplier-source-1",
        baseline_role=ShadowBaselineSourceRole.ADDITIONAL_BASELINE_EVIDENCE,
        availability=ShadowBaselineAvailability.AVAILABLE,
        truth_scope=ShadowBaselineTruthScope.SOURCE_DEFINED,
        source_fingerprint="c" * 64,
    )
    with pytest.raises(ValueError, match="availability times"):
        _baseline(
            registration_value=registration,
            source_manifest=_manifest(registration, unknown_time),
        )
    provisional = _baseline(
        registration_value=registration,
        source_manifest=_manifest(registration, unknown_time),
        calibration_eligibility=ShadowCalibrationEligibility.PROVISIONAL,
        calibration_reason_codes=(
            ShadowCalibrationEligibilityReason.SOURCE_AVAILABILITY_TIME_UNAVAILABLE,
        ),
    )
    assert provisional.calibration_eligibility is ShadowCalibrationEligibility.PROVISIONAL


def test_fingerprints_and_serialization_are_deterministic_and_corruption_safe() -> None:
    registration = _registration()
    same_in_kst = _registration(
        registered_at=REGISTERED_AT.astimezone(timezone(timedelta(hours=9))),
        knowledge_cutoff_at=CUTOFF_AT.astimezone(timezone(timedelta(hours=9))),
    )
    assert registration.integrity_fingerprint == same_in_kst.integrity_fingerprint
    assert serialize_shadow_validation_registration(registration) == serialize_shadow_validation_registration(same_in_kst)
    assert _registration(registration_reason="different factual reason").integrity_fingerprint != registration.integrity_fingerprint

    baseline = _baseline(registration_value=registration)
    assert json.loads(serialize_shadow_baseline_snapshot(baseline))["evidence_class"] == "SHADOW_MARKET_THESIS"
    with pytest.raises(ValueError, match="canonical content"):
        replace(baseline, integrity_fingerprint="f" * 64)


def test_shadow_contracts_have_no_real_commerce_or_actual_outcome_fields() -> None:
    forbidden = {
        "units_sold", "sold_quantity", "revenue", "realized_revenue", "profit",
        "virtual_profit", "conversion_rate", "advertising_performance",
        "fulfillment_performance", "purchase_execution_id", "actual_outcome_id",
        "approved", "buy_authorized", "investment_approved", "capital_ready",
    }
    contract_fields = {
        field.name
        for contract in (
            ShadowValidationRegistration,
            ShadowBaselineSnapshot,
            ShadowO2SubjectLineage,
            ShadowScreeningLineage,
            ShadowBaselineSourceReference,
        )
        for field in fields(contract)
    }
    assert forbidden.isdisjoint(contract_fields)
