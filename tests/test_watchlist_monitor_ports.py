from __future__ import annotations

from app.application.watchlist import (
    ListingLookupPort,
)
from app.models import Product


class FakeListingLookup:
    def __init__(
        self,
        product: Product | None,
    ) -> None:
        self.product = product
        self.calls: list[tuple[str, str, str]] = []

    def get_listing(
        self,
        *,
        marketplace: str,
        item_id: str,
        url: str = "",
    ) -> Product | None:
        self.calls.append(
            (marketplace, item_id, url)
        )
        return self.product


class InvalidListingLookup:
    pass


def make_product() -> Product:
    return Product(
        marketplace="ebay",
        item_id="item-001",
        title="Apple iPhone 17 128GB",
        price=450.0,
        currency="USD",
        condition="New",
        url="https://example.com/item-001",
    )


def test_structural_implementation_satisfies_port(
) -> None:
    lookup = FakeListingLookup(
        make_product()
    )

    assert isinstance(
        lookup,
        ListingLookupPort,
    )


def test_object_without_lookup_method_does_not_satisfy_port(
) -> None:
    assert not isinstance(
        InvalidListingLookup(),
        ListingLookupPort,
    )


def test_lookup_contract_returns_product_and_tracks_identity(
) -> None:
    product = make_product()
    lookup = FakeListingLookup(product)

    result = lookup.get_listing(
        marketplace="ebay",
        item_id="item-001",
        url="https://example.com/item-001",
    )

    assert result is product
    assert lookup.calls == [
        (
            "ebay",
            "item-001",
            "https://example.com/item-001",
        )
    ]


def test_lookup_contract_allows_missing_listing(
) -> None:
    lookup = FakeListingLookup(None)

    result = lookup.get_listing(
        marketplace="ebay",
        item_id="missing-item",
    )

    assert result is None
