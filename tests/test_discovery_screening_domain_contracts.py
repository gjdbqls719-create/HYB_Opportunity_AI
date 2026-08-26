from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json

import pytest

from app.domain.discovery import (
    PRODUCTION_SAFETY_POLICY_V1,
    PRODUCTION_SCREENING_POLICY_DESCRIPTORS_V1,
    PRODUCTION_SCREENING_RANKING_POLICY_V1,
    DiscoveryScreeningEvaluationSnapshot,
    DiscoveryScreeningRankingPublication,
    NotRankedScreeningEntry,
    NotRankedScreeningReasonCode,
    RankedScreeningEntry,
    ScreeningEvidenceValue,
    ScreeningInputManifest,
    ScreeningInputReference,
    ScreeningPolicyReference,
    ScreeningProvenanceKind,
    ScreeningReasonCategory,
    ScreeningReasonPolarity,
    ScreeningRecommendationSemantics,
    ScreeningRecommendationValue,
    ScreeningSourceKind,
    ScreeningSourceReference,
    ScreeningTruthScope,
    StructuredScreeningReason,
    discovery_screening_evaluation_to_canonical_data,
    discovery_screening_ranking_publication_to_canonical_data,
    screening_evidence_value_to_canonical_data,
    serialize_discovery_screening_evaluation,
    serialize_discovery_screening_ranking_publication,
)
from app.domain.discovery_identity import FinalizedProductGroup


NOW = datetime(2026, 8, 26, 4, 30, 15, 123456, tzinfo=timezone.utc)
POLICY = ScreeningPolicyReference(
    policy_name="production-discovery-screening-score",
    policy_version="1.0.0",
    algorithm_id="opportunity-explainable-screening-v1",
)


def source(
    reference_id: str = "source.observation-1",
    *,
    observed_at: datetime | None = NOW,
) -> ScreeningSourceReference:
    return ScreeningSourceReference(
        reference_id=reference_id,
        source_kind=ScreeningSourceKind.COLLECTED_PRODUCT_OBSERVATION,
        source_identity="observation-1",
        source_fingerprint="a" * 64,
        source_revision="collector-observation-v1",
        observed_at=observed_at,
    )


def observed(
    role: str,
    value: Decimal | int | str | bool,
    *,
    unit: str | None = None,
    currency: str | None = None,
) -> ScreeningEvidenceValue:
    return ScreeningEvidenceValue(
        semantic_role=role,
        provenance_kind=ScreeningProvenanceKind.OBSERVED,
        truth_scope=ScreeningTruthScope.SOURCE_LISTING,
        value=value,
        unit=unit,
        currency=currency,
        source_references=(source(),),
    )


def assumption(
    role: str,
    value: Decimal | int | str | bool,
    *,
    unit: str | None = None,
    currency: str | None = None,
) -> ScreeningEvidenceValue:
    return ScreeningEvidenceValue(
        semantic_role=role,
        provenance_kind=ScreeningProvenanceKind.POLICY_ASSUMPTION,
        truth_scope=ScreeningTruthScope.POLICY_DEFINED,
        value=value,
        unit=unit,
        currency=currency,
        method_reference=POLICY,
    )


def unknown(role: str) -> ScreeningEvidenceValue:
    return ScreeningEvidenceValue(
        semantic_role=role,
        provenance_kind=ScreeningProvenanceKind.UNKNOWN,
        truth_scope=ScreeningTruthScope.FINALIZED_GROUP,
        value=None,
    )


def calculated(
    role: str,
    value: Decimal | int,
    *dependencies: str,
    unit: str | None = None,
    currency: str | None = None,
) -> ScreeningEvidenceValue:
    return ScreeningEvidenceValue(
        semantic_role=role,
        provenance_kind=ScreeningProvenanceKind.CALCULATED,
        truth_scope=ScreeningTruthScope.FINALIZED_GROUP,
        value=value,
        unit=unit,
        currency=currency,
        dependency_references=tuple(sorted(dependencies)),
        method_reference=POLICY,
    )


