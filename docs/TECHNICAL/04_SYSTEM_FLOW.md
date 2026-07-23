# System Flow

## Current User-Triggered Flow

```text
User enters a search query
        ↓
Application requests results from enabled marketplaces
        ↓
Each marketplace runs independently
        ↓
Failures are recorded without stopping successful marketplaces
        ↓
Listings are converted to the shared Product model
        ↓
Products are grouped or compared by Product Matching
        ↓
Price Intelligence calculates market price information
        ↓
Trend and Confidence modules calculate supporting signals
        ↓
Opportunity module produces an opportunity score
        ↓
Recommendation module produces an action-oriented result
        ↓
Result is printed and optionally stored in SQLite
```

## Planned Autonomous Flow

```text
Scheduler triggers collection jobs
        ↓
Collectors gather category and keyword data
        ↓
Deduplication and product identity resolution
        ↓
Historical data update
        ↓
Market and cost analysis
        ↓
Opportunity ranking
        ↓
Recommendation generation
        ↓
Threshold and risk checks
        ↓
Alert / dashboard / API delivery
```

## Failure Handling

- One marketplace failure must not stop other marketplaces.
- Missing data lowers confidence rather than silently becoming zero.
- Invalid prices must be rejected or flagged.
- Empty result sets must produce a clear state.
- Storage failure should not corrupt the analysis result.
- Recommendation output must state when evidence is insufficient.
