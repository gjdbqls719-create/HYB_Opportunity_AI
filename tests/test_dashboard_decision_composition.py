from dataclasses import replace
from datetime import datetime, timezone
import inspect
import sqlite3

import pytest
from fastapi.testclient import TestClient

from app.application.dashboard_api import (
    DashboardCompositionUnavailableError,
    DashboardIdentityConflictError,
    DashboardOpportunityNotFoundError,
    ProductionOpportunityDecisionDashboardProvider,
)
from app.application.opportunity_validation import (
    AddToValidationQueueCommand,
    OpportunityValidationService,
)
from app.infrastructure.opportunity_validation import (
    SQLiteValidationQueueRepository,
)
from app.web import app, get_opportunity_decision_dashboard_provider


NOW = datetime(2026, 8, 3, tzinfo=timezone.utc)


def populated_repository():
    repository = SQLiteValidationQueueRepository(":memory:")
    service = OpportunityValidationService(
        queue_repository=repository,
        lifecycle_repository=repository,
    )
    service.add(
        AddToValidationQueueCommand(
            opportunity_id="opp-production",
            discovery_reference="ebay:item-production",
            marketplace="ebay",
            title="Persisted Camera",
            admission_recommendation="WATCH",
            admission_score=68.0,
            admission_roi=22.5,
            currency="USD",
            admission_safety_status="READY",
            operator_id="founder",
            reason="selected",
            captured_at=NOW,
        )
    )
    return repository


def table_counts(repository):
    connection = repository._connection
    return {
        table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in (
            "opportunity_lifecycles",
            "opportunity_lifecycle_transitions",
            "validation_queue_admission_snapshots",
        )
    }


def test_persisted_subject_detects_missing_market_identity_without_fabrication() -> None:
    repository = populated_repository()
    provider = ProductionOpportunityDecisionDashboardProvider(repository)
    try:
        with pytest.raises(
            DashboardCompositionUnavailableError,
            match="finalized decision composition not found",
        ):
            provider.get("opp-production")
    finally:
        repository.close()


def test_persistence_gap_maps_to_http_503_and_query_is_read_only() -> None:
    repository = populated_repository()
    before = table_counts(repository)
    provider = ProductionOpportunityDecisionDashboardProvider(repository)
    app.dependency_overrides[get_opportunity_decision_dashboard_provider] = (
        lambda: provider
    )
    try:
        response = TestClient(app).get(
            "/api/v1/opportunities/opp-production/decision-dashboard"
        )
        after = table_counts(repository)
    finally:
        app.dependency_overrides.clear()
        repository.close()

    assert response.status_code == 503
    assert response.json()["detail"] == "finalized decision composition not found"
    assert after == before


def test_missing_persisted_opportunity_maps_to_http_404() -> None:
    repository = SQLiteValidationQueueRepository(":memory:")
    provider = ProductionOpportunityDecisionDashboardProvider(repository)
    app.dependency_overrides[get_opportunity_decision_dashboard_provider] = (
        lambda: provider
    )
    try:
        response = TestClient(app).get(
            "/api/v1/opportunities/missing/decision-dashboard"
        )
    finally:
        app.dependency_overrides.clear()
        repository.close()

    assert response.status_code == 404
    assert response.json()["detail"] == "dashboard opportunity not found"


def test_provider_rejects_persisted_opportunity_identity_mismatch() -> None:
    repository = populated_repository()
    item = repository.get_queue_item("opp-production")

    class MismatchedReader:
        def get_queue_item(self, opportunity_id):
            return replace(item, opportunity_id="different")

    with pytest.raises(DashboardIdentityConflictError, match="does not match"):
        ProductionOpportunityDecisionDashboardProvider(MismatchedReader()).get(
            "opp-production"
        )
    repository.close()


def test_sqlite_infrastructure_failure_is_explicitly_unavailable() -> None:
    class FailingReader:
        def get_queue_item(self, opportunity_id):
            raise sqlite3.OperationalError("database is locked")

    with pytest.raises(
        DashboardCompositionUnavailableError,
        match="validation persistence is unavailable",
    ):
        ProductionOpportunityDecisionDashboardProvider(FailingReader()).get(
            "opp-production"
        )


def test_gap_detection_is_deterministic_and_does_not_mutate_source() -> None:
    repository = populated_repository()
    item_before = repository.get_queue_item("opp-production")
    provider = ProductionOpportunityDecisionDashboardProvider(repository)
    messages = []
    try:
        for _ in range(2):
            with pytest.raises(DashboardCompositionUnavailableError) as error:
                provider.get("opp-production")
            messages.append(str(error.value))
        assert messages == ["finalized decision composition not found"] * 2
        assert repository.get_queue_item("opp-production") == item_before
    finally:
        repository.close()


def test_production_provider_contains_no_formula_threshold_or_dummy_facts() -> None:
    source = inspect.getsource(ProductionOpportunityDecisionDashboardProvider)

    for forbidden in (
        "Decimal(",
        "CompetitionAssessment(",
        "DemandAssessment(",
        "VerifiedEconomicsInput(",
        "ProductionSafetyAssessment(",
        "MarketObservationIdentity(",
    ):
        assert forbidden not in source