def manifest() -> ScreeningInputManifest:
    values = (
        ScreeningInputReference(
            "input.competitor_count",
            "score_policy_assumption",
            assumption("competitor_count", 20, unit="listings"),
        ),
        ScreeningInputReference(
            "input.estimated_monthly_sales",
            "score_policy_assumption",
            assumption("estimated_monthly_sales", 100, unit="units_per_month"),
        ),
        ScreeningInputReference(
            "input.purchase_price",
            "economics_input",
            observed("purchase_price", Decimal("10.00"), currency="USD"),
        ),
        ScreeningInputReference(
            "input.risk_level",
            "score_policy_assumption",
            assumption("risk_level", "medium"),
        ),
        ScreeningInputReference(
            "input.shipping_cost",
            "economics_input",
            unknown("shipping_cost"),
        ),
        ScreeningInputReference(
            "input.shipping_cost_calculation_fallback",
            "implementation_fallback_assumption",
            assumption(
                "shipping_cost_calculation_fallback",
                Decimal("0"),
                currency="USD",
            ),
        ),
    )
    return ScreeningInputManifest(
        inputs=values,
        used_input_reference_ids=tuple(
            value.input_reference_id for value in values
        ),
    )


def recommendation() -> ScreeningRecommendationSemantics:
    raw = ScreeningRecommendationValue(
        grade="BUY",
        action="review",
        summary="raw summary",
    )
    effective = ScreeningRecommendationValue(
        grade="WATCH",
        action="review carefully",
        summary="effective summary",
    )
    safety_reason = StructuredScreeningReason(
        reason_code=(
            "discovery.screening.reason.v1.production_safety.missing.shipping_cost"
        ),
        category=ScreeningReasonCategory.PRODUCTION_SAFETY,
        polarity=ScreeningReasonPolarity.BLOCKING,
        source_component="engine.production_safety",
        message="shipping cost is missing",
    )
    return ScreeningRecommendationSemantics(
        raw_recommendation=raw,
        effective_recommendation=effective,
        recommendation_score=72,
        safety_intervention_occurred=True,
        safety_status="INSUFFICIENT_DATA",
        structured_reasons=(safety_reason,),
        safety_reasons=(safety_reason,),
        safety_policy=PRODUCTION_SAFETY_POLICY_V1,
    )


def finalized_group() -> FinalizedProductGroup:
    return FinalizedProductGroup(
        finalized_group_id="group-1",
        discovery_execution_id="execution-1",
        observation_ids=("observation-1", "observation-2"),
        grouping_policy_version="1.0.0",
        representative_observation_id="observation-1",
        finalized_at=NOW,
    )


def evaluation(
    evaluation_id: str = "evaluation-1",
    group_id: str = "group-1",
    *,
    final_score: Decimal = Decimal("81.50"),
    net_profit: Decimal = Decimal("12.00"),
    evaluated_at: datetime = NOW,
) -> DiscoveryScreeningEvaluationSnapshot:
    inputs = manifest()
    net_dependencies = (
        "input.purchase_price",
        "input.shipping_cost",
        "input.shipping_cost_calculation_fallback",
    )
    return DiscoveryScreeningEvaluationSnapshot(
        screening_evaluation_id=evaluation_id,
        command_id="command-1",
        discovery_execution_id="execution-1",
        finalized_group_id=group_id,
        group_membership_fingerprint=finalized_group().membership_fingerprint,
        screening_recommendation=recommendation(),
        final_opportunity_score=calculated(
            "final_opportunity_score",
            final_score,
            "input.competitor_count",
            "input.estimated_monthly_sales",
            "input.risk_level",
        ),
        ranking_economics_key=calculated(
            "per_unit_net_profit",
            net_profit,
            *net_dependencies,
            currency="USD",
        ),
        expected_economics=(
            calculated(
                "net_profit",
                net_profit,
                *net_dependencies,
                currency="USD",
            ),
            observed("purchase_price", Decimal("10"), currency="USD"),
            replace(
                unknown("shipping_cost"),
                dependency_references=("input.shipping_cost",),
            ),
        ),
        screening_policy_manifest=PRODUCTION_SCREENING_POLICY_DESCRIPTORS_V1,
        input_manifest=inputs,
        evaluated_at=evaluated_at,
    )


