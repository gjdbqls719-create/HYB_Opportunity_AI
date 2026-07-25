# Sprint 3 — Opportunity Engine Status

## Goal

Produce an explainable and testable profitability result from purchase price, selling price, fees, shipping, tax, and other costs.

## Completed — Iteration 1

- Unified cost calculation in `engine/opportunity.py`
- Decimal conversion and deterministic rounding
- Marketplace/payment/tax cost calculation
- Landed cost, selling cost, total cost
- Net profit, margin rate, ROI, landed-cost ROI
- Minimum net-profit and ROI filters
- Decision reason and risk warnings
- Orchestrator parameter wiring
- Three new tests
- Full suite: 123 passed

## Current Output Contract

```text
marketplace_fee
payment_fee
tax_cost
selling_cost
landed_cost
total_cost
net_profit
margin_rate
roi
landed_cost_roi
estimated_monthly_profit
opportunity_score
recommendation
decision_reason
reasons
risk_warnings
passes_net_profit_filter
passes_roi_filter
passes_profitability_filter
```

## Next Iteration

Create typed Opportunity request/result models and connect the new cost fields to CLI, persistence, and dashboard output.
