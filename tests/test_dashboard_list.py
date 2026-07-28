from app.models.product import Product
from presentation.dashboard_list import (
    build_opportunity_list_card,
)
from tests.test_dashboard_builder import (
    _make_opportunity_result,
)


def test_build_opportunity_list_card_preserves_order() -> None:
    first = _make_opportunity_result()
    second = _make_opportunity_result()

    second.product = Product(
        marketplace="amazon",
        item_id="second-1",
        title="Second Product",
        price=100.0,
        currency="USD",
        url="https://example.com/second-1",
    )
    second.final_opportunity_score = 60.0
    second.analysis["net_profit"] = 45.0
    second.analysis["roi"] = 18.0

    card = build_opportunity_list_card(
        [first, second]
    )

    assert card.total_count == 2
    assert len(card.items) == 2

    assert card.items[0].rank == 1
    assert card.items[0].title == (
        "Apple iPhone 17 128GB"
    )
    assert card.items[0].decision == "Buy"
    assert card.items[0].score == 72.0
    assert card.items[0].net_profit == 130.0
    assert card.items[0].roi == 25.0
    assert card.items[0].confidence_level == "HIGH"

    assert card.items[1].rank == 2
    assert card.items[1].marketplace == "amazon"
    assert card.items[1].title == "Second Product"
    assert card.items[1].score == 60.0


def test_build_opportunity_list_card_applies_limit() -> None:
    results = [
        _make_opportunity_result(),
        _make_opportunity_result(),
        _make_opportunity_result(),
    ]

    card = build_opportunity_list_card(
        results,
        limit=2,
    )

    assert card.total_count == 3
    assert len(card.items) == 2
    assert [item.rank for item in card.items] == [1, 2]


def test_build_opportunity_list_card_handles_empty_input() -> None:
    card = build_opportunity_list_card([])

    assert card.total_count == 0
    assert card.items == ()
    assert card.to_dict() == {
        "items": [],
        "total_count": 0,
    }


def test_build_opportunity_list_card_rejects_negative_limit() -> None:
    try:
        build_opportunity_list_card(
            [_make_opportunity_result()],
            limit=-1,
        )
    except ValueError as error:
        assert str(error) == (
            "limit must be zero or greater"
        )
    else:
        raise AssertionError(
            "negative limit must raise ValueError"
        )


def test_opportunity_list_card_converts_to_dict() -> None:
    data = build_opportunity_list_card(
        [_make_opportunity_result()]
    ).to_dict()

    assert data["total_count"] == 1
    assert data["items"][0]["rank"] == 1
    assert data["items"][0]["title"] == (
        "Apple iPhone 17 128GB"
    )
    assert data["items"][0]["currency"] == "USD"
