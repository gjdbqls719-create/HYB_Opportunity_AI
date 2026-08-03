from __future__ import annotations

from dataclasses import replace
from math import isfinite
from typing import Mapping

from app.models import Product, ProductDataSource
from app.domain.opportunity import (
    EconomicsCalculation,
    ProductionSafetyAssessment,
    ProductionSafetyStatus,
)
from engine.price_intelligence import PriceIntelligence
from engine.recommendation import RecommendationResult


def assess_production_safety(
    *,
    product: Product,
    analysis: Mapping[str, object],
    price_intelligence: PriceIntelligence,
    economics: EconomicsCalculation | None = None,
) -> ProductionSafetyAssessment:
    """BUY 추천에 필요한 최소 운영 출처와 경제 데이터를 확인한다."""
    missing: list[str] = []

    if product.data_source is not ProductDataSource.PRODUCTION:
        missing.append("production_source")
    if economics is None:
        if not _is_positive_number(product.price):
            missing.append("purchase_price")
    elif not _is_positive_number(economics.inputs.purchase_cost.amount):
        missing.append("purchase_price")
    if not product.currency.strip():
        missing.append("currency")

    if economics is None:
        shipping_is_known = (
            product.shipping_cost_known
            or analysis.get("shipping_cost_source") == "override"
        )
        if not shipping_is_known:
            missing.append("shipping_cost")

    if (
        price_intelligence.sample_size < 2
        or not _is_positive_number(
            price_intelligence.recommended_selling_price
        )
    ):
        missing.append("expected_selling_price")

    if economics is None:
        fee_fields = (
            ("marketplace_fee_rate", "marketplace_fee_known"),
            ("payment_fee_rate", "payment_fee_known"),
            ("fixed_fee", "fixed_fee_known"),
        )
        for value_field, known_field in fee_fields:
            if (
                analysis.get(known_field) is not True
                or not _is_non_negative_number(analysis.get(value_field))
            ):
                missing.append(value_field)
    else:
        missing.extend(economics.inputs.readiness_missing_fields)

    economic_results = (
        {
            "net_profit": economics.net_profit.amount,
            "roi": economics.roi,
        }
        if economics is not None
        else analysis
    )
    for field_name in ("net_profit", "roi"):
        if not _is_number(economic_results.get(field_name)):
            missing.append(field_name)

    missing = list(dict.fromkeys(missing))

    failed_checks = (
        ()
        if analysis.get("passes_profitability_filter") is True
        else ("profitability_filter",)
    )

    if missing:
        return ProductionSafetyAssessment(
            status=ProductionSafetyStatus.INSUFFICIENT_DATA,
            missing_fields=tuple(missing),
            failed_checks=failed_checks,
        )

    if failed_checks:
        return ProductionSafetyAssessment(
            status=ProductionSafetyStatus.PROFITABILITY_FAILED,
            failed_checks=failed_checks,
        )

    return ProductionSafetyAssessment(status=ProductionSafetyStatus.READY)


def apply_production_safety_gate(
    recommendation: RecommendationResult,
    assessment: ProductionSafetyAssessment,
) -> RecommendationResult:
    """점수는 보존하고 불완전한 BUY 계열 추천만 WATCH로 하향한다."""
    original_grade = recommendation.original_grade or recommendation.grade

    if assessment.can_recommend_buy:
        return replace(
            recommendation,
            safety_status=assessment.status.value,
            safety_reasons=(),
            original_grade=original_grade,
            effective_grade=recommendation.grade,
        )

    reasons = tuple(
        f"필수 운영 데이터 누락: {field_name}"
        for field_name in assessment.missing_fields
    )
    reasons += tuple(
        "수익성 기준 실패: profitability_filter"
        for field_name in assessment.failed_checks
        if field_name == "profitability_filter"
    )
    warnings = recommendation.warnings + reasons

    if recommendation.grade not in {"BUY", "STRONG_BUY"}:
        return replace(
            recommendation,
            warnings=warnings,
            safety_status=assessment.status.value,
            safety_reasons=reasons,
            original_grade=original_grade,
            effective_grade=recommendation.grade,
        )

    profitability_failed = (
        assessment.status is ProductionSafetyStatus.PROFITABILITY_FAILED
    )
    return replace(
        recommendation,
        grade="WATCH",
        action=(
            "수익성 기준 재검토 필요"
            if profitability_failed
            else "필수 경제 데이터 확인 필요"
        ),
        warnings=warnings,
        summary=(
            "PROFITABILITY_FAILED: 점수는 유지되지만 최소 수익성 기준을 "
            "충족하지 않아 매입 추천을 보류합니다."
            if profitability_failed
            else "INSUFFICIENT_DATA: 점수는 유지되지만 필수 운영 데이터가 "
            "완전하지 않아 매입 추천을 보류합니다."
        ),
        safety_status=assessment.status.value,
        safety_reasons=reasons,
        original_grade=original_grade,
        effective_grade="WATCH",
    )


def _is_positive_number(value: object) -> bool:
    return _is_number(value) and float(value) > 0


def _is_non_negative_number(value: object) -> bool:
    return _is_number(value) and float(value) >= 0


def _is_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return isfinite(float(value))
    except (TypeError, ValueError):
        return False
