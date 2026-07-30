from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.models import Product
from app.web import app
from engine.orchestrator import OpportunityResult


client = TestClient(app)


def test_index_renders_html_landing_page() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "HYB Opportunity AI" in response.text
    assert "<form" in response.text
    assert "<input" in response.text


def test_index_contains_api_first_search_controls() -> None:
    response = client.get("/")

    assert 'id="query"' in response.text
    assert 'id="search-button"' in response.text
    assert 'id="results"' in response.text
    assert 'id="error-message"' in response.text
    assert 'id="loading"' in response.text
    assert "async function searchOpportunities()" in response.text
    assert 'fetch("/api/v1/opportunities/search"' in response.text


def make_result(
    *,
    item_id: str,
    title: str,
    score: float,
) -> OpportunityResult:
    return OpportunityResult(
        product=Product(
            marketplace="ebay",
            item_id=item_id,
            title=title,
            price=100.0,
            shipping_cost=10.0,
            currency="USD",
            condition="New",
            url=f"https://example.com/{item_id}",
        ),
        analysis={
            "expected_selling_price": 160.0,
            "net_profit": 30.0,
            "roi": 27.27,
            "opportunity_score": 65.0,
        },
        matched_product_count=3,
        price_intelligence=SimpleNamespace(),
        adjusted_opportunity_score=67.0,
        final_opportunity_score=score,
    )


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_endpoint_reports_only_known_information() -> None:
    response = client.get("/version")

    assert response.status_code == 200
    assert response.json() == {
        "project": "HYB Opportunity AI",
        "api_version": "v1",
    }


def test_search_endpoint_uses_orchestrator_and_presentation(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_find_best_opportunities(**kwargs):
        captured.update(kwargs)
        return [
            make_result(
                item_id="first",
                title="First Product",
                score=80.0,
            ),
            make_result(
                item_id="second",
                title="Second Product",
                score=70.0,
            ),
        ]

    monkeypatch.setattr(
        "app.web.find_best_opportunities",
        fake_find_best_opportunities,
    )

    response = client.post(
        "/api/v1/opportunities/search",
        json={
            "query": " camera ",
            "limit": 20,
            "top": 1,
        },
    )

    assert response.status_code == 200
    assert captured == {
        "query": "camera",
        "limit": 20,
    }

    payload = response.json()

    assert payload["query"] == "camera"
    assert payload["opportunities"]["total_count"] == 2
    assert len(payload["opportunities"]["items"]) == 1
    assert payload["opportunities"]["items"][0]["item_id"] == "first"
    assert len(payload["dashboard_cards"]) == 1
    assert payload["dashboard_cards"][0]["product"]["item_id"] == "first"
    assert payload["dashboard_cards"][0]["metrics"][
        "final_opportunity_score"
    ] == 80.0


def test_search_endpoint_rejects_blank_query(
    monkeypatch,
) -> None:
    def fail_if_called(**kwargs):
        raise AssertionError(
            "blank query must not call Marketplace orchestration"
        )

    monkeypatch.setattr(
        "app.web.find_best_opportunities",
        fail_if_called,
    )

    response = client.post(
        "/api/v1/opportunities/search",
        json={"query": "   "},
    )

    assert response.status_code == 422


def test_search_endpoint_maps_value_error_to_422(
    monkeypatch,
) -> None:
    def raise_value_error(**kwargs):
        raise ValueError("invalid search input")

    monkeypatch.setattr(
        "app.web.find_best_opportunities",
        raise_value_error,
    )

    response = client.post(
        "/api/v1/opportunities/search",
        json={"query": "camera"},
    )

    assert response.status_code == 422
    assert response.json() == {
        "detail": "invalid search input",
    }


def test_search_endpoint_maps_runtime_error_to_502(
    monkeypatch,
) -> None:
    def raise_runtime_error(**kwargs):
        raise RuntimeError(
            "secret marketplace credential failure"
        )

    monkeypatch.setattr(
        "app.web.find_best_opportunities",
        raise_runtime_error,
    )

    response = client.post(
        "/api/v1/opportunities/search",
        json={"query": "camera"},
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "opportunity search failed",
    }

    assert "credential" not in response.text
