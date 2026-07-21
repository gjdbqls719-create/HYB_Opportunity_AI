# Architecture

## Architectural Style

HYB Opportunity AI uses a modular pipeline architecture. Marketplace-specific code is isolated from domain analysis, and analysis modules are coordinated by an orchestrator.

## High-Level Flow

```text
main.py / CLI / future API
          ↓
Application Layer
          ↓
Marketplace Collectors
          ↓
Normalized Product Objects
          ↓
Engine Orchestrator
   ├─ Product Matching
   ├─ Price Intelligence
   ├─ Price Trend
   ├─ Trend Scoring
   ├─ Confidence
   ├─ Opportunity
   └─ Recommendation
          ↓
Storage / Presentation / Alerts
```

## Main Packages

### `app/`
Application entry behavior, CLI coordination, and later API-facing application services.

### `collectors/`
Shared collector contracts and common collection behavior.

### `marketplaces/`
Marketplace-specific adapters such as eBay and Amazon.

### `engine/`
Domain analysis. This is the core intellectual property of the project.

### `database/`
Persistence-facing models or compatibility exports. Domain model duplication must be avoided.

### `storage/`
Local persistence implementations such as price history and opportunity history.

### `market_data/`
Market snapshots and market-level data structures.

### `services/`
External-service support such as marketplace authentication.

### `tests/`
Unit and integration tests for domain behavior.

## Core Rule

Marketplace adapters return normalized domain objects. Engine modules must not depend on raw marketplace response formats.

## Orchestrator Responsibility

The orchestrator coordinates modules but should not contain every calculation. Each engine module should:

- Accept explicit typed inputs.
- Return explicit typed outputs.
- Avoid hidden global state.
- Provide evidence or reasons where possible.
- Remain independently testable.

## Future Boundaries

```text
Collectors → Domain Models → Analysis Engine → Application Services → API/UI
```

FastAPI and React should be added outside the engine and must not force engine logic into route handlers or components.
