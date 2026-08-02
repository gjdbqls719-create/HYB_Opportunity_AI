from __future__ import annotations

from datetime import datetime

from app.domain.opportunity import (
    EconomicsCalculation,
    EstimatedEconomicsSnapshot,
)


def map_economics_calculation_to_snapshot(
    *,
    snapshot_id: str,
    opportunity_id: str,
    baseline_kind: str,
    economics: EconomicsCalculation,
    calculation_version: str,
    variance_formula_version: str,
    captured_at: datetime,
) -> EstimatedEconomicsSnapshot:
    inputs = economics.inputs
    required = {
        "purchase_price": inputs.purchase_cost.amount,
        "shipping_cost": inputs.shipping_cost.amount,
        "expected_sale_price": inputs.expected_sale_price.amount,
        "marketplace_fee": economics.marketplace_fee.amount,
        "payment_fee": economics.payment_fee.amount,
        "fixed_fee": inputs.fixed_fee.amount,
        "expected_profit": economics.net_profit.amount,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise ValueError(f"economics calculation is missing: {', '.join(missing)}")

    evidence_metadata = {
        "purchase_price": inputs.purchase_cost.evidence,
        "shipping_cost": inputs.shipping_cost.evidence,
        "expected_sale_price": inputs.expected_sale_price.evidence,
        "marketplace_fee": inputs.marketplace_fee_rate.evidence,
        "payment_fee": inputs.payment_fee_rate.evidence,
        "fixed_fee": inputs.fixed_fee.evidence,
        "tax_rate": inputs.tax_rate.evidence,
        "tax_cost": economics.tax_cost.evidence,
        "other_cost": inputs.other_cost.evidence,
        "duty_cost": inputs.duty_cost.evidence,
        "expected_profit": economics.net_profit.evidence,
        "expected_roi": economics.net_profit.evidence,
    }
    return EstimatedEconomicsSnapshot(
        snapshot_id=snapshot_id,
        opportunity_id=opportunity_id,
        baseline_kind=baseline_kind,
        currency=economics.inputs.currency,
        purchase_price=required["purchase_price"],
        shipping_cost=required["shipping_cost"],
        expected_sale_price=required["expected_sale_price"],
        marketplace_fee=required["marketplace_fee"],
        payment_fee=required["payment_fee"],
        fixed_fee=required["fixed_fee"],
        expected_profit=required["expected_profit"],
        expected_roi=economics.roi,
        tax_cost=economics.tax_cost.amount,
        other_cost=inputs.other_cost.amount,
        duty_cost=inputs.duty_cost.amount,
        evidence_metadata=evidence_metadata,
        calculation_version=calculation_version,
        variance_formula_version=variance_formula_version,
        captured_at=captured_at,
    )
