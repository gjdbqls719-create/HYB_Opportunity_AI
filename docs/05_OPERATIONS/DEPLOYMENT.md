# HYB Deployment Guide

## Current Minimum Contract

Development → Staging → Production. Test before deployment and retain a
rollback path.

The authoritative FastAPI composition in `app.web` opens the configured
file-backed SQLite database for production repositories. Discovery command,
observation, finalized Group, and execution-result persistence are currently
wired; Competition, Demand, and Domestic Market Validation v2 use `/api/v2`
routes while the rest of the controlled run also uses `/api/v1` routes.

Before deployment:

1. run the focused OpenAPI/runbook contract test;
2. run documentation/UTF-8/link validation;
3. run the affected feature tests;
4. run the complete regression suite;
5. preserve a recoverable database/deployment rollback point.

Do not treat deployment success as authorization for a genuine run. Follow
`FIRST_REAL_WORLD_VALIDATION_RUNBOOK.md`; keep its STOP conditions in force.
In particular, NAVER total search volume may include overseas searches and is
not Korea-only demand evidence.

## eBay Account Deletion Compliance Deployment

Configure these values through the deployment secret/configuration system:

```text
EBAY_ENV=production
EBAY_CLIENT_ID=<production application client ID>
EBAY_CLIENT_SECRET=<production application client secret>
EBAY_ACCOUNT_DELETION_ENDPOINT_URL=https://<public-host>/api/v1/integrations/ebay/account-deletion
EBAY_ACCOUNT_DELETION_VERIFICATION_TOKEN=<32-80 allowed characters>
```

The endpoint URL must be the exact externally registered absolute HTTPS URL.
Do not use localhost, a private IP, embedded credentials, a fragment, a
request-derived host, or a different trailing-slash form. The verification
token permits only letters, numbers, underscore, and hyphen. Never log or
commit the token, client secret, OAuth token, notification signature, or raw
notification body.

The application process must have read/write access to the configured SQLite
database and its parent directory. Preserve database and WAL/sidecar consistency
in backup/restore procedures, retain a recoverable pre-deployment snapshot, and
verify available disk space. The reverse proxy should enforce HTTPS and a body
limit no greater than the application's 64 KiB limit. It may preserve the public
Host for ordinary routing, but the challenge hash always uses the exact
configured URL.

Rollout milestones are deliberately separate:

1. Deploy the software and configuration to an externally reachable HTTPS URL.
2. Confirm GET challenge response against the exact registered endpoint/token.
3. Confirm a signed eBay test notification returns 202 and creates one verified
   `PENDING_DELETION_REVIEW` receipt; confirm retry returns `REPLAYED`.
4. Monitor 412, 409, 413, and 503 rates without logging sensitive bodies or
   identifiers; verify OAuth/public-key egress to the selected eBay environment.
5. Establish manual receipt review and escalation while PR1 has no deletion
   executor.
6. Complete the audited PR2 data inventory and deletion/anonymization workflow.
7. Complete eBay production key activation/subscription requirements. Real
   production Browse API validation remains a separate milestone.

Rollback may remove the application deployment/configuration, but must preserve
accepted append-only receipt history. Never truncate or mutate the receipt table
to roll back code. If verification or storage is unavailable, keep returning a
retryable 503 rather than acknowledging an unverified or uncommitted event.

Current contract references: the
[Marketplace Account Deletion guide](https://developer.ebay.com/develop/guides/sell/marketplace-user-account-deletion),
[Notification topics](https://developer.ebay.com/develop/api/buy/notification_events),
[public-key API](https://developer.ebay.com/develop/api/commerce/notification_api/public_key/getPublicKey),
and [production keyset guide](https://developer.ebay.com/api-docs/static/gs_create-the-ebay-api-keysets.html).
