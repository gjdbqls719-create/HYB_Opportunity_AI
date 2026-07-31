# ADR-0002: Price Observation Idempotency and Partial Failure

## Status

Accepted

## Context

The WatchList Monitor records a price observation before saving the updated
WatchItem. If the observation succeeds but the WatchItem save fails, retrying
the same monitoring attempt must not append a duplicate observation.

Price History and WatchList repositories use separate SQLite connections.
Combining them into one transaction would require a broader repository and
transaction-boundary redesign.

## Decision

An observation identity consists of:

- `canonical_product_id`
- `marketplace`
- `item_id`
- `observed_at`

Price is observation data, not identity.

For an existing identity:

- Identical stored data returns the existing record ID.
- Different data raises `PriceObservationConflictError`.
- The existing record is never updated or deleted.

Data equality compares every persisted observation value:
`canonical_product_id`, `marketplace`, `item_id`, `seller_id`, `title`,
`price`, `currency`, `condition`, `url`, and `observed_at`.

`save_product_price()` starts a SQLite `BEGIN IMMEDIATE` transaction before
checking the identity and inserting. Repository callers using this method are
therefore serialized across separate connections for the same database.

The Monitor retains its existing order:

```text
Change Detection
→ Price Observation Recording
→ WatchItem update
→ WatchList save
```

If observation recording fails, the WatchItem is not updated or saved. If the
observation succeeds and WatchList save fails, the observation remains. A
retry returns its existing ID and continues through WatchList save.

## Alternatives

- A unique index was not added because existing databases may already contain
  duplicate identities, and the project has no migration framework for
  resolving them without deleting or rewriting history.
- A read followed by an ordinary insert was rejected because concurrent
  repository instances could both observe absence and append duplicates.
- A shared Unit of Work, outbox, compensation delete, or cross-repository
  transaction was deferred because it exceeds this PR's scope.

## Consequences

Positive:

- Identical retries are successful and do not append another row.
- Conflicting retries cannot overwrite append-only history.
- A WatchList save failure can recover on retry without duplicate observation
  rows.
- No existing schema or historical row is rewritten.

Trade-offs:

- Price History and WatchList writes remain non-atomic.
- `BEGIN IMMEDIATE` serializes SQLite writers and may increase write
  contention.
- The guarantee applies to writes made through `save_product_price()`;
  direct SQL or other write APIs do not share its idempotency policy.
- Existing duplicate identities are preserved. If their stored values
  disagree, a later retry raises a conflict.

Unit of Work or Outbox should be reconsidered if monitoring becomes
multi-process at high write volume, moves across different databases, or
requires atomic downstream notifications.
