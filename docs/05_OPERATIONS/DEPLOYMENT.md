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
