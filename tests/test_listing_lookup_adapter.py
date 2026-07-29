from __future__ import annotations

import pytest

from app.application.watchlist import ListingLookupPort
from app.infrastructure.watchlist import (
    MarketplaceListingLookupAdapter,
    MarketplaceListingReader,
    UnsupportedMarketplaceError,
)
from app.models import Product


class FakeReader:
    def __init__(self, result: Product | None) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def get_listing(
        self,
        *,
        item_id: str,
        url: str = "",
    ) -> Product | None:
        self.calls.append((item_id, url))
        return self.result


class InvalidReader:
    pass


class InvalidResultReader:
    def get_listing(self, *, item_id: str, url: str = "") -> object:
        return object()


def make_product(*, marketplace: str = "ebay") -> Product:
    return Product(
        marketplace=marketplace,
        item_id="item-001",
        title="Apple iPhone 17 128GB",
        price=450.0,
        currency="USD",
        condition="New",
        url="https://example.com/item-001",
    )


def test_adapter_satisfies_application_listing_lookup_port() -> None:
    adapter = MarketplaceListingLookupAdapter(
        readers={"ebay": FakeReader(make_product())},
    )

    assert isinstance(adapter, ListingLookupPort)


def test_fake_reader_satisfies_reader_contract() -> None:
    assert isinstance(FakeReader(None), MarketplaceListingReader)


def test_dispatches_to_normalized_marketplace_reader() -> None:
    product = make_product()
    reader = FakeReader(product)
    adapter = MarketplaceListingLookupAdapter(readers={" eBay ": reader})

    result = adapter.get_listing(
        marketplace=" EBAY ",
        item_id=" item-001 ",
        url=" https://example.com/item-001 ",
    )

    assert result is product
    assert reader.calls == [
        ("item-001", "https://example.com/item-001")
    ]


def test_returns_none_when_reader_cannot_find_listing() -> None:
    adapter = MarketplaceListingLookupAdapter(
        readers={"ebay": FakeReader(None)},
    )

    assert (
        adapter.get_listing(marketplace="ebay", item_id="missing")
        is None
    )


def test_supports_url_only_lookup() -> None:
    reader = FakeReader(make_product())
    adapter = MarketplaceListingLookupAdapter(readers={"ebay": reader})

    adapter.get_listing(
        marketplace="ebay",
        item_id="",
        url="https://example.com/item-001",
    )

    assert reader.calls == [("", "https://example.com/item-001")]


def test_rejects_lookup_without_item_id_or_url() -> None:
    adapter = MarketplaceListingLookupAdapter(
        readers={"ebay": FakeReader(None)},
    )

    with pytest.raises(ValueError, match="item_id 또는 url"):
        adapter.get_listing(marketplace="ebay", item_id="", url="")


def test_rejects_unsupported_marketplace() -> None:
    adapter = MarketplaceListingLookupAdapter(
        readers={"ebay": FakeReader(None)},
    )

    with pytest.raises(UnsupportedMarketplaceError, match="amazon"):
        adapter.get_listing(marketplace="amazon", item_id="item-001")


def test_propagates_reader_execution_error() -> None:
    class FailingReader:
        def get_listing(self, *, item_id: str, url: str = "") -> None:
            raise RuntimeError("network unavailable")

    adapter = MarketplaceListingLookupAdapter(
        readers={"ebay": FailingReader()},
    )

    with pytest.raises(RuntimeError, match="network unavailable"):
        adapter.get_listing(marketplace="ebay", item_id="item-001")


def test_rejects_invalid_reader_during_registration() -> None:
    with pytest.raises(TypeError, match=r"get_listing\(\)"):
        MarketplaceListingLookupAdapter(
            readers={"ebay": InvalidReader()},
        )


def test_rejects_duplicate_normalized_marketplace_registration() -> None:
    with pytest.raises(ValueError, match="중복"):
        MarketplaceListingLookupAdapter(
            readers={
                "ebay": FakeReader(None),
                " EBAY ": FakeReader(None),
            },
        )


def test_rejects_invalid_reader_result() -> None:
    adapter = MarketplaceListingLookupAdapter(
        readers={"ebay": InvalidResultReader()},
    )

    with pytest.raises(TypeError, match="Product 또는 None"):
        adapter.get_listing(marketplace="ebay", item_id="item-001")


@pytest.mark.parametrize("marketplace", ["", "   "])
def test_rejects_empty_marketplace(marketplace: str) -> None:
    adapter = MarketplaceListingLookupAdapter(readers={})

    with pytest.raises(ValueError, match="marketplace"):
        adapter.get_listing(marketplace=marketplace, item_id="item-001")


def test_rejects_non_mapping_reader_registry() -> None:
    with pytest.raises(TypeError, match="Mapping"):
        MarketplaceListingLookupAdapter(readers=[])  # type: ignore[arg-type]
