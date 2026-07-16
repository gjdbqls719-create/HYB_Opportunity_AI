import pytest

from collectors.base import (
    parse_price,
    parse_rating,
    parse_review_count,
)


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("$1,299.99", 1299.99),
        ("£18.50", 18.50),
        ("₩19900", 19900.0),
        (25, 25.0),
        (12.345, 12.35),
    ],
)
def test_parse_price(raw_value, expected) -> None:
    assert parse_price(raw_value) == expected


def test_parse_price_rejects_negative_value() -> None:
    with pytest.raises(ValueError):
        parse_price("-5")


def test_parse_rating() -> None:
    assert parse_rating("4.7") == 4.7
    assert parse_rating(None) is None


def test_parse_rating_rejects_invalid_value() -> None:
    with pytest.raises(ValueError):
        parse_rating(5.5)


def test_parse_review_count() -> None:
    assert parse_review_count("1,234") == 1234
    assert parse_review_count(None) is None