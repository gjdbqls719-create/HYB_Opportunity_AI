from copy import deepcopy
import inspect

import pytest
from fastapi.testclient import TestClient

from app.application.dashboard_api import (
    DashboardDecisionConflictError,
    DashboardDecisionNotFoundError,
    DashboardDecisionUnavailableError,
    OpportunityDecisionDashboardSource,
)
from app.domain.decision_engine import DecisionOutcome, OpportunityIdentity
from app.web import app, get_opportunity_decision_dashboard_provider
from app.web import get_opportunity_decision_dashboard
from test_dashboard_read_model import read_model


class FakeDashboardProvider:
    def __init__(self, source=None, error=None):
        self.source = source
        self.error = error
        self.calls = []

    def get(self, opportunity_id):
        self.calls.append(opportunity_id)
        if self.error is not None:
            raise self.error
        return self.source


def source(outcome=DecisionOutcome.INVEST, opportunity_id="opp-api"):
    return OpportunityDecisionDashboardSource(
        opportunity_identity=OpportunityIdentity(
            opportunity_id=opportunity_id,
            discovery_reference="ebay:item-api",
        ),
        read_model=read_model(outcome),
    )


@pytest.fixture
def client_and_provider():
    provider = FakeDashboardProvider(source())
    app.dependency_overrides[get_opportunity_decision_dashboard_provider] = (
        lambda: provider
    )
    try:
        yield TestClient(app), provider
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "outcome",
    tuple(DecisionOutcome),
)
def test_all_business_outcomes_return_http_200(outcome) -> None:
    provider = FakeDashboardProvider(source(outcome))
    app.dependency_overrides[get_opportunity_decision_dashboard_provider] = (
        lambda: provider
    )
    try:
        response = TestClient(app).get(
            "/api/v1/opportunities/opp-api/decision-dashboard"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["summary"]["outcome"] == outcome.value


def test_response_uses_exact_dto_serialization_and_preserves_order(
    client_and_provider,
) -> None:
    client, provider = client_and_provider
    before = deepcopy(provider.source)

    response = client.get("/api/v1/opportunities/opp-api/decision-dashboard")
    payload = response.json()

    assert set(payload) == {"summary", "action", "warnings", "evidence", "metadata"}
    assert payload["summary"]["confidence"] == "0.875"
    assert isinstance(payload["summary"]["confidence"], str)
    assert payload["summary"]["summary_code"] == "invest_ready"
    assert [item["dimension"] for item in payload["evidence"]] == [
        "economics", "safety", "competition", "demand", "external_reference"
    ]
    assert [item["display_order"] for item in payload["warnings"]] == list(
        range(1, len(payload["warnings"]) + 1)
    )
    assert payload["metadata"]["generated_at"].endswith("+00:00")
    assert payload["metadata"]["read_model_version"] == "1.0"
    assert payload["metadata"]["schema_version"] == "decision-input-v1"
    assert payload["metadata"]["policy_version"] == "decision-policy-v1"
    assert provider.source == before


def test_path_opportunity_id_is_propagated_without_writes(client_and_provider) -> None:
    client, provider = client_and_provider

    response = client.get("/api/v1/opportunities/opp-api/decision-dashboard")

    assert response.status_code == 200
    assert provider.calls == ["opp-api"]


@pytest.mark.parametrize(
    ("error", "status_code"),
    (
        (DashboardDecisionNotFoundError("dashboard source not found"), 404),
        (DashboardDecisionConflictError("dashboard state conflict"), 409),
        (DashboardDecisionUnavailableError("dashboard source unavailable"), 503),
    ),
)
def test_application_errors_have_explicit_http_mapping(error, status_code) -> None:
    provider = FakeDashboardProvider(error=error)
    app.dependency_overrides[get_opportunity_decision_dashboard_provider] = (
        lambda: provider
    )
    try:
        response = TestClient(app).get(
            "/api/v1/opportunities/opp-api/decision-dashboard"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == status_code
    assert response.json()["detail"] == str(error)


def test_invalid_blank_opportunity_id_maps_to_422(client_and_provider) -> None:
    client, provider = client_and_provider

    response = client.get("/api/v1/opportunities/%20/decision-dashboard")

    assert response.status_code == 422
    assert provider.calls == []


def test_identity_mismatch_maps_to_conflict() -> None:
    provider = FakeDashboardProvider(source(opportunity_id="other-opportunity"))
    app.dependency_overrides[get_opportunity_decision_dashboard_provider] = (
        lambda: provider
    )
    try:
        response = TestClient(app).get(
            "/api/v1/opportunities/opp-api/decision-dashboard"
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert "identity" in response.json()["detail"]


def test_default_provider_fails_explicitly_without_fabricated_facts() -> None:
    response = TestClient(app).get(
        "/api/v1/opportunities/opp-api/decision-dashboard"
    )

    assert response.status_code == 503
    assert "production composition" in response.json()["detail"]


def test_repeated_requests_are_deterministic(client_and_provider) -> None:
    client, provider = client_and_provider

    first = client.get("/api/v1/opportunities/opp-api/decision-dashboard")
    second = client.get("/api/v1/opportunities/opp-api/decision-dashboard")

    assert first.json() == second.json()
    assert provider.calls == ["opp-api", "opp-api"]


def test_review_warning_order_is_preserved() -> None:
    dashboard_source = source(DecisionOutcome.REVIEW)
    provider = FakeDashboardProvider(dashboard_source)
    app.dependency_overrides[get_opportunity_decision_dashboard_provider] = (
        lambda: provider
    )
    try:
        payload = TestClient(app).get(
            "/api/v1/opportunities/opp-api/decision-dashboard"
        ).json()
    finally:
        app.dependency_overrides.clear()

    expected = [
        card.item.reason_code.value
        for card in dashboard_source.read_model.warning_cards
    ]
    assert [item["reason_code"] for item in payload["warnings"]] == expected


def test_web_handler_contains_no_decision_or_explanation_logic() -> None:
    handler_source = inspect.getsource(get_opportunity_decision_dashboard)

    for forbidden in (
        "DecisionMatrix",
        "DecisionExplanationService",
        "DashboardReadModelAssembler",
        "DecisionEvaluationService",
    ):
        assert forbidden not in handler_source


def test_existing_health_and_version_endpoints_are_unchanged(client_and_provider) -> None:
    client, _ = client_and_provider

    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/version").json() == {
        "project": "HYB Opportunity AI",
        "api_version": "v1",
    }
