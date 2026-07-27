# Sprint 4.5.2 PR-3 — Volatility and Price Position

## Added

- immutable `TrendAnalysisPolicy`
- average-price-normalized volatility classification
- `LOW`, `MEDIUM`, and `HIGH` volatility policies
- near-lowest and near-highest price-position analysis
- configurable direction, volatility, and proximity thresholds
- validation for invalid policy configuration

## Default Volatility Policy

The engine calculates:

`range_rate = (highest_price - lowest_price) / average_price * 100`

Then classifies:

- `range_rate <= 5.0%` → `LOW`
- `5.0% < range_rate <= 15.0%` → `MEDIUM`
- `range_rate > 15.0%` → `HIGH`

If the average price is zero, volatility is treated as `LOW`.

## Default Price-Position Policy

The engine uses a 5.0% band at each end of the observed price range.

- distance from lowest <= 5.0% of range → `near_lowest=True`
- distance from highest <= 5.0% of range → `near_highest=True`

If all observed prices are equal, the current price is simultaneously the
lowest and highest price, so both flags are `True`.

## Architecture Decision

Thresholds are isolated in `TrendAnalysisPolicy` rather than embedded
throughout the engine. Future marketplace-specific or category-specific
policies can therefore be injected without rewriting calculation logic.

## Test Baseline

- Before PR: 692 passed
- Feature test command:
  `python -m pytest tests/test_trend_analysis_engine.py -q`
- Full regression command:
  `python -m pytest -q`
- Final total: update after local verification
