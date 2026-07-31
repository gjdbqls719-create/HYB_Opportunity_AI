from __future__ import annotations

import pytest

from app.application.watchlist import ListingLookupPort
from app.infrastructure.watchlist import (
    AmazonListingReader,
    EbayListingReader,
    MarketplaceListingReader,
    create_marketplace_listing_lookup_adapter,
)
from app.models import Product


def make_product(
    *,
    marketplace: str,
    item_id: str,
) -> Product:
    return Product(
        marketplace=marketplace,
        item_id=item_id,
        title=f"{marketplace} product",
        price=100.0,
        currency="USD",
        condition="New",
        url=f"https://example.com/{item_id}",
    )


@pytest.mark.parametrize(
    "reader",
    [
        EbayListingReader(),
        AmazonListingReader(),
    ],
)
def test_reader_satisfies_marketplace_listing_contract(
    reader: MarketplaceListingReader,
) -> None:
    assert isinstance(reader, MarketplaceListingReader)


def test_ebay_reader_delegates_to_exact_item_lookup(
    monkeypatch,
) -> None:
    product = make_product(
        marketplace="ebay",
        item_id="ebay-1",
    )
    calls: list[str] = []

    def fake_get_product_by_id(item_id: str) -> Product:
        calls.append(item_id)
        return product

    monkeypatch.setattr(
        "app.infrastructure.watchlist.marketplace_readers."
        "ebay.get_product_by_id",
        fake_get_product_by_id,
    )

    result = EbayListingReader().get_listing(
        item_id="ebay-1",
        url="https://example.com/ebay-1",
    )

    assert result is product
    assert calls == ["ebay-1"]


def test_amazon_reader_delegates_to_exact_item_lookup(
    monkeypatch,
) -> None:
    product = make_product(
        marketplace="amazon",
        item_id="amazon-1",
    )
    calls: list[str] = []

    def fake_get_product_by_id(item_id: str) -> Product:
        calls.append(item_id)
        return product

    monkeypatch.setattr(
        "app.infrastructure.watchlist.marketplace_readers."
        "amazon.get_product_by_id",
        fake_get_product_by_id,
    )

    result = AmazonListingReader().get_listing(
        item_id="amazon-1",
        url="https://example.com/amazon-1",
    )

    assert result is product
    assert calls == ["amazon-1"]


def test_registered_adapter_dispatches_to_ebay_and_amazon(
    monkeypatch,
) -> None:
    ebay_product = make_product(
        marketplace="ebay",
        item_id="ebay-1",
    )
    amazon_product = make_product(
        marketplace="amazon",
        item_id="amazon-1",
    )

    monkeypatch.setattr(
        "app.infrastructure.watchlist.marketplace_readers."
        "ebay.get_product_by_id",
        lambda item_id: ebay_product,
    )
    monkeypatch.setattr(
        "app.infrastructure.watchlist.marketplace_readers."
        "amazon.get_product_by_id",
        lambda item_id: amazon_product,
    )

    adapter = create_marketplace_listing_lookup_adapter()

    assert isinstance(adapter, ListingLookupPort)
    assert (
        adapter.get_listing(
            marketplace=" eBay ",
            item_id="ebay-1",
        )
        is ebay_product
    )
    assert (
        adapter.get_listing(
            marketplace=" AMAZON ",
            item_id="amazon-1",
        )
        is amazon_product
    )