def ranked_entry(
    value: DiscoveryScreeningEvaluationSnapshot,
    rank: int = 1,
) -> RankedScreeningEntry:
    return RankedScreeningEntry(
        rank=rank,
        discovery_execution_id=value.discovery_execution_id,
        finalized_group_id=value.finalized_group_id,
        screening_evaluation_id=value.screening_evaluation_id,
        evaluation_fingerprint=value.integrity_fingerprint,
    )


def publication(
    ranked_entries: tuple[RankedScreeningEntry, ...],
    not_ranked_entries: tuple[NotRankedScreeningEntry, ...] = (),
    *,
    zero_result: bool = False,
    ranking_created_at: datetime = NOW,
) -> DiscoveryScreeningRankingPublication:
    return DiscoveryScreeningRankingPublication(
        screening_ranking_publication_id="publication-1",
        command_id="command-1",
        discovery_execution_id="execution-1",
        ranked_entries=ranked_entries,
        not_ranked_entries=not_ranked_entries,
        ranking_policy=PRODUCTION_SCREENING_RANKING_POLICY_V1,
        ranking_created_at=ranking_created_at,
        zero_result=zero_result,
    )


def test_evaluation_is_immutable_and_rank_is_not_part_of_the_contract() -> None:
    value = evaluation()

    assert not hasattr(value, "rank")
    assert value.screening_score == value.screening_recommendation.recommendation_score
    with pytest.raises(FrozenInstanceError):
        value.finalized_group_id = "changed"  # type: ignore[misc]


@pytest.mark.parametrize(
    "field",
    (
        "screening_evaluation_id",
        "command_id",
        "discovery_execution_id",
        "finalized_group_id",
    ),
)
def test_evaluation_requires_canonical_non_empty_identities(field: str) -> None:
    with pytest.raises((TypeError, ValueError), match=field):
        replace(evaluation(), **{field: " ", "integrity_fingerprint": ""})


def test_evaluation_requires_aware_time_policy_manifest_and_exact_group_fingerprint() -> None:
    value = evaluation()

    assert value.finalized_group_id == finalized_group().finalized_group_id
    assert value.group_membership_fingerprint == finalized_group().membership_fingerprint
    assert value.screening_policy_manifest is PRODUCTION_SCREENING_POLICY_DESCRIPTORS_V1
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(value, evaluated_at=NOW.replace(tzinfo=None), integrity_fingerprint="")
    with pytest.raises(TypeError, match="screening_policy_manifest"):
        replace(  # type: ignore[arg-type]
            value,
            screening_policy_manifest=None,
            integrity_fingerprint="",
        )


def test_evaluation_composes_pr3_raw_effective_safety_and_structured_reasons() -> None:
    value = evaluation()

    assert value.screening_recommendation.raw_grade == "BUY"
    assert value.screening_recommendation.effective_grade == "WATCH"
    assert value.screening_recommendation.safety_intervention_occurred is True
    assert value.structured_reasons == value.screening_recommendation.structured_reasons
    assert value.screening_recommendation.safety_policy == (
        value.screening_policy_manifest.production_safety
    )


@pytest.mark.parametrize(
    ("kind", "kwargs"),
    (
        (
            ScreeningProvenanceKind.OBSERVED,
            {"source_references": (source(),)},
        ),
        (
            ScreeningProvenanceKind.CALCULATED,
            {"dependency_references": ("input.purchase_price",)},
        ),
        (
            ScreeningProvenanceKind.ESTIMATED,
            {"method_reference": POLICY},
        ),
        (
            ScreeningProvenanceKind.POLICY_ASSUMPTION,
            {"method_reference": POLICY},
        ),
        (ScreeningProvenanceKind.UNKNOWN, {"value": None}),
        (ScreeningProvenanceKind.UNSUPPORTED, {"value": None}),
    ),
)
def test_each_discovery_screening_provenance_kind_is_representable(kind, kwargs) -> None:
    parameters = {
        "semantic_role": "test_value",
        "provenance_kind": kind,
        "truth_scope": ScreeningTruthScope.FINALIZED_GROUP,
        "value": Decimal("1"),
    }
    parameters.update(kwargs)
    value = ScreeningEvidenceValue(**parameters)

    assert value.provenance_kind is kind


