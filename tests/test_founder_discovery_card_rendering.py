from __future__ import annotations

from fastapi.testclient import TestClient

from app.web import app


def _card_renderer() -> str:
    html = TestClient(app).get("/").text
    start = html.index("function renderFinalizedGroups")
    end = html.index("async function searchOpportunities", start)
    return html[start:end]


def test_founder_card_renders_only_representative_preview_product_facts() -> None:
    renderer = _card_renderer()

    for value in (
        "preview.title",
        "preview.image_url",
        "preview.marketplace",
        "preview.price",
        "preview.currency",
        "preview.url",
        "group.observation_count",
    ):
        assert value in renderer

    assert "group.finalized_group_id" not in renderer
    assert "group.representative_observation_id" not in renderer
    assert "group.observation_ids" not in renderer
    assert "group.grouping_policy_version" not in renderer
    assert "price_range" not in renderer
    assert "score" not in renderer.lower()


def test_founder_card_has_image_and_url_fallbacks() -> None:
    renderer = _card_renderer()

    assert 'imagePlaceholder.textContent = "Image unavailable"' in renderer
    assert 'image.alt = preview.title' in renderer
    assert 'image.loading = "lazy"' in renderer
    assert "if (preview.image_url)" in renderer
    assert "if (preview.url)" in renderer
    assert "detailButton.disabled = true" in renderer
    assert 'detailButton.textContent = "View product"' in renderer
    assert "new URL" not in renderer


def test_founder_card_layout_is_responsive_and_product_first() -> None:
    html = TestClient(app).get("/").text
    renderer = _card_renderer()

    assert "grid-template-columns: repeat(auto-fit" in html
    assert "minmax(min(100%, 18rem), 1fr)" in html
    assert "aspect-ratio:" in html
    assert "object-fit:" in html
    assert renderer.index("card.append(title)") < renderer.index(
        "card.append(media)"
    )
    assert renderer.index("card.append(price)") < renderer.index(
        "card.append(marketplace)"
    )


def test_zero_result_message_contract_remains_present() -> None:
    renderer = _card_renderer()

    assert "if (groups.length === 0)" in renderer
    assert "No opportunities found" in renderer


def _screening_renderer() -> str:
    html = TestClient(app).get("/").text
    start = html.index("function renderScreeningRanking")
    end = html.index("function renderFinalizedGroups", start)
    return html[start:end]


def test_recorded_screening_cards_use_safe_review_priority_and_exact_rank() -> None:
    renderer = _screening_renderer()

    assert "item.rank_label" in renderer
    assert "recommendation.review_priority_label" in renderer
    assert "Screening score:" in renderer
    assert "Screening-time expected economics" in renderer
    assert "Why HYB screened it this way" in renderer
    assert "Review priority is not Candidate issuance" in renderer
    assert "permission to spend" in renderer
    assert 'textContent = recommendation.raw.grade' not in renderer


def test_screening_cards_show_reasons_provenance_and_safety_as_detail() -> None:
    renderer = _screening_renderer()

    for value in (
        "evidence.provenance_kind",
        "evidence.truth_scope",
        "reason.polarity",
        "reason.category",
        "reason.message",
        "Raw screening engine label:",
        "Effective screening engine label:",
        "Safety intervention:",
        "Safety reason:",
        "Ranking policy:",
    ):
        assert value in renderer
    assert '<details>' not in renderer
    assert 'document.createElement("details")' in renderer


def test_any_selected_rank_or_not_ranked_group_can_use_existing_candidate_api() -> None:
    html = TestClient(app).get("/").text
    start = html.index("async function issueSelectedCandidate")
    end = html.index("function renderScreeningRanking", start)
    selection = html[start:end]

    assert 'fetch("/api/v1/candidates"' in selection
    assert "finalized_group_id: item.finalized_group.finalized_group_id" in selection
    assert "discovery_reference: handoff.discovery_reference" in selection
    assert "market_observation_identity: handoff.market_observation_identity" in selection
    assert "screening.command_id" in selection
    assert "screening.discovery_execution_id" in selection
    assert "screening.ranked[0]" not in selection
    assert "/candidate-promotions" not in selection
    assert "/capital" not in selection.lower()


def test_legacy_and_page_reload_paths_are_read_only_and_never_infer_rank() -> None:
    html = TestClient(app).get("/").text
    start = html.index("async function restoreCompletedDiscovery")
    end = html.index("const pendingEnvelope", start)
    restore = html[start:end]

    assert "Screening ranking was not recorded for this legacy Discovery" in html
    assert "Finalized Groups are shown without rank" in html
    assert "SCREENING_NOT_RECORDED_LEGACY" not in _screening_renderer()
    assert "/screening-ranking" in restore
    assert 'method: "POST"' not in restore
    assert "/opportunities/search" not in restore
    assert "renderFinalizedGroups(groupRead.finalized_groups" in restore
    assert ".sort(" not in restore
