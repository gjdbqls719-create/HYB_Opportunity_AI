from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.application.discovery import (
    FOUNDER_CONSERVATIVE_EBAY_US_V1,
    PersistedDiscoveryResultReader,
)
from app.web import (
    app,
    get_authoritative_discovery_entry,
    get_authoritative_discovery_reader,
)
from tests.test_discovery_execution_completion import close_all, sqlite_entry
from tests.test_discovery_phase_checkpoints import CheckpointRuntime


NOW = datetime(2026, 8, 6, 3, 0, tzinfo=timezone.utc)


def founder_payload(**changes: object) -> dict[str, object]:
    parameters = FOUNDER_CONSERVATIVE_EBAY_US_V1.build_parameters(
        query="mirrorless camera",
        limit=25,
    )
    payload: dict[str, object] = {
        "command_id": "founder-command-1",
        "discovery_execution_id": "founder-execution-1",
        "requested_at": NOW.isoformat(),
        "query": parameters.query,
        "selling_price_multiplier": str(parameters.selling_price_multiplier),
        "shipping_cost": str(parameters.shipping_cost),
        "marketplace_fee_rate": str(parameters.marketplace_fee_rate),
        "payment_fee_rate": str(parameters.payment_fee_rate),
        "fixed_fee": str(parameters.fixed_fee),
        "marketplace_fee_known": parameters.marketplace_fee_known,
        "payment_fee_known": parameters.payment_fee_known,
        "fixed_fee_known": parameters.fixed_fee_known,
        "tax_rate": str(parameters.tax_rate),
        "other_cost": str(parameters.other_cost),
        "minimum_net_profit": str(parameters.minimum_net_profit),
        "minimum_roi": str(parameters.minimum_roi),
        "estimated_monthly_sales": parameters.estimated_monthly_sales,
        "competitor_count": parameters.competitor_count,
        "risk_level": parameters.risk_level,
        "limit": parameters.limit,
        "match_threshold": str(parameters.match_threshold),
        "target_currency": parameters.target_currency,
        "policy_references": [list(value) for value in parameters.policy_references],
        "source_references": [list(value) for value in parameters.source_references],
    }
    payload.update(changes)
    return payload


class RecordingEntry:
    def __init__(self) -> None:
        self.commands = []

    def execute(self, command):
        self.commands.append(command)
        return SimpleNamespace(
            execution_result=SimpleNamespace(
                command_id=command.command_id,
                discovery_execution_id=command.discovery_execution_id,
                completed_at=NOW,
                is_zero_result=True,
            ),
            finalized_groups=(),
            completion_replayed=False,
        )


def test_home_exposes_only_server_supplied_founder_profile() -> None:
    response = TestClient(app).get("/")

    assert response.status_code == 200
    assert '"profile_name": "founder-conservative-ebay-us"' in response.text
    assert '"profile_version": "1.0.0"' in response.text
    assert '"marketplace": "ebay"' in response.text
    assert '"marketplace_source_reference": "EBAY_US"' in response.text
    assert '"shipping_cost": "12.00"' in response.text
    assert '"marketplace_fee_rate": "0.153"' in response.text
    assert '"match_threshold": "90"' in response.text


def test_home_uses_authoritative_post_then_result_and_group_reads() -> None:
    html = TestClient(app).get("/").text

    post = 'fetch("/api/v1/discovery/executions"'
    result = 'fetch(`/api/v1/discovery/executions/${executionId}`'
    groups = (
        'fetch(`/api/v1/discovery/executions/${executionId}/finalized-groups`'
    )
    assert post in html
    assert result in html
    assert groups in html
    assert html.index(post) < html.index(result) < html.index(groups)
    assert 'fetch("/api/v1/opportunities/search"' not in html


def test_home_retains_exact_replay_envelope_and_loading_states() -> None:
    html = TestClient(app).get("/").text

    assert "crypto.randomUUID()" in html
    assert "sessionStorage.setItem" in html
    assert "sessionStorage.getItem" in html
    assert "requested_at: new Date().toISOString()" in html
    assert "Searching eBay..." in html
    assert "Discovery running..." in html
    assert "Reading Result..." in html
    assert "Reading Groups..." in html
    assert "Completed" in html


