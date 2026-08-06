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
