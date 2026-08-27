"""Construct immutable screening completion from authoritative runtime results."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime
from decimal import Decimal, InvalidOperation

from app.application.discovery.ports import ScreeningIdentityProvider
from app.application.discovery.screening_persistence import (
    DiscoveryScreeningCompletionBinding,
    DiscoveryScreeningCompletionBundle,
)
from app.domain.discovery import (
    DiscoveryResult,
    DiscoveryScreeningEvaluationSnapshot,
    DiscoveryScreeningRankingPublication,
    NotRankedScreeningEntry,
    NotRankedScreeningReasonCode,
    RankedScreeningEntry,
    ScreeningEvidenceValue,
    ScreeningInputManifest,
    ScreeningInputReference,
    ScreeningPolicyDescriptors,
    ScreeningPolicyReference,
    ScreeningProvenanceKind,
    ScreeningSourceKind,
    ScreeningSourceReference,
    ScreeningTruthScope,
)
from app.domain.discovery_identity import (
    CollectedProductObservation,
    DiscoveryCommand,
    DiscoveryExecutionResult,
    FinalizedProductGroup,
)


class DiscoveryScreeningConstructionError(RuntimeError):
    """The live runtime output cannot become an authoritative PR4 snapshot."""


def _decimal(value: object, name: str) -> Decimal:
    if isinstance(value, bool):
        raise DiscoveryScreeningConstructionError(f"{name} must be numeric")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise DiscoveryScreeningConstructionError(
            f"{name} must be numeric"
        ) from error
    if not result.is_finite():
        raise DiscoveryScreeningConstructionError(f"{name} must be finite")
    return result


def _optional_decimal(value: object, name: str) -> Decimal | None:
    if value is None:
        return None
    return _decimal(value, name)


def _analysis(result: DiscoveryResult) -> Mapping[str, object]:
    value = result.metadata.get("analysis")
    if not isinstance(value, Mapping):
        raise DiscoveryScreeningConstructionError(
            "runtime result is missing its exact analysis projection"
        )
    return value


def _policy_reference(
    manifest: ScreeningPolicyDescriptors,
) -> ScreeningPolicyReference:
    score = manifest.score
    return ScreeningPolicyReference(
        policy_name=score.policy_name,
        policy_version=score.policy_version,
        algorithm_id=score.algorithm_id,
    )


def _safety_policy_reference(
    manifest: ScreeningPolicyDescriptors,
) -> ScreeningPolicyReference:
    safety = manifest.production_safety
    return ScreeningPolicyReference(
        policy_name=safety.policy_name,
        policy_version=safety.policy_version,
        algorithm_id=safety.algorithm_id,
    )


def _runtime_method_reference() -> ScreeningPolicyReference:
    return ScreeningPolicyReference(
        policy_name="production-discovery-runtime-economics",
        policy_version="1.0.0",
        algorithm_id="verified-economics-legacy-calculator-v1",
    )


def _price_method_reference() -> ScreeningPolicyReference:
    return ScreeningPolicyReference(
        policy_name="production-discovery-price-intelligence",
        policy_version="1.0.0",
        algorithm_id="group-price-intelligence-v1",
    )


def _source_references(
    *,
    command: DiscoveryCommand,
    group: FinalizedProductGroup,
    observations_by_id: Mapping[str, CollectedProductObservation],
    evaluated_at: datetime,
) -> tuple[
    ScreeningSourceReference,
    ScreeningSourceReference,
    tuple[ScreeningSourceReference, ...],
    ScreeningSourceReference,
]:
    command_reference = ScreeningSourceReference(
        reference_id="source.command",
        source_kind=ScreeningSourceKind.DISCOVERY_COMMAND,
        source_identity=command.command_id,
        source_fingerprint=command.fingerprint,
        source_revision=command.schema_version,
        effective_at=command.requested_at,
    )
    group_reference = ScreeningSourceReference(
        reference_id="source.finalized_group",
        source_kind=ScreeningSourceKind.FINALIZED_PRODUCT_GROUP,
        source_identity=group.finalized_group_id,
        source_fingerprint=group.membership_fingerprint,
        source_revision=group.schema_version,
        effective_at=group.finalized_at,
    )
    observation_references = tuple(
        ScreeningSourceReference(
            reference_id=f"source.observation.{position:04d}",
            source_kind=ScreeningSourceKind.COLLECTED_PRODUCT_OBSERVATION,
            source_identity=observation.observation_id,
            source_revision=observation.schema_version,
            observed_at=observation.observed_at,
        )
        for position, observation_id in enumerate(group.observation_ids, start=1)
        for observation in (observations_by_id[observation_id],)
    )
    runtime_reference = ScreeningSourceReference(
        reference_id="source.runtime_derivation",
        source_kind=ScreeningSourceKind.RUNTIME_DERIVATION,
        source_identity=command.discovery_execution_id,
        effective_at=evaluated_at,
    )
    return (
        command_reference,
        group_reference,
        observation_references,
        runtime_reference,
    )


def _observed(
    role: str,
    value: Decimal | int | bool | str,
    source: ScreeningSourceReference,
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
        source_references=(source,),
    )


def _assumption(
    role: str,
    value: Decimal | int | bool | str,
    *,
    method: ScreeningPolicyReference,
    command_reference: ScreeningSourceReference,
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
        source_references=(command_reference,),
        method_reference=method,
    )


def _missing(
    role: str,
    *,
    kind: ScreeningProvenanceKind = ScreeningProvenanceKind.UNKNOWN,
    sources: tuple[ScreeningSourceReference, ...] = (),
    dependencies: tuple[str, ...] = (),
) -> ScreeningEvidenceValue:
    return ScreeningEvidenceValue(
        semantic_role=role,
        provenance_kind=kind,
        truth_scope=ScreeningTruthScope.FINALIZED_GROUP,
        value=None,
        source_references=tuple(sorted(sources, key=lambda value: value.reference_id)),
        dependency_references=tuple(sorted(dependencies)),
    )


def _calculated(
    role: str,
    value: Decimal | int,
    *dependencies: str,
    method: ScreeningPolicyReference,
    runtime_reference: ScreeningSourceReference,
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
        source_references=(runtime_reference,),
        dependency_references=tuple(sorted(dependencies)),
        method_reference=method,
    )


def _estimated(
    role: str,
    value: Decimal | int,
    *dependencies: str,
    method: ScreeningPolicyReference,
    sources: tuple[ScreeningSourceReference, ...],
    unit: str | None = None,
    currency: str | None = None,
) -> ScreeningEvidenceValue:
    return ScreeningEvidenceValue(
        semantic_role=role,
        provenance_kind=ScreeningProvenanceKind.ESTIMATED,
        truth_scope=ScreeningTruthScope.FINALIZED_GROUP,
        value=value,
        unit=unit,
        currency=currency,
        source_references=tuple(sorted(sources, key=lambda item: item.reference_id)),
        dependency_references=tuple(sorted(dependencies)),
        method_reference=method,
    )


def _input(
    reference_id: str,
    dependency_role: str,
    evidence: ScreeningEvidenceValue,
) -> ScreeningInputReference:
    return ScreeningInputReference(reference_id, dependency_role, evidence)


def _construct_input_manifest(
    *,
    command: DiscoveryCommand,
    group: FinalizedProductGroup,
    result: DiscoveryResult,
    observations_by_id: Mapping[str, CollectedProductObservation],
    evaluated_at: datetime,
    policy_manifest: ScreeningPolicyDescriptors,
) -> tuple[
    ScreeningInputManifest,
    dict[str, ScreeningInputReference],
    ScreeningSourceReference,
]:
    analysis = _analysis(result)
    (
        command_source,
        group_source,
        observation_sources,
        runtime_source,
    ) = _source_references(
        command=command,
        group=group,
        observations_by_id=observations_by_id,
        evaluated_at=evaluated_at,
    )
    representative = observations_by_id[group.representative_observation_id]
    observed_product = representative.product
    runtime_product = result.product
    score_method = _policy_reference(policy_manifest)
    safety_method = _safety_policy_reference(policy_manifest)
    runtime_method = _runtime_method_reference()
    price_method = _price_method_reference()
    currency = str(analysis.get("analysis_currency") or runtime_product.currency).upper()
    parameters = command.parameters
    values: list[ScreeningInputReference] = []

    group_price_ids = []
    for position, (observation_id, source) in enumerate(
        zip(group.observation_ids, observation_sources, strict=True),
        start=1,
    ):
        observation = observations_by_id[observation_id]
        reference_id = f"input.group_price.{position:04d}"
        group_price_ids.append(reference_id)
        values.append(
            _input(
                reference_id,
                "price_intelligence_source",
                _observed(
                    "source_listing_price",
                    _decimal(observation.product.price, "source listing price"),
                    source,
                    currency=observation.product.currency,
                ),
            )
        )

    normalized = (
        runtime_product.currency != observed_product.currency
        or _decimal(runtime_product.price, "runtime purchase price")
        != _decimal(observed_product.price, "observed purchase price")
    )
    conversion_dependencies: tuple[str, ...] = ()
    if parameters.target_currency is not None:
        values.append(
            _input(
                "input.target_currency",
                "currency_normalization_target",
                _assumption(
                    "target_currency",
                    parameters.target_currency,
                    method=runtime_method,
                    command_reference=command_source,
                ),
            )
        )
    if normalized:
        if parameters.target_currency is None:
            raise DiscoveryScreeningConstructionError(
                "runtime purchase price changed without target-currency provenance"
            )
        values.append(
            _input(
                "input.currency_conversion_provenance",
                "currency_conversion_limitation",
                _missing(
                    "currency_conversion_provenance",
                    kind=ScreeningProvenanceKind.UNSUPPORTED,
                    sources=(group_source, runtime_source),
                ),
            )
        )
        conversion_dependencies = (
            "input.currency_conversion_provenance",
            "input.target_currency",
        )

    representative_source = observation_sources[
        group.observation_ids.index(group.representative_observation_id)
    ]
    representative_position = (
        group.observation_ids.index(group.representative_observation_id) + 1
    )
    purchase_dependencies = (
        f"input.group_price.{representative_position:04d}",
        *conversion_dependencies,
    )
    purchase_evidence = (
        _calculated(
            "purchase_price",
            _decimal(runtime_product.price, "purchase price"),
            *purchase_dependencies,
            method=runtime_method,
            runtime_reference=runtime_source,
            currency=currency,
        )
        if normalized
        else _observed(
            "purchase_price",
            _decimal(runtime_product.price, "purchase price"),
            representative_source,
            currency=currency,
        )
    )
    values.extend(
        (
            _input("input.purchase_price", "economics_input", purchase_evidence),
            _input(
                "input.data_source",
                "production_safety_input",
                _observed(
                    "product_data_source",
                    runtime_product.data_source.value,
                    representative_source,
                ),
            ),
            _input(
                "input.in_stock",
                "market_adjustment_input",
                _observed(
                    "in_stock",
                    runtime_product.in_stock,
                    representative_source,
                ),
            ),
        )
    )

    if runtime_product.rating is None:
        seller_rating = _missing(
            "seller_rating",
            sources=(representative_source,),
        )
    else:
        seller_rating = _observed(
            "seller_rating",
            _decimal(runtime_product.rating, "seller rating"),
            representative_source,
        )
    values.append(_input("input.seller_rating", "market_adjustment_input", seller_rating))

    command_assumptions = (
        (
            "competitor_count",
            parameters.competitor_count,
            "listings",
            "score_and_recommendation_input",
            score_method,
        ),
        (
            "estimated_monthly_sales",
            parameters.estimated_monthly_sales,
            "units_per_month",
            "score_and_economics_input",
            score_method,
        ),
        (
            "marketplace_fee_known",
            parameters.marketplace_fee_known,
            None,
            "production_safety_input",
            safety_method,
        ),
        (
            "marketplace_fee_rate",
            parameters.marketplace_fee_rate,
            "ratio",
            "economics_input",
            runtime_method,
        ),
        (
            "minimum_net_profit",
            parameters.minimum_net_profit,
            None,
            "score_recommendation_and_safety_input",
            score_method,
        ),
        (
            "minimum_roi",
            parameters.minimum_roi,
            "percent",
            "score_recommendation_and_safety_input",
            score_method,
        ),
        (
            "other_cost",
            parameters.other_cost,
            None,
            "economics_input",
            runtime_method,
        ),
        (
            "payment_fee_known",
            parameters.payment_fee_known,
            None,
            "production_safety_input",
            safety_method,
        ),
        (
            "payment_fee_rate",
            parameters.payment_fee_rate,
            "ratio",
            "economics_input",
            runtime_method,
        ),
        (
            "risk_level",
            parameters.risk_level,
            None,
            "score_and_recommendation_input",
            score_method,
        ),
        (
            "tax_rate",
            parameters.tax_rate,
            "ratio",
            "economics_input",
            runtime_method,
        ),
    )
    for role, value, unit, dependency_role, method in command_assumptions:
        values.append(
            _input(
                f"input.{role}",
                dependency_role,
                _assumption(
                    role,
                    value,
                    method=method,
                    command_reference=command_source,
                    unit=unit,
                    currency=(currency if role in {"minimum_net_profit", "other_cost"} else None),
                ),
            )
        )

    if parameters.shipping_cost is not None:
        shipping = _assumption(
            "shipping_cost",
            parameters.shipping_cost,
            method=runtime_method,
            command_reference=command_source,
            currency=currency,
        )
    elif runtime_product.shipping_cost_known:
        if normalized:
            values.append(
                _input(
                    "input.source_shipping_cost",
                    "currency_conversion_source",
                    _observed(
                        "source_shipping_cost",
                        _decimal(
                            observed_product.shipping_cost,
                            "source shipping cost",
                        ),
                        representative_source,
                        currency=observed_product.currency,
                    ),
                )
            )
            shipping = _calculated(
                "shipping_cost",
                _decimal(runtime_product.shipping_cost, "shipping cost"),
                "input.source_shipping_cost",
                *conversion_dependencies,
                method=runtime_method,
                runtime_reference=runtime_source,
                currency=currency,
            )
        else:
            shipping = _observed(
                "shipping_cost",
                _decimal(runtime_product.shipping_cost, "shipping cost"),
                representative_source,
                currency=currency,
            )
    else:
        shipping = _missing("shipping_cost", sources=(representative_source,))
    values.append(_input("input.shipping_cost", "economics_input", shipping))
    if shipping.value is None:
        values.append(
            _input(
                "input.shipping_cost_calculation_fallback",
                "implementation_fallback_assumption",
                _assumption(
                    "shipping_cost_calculation_fallback",
                    Decimal("0"),
                    method=runtime_method,
                    command_reference=command_source,
                    currency=currency,
                ),
            )
        )

    if parameters.fixed_fee is None:
        fixed_fee = _missing("fixed_fee", sources=(command_source,))
    else:
        fixed_fee = _assumption(
            "fixed_fee",
            parameters.fixed_fee,
            method=runtime_method,
            command_reference=command_source,
            currency=currency,
        )
    values.extend(
        (
            _input("input.fixed_fee", "economics_input", fixed_fee),
            _input(
                "input.fixed_fee_known",
                "production_safety_input",
                _assumption(
                    "fixed_fee_known",
                    parameters.fixed_fee_known,
                    method=safety_method,
                    command_reference=command_source,
                ),
            ),
        )
    )
    if fixed_fee.value is None:
        values.append(
            _input(
                "input.fixed_fee_calculation_fallback",
                "implementation_fallback_assumption",
                _assumption(
                    "fixed_fee_calculation_fallback",
                    Decimal("0"),
                    method=runtime_method,
                    command_reference=command_source,
                    currency=currency,
                ),
            )
        )

    if len(group.observation_ids) == 1:
        values.append(
            _input(
                "input.selling_price_multiplier",
                "price_intelligence_fallback",
                _assumption(
                    "selling_price_multiplier",
                    parameters.selling_price_multiplier,
                    method=score_method,
                    command_reference=command_source,
                ),
            )
        )
    expected_sale_dependencies = (
        *group_price_ids,
        *conversion_dependencies,
        *(("input.selling_price_multiplier",) if len(group.observation_ids) == 1 else ()),
    )
    expected_selling_price = _estimated(
        "expected_selling_price",
        _decimal(analysis.get("selling_price"), "expected selling price"),
        *expected_sale_dependencies,
        method=price_method,
        sources=(*observation_sources, runtime_source),
        currency=currency,
    )
    values.append(
        _input(
            "input.expected_selling_price",
            "economics_input",
            expected_selling_price,
        )
    )

    economics_dependencies = tuple(
        sorted(
            {
                "input.expected_selling_price",
                "input.fixed_fee",
                "input.marketplace_fee_rate",
                "input.other_cost",
                "input.payment_fee_rate",
                "input.purchase_price",
                "input.shipping_cost",
                "input.tax_rate",
                *(("input.fixed_fee_calculation_fallback",) if fixed_fee.value is None else ()),
                *(("input.shipping_cost_calculation_fallback",) if shipping.value is None else ()),
            }
        )
    )
    net_profit = _optional_decimal(analysis.get("net_profit"), "per-unit net profit")
    roi = _optional_decimal(analysis.get("roi"), "roi")
    if net_profit is not None:
        values.append(
            _input(
                "input.net_profit",
                "recommendation_and_ranking_input",
                _calculated(
                    "net_profit",
                    net_profit,
                    *economics_dependencies,
                    method=runtime_method,
                    runtime_reference=runtime_source,
                    currency=currency,
                ),
            )
        )
    if roi is not None:
        values.append(
            _input(
                "input.roi",
                "recommendation_input",
                _calculated(
                    "roi",
                    roi,
                    *economics_dependencies,
                    method=runtime_method,
                    runtime_reference=runtime_source,
                    unit="percent",
                ),
            )
        )

    raw_score = _decimal(analysis.get("raw_opportunity_score"), "raw opportunity score")
    values.append(
        _input(
            "input.raw_opportunity_score",
            "score_input",
            _calculated(
                "raw_opportunity_score",
                raw_score,
                "input.competitor_count",
                "input.estimated_monthly_sales",
                "input.minimum_net_profit",
                "input.minimum_roi",
                "input.risk_level",
                *(("input.net_profit",) if net_profit is not None else ()),
                *(("input.roi",) if roi is not None else ()),
                method=score_method,
                runtime_reference=runtime_source,
            ),
        )
    )
    confidence_score = _decimal(
        result.metadata.get("confidence_score"), "confidence score"
    )
    values.append(
        _input(
            "input.confidence_score",
            "score_and_recommendation_input",
            _calculated(
                "confidence_score",
                confidence_score,
                *group_price_ids,
                method=score_method,
                runtime_reference=runtime_source,
                unit="percent",
            ),
        )
    )
    adjusted_score = _decimal(
        analysis.get("adjusted_opportunity_score"), "adjusted opportunity score"
    )
    values.append(
        _input(
            "input.adjusted_opportunity_score",
            "final_score_component",
            _calculated(
                "adjusted_opportunity_score",
                adjusted_score,
                "input.confidence_score",
                "input.raw_opportunity_score",
                method=score_method,
                runtime_reference=runtime_source,
            ),
        )
    )

    price_trend_available = result.metadata.get("price_trend_available")
    if price_trend_available not in (True, False, None):
        raise DiscoveryScreeningConstructionError(
            "price trend availability must be boolean when supplied"
        )
    history_kind = (
        ScreeningProvenanceKind.UNSUPPORTED
        if price_trend_available
        else ScreeningProvenanceKind.UNKNOWN
    )
    values.append(
        _input(
            "input.price_history",
            "trend_source",
            _missing("price_history", kind=history_kind, sources=(runtime_source,)),
        )
    )
    trend_adjustment = _decimal(
        result.metadata.get("trend_score_adjustment"), "trend score adjustment"
    )
    values.append(
        _input(
            "input.trend_score_adjustment",
            "final_score_component",
            _calculated(
                "trend_score_adjustment",
                trend_adjustment,
                "input.price_history",
                method=score_method,
                runtime_reference=runtime_source,
            ),
        )
    )
    market_adjustment = _decimal(
        result.metadata.get("market_adjustment"), "market adjustment"
    )
    values.append(
        _input(
            "input.market_adjustment",
            "final_score_and_recommendation_component",
            _calculated(
                "market_adjustment",
                market_adjustment,
                "input.competitor_count",
                "input.in_stock",
                "input.price_history",
                "input.seller_rating",
                method=score_method,
                runtime_reference=runtime_source,
            ),
        )
    )

    ordered = tuple(sorted(values, key=lambda value: value.input_reference_id))
    if len({value.input_reference_id for value in ordered}) != len(ordered):
        raise DiscoveryScreeningConstructionError(
            "screening input construction produced duplicate references"
        )
    manifest = ScreeningInputManifest(
        inputs=ordered,
        used_input_reference_ids=tuple(
            value.input_reference_id for value in ordered
        ),
    )
    return manifest, {value.input_reference_id: value for value in ordered}, runtime_source


def _evaluation(
    *,
    command: DiscoveryCommand,
    group: FinalizedProductGroup,
    result: DiscoveryResult,
    observations_by_id: Mapping[str, CollectedProductObservation],
    identity_provider: ScreeningIdentityProvider,
    evaluated_at: datetime,
) -> DiscoveryScreeningEvaluationSnapshot:
    policy_manifest = result.screening_policy_descriptors
    recommendation = result.screening_recommendation
    if policy_manifest is None or recommendation is None:
        raise DiscoveryScreeningConstructionError(
            "authoritative runtime result is missing PR3 screening semantics"
        )
    manifest, inputs, runtime_source = _construct_input_manifest(
        command=command,
        group=group,
        result=result,
        observations_by_id=observations_by_id,
        evaluated_at=evaluated_at,
        policy_manifest=policy_manifest,
    )
    score_method = _policy_reference(policy_manifest)
    runtime_method = _runtime_method_reference()
    analysis = _analysis(result)
    currency = str(analysis.get("analysis_currency") or result.product.currency).upper()
    net_input = inputs.get("input.net_profit")
    if net_input is None:
        ranking_key = _missing("per_unit_net_profit")
    else:
        ranking_key = _calculated(
            "per_unit_net_profit",
            _decimal(net_input.evidence.value, "per-unit net profit"),
            "input.net_profit",
            method=runtime_method,
            runtime_reference=runtime_source,
            currency=currency,
        )
    final_score = _calculated(
        "final_opportunity_score",
        _decimal(result.opportunity_score, "final opportunity score"),
        "input.adjusted_opportunity_score",
        "input.market_adjustment",
        "input.trend_score_adjustment",
        method=score_method,
        runtime_reference=runtime_source,
    )
    shipping = replace(
        inputs["input.shipping_cost"].evidence,
        dependency_references=("input.shipping_cost",),
    )
    purchase = replace(
        inputs["input.purchase_price"].evidence,
        dependency_references=("input.purchase_price",),
    )
    expected_selling = replace(
        inputs["input.expected_selling_price"].evidence,
        dependency_references=("input.expected_selling_price",),
    )
    expected: list[ScreeningEvidenceValue] = [
        expected_selling,
        purchase,
        shipping,
    ]
    if net_input is not None:
        expected.append(
            _calculated(
                "net_profit",
                _decimal(net_input.evidence.value, "net profit"),
                "input.net_profit",
                method=runtime_method,
                runtime_reference=runtime_source,
                currency=currency,
            )
        )
    roi_input = inputs.get("input.roi")
    if roi_input is not None:
        expected.append(
            _calculated(
                "roi",
                _decimal(roi_input.evidence.value, "roi"),
                "input.roi",
                method=runtime_method,
                runtime_reference=runtime_source,
                unit="percent",
            )
        )
    monthly_profit = _optional_decimal(
        analysis.get("estimated_monthly_profit"), "estimated monthly profit"
    )
    if monthly_profit is not None and net_input is not None:
        expected.append(
            _calculated(
                "estimated_monthly_profit",
                monthly_profit,
                "input.estimated_monthly_sales",
                "input.net_profit",
                method=runtime_method,
                runtime_reference=runtime_source,
                currency=currency,
            )
        )
    return DiscoveryScreeningEvaluationSnapshot(
        screening_evaluation_id=(
            identity_provider.provide_screening_evaluation_id()
        ),
        command_id=command.command_id,
        discovery_execution_id=command.discovery_execution_id,
        finalized_group_id=group.finalized_group_id,
        group_membership_fingerprint=group.membership_fingerprint,
        screening_recommendation=recommendation,
        final_opportunity_score=final_score,
        ranking_economics_key=ranking_key,
        expected_economics=tuple(
            sorted(expected, key=lambda value: value.semantic_role)
        ),
        screening_policy_manifest=policy_manifest,
        input_manifest=manifest,
        evaluated_at=evaluated_at,
    )


def build_discovery_screening_completion_bundle(
    *,
    command: DiscoveryCommand,
    execution_result: DiscoveryExecutionResult,
    finalized_groups: tuple[FinalizedProductGroup, ...],
    discovery_results: tuple[DiscoveryResult, ...],
    observations: tuple[CollectedProductObservation, ...],
    identity_provider: ScreeningIdentityProvider,
    completed_at: datetime,
    zero_result_policy_manifest: ScreeningPolicyDescriptors,
) -> DiscoveryScreeningCompletionBundle:
    """Freeze live screening once; persistence and replay never recalculate it."""

    if not isinstance(identity_provider, ScreeningIdentityProvider):
        raise TypeError("identity_provider must be ScreeningIdentityProvider")
    observations_by_id = {value.observation_id: value for value in observations}
    if len(observations_by_id) != len(observations):
        raise DiscoveryScreeningConstructionError(
            "screening construction received duplicate observations"
        )
    if any(
        observation.discovery_execution_id != command.discovery_execution_id
        for observation in observations
    ):
        raise DiscoveryScreeningConstructionError(
            "screening observation execution differs from the command"
        )
    results_by_group = {value.finalized_group_id: value for value in discovery_results}
    if None in results_by_group or len(results_by_group) != len(discovery_results):
        raise DiscoveryScreeningConstructionError(
            "screening construction requires unique explicit Group correlation"
        )
    if set(results_by_group) != {
        value.finalized_group_id for value in finalized_groups
    }:
        raise DiscoveryScreeningConstructionError(
            "screening results and finalized Groups do not correlate exactly"
        )
    for group in finalized_groups:
        if any(value not in observations_by_id for value in group.observation_ids):
            raise DiscoveryScreeningConstructionError(
                "screening Group references a missing observation"
            )

    evaluations = tuple(
        _evaluation(
            command=command,
            group=group,
            result=results_by_group[group.finalized_group_id],
            observations_by_id=observations_by_id,
            identity_provider=identity_provider,
            evaluated_at=completed_at,
        )
        for group in finalized_groups
    )
    evaluations_by_group = {
        value.finalized_group_id: value for value in evaluations
    }
    policies = {
        value.screening_policy_manifest.ranking for value in evaluations
    }
    if len(policies) > 1:
        raise DiscoveryScreeningConstructionError(
            "one execution cannot publish multiple ranking policies"
        )
    ranking_policy = (
        next(iter(policies))
        if policies
        else zero_result_policy_manifest.ranking
    )
    ranked: list[RankedScreeningEntry] = []
    not_ranked: list[NotRankedScreeningEntry] = []
    for result in discovery_results:
        evaluation = evaluations_by_group[result.finalized_group_id]
        unavailable = tuple(
            value.semantic_role
            for value in (
                evaluation.final_opportunity_score,
                evaluation.ranking_economics_key,
            )
            if value.provenance_kind
            in {
                ScreeningProvenanceKind.UNKNOWN,
                ScreeningProvenanceKind.UNSUPPORTED,
            }
        )
        if unavailable:
            kinds = {
                value.provenance_kind
                for value in (
                    evaluation.final_opportunity_score,
                    evaluation.ranking_economics_key,
                )
                if value.semantic_role in unavailable
            }
            not_ranked.append(
                NotRankedScreeningEntry(
                    discovery_execution_id=command.discovery_execution_id,
                    finalized_group_id=evaluation.finalized_group_id,
                    screening_evaluation_id=evaluation.screening_evaluation_id,
                    evaluation_fingerprint=evaluation.integrity_fingerprint,
                    reason_code=(
                        NotRankedScreeningReasonCode.UNSUPPORTED_RANKING_KEY
                        if ScreeningProvenanceKind.UNSUPPORTED in kinds
                        else NotRankedScreeningReasonCode.UNKNOWN_RANKING_KEY
                    ),
                    unavailable_semantic_roles=tuple(sorted(unavailable)),
                )
            )
        else:
            ranked.append(
                RankedScreeningEntry(
                    rank=len(ranked) + 1,
                    discovery_execution_id=command.discovery_execution_id,
                    finalized_group_id=evaluation.finalized_group_id,
                    screening_evaluation_id=evaluation.screening_evaluation_id,
                    evaluation_fingerprint=evaluation.integrity_fingerprint,
                )
            )
    publication = DiscoveryScreeningRankingPublication(
        screening_ranking_publication_id=(
            identity_provider.provide_screening_ranking_publication_id()
        ),
        command_id=command.command_id,
        discovery_execution_id=command.discovery_execution_id,
        ranked_entries=tuple(ranked),
        not_ranked_entries=tuple(not_ranked),
        ranking_policy=ranking_policy,
        ranking_created_at=completed_at,
        zero_result=execution_result.is_zero_result,
    )
    binding = DiscoveryScreeningCompletionBinding(
        command_id=command.command_id,
        discovery_execution_id=command.discovery_execution_id,
        result_schema_version=execution_result.schema_version,
        result_fingerprint=execution_result.fingerprint,
        screening_ranking_publication_id=(
            publication.screening_ranking_publication_id
        ),
        ranking_publication_fingerprint=publication.integrity_fingerprint,
    )
    return DiscoveryScreeningCompletionBundle(
        execution_result=execution_result,
        finalized_groups=finalized_groups,
        evaluations=evaluations,
        ranking_publication=publication,
        completion_binding=binding,
    )


__all__ = [
    "DiscoveryScreeningConstructionError",
    "build_discovery_screening_completion_bundle",
]
