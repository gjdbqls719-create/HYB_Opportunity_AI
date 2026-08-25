from pathlib import Path

from fastapi.testclient import TestClient

from app.web import app


CLIENT = TestClient(app)
TEMPLATE = Path(__file__).parents[1] / "templates" / "decision_dashboard.html"


def test_browser_routes_return_200_and_propagate_opportunity_id_safely() -> None:
    entry = CLIENT.get("/dashboard/decision")
    page = CLIENT.get("/dashboard/opportunities/opp-ui/decision")
    unsafe = CLIENT.get("/dashboard/opportunities/%3Cimg%20src=x%20onerror=alert(1)%3E/decision")

    assert entry.status_code == 200
    assert page.status_code == 200
    assert 'value="opp-ui"' in page.text
    assert "<img src=x onerror=alert(1)>" not in unsafe.text
    assert "&lt;img src=x onerror=alert(1)&gt;" in unsafe.text


def test_page_contains_required_dashboard_sections_and_metadata_fields() -> None:
    html = CLIENT.get("/dashboard/opportunities/opp-ui/decision").text
    for value in (
        "Summary", "Action", "Warnings", "Evidence", "Metadata",
        "Generated at", "Schema version", "Policy version", "Read model version",
    ):
        assert value in html
    assert "legacy screening outcomes" in html
    assert "not Capital Gate PASS, Founder Approval, or spending authority" in html


def test_finalization_form_has_only_approved_controls_and_accessible_labels() -> None:
    html = CLIENT.get("/dashboard/decision").text
    for value in (
        'for="opportunity-id"', 'for="external-signal-ids"',
        'for="requested-by"', '<legend>External Signal selection</legend>',
        'value="default"', 'value="none"', 'value="explicit"',
        'role="status"', 'aria-live="polite"',
    ):
        assert value in html
    for forbidden in (
        'name="confidence"', 'name="freshness"', 'name="availability"',
        'name="outcome"', 'name="economics"', 'name="safety"',
        'name="competition"', 'name="demand"',
    ):
        assert forbidden not in html.lower()


def test_ui_consumes_existing_get_and_post_contracts_without_auto_finalization() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")
    assert 'endpoint("decision-dashboard")' in source
    assert 'endpoint("decision-compositions")' in source
    assert 'method:"POST"' in source
    assert "if (document.body.dataset.initialOpportunityId) loadDashboard();" in source
    assert "await api(endpoint(\"decision-compositions\")" not in source.split(
        "if (document.body.dataset.initialOpportunityId)"
    )[1]


def test_all_outcomes_and_truthful_evidence_states_remain_visible() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")
    for outcome in ("invest", "review", "reject", "insufficient_evidence"):
        assert outcome in source
    for field in (
        "item.availability", "item.confidence", "item.freshness",
        "item.severity", "data.summary.outcome", "data.summary.confidence",
    ):
        assert field in source
    assert "Decision composition not finalized" in source
    assert "Legacy Screening Decision Result" in source


def test_error_states_and_api_ordering_are_preserved() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")
    assert "error.status===503" in source
    assert "Dashboard request failed" in source
    assert "Finalization failed" in source
    assert "data.warnings.forEach" in source
    assert "data.evidence.forEach" in source
    assert ".sort(" not in source


def test_client_rendering_is_safe_and_contains_no_business_or_database_logic() -> None:
    source = TEMPLATE.read_text(encoding="utf-8")
    assert ".textContent" in source
    assert "innerHTML" not in source
    for forbidden in (
        "DecisionMatrix", "DecisionInput", "DecisionOutcome", "sqlite",
        "SELECT ", "INSERT ", "UPDATE ", "DELETE ", "confidence /", "confidence *",
    ):
        assert forbidden not in source


def test_repeated_server_render_is_deterministic_and_unrelated_routes_work() -> None:
    first = CLIENT.get("/dashboard/opportunities/opp-ui/decision")
    second = CLIENT.get("/dashboard/opportunities/opp-ui/decision")
    assert first.content == second.content
    assert CLIENT.get("/").status_code == 200
    assert CLIENT.get("/health").json() == {"status": "ok"}
    assert CLIENT.get("/version").status_code == 200
