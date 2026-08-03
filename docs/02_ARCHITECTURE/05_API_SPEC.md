# HYB API Specification

API는 Engine 외부 계층이다.

API
↓
Service
↓
Engine
↓
Marketplace / Storage

Route에 분석 로직을 넣지 않는다.

## Decision Composition Finalization

`POST /api/v1/opportunities/{opportunity_id}/decision-compositions` explicitly finalizes one immutable production Decision Composition and returns HTTP 201. The optional request fields are `external_signal_ids`, timezone-aware `generated_at`, and `requested_by`; `requested_by` is an audit hint and is not persisted by the current snapshot contract. Omitted or null signal IDs select all latest HUMAN_VERIFIED series, while an empty list selects none.

The endpoint delegates all source selection, metadata, provenance, versioning, and atomic persistence to the application/repository boundaries. It writes only `decision_composition_history` and `decision_composition_current`. Repeated identical provenance returns HTTP 409. The existing Dashboard GET remains read-only and returns HTTP 200 after successful finalization.
