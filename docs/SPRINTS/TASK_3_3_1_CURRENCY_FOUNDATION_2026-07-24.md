# Task 3.3.1 — Currency Foundation

## Status

Implemented and verified. This document records a task checkpoint only; it does not close Sprint 3.3.

## Added modules

- `services/currency/models.py`
  - currency-code normalization
  - `ExchangeRate` immutable value model
  - Decimal-safe numeric conversion
  - inverse-rate generation
- `services/currency/provider.py`
  - `ExchangeRateProvider` abstract interface
  - `ExchangeRateNotFoundError`
- `services/currency/mock_provider.py`
  - in-memory rates for tests and local development
  - direct, inverse, and same-currency lookup
- `services/currency/converter.py`
  - provider-driven currency conversion
  - Decimal arithmetic
  - configurable monetary rounding
- `services/currency/__init__.py`
  - public currency API exports

## Tests

- Added `tests/test_currency.py` with 12 tests.
- Existing behavior remains unchanged.
- Full suite result: **136 passed**.

## Integration boundary

Currency Foundation is intentionally isolated from Opportunity Engine, CLI, dashboard, and storage. Integration will be handled as a separate task after the foundation API is reviewed.
