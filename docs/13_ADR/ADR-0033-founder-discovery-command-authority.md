# ADR-0033: Founder Discovery Command Authority

## Status

Accepted (PR44-B1)

## Context

The Founder Home intentionally asks for only three values: marketplace,
keyword, and collection limit. The authoritative Discovery API accepts a
complete `DiscoveryCommand`, whose parameters also contain pricing, cost, fee,
profitability, sales, competition, risk, currency, matching, policy-reference,
and source-reference facts.

ADR-0029 requires the production runtime to execute every execution-affecting
value from the committed command. A smaller request must not silently fall back
to Engine defaults. The current `config.settings` contains eBay connectivity
configuration only. CLI defaults, `find_best_opportunities` default arguments,
test fixtures, marketplace fee profiles, and the Engine-owned grouping policy
descriptor are not an authoritative Founder Discovery command profile.

The complete-command API currently makes command identity, execution identity,
and `requested_at` caller-supplied. Other production web commands follow the
same pattern: the caller captures intent identity and time, while Application
owners request server-owned aggregate or snapshot identities from injected
suppliers. Discovery production suppliers currently issue observation and
finalized Group identities, not command or execution identities.

Without an explicit command-composition authority, the Home could call the
authoritative API only by exposing every field, hard-coding JavaScript values,
or reusing Engine defaults. None of those behaviors establishes policy
ownership or safe replay.

## Decision

Choose **B: a versioned Founder Discovery Policy Profile**.

The Founder Discovery production composition has three distinct authorities:

1. the Founder Home caller owns the visible search intent and its command
   envelope identity and intent time;
2. the Discovery Application layer owns an immutable, versioned Founder
   Discovery Policy Profile and validates that a submitted complete command
   exactly matches that profile; and
3. the existing Discovery repositories own committed command, completion,
   replay, conflict, and reconstruction facts.

The existing complete `POST /api/v1/discovery/executions` contract remains the
authoritative write boundary. A future Home integration may compose its full
request from server-supplied profile data, but the browser must not invent,
default, or alter hidden execution parameters. The Application boundary must
validate the referenced profile and complete parameter payload before command
persistence.

### Founder-Adjustable Input

The standard Founder Home exposes only:

- marketplace, restricted to production-supported choices;
- a non-blank keyword; and
- a positive collection limit selected from the Home contract.

Those values are explicit Founder intent. A change to any of them is a new
command, not replay of an earlier command.

An advanced trusted caller may continue to submit the existing complete API
request. That interface does not make the standard Founder Home responsible for
all policy fields, and it does not permit the standard Home to bypass active
profile validation.

### Founder Discovery Policy Profile

The Discovery Application layer owns the profile's meaning, validation, and
version. Production composition supplies one immutable supported profile for
each advertised marketplace. A profile contains:

- profile name and version;
- supported marketplace;
- selling-price multiplier;
- shipping and fixed-cost policy;
- marketplace and payment fee rates plus their known flags;
- tax and other cost;
- minimum net profit and ROI;
- estimated monthly sales and competitor count;
- risk level;
- matching threshold;
- target currency when configured; and
- required policy and source references.

Profile values are copied unchanged into `DiscoveryCommandParameters`. They
are not calculated from the keyword, result set, timestamp, collector response,
or Engine defaults. Environment variables may select a deployed profile but
must not anonymously override individual values without a new profile version.

The current eBay credential settings are not this profile. Existing fee
profiles may inform a separately approved Founder profile, but they do not
become command authority merely because they contain fee values.

### Policy and Source References

The complete command records the selected profile through two explicit
`policy_references` entries:

- `("founder_discovery_profile", profile_name)`; and
- `("founder_discovery_profile_version", profile_version)`.

The selected marketplace is preserved in `source_references` as:

- `("marketplace", marketplace)`.

Additional profile-approved source references may be included, but the Home
must not manufacture them. The existing Domain canonicalization remains
authoritative for ordering and fingerprinting these reference pairs.

These command references describe command policy and collection scope. They do
not replace the Engine-owned `GroupingPolicyDescriptor`; finalized Groups
continue to preserve the grouping policy version actually emitted by the
Engine.

### Marketplace Authority

The Founder owns the explicit marketplace choice from the choices advertised
by production composition. The Application profile resolver validates that the
marketplace, profile, and source reference agree.

The current production runtime has only an eBay collection path. Therefore the
standard Home may advertise only eBay. A `source_references` entry is audit
metadata and does not by itself select an Engine collector. Adding another
marketplace requires an explicit runtime and command-contract decision; the UI
must not claim support by adding an option alone.

### Command Identity and Execution Identity

The Founder Home, as the API caller, owns issuance of `command_id` and
`discovery_execution_id` for a fresh submission. Each is an independently
generated opaque value created once when the Founder submits the form.

