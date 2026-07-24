import pytest

from services.shipping import resolve_shipping_cost


def test_uses_marketplace_shipping_when_override_is_omitted() -> None:
    result = resolve_shipping_cost(4.25)

    assert result.cost == 4.25
    assert result.source == "marketplace"
    assert result.is_free_shipping is False


def test_explicit_override_replaces_marketplace_shipping() -> None:
    result = resolve_shipping_cost(4.25, 2.5)

    assert result.cost == 2.5
    assert result.source == "override"
    assert result.is_free_shipping is False


def test_explicit_zero_override_means_free_shipping() -> None:
    result = resolve_shipping_cost(4.25, 0)

    assert result.cost == 0.0
    assert result.source == "override"
    assert result.is_free_shipping is True


def test_marketplace_zero_is_free_shipping() -> None:
    result = resolve_shipping_cost(0)

    assert result.is_free_shipping is True
    assert result.source == "marketplace"


@pytest.mark.parametrize("value", [-1, "-0.01"])
def test_negative_shipping_is_rejected(value: object) -> None:
    with pytest.raises(ValueError, match="0 이상"):
        resolve_shipping_cost(value)