def test_observed_evidence_requires_actual_source_and_observation_time() -> None:
    with pytest.raises(ValueError, match="source lineage"):
        ScreeningEvidenceValue(
            "observed_value",
            ScreeningProvenanceKind.OBSERVED,
            ScreeningTruthScope.SOURCE_LISTING,
            Decimal("1"),
        )
    with pytest.raises(ValueError, match="observation time"):
        ScreeningEvidenceValue(
            "observed_value",
            ScreeningProvenanceKind.OBSERVED,
            ScreeningTruthScope.SOURCE_LISTING,
            Decimal("1"),
            source_references=(source(observed_at=None),),
        )


def test_calculated_estimated_and_policy_assumption_require_lineage() -> None:
    with pytest.raises(ValueError, match="dependency lineage"):
        ScreeningEvidenceValue(
            "calculated_value",
            ScreeningProvenanceKind.CALCULATED,
            ScreeningTruthScope.FINALIZED_GROUP,
            Decimal("1"),
        )
    for kind in (
        ScreeningProvenanceKind.ESTIMATED,
        ScreeningProvenanceKind.POLICY_ASSUMPTION,
    ):
        with pytest.raises(ValueError, match="method/policy reference"):
            ScreeningEvidenceValue(
                "method_value",
                kind,
                ScreeningTruthScope.POLICY_DEFINED,
                Decimal("1"),
            )


@pytest.mark.parametrize(
    "kind",
    (ScreeningProvenanceKind.UNKNOWN, ScreeningProvenanceKind.UNSUPPORTED),
)
def test_unknown_and_unsupported_forbid_invented_values(kind) -> None:
    with pytest.raises(ValueError, match="cannot carry a value"):
        ScreeningEvidenceValue(
            "missing_value",
            kind,
            ScreeningTruthScope.FINALIZED_GROUP,
            Decimal("0"),
        )


def test_known_zero_remains_distinct_from_missing() -> None:
    zero = observed("observed_zero", Decimal("0"), unit="items")
    missing = unknown("missing_value")

    assert zero.value == Decimal("0")
    assert zero.provenance_kind is ScreeningProvenanceKind.OBSERVED
    assert missing.value is None
    assert screening_evidence_value_to_canonical_data(zero)["value"] == {
        "kind": "decimal",
        "value": "0",
    }

    with pytest.raises(ValueError, match="must carry an exact value"):
        ScreeningEvidenceValue(
            "calculated_missing",
            ScreeningProvenanceKind.CALCULATED,
            ScreeningTruthScope.FINALIZED_GROUP,
            None,
            dependency_references=("input.purchase_price",),
        )
    with pytest.raises((TypeError, ValueError), match="screening evidence value"):
        observed("unstable_float", 1.5, unit="items")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="numeric evidence value"):
        observed("boolean_units", True, unit="items")


def test_manifest_distinguishes_available_from_actually_used_inputs() -> None:
    available = (
        ScreeningInputReference("input.available", "context", assumption("available", 1)),
        ScreeningInputReference("input.used", "score_input", assumption("used", 2)),
    )
    value = ScreeningInputManifest(available, ("input.used",))

    assert value.inputs == available
    assert value.used_inputs == (available[1],)
    with pytest.raises(ValueError, match="must exist"):
        replace(value, used_input_reference_ids=("input.not-present",))
    self_dependent = ScreeningInputReference(
        "input.self",
        "derived_input",
        calculated("self_value", 1, "input.self"),
    )
    with pytest.raises(ValueError, match="cannot depend on themselves"):
        ScreeningInputManifest((self_dependent,), ("input.self",))


def test_current_fixed_sales_competition_and_risk_are_policy_assumptions() -> None:
    by_role = {item.evidence.semantic_role: item.evidence for item in manifest().inputs}

    for role in ("estimated_monthly_sales", "competitor_count", "risk_level"):
        assert by_role[role].provenance_kind is (
            ScreeningProvenanceKind.POLICY_ASSUMPTION
        )
        assert by_role[role].method_reference == POLICY