- The two identities must not be equal by reuse or derived from each other.
- Neither identity may be derived from marketplace, keyword, limit, profile,
  timestamp, policy references, or source references.
- Observation, finalized Group, Candidate, Opportunity, Snapshot, receipt,
  fingerprint, and repository-row identities must not be reused.
- Repository and Application persistence services validate and preserve the
  supplied values; they do not replace them.

This ADR fixes ownership and independence, not a shared identity service or a
new Domain identity type. The production Home adapter may use the platform's
cryptographically secure opaque-ID facility, consistent with existing web
command callers.

### Requested Time

The Founder Home caller owns `requested_at` as the timezone-aware UTC instant
captured once when the fresh command envelope is created. It represents intent
submission time, not collection time, observation time, completion time, or
repository commit time.

The value is preserved unchanged through retries. Repository commit clocks,
observation timestamps, Group finalization clocks, and Discovery completion
clocks retain their existing independent ownership.

### Replay Payload Preservation

The Home adapter creates one complete request envelope per submission and must
retain that exact envelope while the attempt is pending or retryable. A retry
resends the same:

- command ID;
- execution ID;
- requested time;
- visible Founder input;
- profile name and version;
- hidden profile values; and
- policy and source references.

The Home's retained envelope is transport retry state, not authoritative
storage. Once the command is committed, the `DiscoveryCommandRepository` is the
authority for its canonical payload and fingerprint. Repository validation
wins if client retry state differs.

The future Home adapter must preserve pending envelopes across a page reload or
explicitly surface that recovery is unavailable; it must never regenerate a
partially matching command and call that replay. The storage mechanism for this
non-authoritative client retry state is an implementation concern, not a new
Discovery repository contract.

### Policy Change and Replay

The active profile is resolved only when a fresh command envelope is created.

- Exact replay retains the original profile version and values even if a newer
  profile is active.
- Reusing a command ID with a new profile, parameter, reference, timestamp, or
  Founder input is a changed-payload conflict.
- A Founder who intentionally runs under a newer profile creates a new command
  ID and execution ID.
- A profile value change requires a new profile version; silent in-place
  profile mutation is prohibited.

This preserves ADR-0010 through ADR-0012 fingerprint and replay semantics.

### Zero Result and Failure Retry

An authoritative zero-result is a successful committed
`DiscoveryExecutionResult`. Repeating its exact command is completion replay
and must not run the Collector again. A new live search after zero-result uses
new command and execution identities.

A collector or runtime failure after command persistence leaves the committed
command intact and no successful execution result. Retrying that attempt uses
the exact original envelope so the existing persisted command is replayed and
the runtime may execute again. Changing Founder input or policy after such a
failure creates a new command and execution rather than rewriting the failed
command.

Command persistence failure also retains the same pending envelope for an exact
transport retry. No failure path converts a collector failure into zero-result.

## Alternatives

### A. Expose every command value in Founder Home

Rejected for the standard Home. It would make the Founder responsible for
internal pricing, evidence-known, economics, risk, matching, and provenance
policy before a first search. It also would not define which combinations are
approved production policy.

### C. Require a complete command from a separate advanced interface

Retained only as compatibility for trusted advanced callers. It cannot satisfy
the standard Founder Home mission because the Home would still have no owner
for hidden values. It is not the selected production Home path.

### D. Leave authority undecided

Rejected. Existing complete-command, fingerprint, repository replay, caller
command-envelope, and Application policy patterns provide enough boundaries to
assign ownership without changing Discovery calculations.

## Consequences

- The Founder Home remains understandable without presenting internal
  calculation controls.
- JavaScript literals and Engine/CLI defaults cannot become production policy.
- A versioned profile change is auditable in the committed command and always
  creates a new live command.
- The existing Domain command, runtime parameter mapping, persistence,
  completion, read APIs, zero-result, and legacy search contracts remain
  unchanged by this ADR.
- A future implementation needs an Application profile contract and validator,
  a production profile composition, and Home retry-envelope handling before the
  Home can call authoritative Discovery safely.
- This ADR adds no Python code, API behavior, UI behavior, repository, schema,
  test, Candidate workflow, or downstream orchestration.

## Future Implementation Sequence

1. Add the immutable Founder Discovery Policy Profile Application contract and
   production profile composition, without changing Engine defaults.
2. Add profile validation and complete `DiscoveryCommand` assembly for the
   existing authoritative Discovery API boundary.
3. Update Founder Home to create and retain one caller-owned command envelope,
   post it to `POST /api/v1/discovery/executions`, and keep the current loading,
   zero-result, and collector-failure UX.
4. Read the persisted result and ordered finalized Groups through the existing
   GET endpoints using the retained execution ID.
5. Verify fresh execution, exact replay, failed-command retry, profile-version
   change, zero-result, response-loss recovery, and legacy search
   non-regression before production release.