def test_profile_referenced_request_is_validated_before_runtime_entry() -> None:
    entry = RecordingEntry()
    app.dependency_overrides[get_authoritative_discovery_entry] = lambda: entry
    client = TestClient(app)
    try:
        accepted = client.post(
            "/api/v1/discovery/executions",
            json=founder_payload(),
        )
        rejected = client.post(
            "/api/v1/discovery/executions",
            json=founder_payload(shipping_cost="11.00"),
        )
    finally:
        app.dependency_overrides.clear()

    assert accepted.status_code == 201
    assert accepted.json()["is_zero_result"] is True
    assert rejected.status_code == 422
    assert "does not match founder discovery profile" in rejected.json()["detail"]
    assert len(entry.commands) == 1
    assert entry.commands[0].parameters.shipping_cost == Decimal("12.00")


def test_profile_referenced_request_rejects_unsupported_or_incomplete_identity() -> None:
    entry = RecordingEntry()
    app.dependency_overrides[get_authoritative_discovery_entry] = lambda: entry
    client = TestClient(app)
    references = founder_payload()["policy_references"]
    assert isinstance(references, list)
    try:
        unsupported = client.post(
            "/api/v1/discovery/executions",
            json=founder_payload(
                policy_references=[
                    references[0],
                    ["founder_discovery_profile_version", "2.0.0"],
                ]
            ),
        )
        incomplete = client.post(
            "/api/v1/discovery/executions",
            json=founder_payload(policy_references=[references[0]]),
        )
    finally:
        app.dependency_overrides.clear()

    assert unsupported.status_code == 422
    assert incomplete.status_code == 422
    assert entry.commands == []


def test_founder_profile_collector_failure_remains_explicit_502() -> None:
    class FailingEntry:
        def execute(self, command):
            raise RuntimeError("collector unavailable")

    app.dependency_overrides[get_authoritative_discovery_entry] = FailingEntry
    try:
        response = TestClient(app).post(
            "/api/v1/discovery/executions",
            json=founder_payload(),
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 502
    assert response.json()["detail"] == "authoritative discovery execution failed"


def test_founder_profile_fresh_replay_and_authoritative_reads(tmp_path) -> None:
    runtime = CheckpointRuntime([])
    entry, *repositories = sqlite_entry(tmp_path / "founder.db", runtime)
    reader = PersistedDiscoveryResultReader(
        result_repository=repositories[3],
        group_repository=repositories[2],
    )
    app.dependency_overrides[get_authoritative_discovery_entry] = lambda: entry
    app.dependency_overrides[get_authoritative_discovery_reader] = lambda: reader
    client = TestClient(app)
    try:
        fresh = client.post(
            "/api/v1/discovery/executions",
            json=founder_payload(),
        )
        replay = client.post(
            "/api/v1/discovery/executions",
            json=founder_payload(),
        )
        result = client.get(
            "/api/v1/discovery/executions/founder-execution-1"
        )
        groups = client.get(
            "/api/v1/discovery/executions/"
            "founder-execution-1/finalized-groups"
        )
    finally:
        app.dependency_overrides.clear()
        close_all(*repositories)

    assert fresh.status_code == 201
    assert replay.status_code == 200
    assert replay.json()["completion_replayed"] is True
    assert result.status_code == groups.status_code == 200
    assert result.json()["discovery_execution_id"] == "founder-execution-1"
    assert result.json()["finalized_group_ids"] == [
        group["finalized_group_id"]
        for group in groups.json()["finalized_groups"]
    ]
    assert len(runtime.calls) == 1


def test_founder_profile_zero_result_is_completed_and_readable(tmp_path) -> None:
    runtime = CheckpointRuntime([])
    runtime.collection_facts = ()
    runtime.grouping_correlations = ()
    entry, *repositories = sqlite_entry(tmp_path / "founder-zero.db", runtime)
    reader = PersistedDiscoveryResultReader(
        result_repository=repositories[3],
        group_repository=repositories[2],
    )
    app.dependency_overrides[get_authoritative_discovery_entry] = lambda: entry
    app.dependency_overrides[get_authoritative_discovery_reader] = lambda: reader
    client = TestClient(app)
    try:
        fresh = client.post(
            "/api/v1/discovery/executions",
            json=founder_payload(),
        )
        result = client.get(
            "/api/v1/discovery/executions/founder-execution-1"
        )
        groups = client.get(
            "/api/v1/discovery/executions/"
            "founder-execution-1/finalized-groups"
        )
    finally:
        app.dependency_overrides.clear()
        close_all(*repositories)

    assert fresh.status_code == 201
    assert fresh.json()["is_zero_result"] is True
    assert result.status_code == groups.status_code == 200
    assert result.json()["is_zero_result"] is True
    assert result.json()["finalized_group_ids"] == []
    assert groups.json()["finalized_groups"] == []