def test_mixed_geography_observation_cannot_be_labeled_korea_only() -> None:
    mixed = ScreeningEvidenceValue(
        semantic_role="total_search_volume",
        provenance_kind=ScreeningProvenanceKind.OBSERVED,
        truth_scope=ScreeningTruthScope.MIXED_GEOGRAPHY,
        value=Decimal("10"),
        unit="searches",
        source_references=(source(),),
    )

    assert mixed.truth_scope is ScreeningTruthScope.MIXED_GEOGRAPHY
    assert mixed.truth_scope is not ScreeningTruthScope.KOREA_ONLY


def test_missing_shipping_is_retained_alongside_explicit_fallback_assumption() -> None:
    inputs = {item.input_reference_id: item.evidence for item in manifest().inputs}
    value = evaluation()

    assert inputs["input.shipping_cost"].provenance_kind is ScreeningProvenanceKind.UNKNOWN
    assert inputs["input.shipping_cost"].value is None
    assert inputs["input.shipping_cost_calculation_fallback"].value == Decimal("0")
    assert inputs[
        "input.shipping_cost_calculation_fallback"
    ].provenance_kind is ScreeningProvenanceKind.POLICY_ASSUMPTION
    assert "input.shipping_cost" in value.ranking_economics_key.dependency_references


def test_group_membership_fingerprint_reuses_authoritative_ordered_group_semantics() -> None:
    first = finalized_group()
    repeated = finalized_group()
    changed_membership = replace(
        first,
        observation_ids=("observation-2", "observation-1"),
    )

    assert first.membership_fingerprint == repeated.membership_fingerprint
    assert first.membership_fingerprint != changed_membership.membership_fingerprint
    assert evaluation().group_membership_fingerprint == first.membership_fingerprint


def test_evaluation_fingerprint_is_repeatable_and_rejects_corruption() -> None:
    first = evaluation()
    second = evaluation()

    assert first.integrity_fingerprint == second.integrity_fingerprint
    assert len(first.integrity_fingerprint) == 64
    with pytest.raises(ValueError, match="does not match canonical content"):
        replace(first, integrity_fingerprint="b" * 64)


def test_semantic_change_changes_evaluation_fingerprint() -> None:
    first = evaluation()
    changed = evaluation(final_score=Decimal("81.51"))

    assert first.integrity_fingerprint != changed.integrity_fingerprint


def test_decimal_and_datetime_canonicalization_are_stable() -> None:
    first = evaluation(
        final_score=Decimal("81.5000"),
        net_profit=Decimal("12.00"),
    )
    same_instant = NOW.astimezone(timezone(timedelta(hours=9)))
    second = evaluation(
        final_score=Decimal("81.5"),
        net_profit=Decimal("12"),
        evaluated_at=same_instant,
    )

    assert first.integrity_fingerprint == second.integrity_fingerprint
    assert discovery_screening_evaluation_to_canonical_data(first)[
        "evaluated_at"
    ].endswith("Z")


def test_canonical_projection_is_json_field_order_independent() -> None:
    data = discovery_screening_evaluation_to_canonical_data(evaluation())
    reversed_data = dict(reversed(tuple(data.items())))

    assert json.dumps(data, sort_keys=True) == json.dumps(reversed_data, sort_keys=True)
    assert serialize_discovery_screening_evaluation(evaluation()) == (
        serialize_discovery_screening_evaluation(evaluation())
    )


def test_ranking_publication_enforces_contiguous_ranks() -> None:
    first = evaluation()
    second = evaluation("evaluation-2", "group-2")

    with pytest.raises(ValueError, match="contiguous"):
        publication((ranked_entry(first, 1), ranked_entry(second, 3)))
    with pytest.raises(ValueError, match="contiguous"):
        publication((ranked_entry(first, 1), ranked_entry(second, 1)))


def test_ranking_publication_rejects_duplicate_evaluations_and_groups() -> None:
    first = evaluation()
    same_evaluation_other_group = replace(
        ranked_entry(first, 2), finalized_group_id="group-2"
    )
    with pytest.raises(ValueError, match="exactly once"):
        publication((ranked_entry(first), same_evaluation_other_group))

    second = evaluation("evaluation-2", "group-1")
    with pytest.raises(ValueError, match="finalized Groups"):
        publication((ranked_entry(first), ranked_entry(second, 2)))


