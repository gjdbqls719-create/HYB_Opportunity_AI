import pytest

from market_data.snapshot import MarketSnapshot


def test_market_snapshot_calculations() -> None:
    snapshot = MarketSnapshot(
        product_name="Wireless Gaming Mouse",
        marketplace="eBay",
        currency="usd",
        current_price=18.0,
        average_price=30.0,
        lowest_price=15.0,
        highest_price=45.0,
        estimated_monthly_sales=240,
        competitor_count=12,
        rating=4.6,
        review_count=1250,
        price_change_rate=-8.5,
    )

    assert snapshot.currency == "USD"
    assert snapshot.price_position_rate == 10.0
    assert snapshot.discount_from_average_rate == 40.0

    data = snapshot.to_dict()

    assert data["marketplace"] == "eBay"
    assert data["estimated_monthly_sales"] == 240
    assert data["discount_from_average_rate"] == 40.0


def test_market_snapshot_rejects_negative_price() -> None:
    with pytest.raises(ValueError):
        MarketSnapshot(
            product_name="Invalid Product",
            marketplace="Amazon",
            currency="USD",
            current_price=-1.0,
            average_price=10.0,
            lowest_price=5.0,
            highest_price=15.0,
        )


def test_market_snapshot_rejects_invalid_price_order() -> None:
    with pytest.raises(ValueError):
        MarketSnapshot(
            product_name="Invalid Price Range",
            marketplace="Walmart",
            currency="USD",
            current_price=20.0,
            average_price=15.0,
            lowest_price=30.0,
            highest_price=10.0,
        )


def test_market_snapshot_rejects_invalid_rating() -> None:
    with pytest.raises(ValueError):
        MarketSnapshot(
            product_name="Invalid Rating",
            marketplace="Coupang",
            currency="KRW",
            current_price=20000,
            average_price=22000,
            lowest_price=18000,
            highest_price=25000,
            rating=5.5,
        )