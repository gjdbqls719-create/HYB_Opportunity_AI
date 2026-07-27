# Sprint 4.5.2 PR-2 — Trend Direction

## Added

- first-to-latest price change-rate calculation
- one-decimal percentage quantization using `ROUND_HALF_UP`
- `UP`, `DOWN`, and `STABLE` direction classification
- inclusive stable band from -1.0% through +1.0%
- deterministic chronological ordering before trend calculation
- explicit zero-baseline safety policy

## Direction Policy

- `change_rate > 1.0%` → `UP`
- `change_rate < -1.0%` → `DOWN`
- otherwise → `STABLE`

## Zero-Baseline Policy

Percentage change from a zero baseline is mathematically undefined.

To prevent infinity or division-by-zero values from entering later scoring
layers, the engine applies this bounded policy:

- `0 → 0` returns `0.0%` and `STABLE`
- `0 → positive` returns `100.0%` and `UP`

This policy is explicit and can later be replaced by a richer
`change_rate_status` domain representation if the product model requires it.

## Scope Boundary

Volatility thresholds and near-lowest/near-highest proximity bands remain
reserved for PR-3. Exact boundary flags from PR-1 remain unchanged.

## Test Baseline

- Before PR: 682 passed
- Feature test command:
  `python -m pytest tests/test_trend_analysis_engine.py -q`
- Full regression command:
  `python -m pytest -q`
- Final total: update after local verification
