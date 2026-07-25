# HYB Opportunity AI — Project North Star

## Final Goal

HYB Opportunity AI is an AI-driven commerce opportunity discovery platform.

The system must continuously collect product and market data from multiple online marketplaces, identify equivalent products, estimate true landed cost and realistic selling potential, and surface profitable opportunities before a human manually finds them.

The long-term target is a semi-automated or automated system that can:

1. Monitor marketplaces continuously.
2. Discover products without requiring a user search.
3. Match identical or equivalent products across marketplaces.
4. Compare prices across countries and channels.
5. Include shipping, fees, duties, taxes, risk, competition, and sales velocity.
6. Produce an explainable Opportunity Score.
7. Recommend where, when, and whether to sell.
8. Notify users when high-quality opportunities appear.
9. Later support listing and operational automation.

## North-Star Statement

> AI finds profitable product opportunities before the user does.

## Non-Negotiable Principles

- Architecture before surface features.
- The analysis engine is more important than the UI.
- Real data must gradually replace fake and sandbox data.
- Every score must be explainable and testable.
- Marketplace failures must be isolated from one another.
- New features must contribute to the final goal or be explicitly marked as support work.
- Core domain models must remain unified.
- Tests are required for important behavior.
- Documentation must reflect the real codebase.
- Fast experiments are allowed, but they must not redefine the direction.

## Priority Order

1. Stable architecture and domain model
2. Product matching
3. Price intelligence and landed-cost calculation
4. Opportunity scoring
5. Recommendation engine
6. Real marketplace integrations
7. Automated collection and scheduling
8. API layer
9. Web and app interfaces
10. Alerts, monitoring, and operational automation

## Decision Test

Before adding a feature, ask:

1. Does this improve opportunity discovery, analysis, reliability, or automation?
2. Does it fit the existing architecture?
3. Can it be tested?
4. Is it the highest-value next step?
5. Is it core work or supporting work?

If the feature does not clearly help the North Star, postpone it.
