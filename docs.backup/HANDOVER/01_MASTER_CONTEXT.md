# Master Context

## Project Name

HYB Opportunity AI

## Product Definition

A multi-market product intelligence system that collects listings, matches equivalent products, analyses price and market signals, calculates opportunity quality, and generates recommendations.

## Intended Markets

Initial focus:

- United States
- South Korea

Planned marketplace coverage:

- eBay
- Amazon
- Walmart
- Coupang
- AliExpress
- Temu
- Additional marketplaces through a common collector interface

## Core Processing Pipeline

```text
Marketplace Collectors
        ↓
Normalized Product Model
        ↓
Product Matching
        ↓
Price Intelligence
        ↓
Trend / Confidence Analysis
        ↓
Opportunity Scoring
        ↓
Recommendation Engine
        ↓
Storage / API / Dashboard / Alerts
```

## Development Philosophy

The project is not primarily a search page, scraper, or price-comparison site. Those are components. The core product is the decision engine that determines whether a product opportunity is credible and worthwhile.

## Current Working Assumptions

- Python is the primary backend language.
- SQLite is acceptable during local development.
- A common Product model is used across collectors, engines, and storage.
- Each marketplace must fail independently.
- CLI remains useful for development and testing.
- Web UI is support infrastructure and should not drive domain design.
- Fake marketplace data may be used temporarily but must be clearly identified.