def test_ranked_and_not_ranked_sets_cannot_overlap() -> None:
    value = evaluation()
    not_ranked = NotRankedScreeningEntry(
        discovery_execution_id=value.discovery_execution_id,
        finalized_group_id=value.finalized_group_id,
        screening_evaluation_id="evaluation-other",
        evaluation_fingerprint=value.integrity_fingerprint,
        reason_code=NotRankedScreeningReasonCode.UNKNOWN_RANKING_KEY,
        unavailable_semantic_roles=("per_unit_net_profit",),
    )

    with pytest.raises(ValueError, match="cannot overlap"):
        publication((ranked_entry(value),), (not_ranked,))


def test_not_ranked_entry_requires_typed_reason_and_exact_missing_roles() -> None:
    value = evaluation()
    entry = NotRankedScreeningEntry(
        discovery_execution_id=value.discovery_execution_id,
        finalized_group_id=value.finalized_group_id,
        screening_evaluation_id=value.screening_evaluation_id,
        evaluation_fingerprint=value.integrity_fingerprint,
        reason_code=NotRankedScreeningReasonCode.UNSUPPORTED_RANKING_KEY,
        unavailable_semantic_roles=("final_opportunity_score", "per_unit_net_profit"),
    )

    assert entry.reason_code is NotRankedScreeningReasonCode.UNSUPPORTED_RANKING_KEY
    with pytest.raises(ValueError, match="must not be empty"):
        replace(entry, unavailable_semantic_roles=())


def test_publication_rejects_cross_execution_entries() -> None:
    entry = replace(ranked_entry(evaluation()), discovery_execution_id="other")

    with pytest.raises(ValueError, match="one execution"):
        publication((entry,))


def test_zero_result_and_non_zero_semantics_are_explicit() -> None:
    zero = publication((), zero_result=True)

    assert zero.zero_result is True
    assert zero.ranked_entries == zero.not_ranked_entries == ()
    with pytest.raises(ValueError, match="zero-result"):
        publication((ranked_entry(evaluation()),), zero_result=True)
    with pytest.raises(ValueError, match="non-zero"):
        publication(())


def test_publication_requires_aware_time_and_versioned_ranking_policy() -> None:
    value = publication((ranked_entry(evaluation()),))

    assert value.ranking_policy.policy_name
    assert value.ranking_policy.policy_version == "1.0.0"
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(
            value,
            ranking_created_at=NOW.replace(tzinfo=None),
            integrity_fingerprint="",
        )
    with pytest.raises(TypeError, match="ranking_policy"):
        replace(value, ranking_policy=None, integrity_fingerprint="")  # type: ignore[arg-type]


def test_publication_fingerprint_covers_ordered_entries_and_rejects_corruption() -> None:
    first_evaluation = evaluation()
    second_evaluation = evaluation("evaluation-2", "group-2")
    first = publication(
        (ranked_entry(first_evaluation, 1), ranked_entry(second_evaluation, 2))
    )
    reordered = publication(
        (ranked_entry(second_evaluation, 1), ranked_entry(first_evaluation, 2))
    )

    assert first.integrity_fingerprint != reordered.integrity_fingerprint
    assert first.integrity_fingerprint == publication(first.ranked_entries).integrity_fingerprint
    assert discovery_screening_ranking_publication_to_canonical_data(first)[
        "ranked_entries"
    ][0]["evaluation_fingerprint"] == first_evaluation.integrity_fingerprint
    assert serialize_discovery_screening_ranking_publication(first) == (
        serialize_discovery_screening_ranking_publication(first)
    )
    with pytest.raises(ValueError, match="does not match canonical content"):
        replace(first, integrity_fingerprint="c" * 64)


def test_pr3_ranking_semantics_remain_unchanged_and_have_no_grouping_ordinal() -> None:
    policy = publication((ranked_entry(evaluation()),)).ranking_policy

    assert policy.ordered_sort_keys == (
        "effective_recommendation_score:desc",
        "final_opportunity_score:desc",
        "per_unit_net_profit:desc",
    )
    assert policy.equal_key_tie_behavior == "stable_input_order"
    assert all("grouping_ordinal" not in key for key in policy.ordered_sort_keys)
