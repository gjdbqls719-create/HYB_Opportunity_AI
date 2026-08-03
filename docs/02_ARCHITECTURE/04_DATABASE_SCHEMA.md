# HYB Database Schema

Domain Model과 Database Model은 명확히 분리한다.

관리 대상:
Product
Price History
Opportunity History
Recommendation History

Product 모델 중복 문제는 통합 대상으로 관리한다.

## Decision Composition Finalization

Production Decision inputs are finalized after admission and authoritative market assessment. `decision_composition_history` is append-only and stores exact source IDs, five evidence metadata values, supported schema/policy versions, and a provenance fingerprint. `decision_composition_current` is an atomic latest projection; Dashboard GET reads it without writes and reconstructs every referenced source from immutable history.

Metadata policy `decision-composition-metadata-v1` uses a 30-day freshness window at explicit finalization `as_of`. Economics and Safety preserve unknown confidence when no authoritative confidence exists. External confidence is the minimum selected-signal confidence; freshness is stale if any selected signal is stale, unknown if timestamps are insufficient, and unavailable when no signal is selected.
